"""
PractiCare AI Shared Helpers & Utilities
Provides domain-neutral normalization, parsing, and calculation logic.
Adheres to DRY and SRP principles.
"""

import re
from datetime import date
from typing import Any, List, Optional, Dict


def parse_bool_arg(val: Any, default: bool = False) -> bool:
    """
    Safely parses boolean inputs from string, int, or bool representations.
    Avoids Python's bool("false") -> True pitfall.
    """
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        cleaned = val.strip().lower()
        if cleaned in ("true", "1", "yes", "y", "t"):
            return True
        if cleaned in ("false", "0", "no", "n", "f", ""):
            return False
        return default
    return bool(val)


def normalize_task_id_candidates(raw_id: str) -> List[str]:
    """
    Standardizes task ID resolution across candidate patterns.
    Supports formats like '15', 'tsk-15', 'task-15', '02', 'tsk-02'.
    Returns an ordered list of distinct candidate primary key IDs to check.
    """
    if not raw_id:
        return []

    clean = str(raw_id).strip().lower()
    candidates: List[str] = [clean]

    # If already prefixed
    stripped = re.sub(r"^(?:tsk|task)-?", "", clean)
    if stripped != clean and stripped:
        candidates.append(stripped)
        candidates.append(f"tsk-{stripped}")
        candidates.append(f"task-{stripped}")
        if stripped.isdigit():
            candidates.append(f"tsk-{int(stripped):02d}")
    else:
        candidates.append(f"tsk-{clean}")
        candidates.append(f"task-{clean}")
        if clean.isdigit():
            candidates.append(f"tsk-{int(clean):02d}")

    # Remove duplicates while preserving insertion order
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)

    return result


def is_staff_active(staff_member: Any) -> bool:
    """Returns True if the staff account is active."""
    return bool(getattr(staff_member, "is_active", True))


def is_staff_on_shift(staff_member: Any) -> bool:
    """Returns True if the staff member is currently on duty/shift."""
    return bool(getattr(staff_member, "on_shift", True))


def format_staff_status_labels(staff_member: Any) -> Dict[str, str]:
    """
    Returns independent shift status and account status labels.
    Never equates account activation with shift availability.
    """
    active = is_staff_active(staff_member)
    on_shift = is_staff_on_shift(staff_member)

    shift_label = "On Shift" if on_shift else "Off Duty"
    acct_label = "Active" if active else "Inactive"
    display_label = (
        f"{getattr(staff_member, 'name', 'Unknown')} "
        f"({getattr(staff_member, 'role', 'Staff')}, ID: {getattr(staff_member, 'id', '')}) "
        f"— {shift_label} [{acct_label}]"
    )

    return {
        "shift_label": shift_label,
        "account_label": acct_label,
        "display_label": display_label,
    }


def is_task_overdue(
    due_date_str: Optional[str],
    status: Optional[str],
    reference_date_str: Optional[str] = None,
) -> bool:
    """
    Calculates if a clinical task is overdue relative to reference date.
    Tasks marked 'completed' are never overdue.
    """
    if not due_date_str:
        return False
    ref = reference_date_str or date.today().isoformat()
    is_completed = (status or "").strip().lower() == "completed"
    return bool(due_date_str < ref and not is_completed)


def get_user_staff_ids(db: Any, tenant_id: str, user_id: str) -> set:
    """Resolves all Staff IDs corresponding to an authenticated User ID within a tenant."""
    if not user_id or not tenant_id or db is None:
        return set()
    import models
    staff_records = db.query(models.Staff.id).filter(
        models.Staff.tenant_id == tenant_id,
        (models.Staff.user_id == user_id) | (models.Staff.id == user_id)
    ).all()
    staff_ids = {s.id for s in staff_records}
    staff_ids.add(user_id)
    return staff_ids


def get_user_primary_staff(db: Any, tenant_id: str, user_id: str) -> Optional[Any]:
    """Returns the primary Staff record for a User ID within a tenant."""
    if not user_id or not tenant_id or db is None:
        return None
    import models
    return db.query(models.Staff).filter(
        models.Staff.tenant_id == tenant_id,
        (models.Staff.user_id == user_id) | (models.Staff.id == user_id)
    ).first()


def is_task_assigned_to_user(task: Any, user_id: str, db: Any) -> bool:
    """Returns True if the task is assigned to the authenticated user."""
    if not task or not getattr(task, "assigned_staff_id", None):
        return False
    staff_ids = get_user_staff_ids(db, getattr(task, "tenant_id", ""), user_id)
    return task.assigned_staff_id in staff_ids


def is_checklist_assigned_to_user(checklist: Any, user_id: str, db: Any) -> bool:
    """Returns True if the checklist is assigned to the authenticated user."""
    if not checklist or not getattr(checklist, "assigned_staff_id", None):
        return False
    staff_ids = get_user_staff_ids(db, getattr(checklist, "tenant_id", ""), user_id)
    return checklist.assigned_staff_id in staff_ids

