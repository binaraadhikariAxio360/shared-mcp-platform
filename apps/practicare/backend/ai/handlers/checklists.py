"""
PractiCare AI Checklists Domain Handlers
Handles hygiene and sterilization checklist status updates and governance-controlled deletions.
Enforces human-in-the-loop validation and transactional rollback on database errors.
"""

from typing import Dict, Any
from sqlalchemy.orm import Session

import models
from ai.context import SecurityContext
from ai.helpers import parse_bool_arg, is_checklist_assigned_to_user
from ai.policy import (
    can_user_view_checklist,
    can_user_update_checklist,
    can_user_delete_checklist,
)


def execute_update_checklist_status(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Updates completion status for sterilization/hygiene checklists."""
    tenant_id = context.tenant_id
    checklist_id = args.get("checklist_id")
    if not checklist_id:
        raise ValueError("checklist_id is required.")

    is_completed = parse_bool_arg(args.get("is_completed"), default=True)

    checklist = (
        db.query(models.Checklist)
        .filter(models.Checklist.id == checklist_id, models.Checklist.tenant_id == tenant_id)
        .first()
    )
    if not checklist:
        raise ValueError(f"Checklist with ID '{checklist_id}' not found in current clinic partition.")

    allowed, reason = can_user_update_checklist(
        context.user_role,
        context.user_id,
        checklist,
        {"is_completed": is_completed},
        db,
    )
    if not allowed:
        raise PermissionError(f"User '{context.user_id}' with role '{context.user_role}' is not authorized to update checklist '{checklist.id}': {reason}")

    try:
        checklist.is_completed = is_completed
        db.commit()
        db.refresh(checklist)
    except Exception:
        db.rollback()
        raise

    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "update_checklist_status",
        "action": "UPDATE_CHECKLIST",
        "checklist_id": checklist.id,
        "resource_id": checklist.id,
        "tenant_id": tenant_id,
        "title": checklist.title,
        "is_completed": checklist.is_completed,
        "category": checklist.category,
        "persisted": True,
        "message": f"Checklist '{checklist.title}' updated to {'Completed' if is_completed else 'Pending'}.",
    }


def execute_update_checklist(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Updates an existing checklist: assigns or reassigns staff, updates title/category/status.
    Requires at least one field to update, validates tenant scoping and staff activation,
    commits the transaction and reads back the updated record to verify persistence.
    """
    tenant_id = context.tenant_id
    checklist_id = args.get("checklist_id")
    if not checklist_id:
        raise ValueError("checklist_id is required.")

    # Check for at least one update field
    has_assigned = "assigned_staff_id" in args and args["assigned_staff_id"] is not None
    has_title = "title" in args and args["title"] is not None and str(args["title"]).strip() != ""
    has_category = "category" in args and args["category"] is not None and str(args["category"]).strip() != ""
    has_status = "is_completed" in args and args["is_completed"] is not None

    if not (has_assigned or has_title or has_category or has_status):
        raise ValueError("At least one field to update (assigned_staff_id, title, category, is_completed) is required.")

    checklist = (
        db.query(models.Checklist)
        .filter(models.Checklist.id == checklist_id, models.Checklist.tenant_id == tenant_id)
        .first()
    )
    if not checklist:
        raise ValueError(f"Checklist with ID '{checklist_id}' not found in current clinic partition.")

    update_data = {}
    if has_assigned:
        update_data["assigned_staff_id"] = args.get("assigned_staff_id")
    if has_title:
        update_data["title"] = args.get("title")
    if has_category:
        update_data["category"] = args.get("category")
    if has_status:
        update_data["is_completed"] = args.get("is_completed")

    allowed, reason = can_user_update_checklist(
        context.user_role,
        context.user_id,
        checklist,
        update_data,
        db,
    )
    if not allowed:
        raise PermissionError(reason)

    staff_name = None
    if has_assigned:
        new_staff_id = str(args["assigned_staff_id"]).strip()
        if new_staff_id == "" or new_staff_id.lower() in ("null", "none", "unassigned", "unassign"):
            checklist.assigned_staff_id = None
        else:
            staff = (
                db.query(models.Staff)
                .filter(models.Staff.id == new_staff_id, models.Staff.tenant_id == tenant_id)
                .first()
            )
            if not staff:
                raise ValueError(f"Assigned staff member '{new_staff_id}' not found in tenant '{tenant_id}'.")
            if not staff.is_active:
                raise ValueError(f"Cannot assign checklist to inactive staff member '{staff.name}'.")
            checklist.assigned_staff_id = staff.id
            staff_name = staff.name

    if has_title:
        checklist.title = str(args["title"]).strip()

    if has_category:
        checklist.category = str(args["category"]).strip()

    if has_status:
        checklist.is_completed = parse_bool_arg(args["is_completed"], default=True)

    try:
        db.commit()
        db.refresh(checklist)
    except Exception:
        db.rollback()
        raise

    # Verify persistence by reading back from PostgreSQL
    persisted = (
        db.query(models.Checklist)
        .filter(models.Checklist.id == checklist.id, models.Checklist.tenant_id == tenant_id)
        .first()
    )
    if not persisted:
        db.rollback()
        raise RuntimeError(f"Database persistence verification failed for checklist '{checklist_id}'.")

    if persisted.assigned_staff_id and not staff_name:
        stf = db.query(models.Staff).filter(models.Staff.id == persisted.assigned_staff_id, models.Staff.tenant_id == tenant_id).first()
        staff_name = stf.name if stf else "Unassigned"
    elif not persisted.assigned_staff_id:
        staff_name = "Unassigned"

    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "update_checklist",
        "action": "UPDATE_CHECKLIST",
        "checklist_id": persisted.id,
        "resource_id": persisted.id,
        "tenant_id": persisted.tenant_id,
        "assigned_staff_id": persisted.assigned_staff_id,
        "assigned_staff_name": staff_name,
        "title": persisted.title,
        "category": persisted.category,
        "is_completed": persisted.is_completed,
        "persisted": True,
        "message": f"Successfully updated checklist '{persisted.title}' (ID: {persisted.id}) in tenant '{tenant_id}'.",
    }


def execute_get_checklist_details(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Retrieves tenant-scoped details for a specific checklist."""
    tenant_id = context.tenant_id
    checklist_id = args.get("checklist_id")
    if not checklist_id:
        raise ValueError("checklist_id is required.")

    checklist = (
        db.query(models.Checklist)
        .filter(models.Checklist.id == checklist_id, models.Checklist.tenant_id == tenant_id)
        .first()
    )
    if not checklist:
        raise ValueError(f"Checklist with ID '{checklist_id}' not found in current clinic partition.")

    if not can_user_view_checklist(context.user_role, context.user_id, checklist, db):
        raise PermissionError(f"Access denied: checklist '{checklist_id}' cannot be retrieved by user '{context.user_id}'.")

    staff_name = "Unassigned"
    if checklist.assigned_staff_id:
        stf = db.query(models.Staff).filter(models.Staff.id == checklist.assigned_staff_id, models.Staff.tenant_id == tenant_id).first()
        if stf:
            staff_name = stf.name

    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "get_checklist_details",
        "checklist_id": checklist.id,
        "resource_id": checklist.id,
        "tenant_id": checklist.tenant_id,
        "title": checklist.title,
        "category": checklist.category,
        "frequency": checklist.frequency,
        "is_completed": checklist.is_completed,
        "assigned_staff_id": checklist.assigned_staff_id,
        "assigned_staff_name": staff_name,
        "created_at": checklist.created_at.isoformat() if checklist.created_at else None,
    }


def execute_delete_clinical_checklist(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Deletes a checklist record from the database adhering to role hierarchy policy."""
    tenant_id = context.tenant_id
    checklist_id = args.get("checklist_id")
    if not checklist_id:
        raise ValueError("checklist_id is required.")

    checklist = (
        db.query(models.Checklist)
        .filter(models.Checklist.id == checklist_id, models.Checklist.tenant_id == tenant_id)
        .first()
    )
    if not checklist:
        raise ValueError(f"Checklist with ID '{checklist_id}' not found in current clinic partition.")

    allowed, reason = can_user_delete_checklist(context.user_role, context.user_id, checklist, db)
    if not allowed:
        raise PermissionError(reason)

    title = checklist.title
    try:
        db.delete(checklist)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "status": "SUCCESS",
        "action": "DELETE_CHECKLIST",
        "checklist_id": checklist_id,
        "title": title,
        "message": f"Clinical checklist '{title}' ({checklist_id}) permanently deleted under verified CLINIC_OWNER authorization.",
    }
