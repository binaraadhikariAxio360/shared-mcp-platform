"""
PractiCare Centralized Authorization & RBAC Policy
Defines authoritative business rules and role hierarchy for PractiCare:
  OWNER > MANAGER > DOCTOR > NURSE

Enforces:
  1. Role hierarchy and permissions across REST API and Tool Gateway.
  2. Multi-tenant isolation (strict tenant boundary on every query).
  3. Minimum privilege assignment rules (assigned staff can complete work; assignment never grants deletion).
  4. Role-specific restrictions (Doctors cannot edit Owner/Manager tasks, Nurses cannot edit/delete, etc.).
"""

from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
import models
from ai.context import ROLE_PERMISSIONS, normalize_role
from ai.helpers import (
    get_user_staff_ids,
    is_task_assigned_to_user,
    is_checklist_assigned_to_user,
)


ROLE_RANK: Dict[str, int] = {
    # OWNER (Rank 4)
    "CLINIC_OWNER": 4,
    "OWNER": 4,
    # MANAGER (Rank 3)
    "INVENTORY_MANAGER": 3,
    "MANAGER": 3,
    "CLINIC_MANAGER": 3,
    # DOCTOR (Rank 2)
    "ATTENDING_PHYSICIAN": 2,
    "DOCTOR": 2,
    # NURSE (Rank 1)
    "NURSE_STAFF": 1,
    "NURSE": 1,
    # CLINICAL_AUDITOR is deliberately unranked: read-only until an explicit auditor policy is approved.
}

AUDITOR_ROLE = "CLINICAL_AUDITOR"


def get_role_rank(role: Optional[str]) -> int:
    """Returns numeric role rank (4=Owner, 3=Manager, 2=Doctor, 1=Nurse, 0=Unknown)."""
    return ROLE_RANK.get(normalize_role(role), 0)


def is_owner(role: Optional[str]) -> bool:
    return get_role_rank(role) == 4


def is_manager(role: Optional[str]) -> bool:
    return get_role_rank(role) == 3


def is_doctor(role: Optional[str]) -> bool:
    return get_role_rank(role) == 2


def is_nurse(role: Optional[str]) -> bool:
    return get_role_rank(role) == 1


def is_auditor(role: Optional[str]) -> bool:
    return normalize_role(role) == AUDITOR_ROLE


def is_manager_or_above(role: Optional[str]) -> bool:
    return get_role_rank(role) >= 3


def is_doctor_or_above(role: Optional[str]) -> bool:
    return get_role_rank(role) >= 2


def _is_owner_or_manager_staff(staff: Any, db: Session) -> bool:
    """A linked user account's verified role takes precedence over the free-text staff role label."""
    if staff.user_id and db is not None:
        user = db.query(models.User).filter(models.User.id == staff.user_id).first()
        if user:
            return get_role_rank(user.role) >= 3
    return bool(staff.role and staff.role.lower() in ("admin", "owner", "manager", "inventory manager"))


def _is_owner_or_manager_scope(record: Any, db: Session) -> bool:
    """
    A task/checklist is in Owner/Manager scope when it is the work of an Owner/Manager:
      - assigned to Owner/Manager staff, or
      - unassigned and created by an Owner/Manager.
    Work an Owner/Manager delegates to a Doctor or Nurse is Doctor/Nurse scope, so the assignee can
    see and complete it and Doctors can supervise it.
    """
    if not record:
        return False
    assigned_staff_id = getattr(record, "assigned_staff_id", None)
    if assigned_staff_id and db is not None:
        staff = db.query(models.Staff).filter(
            models.Staff.id == assigned_staff_id,
            models.Staff.tenant_id == getattr(record, "tenant_id", None),
        ).first()
        if staff:
            return _is_owner_or_manager_staff(staff, db)
    return is_created_by_owner_or_manager(record)


def is_created_by_owner_or_manager(record: Any) -> bool:
    """Creator lineage: the record was created by an Owner or Manager (regardless of current assignee)."""
    return get_role_rank(getattr(record, "created_by_role", None)) >= 3


def is_created_by_user(record: Any, user_id: Optional[str]) -> bool:
    """Creator lineage: the record was created by this user. Legacy records without lineage match nobody."""
    creator = getattr(record, "created_by_user_id", None)
    return bool(creator and user_id and creator == user_id)


def is_owner_or_manager_task(task: Any, db: Session) -> bool:
    """Returns True if the task is in Owner/Manager scope (see _is_owner_or_manager_scope)."""
    return _is_owner_or_manager_scope(task, db)


def is_owner_or_manager_checklist(chk: Any, db: Session) -> bool:
    """Returns True if the checklist is in Owner/Manager scope (see _is_owner_or_manager_scope)."""
    return _is_owner_or_manager_scope(chk, db)


def is_staff_nurse(staff: Any, db: Session) -> bool:
    """
    Returns True if staff member is in a Nurse role.
    A linked user account's verified role takes precedence over the free-text staff role label.
    """
    if not staff:
        return False
    if staff.user_id and db is not None:
        user = db.query(models.User).filter(models.User.id == staff.user_id).first()
        if user:
            return is_nurse(user.role)
    return bool(staff.role and "nurse" in staff.role.lower())


def can_doctor_assign_to(user_id: str, staff_id: Optional[str], tenant_id: str, db: Session) -> Tuple[bool, str]:
    """Doctors may assign work only to Nurses or to themselves. Empty assignee (unassign) is allowed."""
    if not staff_id or db is None:
        return True, ""
    target = db.query(models.Staff).filter(
        models.Staff.id == staff_id,
        models.Staff.tenant_id == tenant_id,
    ).first()
    if not target:
        return True, ""  # existence is validated by the caller (404)
    if target.user_id and target.user_id == user_id:
        return True, ""
    if is_staff_nurse(target, db):
        return True, ""
    return False, "Doctors can only assign tasks to Nurses or themselves."


def filter_visible_tasks(user_role: str, user_id: str, tasks: List[Any], db: Session) -> List[Any]:
    """Single visibility filter for every task read path (REST, AI tools, analytics, conflicts, internal tools)."""
    return [t for t in tasks if can_user_view_task(user_role, user_id, t, db)]


# ==============================================================================
# AUTHORITATIVE PERMISSION CHECKS: TASKS
# ==============================================================================

def can_user_view_task(user_role: str, user_id: str, task: Any, db: Session) -> bool:
    """
    Evaluates whether user can view task details:
      - Owner / Manager: full tenant visibility
      - Doctor: Doctor/Nurse scope (cannot view restricted Owner/Manager tasks)
      - Auditor: read-only, same scope as Doctor (no Owner/Manager tasks)
      - Nurse: only tasks assigned to themselves
    """
    if not task:
        return False
    if is_owner(user_role) or is_manager(user_role):
        return True
    if is_doctor(user_role) or is_auditor(user_role):
        # Doctor cannot retrieve restricted Owner/Manager tasks
        return not is_owner_or_manager_task(task, db)
    if is_nurse(user_role):
        # Nurse can only view their own assigned tasks
        return is_task_assigned_to_user(task, user_id, db)
    return False


def can_user_create_task(
    user_role: str,
    assigned_staff_id: Optional[str],
    db: Session,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Evaluates whether user can create a task:
      - Owner / Manager: can create and assign to company staff
      - Doctor: can create within Doctor/Nurse scope and assign to Nurses
      - Nurse: cannot create tasks
    """
    if is_nurse(user_role):
        return False, "Nurses are not permitted to create tasks."

    if is_owner(user_role) or is_manager(user_role):
        return True, ""

    if is_doctor(user_role):
        return can_doctor_assign_to(user_id, assigned_staff_id, tenant_id, db)

    return False, f"Role '{user_role}' is not permitted to create tasks."


def can_user_update_task(
    user_role: str,
    user_id: str,
    task: Any,
    update_data: Dict[str, Any],
    db: Session,
) -> Tuple[bool, str]:
    """
    Evaluates whether user can update a task:
      - Owner: full update access
      - Manager: full update access
      - Doctor: can update Doctor/Nurse scope; cannot edit Owner/Manager tasks; can assign to Nurses
      - Nurse: can complete own assigned tasks (status only); cannot modify other fields or other users' tasks
    """
    if not task:
        return False, "Task not found"

    if is_owner(user_role) or is_manager(user_role):
        return True, ""

    if is_doctor(user_role):
        if is_owner_or_manager_task(task, db):
            return False, "Doctors cannot edit or modify Owner/Manager tasks."
        new_assignee = update_data.get("assigned_staff_id")
        if new_assignee and new_assignee != getattr(task, "assigned_staff_id", None):
            return can_doctor_assign_to(user_id, new_assignee, getattr(task, "tenant_id", ""), db)
        return True, ""

    if is_nurse(user_role):
        if not is_task_assigned_to_user(task, user_id, db):
            return False, "Nurses cannot modify tasks assigned to another user."
        disallowed = [k for k in update_data if k != "status"]
        if disallowed:
            return False, "Nurses may only complete their own assigned tasks. Modifying title, priority, room, or assignee is not permitted."
        return True, ""

    # Auditors and any unrecognised role are read-only
    return False, f"Role '{user_role}' is not permitted to modify tasks."


def can_user_delete_task(user_role: str, user_id: str, task: Any, db: Session) -> Tuple[bool, str]:
    """
    Evaluates whether user can delete a task:
      - Owner: full deletion access
      - Manager: can delete tasks, BUT cannot delete a task assigned to themselves
      - Doctor: can delete only tasks they created themselves that are unassigned or assigned to a Nurse.
                Never a task assigned to themselves, another Doctor's task, an Owner/Manager task, any task
                CREATED by an Owner/Manager (delegation grants view/complete only), or a legacy task with no
                recorded creator. Reassignment never changes creator lineage, so only the current assignee
                can change this decision.
      - Nurse: cannot delete tasks
      - General rule: a user cannot delete an assigned task merely because it is assigned to them
    """
    if not task:
        return False, "Task not found"

    if is_nurse(user_role):
        return False, "Nurses are not permitted to delete tasks."

    is_assigned = is_task_assigned_to_user(task, user_id, db)
    # Manager and Doctor cannot delete tasks assigned to themselves
    if is_assigned and not is_owner(user_role):
        return False, "A user cannot delete a task assigned to themselves."

    if is_owner(user_role):
        return True, ""

    if is_manager(user_role):
        return True, ""

    if is_doctor(user_role):
        if is_owner_or_manager_task(task, db):
            return False, "Doctors cannot delete Owner or Manager tasks."
        if is_created_by_owner_or_manager(task):
            return False, "Doctors cannot delete tasks created by an Owner or Manager."
        if not is_created_by_user(task, user_id):
            return False, "Doctors can only delete tasks they created."
        assigned_staff_id = getattr(task, "assigned_staff_id", None)
        if assigned_staff_id and db is not None:
            assignee = db.query(models.Staff).filter(
                models.Staff.id == assigned_staff_id,
                models.Staff.tenant_id == getattr(task, "tenant_id", None),
            ).first()
            if assignee and not is_staff_nurse(assignee, db):
                return False, "Doctors can only delete their own tasks that are unassigned or assigned to a Nurse."
        return True, ""

    return False, f"Role '{user_role}' is not permitted to delete tasks."


# ==============================================================================
# AUTHORITATIVE PERMISSION CHECKS: CHECKLISTS
# ==============================================================================

def can_user_view_checklist(user_role: str, user_id: str, chk: Any, db: Session) -> bool:
    """NURSE, DOCTOR, MANAGER, OWNER can view all checklists within company."""
    return True


def can_user_create_checklist(user_role: str) -> Tuple[bool, str]:
    """Nurses cannot create checklists. Owner, Manager, Doctor can."""
    if is_nurse(user_role):
        return False, "Nurses are not permitted to create checklist definitions."
    if is_owner(user_role) or is_manager(user_role) or is_doctor(user_role):
        return True, ""
    return False, f"Role '{user_role}' is not permitted to create checklists."


def can_user_update_checklist(
    user_role: str,
    user_id: str,
    chk: Any,
    update_data: Dict[str, Any],
    db: Session,
) -> Tuple[bool, str]:
    """
    Evaluates whether user can update a checklist:
      - Owner / Manager: full update and assignment permissions
      - Doctor: can update checklists within Doctor/Nurse scope (cannot edit Owner/Manager checklists)
      - Nurse: can fill, tick, untick, and complete ONLY checklists assigned to themselves.
               Cannot modify another user's checklist or change title/category/assignment.
    """
    if not chk:
        return False, "Checklist not found"

    if is_owner(user_role) or is_manager(user_role):
        return True, ""

    if is_doctor(user_role):
        if is_owner_or_manager_checklist(chk, db):
            return False, "Doctors cannot edit Owner or Manager checklists."
        new_assignee = update_data.get("assigned_staff_id")
        if new_assignee and new_assignee != getattr(chk, "assigned_staff_id", None):
            return can_doctor_assign_to(user_id, new_assignee, getattr(chk, "tenant_id", ""), db)
        return True, ""

    if is_nurse(user_role):
        if not is_checklist_assigned_to_user(chk, user_id, db):
            return False, "Nurses can only fill or complete checklists assigned to themselves."
        disallowed = [k for k in update_data if k not in ("is_completed", "status")]
        if disallowed:
            return False, "Nurses cannot edit checklist definitions, title, category, or reassign checklists."
        return True, ""

    # Auditors and any unrecognised role are read-only
    return False, f"Role '{user_role}' is not permitted to modify checklists."


def can_user_delete_checklist(user_role: str, user_id: str, chk: Any, db: Session) -> Tuple[bool, str]:
    """
    Evaluates whether user can delete a checklist:
      - Owner: can delete
      - Manager: can delete
      - Doctor: can delete within Doctor/Nurse scope (cannot delete Owner/Manager checklists)
      - Nurse: cannot delete checklists
    """
    if not chk:
        return False, "Checklist not found"

    if is_nurse(user_role):
        return False, "Nurses are not permitted to delete checklists."

    if is_owner(user_role) or is_manager(user_role):
        return True, ""

    if is_doctor(user_role):
        if is_owner_or_manager_checklist(chk, db):
            return False, "Doctors cannot delete Owner or Manager checklists."
        return True, ""

    return False, f"Role '{user_role}' is not permitted to delete checklists."


# ==============================================================================
# AUTHORITATIVE PERMISSION CHECKS: INVENTORY & ROOMS
# ==============================================================================

def can_user_manage_inventory(user_role: str) -> bool:
    """Owner and Manager can add, edit, update, and delete inventory."""
    return is_owner(user_role) or is_manager(user_role)


def can_user_create_room(user_role: str) -> bool:
    """Owner and Manager can add rooms."""
    return is_owner(user_role) or is_manager(user_role)


def can_user_update_room_status(user_role: str) -> bool:
    """Owner, Manager, and Doctor can change room status. Nurses have read-only access."""
    return is_owner(user_role) or is_manager(user_role) or is_doctor(user_role)


def can_user_update_room(user_role: str, update_fields: Dict[str, Any]) -> Tuple[bool, str]:
    """Owner/Manager may edit any room field; Doctors may change room status only."""
    if is_owner(user_role) or is_manager(user_role):
        return True, ""
    if is_doctor(user_role):
        other = [k for k in update_fields if k != "status"]
        if other:
            return False, "Doctors may only change room status."
        return True, ""
    return False, f"Role '{user_role}' is not permitted to update rooms."


def can_user_manage_staff_availability(user_role: str, user_id: str, staff: Any, db: Session) -> Tuple[bool, str]:
    """
    Work status and leave records:
      - Any clinical staff member (Owner/Manager/Doctor/Nurse) may manage their own record.
      - Managing another staff member requires the 'staff:leave_manage' permission (Owner, Doctor).
    """
    if get_role_rank(user_role) == 0:
        return False, f"Role '{user_role}' is not permitted to manage staff availability."
    is_self = bool(staff and staff.user_id and staff.user_id == user_id)
    if is_self:
        return True, ""
    if "staff:leave_manage" in ROLE_PERMISSIONS.get(normalize_role(user_role), set()):
        return True, ""
    return False, "You may only manage your own work status and leave."


# ==============================================================================
# PER-RECORD PERMISSION FLAGS (returned to the UI so it never re-implements RBAC)
# ==============================================================================

def task_permission_flags(user_role: str, user_id: str, task: Any, db: Session) -> Dict[str, bool]:
    return {
        "can_complete": can_user_update_task(user_role, user_id, task, {"status": "Completed"}, db)[0],
        "can_edit": can_user_update_task(user_role, user_id, task, {"title": getattr(task, "title", "")}, db)[0],
        "can_delete": can_user_delete_task(user_role, user_id, task, db)[0],
    }


def checklist_permission_flags(user_role: str, user_id: str, chk: Any, db: Session) -> Dict[str, bool]:
    return {
        "can_toggle": can_user_update_checklist(user_role, user_id, chk, {"is_completed": True}, db)[0],
        "can_edit": can_user_update_checklist(user_role, user_id, chk, {"title": getattr(chk, "title", "")}, db)[0],
        "can_delete": can_user_delete_checklist(user_role, user_id, chk, db)[0],
    }


LEAVE_STATUSES = ("PENDING", "APPROVED", "REJECTED")


def can_user_approve_leave(user_role: str, user_id: str, staff: Any) -> Tuple[bool, str]:
    """
    Leave approval requires 'staff:leave_manage' (Owner, Doctor). Nobody approves their own leave,
    except the Clinic Owner, who has no higher approver.
    """
    if "staff:leave_manage" not in ROLE_PERMISSIONS.get(normalize_role(user_role), set()):
        return False, "Only an Owner or Doctor can approve or reject leave."
    is_self = bool(staff and staff.user_id and staff.user_id == user_id)
    if is_self and not is_owner(user_role):
        return False, "You cannot approve or reject your own leave."
    return True, ""


def resolve_new_leave_status(user_role: str, user_id: str, staff: Any, requested: Optional[str]) -> str:
    """Self-service requests start PENDING; an authorized approver may record APPROVED/REJECTED directly."""
    approver, _ = can_user_approve_leave(user_role, user_id, staff)
    if not approver:
        return "PENDING"
    clean = str(requested or "APPROVED").strip().upper()
    return clean if clean in LEAVE_STATUSES else "APPROVED"


def can_user_delete_room(user_role: str) -> bool:
    """Owner only."""
    return is_owner(user_role)
