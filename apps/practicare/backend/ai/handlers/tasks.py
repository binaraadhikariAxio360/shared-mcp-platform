"""
PractiCare AI Tasks Domain Handlers
Handles clinical task querying, scheduling, priority updates, and staff assignment.
Enforces role-based visibility, active staff validation, and transactional rollback.
"""

from typing import Dict, Any
from datetime import date
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from ai.context import SecurityContext
from ai.helpers import (
    normalize_task_id_candidates,
    parse_bool_arg,
    is_task_overdue,
    is_staff_active,
    is_task_assigned_to_user,
    get_user_staff_ids,
)
from ai.policy import (
    can_user_view_task,
    can_user_create_task,
    can_user_update_task,
    can_user_delete_task,
    filter_visible_tasks,
)


def execute_list_tasks(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Retrieves authorized clinical tasks with flexible filtering.
    Supports filtering by status, priority, room_id, assigned_staff_id, and overdue status.
    Enforces role-based scoping (Auditor, Nurse, Physician, Owner).
    """
    tenant_id = context.tenant_id
    user_role = context.user_role
    user_id = context.user_id

    task_id_filter = str(args.get("task_id") or "").strip()
    status_filter = str(args.get("status") or "").strip().lower()
    priority_filter = str(args.get("priority") or "").strip().lower()
    assigned_staff_id = str(args.get("assigned_staff_id") or "").strip()
    room_id = str(args.get("room_id") or "").strip()
    overdue_only = parse_bool_arg(args.get("overdue_only"), default=False)
    limit = min(int(args.get("limit") or 20), 50)

    query = db.query(models.Task).filter(models.Task.tenant_id == tenant_id)

    if task_id_filter:
        clean_tid = task_id_filter.lower()
        candidates = normalize_task_id_candidates(clean_tid)
        query = query.filter(
            or_(
                models.Task.id.in_(candidates),
                models.Task.id.ilike(f"%{clean_tid}%"),
            )
        )
    if status_filter:
        query = query.filter(models.Task.status.ilike(status_filter))
    if priority_filter:
        query = query.filter(models.Task.priority.ilike(priority_filter))
    if assigned_staff_id:
        query = query.filter(models.Task.assigned_staff_id == assigned_staff_id)
    if room_id:
        query = query.filter(models.Task.room_id == room_id)

    today_str = date.today().isoformat()
    if overdue_only:
        query = query.filter(models.Task.due_date < today_str, models.Task.status.ilike("pending"))

    # Visibility is applied before the limit so hidden rows never crowd out tasks the caller may see
    all_tasks = filter_visible_tasks(user_role, user_id, query.order_by(models.Task.due_date).all(), db)[:limit]
    all_staff = {s.id: s for s in db.query(models.Staff).filter(models.Staff.tenant_id == tenant_id).all()}
    all_rooms = {r.id: r for r in db.query(models.Room).filter(models.Room.tenant_id == tenant_id).all()}

    # Role-based visibility scoping
    if user_role == "CLINICAL_AUDITOR":
        # Anonymized data only - zero PII
        anonymized_tasks = []
        for t in all_tasks:
            anonymized_tasks.append({
                "task_hash": f"tsk-aud-{t.id[:6]}",
                "priority": t.priority,
                "status": t.status,
                "is_overdue": is_task_overdue(t.due_date, t.status, today_str),
                "has_assigned_staff": bool(t.assigned_staff_id),
            })
        return {
            "tenant_id": tenant_id,
            "role_scope": "CLINICAL_AUDITOR (Aggregate & Anonymized)",
            "count": len(anonymized_tasks),
            "tasks": anonymized_tasks,
        }

    task_list = []
    my_tasks_only = parse_bool_arg(args.get("my_tasks_only"), default=False) or (assigned_staff_id in ("me", "self", "mine"))
    for t in all_tasks:
        if not can_user_view_task(user_role, user_id, t, db):
            continue
        is_assigned = is_task_assigned_to_user(t, user_id, db)
        if my_tasks_only and not is_assigned:
            continue

        staff_member = all_staff.get(t.assigned_staff_id)
        room_obj = all_rooms.get(t.room_id)
        overdue = is_task_overdue(t.due_date, t.status, today_str)

        task_list.append({
            "task_id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "due_date": t.due_date,
            "is_overdue": overdue,
            "room_id": t.room_id,
            "room_name": f"Room {room_obj.room_number} ({room_obj.name})" if room_obj else "Unassigned Room",
            "assigned_staff_id": t.assigned_staff_id,
            "assigned_to": staff_member.name if staff_member else "Unassigned",
            "description": t.description,
        })

    return {
        "tenant_id": tenant_id,
        "total_returned": len(task_list),
        "pending_count": sum(1 for t in task_list if t["status"].lower() == "pending"),
        "overdue_count": sum(1 for t in task_list if t["is_overdue"]),
        "tasks": task_list,
    }


def execute_create_clinical_task(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Creates a new clinical task for a specific room and assigned staff member."""
    tenant_id = context.tenant_id
    title = str(args.get("title", "")).strip()
    if not title:
        raise ValueError("Task title is required and cannot be empty.")

    room_id = args.get("room_id")
    if not room_id:
        raise ValueError("room_id is required.")

    # Validate room exists in THIS tenant
    room = db.query(models.Room).filter(
        models.Room.id == room_id,
        models.Room.tenant_id == tenant_id,
    ).first()
    if not room:
        raise ValueError(
            f"Room ID '{room_id}' not found in tenant '{tenant_id}'. "
            f"Display room numbers (e.g. '101') differ from database primary keys (e.g. 'room-101'). "
            f"Please call 'search_rooms' to resolve the actual database room_id."
        )

    # Validate staff member if supplied
    assigned_staff_id = args.get("assigned_staff_id")
    allowed, reason = can_user_create_task(context.user_role, assigned_staff_id, db, tenant_id, context.user_id)
    if not allowed:
        raise PermissionError(reason)

    if assigned_staff_id:
        staff_member = db.query(models.Staff).filter(
            models.Staff.id == assigned_staff_id,
            models.Staff.tenant_id == tenant_id,
        ).first()
        if not staff_member:
            raise ValueError(f"Staff ID '{assigned_staff_id}' not found in tenant '{tenant_id}'.")
        if not is_staff_active(staff_member):
            raise ValueError(
                f"Cannot assign task to inactive staff member '{staff_member.name}' (ID: {assigned_staff_id})."
            )

    priority = args.get("priority", "Medium")
    due_date = args.get("due_date") or date.today().isoformat()
    description = args.get("description", "Created autonomously by PractiCare AI")

    # Locate practice_id for this tenant
    practice = db.query(models.Practice).filter(models.Practice.tenant_id == tenant_id).first()
    practice_id = practice.id if practice else f"prac-{tenant_id}"

    new_task = models.Task(
        id=models.generate_id("tsk"),
        title=title,
        description=description,
        priority=priority,
        status="Pending",
        due_date=due_date,
        room_id=room_id,
        assigned_staff_id=assigned_staff_id,
        practice_id=practice_id,
        tenant_id=tenant_id,
        created_by_user_id=context.user_id,
        created_by_role=context.user_role,
    )
    try:
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
    except Exception:
        db.rollback()
        raise

    # Phase 2 & 4: Explicit post-write PostgreSQL persistence verification within tenant
    persisted_task = db.query(models.Task).filter(
        models.Task.id == new_task.id,
        models.Task.tenant_id == tenant_id,
    ).first()
    if not persisted_task:
        db.rollback()
        raise RuntimeError(
            f"Database persistence verification failed for task '{new_task.id}' in tenant partition '{tenant_id}'."
        )

    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "create_clinical_task",
        "resource_type": "clinical_task",
        "resource_id": persisted_task.id,
        "action": "CREATE_TASK",
        "task_id": persisted_task.id,
        "title": persisted_task.title,
        "priority": persisted_task.priority,
        "due_date": persisted_task.due_date,
        "room_id": persisted_task.room_id,
        "assigned_staff_id": persisted_task.assigned_staff_id,
        "tenant_id": tenant_id,
        "persisted": True,
        "message": f"Successfully created clinical task '{persisted_task.title}' in {context.company_name}.",
    }


def execute_update_task_status(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Updates an existing clinical task status, priority, or assigned staff.
    Validates task existence in context.tenant_id and verifies staff identity.
    """
    tenant_id = context.tenant_id
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("task_id is required.")

    task = db.query(models.Task).filter(
        models.Task.id == task_id,
        models.Task.tenant_id == tenant_id,
    ).first()
    if not task:
        for alt in normalize_task_id_candidates(task_id):
            task = db.query(models.Task).filter(
                models.Task.id == alt,
                models.Task.tenant_id == tenant_id,
            ).first()
            if task:
                break
    if not task:
        raise ValueError(f"Task ID '{task_id}' not found in tenant '{tenant_id}'.")

    is_assigned = is_task_assigned_to_user(task, context.user_id, db)
    update_data = {}
    if args.get("status"):
        update_data["status"] = args.get("status")
    if args.get("priority"):
        update_data["priority"] = args.get("priority")
    # Validated args always carry the key (default None); only an explicit value is an update
    if args.get("assigned_staff_id") is not None:
        update_data["assigned_staff_id"] = args.get("assigned_staff_id")
    if args.get("description"):
        update_data["description"] = args.get("description")
    if args.get("room_id"):
        update_data["room_id"] = args.get("room_id")

    allowed, reason = can_user_update_task(context.user_role, context.user_id, task, update_data, db)
    if not allowed:
        raise PermissionError(reason)

    # Update status
    new_status = args.get("status")
    if new_status:
        clean_status = str(new_status).strip()
        valid_statuses = {"pending": "Pending", "in progress": "In Progress", "completed": "Completed"}
        if clean_status.lower() not in valid_statuses:
            raise ValueError(f"Invalid status '{new_status}'. Permitted values: Pending, In Progress, Completed.")
        task.status = valid_statuses[clean_status.lower()]

    # Update priority
    new_priority = args.get("priority")
    if new_priority:
        clean_priority = str(new_priority).strip().capitalize()
        valid_priorities = {"Low", "Medium", "High", "Critical"}
        if clean_priority not in valid_priorities:
            raise ValueError(f"Invalid priority '{new_priority}'. Permitted: Low, Medium, High, Critical.")
        task.priority = clean_priority

    # Update description / instructions
    new_desc = args.get("description")
    if new_desc:
        task.description = str(new_desc).strip()

    # Reassign staff
    new_staff_id = args.get("assigned_staff_id")
    if new_staff_id is not None:
        if new_staff_id == "" or str(new_staff_id).lower() in ("none", "unassigned"):
            task.assigned_staff_id = None
        else:
            staff_member = db.query(models.Staff).filter(
                models.Staff.id == new_staff_id,
                models.Staff.tenant_id == tenant_id,
            ).first()
            if not staff_member:
                raise ValueError(
                    f"Staff ID '{new_staff_id}' not found in tenant '{tenant_id}'. "
                    f"Please call 'search_staff' to resolve the provider ID."
                )
            if not is_staff_active(staff_member):
                raise ValueError(
                    f"Cannot assign task to inactive staff member '{staff_member.name}' (ID: {new_staff_id})."
                )
            task.assigned_staff_id = staff_member.id

    try:
        db.commit()
        db.refresh(task)
    except Exception:
        db.rollback()
        raise

    # Phase 2 & 4: Explicit post-write PostgreSQL persistence verification
    persisted_update = db.query(models.Task).filter(
        models.Task.id == task.id,
        models.Task.tenant_id == tenant_id,
    ).first()
    if not persisted_update:
        db.rollback()
        raise RuntimeError(
            f"Database persistence verification failed for updated task '{task.id}' in tenant partition '{tenant_id}'."
        )

    staff_name = "Unassigned"
    if task.assigned_staff_id:
        assigned_staff = db.query(models.Staff).filter(
            models.Staff.id == task.assigned_staff_id,
            models.Staff.tenant_id == tenant_id,
        ).first()
        if assigned_staff:
            staff_name = assigned_staff.name

    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "update_task_status",
        "resource_type": "clinical_task",
        "resource_id": persisted_update.id,
        "action": "UPDATE_TASK",
        "task_id": persisted_update.id,
        "title": persisted_update.title,
        "updated_status": persisted_update.status,
        "priority": persisted_update.priority,
        "assigned_staff_id": persisted_update.assigned_staff_id,
        "assigned_to": staff_name,
        "tenant_id": tenant_id,
        "persisted": True,
        "message": f"Successfully updated task '{persisted_update.title}' ({persisted_update.id}) to status '{persisted_update.status}', assigned to {staff_name}.",
    }


def execute_get_task_details(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Retrieves tenant-scoped details for a specific clinical task."""
    tenant_id = context.tenant_id
    raw_task_id = str(args.get("task_id") or "").strip()
    if not raw_task_id:
        raise ValueError("task_id is required.")

    task = (
        db.query(models.Task)
        .filter(models.Task.id == raw_task_id, models.Task.tenant_id == tenant_id)
        .first()
    )
    if not task:
        for alt in normalize_task_id_candidates(raw_task_id):
            task = (
                db.query(models.Task)
                .filter(models.Task.id == alt, models.Task.tenant_id == tenant_id)
                .first()
            )
            if task:
                break

    if not task:
        raise ValueError(f"Clinical task '{raw_task_id}' not found in tenant '{tenant_id}'.")

    if not can_user_view_task(context.user_role, context.user_id, task, db):
        raise PermissionError(f"Access denied: task '{raw_task_id}' cannot be retrieved by role '{context.user_role}'.")

    if context.user_role == "CLINICAL_AUDITOR":
        return {
            "status": "SUCCESS",
            "execution_status": "SUCCESS",
            "tool_name": "get_task_details",
            "task_id": f"tsk-aud-{task.id[:6]}",
            "resource_id": task.id,
            "tenant_id": task.tenant_id,
            "priority": task.priority,
            "status_value": task.status,
            "has_assigned_staff": bool(task.assigned_staff_id),
            "due_date": task.due_date,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }

    staff_name = "Unassigned"
    if task.assigned_staff_id:
        stf = db.query(models.Staff).filter(models.Staff.id == task.assigned_staff_id, models.Staff.tenant_id == tenant_id).first()
        if stf:
            staff_name = stf.name

    room_name = None
    if task.room_id:
        rm = db.query(models.Room).filter(models.Room.id == task.room_id, models.Room.tenant_id == tenant_id).first()
        if rm:
            room_name = f"Room {rm.room_number} — {rm.name}"

    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "get_task_details",
        "task_id": task.id,
        "resource_id": task.id,
        "tenant_id": task.tenant_id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status_value": task.status,
        "due_date": task.due_date,
        "room_id": task.room_id,
        "room_name": room_name,
        "assigned_staff_id": task.assigned_staff_id,
        "assigned_staff_name": staff_name,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
