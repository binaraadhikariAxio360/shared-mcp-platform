"""
PractiCare Operational Conflict & Leave Intelligence Handlers
Correlates Tasks and Checklists with Staff Attendance, Work Status, Leave Calendars,
and Inactive Login Events.
Provides clean data for both REST endpoints and ToolGateway AI tool execution.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

import models
from ai.context import SecurityContext
from ai.policy import filter_visible_tasks, can_user_manage_staff_availability, resolve_new_leave_status


def calculate_operational_conflicts(
    db: Session,
    tenant_id: str,
    conflict_type_filter: Optional[str] = None,
    viewer_role: Optional[str] = None,
    viewer_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Scans real tenant database records to detect operational bottlenecks and availability conflicts:
    1. Tasks/Checklists assigned to staff on HOLIDAY.
    2. Tasks/Checklists assigned to staff on DND (Do Not Disturb).
    3. Tasks/Checklists assigned to staff on SICK_LEAVE.
    4. Tasks assigned to staff who have not logged in recently or never logged in.
    5. Overdue clinical tasks and their responsible personnel.
    6. Unassigned tasks in queue.
    When a viewer is supplied, task items are limited to tasks that viewer may see
    (checklists are visible company-wide to every role).
    """
    now = datetime.utcnow()
    today_str = date.today().isoformat()
    tomorrow_str = (date.today() + timedelta(days=1)).isoformat()

    # Pre-fetch tenant staff lookup
    all_staff = db.query(models.Staff).filter(models.Staff.tenant_id == tenant_id).all()
    staff_map = {s.id: s for s in all_staff}

    # Pre-fetch active approved leaves covering today or tomorrow
    active_leaves = db.query(models.StaffLeave).filter(
        models.StaffLeave.tenant_id == tenant_id,
        models.StaffLeave.status == "APPROVED",
        models.StaffLeave.start_date <= now + timedelta(days=2),
        models.StaffLeave.end_date >= now - timedelta(days=1),
    ).all()
    
    staff_leave_map: Dict[str, List[models.StaffLeave]] = {}
    for l in active_leaves:
        staff_leave_map.setdefault(l.staff_id, []).append(l)

    # Fetch pending / in-progress tasks
    tasks = db.query(models.Task).filter(
        models.Task.tenant_id == tenant_id,
        models.Task.status.ilike("%Pending%") | models.Task.status.ilike("%In Progress%"),
    ).all()
    if viewer_role is not None:
        tasks = filter_visible_tasks(viewer_role, viewer_user_id, tasks, db)

    # Fetch incomplete checklists
    checklists = db.query(models.Checklist).filter(
        models.Checklist.tenant_id == tenant_id,
        models.Checklist.is_completed == False,
    ).all()

    conflict_items = []
    holiday_count = 0
    dnd_count = 0
    inactive_login_count = 0
    overdue_count = 0
    unassigned_count = 0

    # 1. Analyze Tasks
    for t in tasks:
        staff = staff_map.get(t.assigned_staff_id) if t.assigned_staff_id else None
        staff_name = staff.name if staff else "Unassigned"
        work_status = getattr(staff, "work_status", "ACTIVE") if staff else "UNKNOWN"
        last_login = getattr(staff, "last_login_at", None) if staff else None

        # Check leaves
        leaves_for_staff = staff_leave_map.get(staff.id, []) if staff else []
        is_on_holiday = (work_status == "HOLIDAY") or any(l.leave_type == "HOLIDAY" for l in leaves_for_staff)
        is_on_dnd = (work_status == "DND") or any(l.leave_type == "DND" for l in leaves_for_staff)
        is_on_sick = (work_status == "SICK_LEAVE") or any(l.leave_type == "SICK_LEAVE" for l in leaves_for_staff)

        # Overdue check
        is_overdue = t.due_date and t.due_date < today_str
        if is_overdue:
            overdue_count += 1

        # Unassigned check
        if not t.assigned_staff_id:
            unassigned_count += 1
            conflict_items.append({
                "conflict_type": "UNASSIGNED_TASK",
                "item_type": "TASK",
                "item_id": t.id,
                "title": t.title,
                "priority": t.priority,
                "due_date": t.due_date,
                "assigned_staff_id": None,
                "assigned_staff_name": "Unassigned",
                "staff_work_status": None,
                "staff_last_login_at": None,
                "message": f"Clinical task '{t.title}' is unassigned and currently pending.",
                "recommendation": "Assign to an available on-shift staff member immediately.",
            })

        # Conflict: Staff is on Holiday
        if staff and is_on_holiday:
            holiday_count += 1
            conflict_items.append({
                "conflict_type": "HOLIDAY_ASSIGNMENT",
                "item_type": "TASK",
                "item_id": t.id,
                "title": t.title,
                "priority": t.priority,
                "due_date": t.due_date,
                "assigned_staff_id": staff.id,
                "assigned_staff_name": staff.name,
                "staff_work_status": "HOLIDAY",
                "staff_last_login_at": last_login.isoformat() if last_login else None,
                "message": f"Task '{t.title}' is assigned to {staff.name}, who is currently marked on Holiday leave.",
                "recommendation": f"Alert clinic manager: Reassign task from {staff.name} to active floor staff.",
            })

        # Conflict: Staff is on DND
        if staff and is_on_dnd:
            dnd_count += 1
            conflict_items.append({
                "conflict_type": "DND_ASSIGNMENT",
                "item_type": "TASK",
                "item_id": t.id,
                "title": t.title,
                "priority": t.priority,
                "due_date": t.due_date,
                "assigned_staff_id": staff.id,
                "assigned_staff_name": staff.name,
                "staff_work_status": "DND",
                "staff_last_login_at": last_login.isoformat() if last_login else None,
                "message": f"Task '{t.title}' is assigned to {staff.name}, who is currently set to Do Not Disturb (DND).",
                "recommendation": f"Notify manager or defer non-urgent task until staff exits DND.",
            })

        # Conflict: Staff is on Sick Leave
        if staff and is_on_sick:
            conflict_items.append({
                "conflict_type": "SICK_LEAVE_ASSIGNMENT",
                "item_type": "TASK",
                "item_id": t.id,
                "title": t.title,
                "priority": t.priority,
                "due_date": t.due_date,
                "assigned_staff_id": staff.id,
                "assigned_staff_name": staff.name,
                "staff_work_status": "SICK_LEAVE",
                "staff_last_login_at": last_login.isoformat() if last_login else None,
                "message": f"Task '{t.title}' is assigned to {staff.name}, who is recorded on Sick Leave.",
                "recommendation": f"Reassign task to covering staff.",
            })

        # Conflict: Inactive Login
        if staff and staff.is_active and not is_on_holiday and not is_on_dnd and not is_on_sick:
            # Check if last login is null or older than 48 hours
            is_login_inactive = False
            inactivity_desc = ""
            if not last_login:
                is_login_inactive = True
                inactivity_desc = "has no recorded login event"
            elif (now - last_login).total_seconds() > 48 * 3600:
                is_login_inactive = True
                hours = int((now - last_login).total_seconds() // 3600)
                inactivity_desc = f"has not logged in for {hours} hours"

            if is_login_inactive:
                inactive_login_count += 1
                conflict_items.append({
                    "conflict_type": "INACTIVE_LOGIN_STAFF",
                    "item_type": "TASK",
                    "item_id": t.id,
                    "title": t.title,
                    "priority": t.priority,
                    "due_date": t.due_date,
                    "assigned_staff_id": staff.id,
                    "assigned_staff_name": staff.name,
                    "staff_work_status": work_status,
                    "staff_last_login_at": last_login.isoformat() if last_login else None,
                    "message": f"Task '{t.title}' is assigned to {staff.name}, but staff {inactivity_desc}.",
                    "recommendation": "Remind manager to verify staff attendance or reassign duty.",
                })

    # 2. Analyze Checklists
    for c in checklists:
        staff = staff_map.get(c.assigned_staff_id) if c.assigned_staff_id else None
        if not staff:
            continue
        work_status = getattr(staff, "work_status", "ACTIVE")
        leaves_for_staff = staff_leave_map.get(staff.id, [])
        is_on_holiday = (work_status == "HOLIDAY") or any(l.leave_type == "HOLIDAY" for l in leaves_for_staff)
        is_on_dnd = (work_status == "DND") or any(l.leave_type == "DND" for l in leaves_for_staff)

        if is_on_holiday:
            holiday_count += 1
            conflict_items.append({
                "conflict_type": "HOLIDAY_ASSIGNMENT",
                "item_type": "CHECKLIST",
                "item_id": c.id,
                "title": c.title,
                "priority": "Medium",
                "due_date": today_str,
                "assigned_staff_id": staff.id,
                "assigned_staff_name": staff.name,
                "staff_work_status": "HOLIDAY",
                "staff_last_login_at": staff.last_login_at.isoformat() if getattr(staff, "last_login_at", None) else None,
                "message": f"Sterilization/Hygiene checklist '{c.title}' is assigned to {staff.name}, who is marked on Holiday.",
                "recommendation": f"Alert manager: Reassign checklist '{c.title}' to on-shift nurse.",
            })
        elif is_on_dnd:
            dnd_count += 1
            conflict_items.append({
                "conflict_type": "DND_ASSIGNMENT",
                "item_type": "CHECKLIST",
                "item_id": c.id,
                "title": c.title,
                "priority": "Medium",
                "due_date": today_str,
                "assigned_staff_id": staff.id,
                "assigned_staff_name": staff.name,
                "staff_work_status": "DND",
                "staff_last_login_at": staff.last_login_at.isoformat() if getattr(staff, "last_login_at", None) else None,
                "message": f"Checklist '{c.title}' is assigned to {staff.name}, currently on Do Not Disturb (DND).",
                "recommendation": f"Notify manager to delegate checklist execution.",
            })

    # Filter if requested
    if conflict_type_filter:
        clean_filt = conflict_type_filter.upper().strip()
        conflict_items = [i for i in conflict_items if clean_filt in i["conflict_type"]]

    return {
        "tenant_id": tenant_id,
        "total_conflicts": len(conflict_items),
        "holiday_conflicts": holiday_count,
        "dnd_conflicts": dnd_count,
        "inactive_login_conflicts": inactive_login_count,
        "overdue_count": overdue_count,
        "unassigned_count": unassigned_count,
        "items": conflict_items,
    }


def execute_get_operational_task_conflicts(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """ToolGateway handler for retrieving operational bottlenecks, leave conflicts, and login inactivity."""
    filt = args.get("conflict_type")
    report = calculate_operational_conflicts(db, context.tenant_id, filt, context.user_role, context.user_id)
    return report


def execute_get_staff_availability(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    ToolGateway handler for inspecting staff members' availability:
    - Active account vs on-shift status
    - Work status: ACTIVE, HOLIDAY, SICK_LEAVE, DND
    - Active approved leaves and dates
    - Last authenticated login timestamp
    """
    tenant_id = context.tenant_id
    query_str = (args.get("query") or "").strip().lower()
    status_filter = (args.get("work_status") or "").strip().upper()

    q = db.query(models.Staff).filter(models.Staff.tenant_id == tenant_id)
    if status_filter:
        q = q.filter(models.Staff.work_status == status_filter)

    staff_list = q.all()
    if query_str:
        staff_list = [
            s for s in staff_list
            if query_str in (s.name or "").lower() or query_str in (s.id or "").lower() or query_str in (s.role or "").lower()
        ]

    now = datetime.utcnow()
    results = []
    for s in staff_list:
        # Check active leaves
        leaves = db.query(models.StaffLeave).filter(
            models.StaffLeave.staff_id == s.id,
            models.StaffLeave.tenant_id == tenant_id,
            models.StaffLeave.status == "APPROVED",
        ).all()

        current_leave = None
        for l in leaves:
            if l.start_date <= now <= l.end_date:
                current_leave = {
                    "leave_type": l.leave_type,
                    "start_date": l.start_date.isoformat(),
                    "end_date": l.end_date.isoformat(),
                    "notes": l.notes,
                }
                break

        w_status = getattr(s, "work_status", "ACTIVE")
        last_login = getattr(s, "last_login_at", None)

        results.append({
            "staff_id": s.id,
            "name": s.name,
            "role": s.role,
            "department": getattr(s, "department", s.role),
            "is_active": s.is_active,
            "on_shift": s.on_shift,
            "work_status": w_status,
            "last_login_at": last_login.isoformat() if last_login else None,
            "current_leave": current_leave,
            "is_available_for_tasks": (s.is_active and s.on_shift and w_status == "ACTIVE" and not current_leave),
        })

    return {
        "tenant_id": tenant_id,
        "total_count": len(results),
        "staff": results,
    }


def execute_set_staff_work_status(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """ToolGateway handler to update a staff member's work status or record holiday/leave."""
    staff_id = (args.get("staff_id") or "").strip()
    new_status = (args.get("work_status") or "").strip().upper()
    valid = {"ACTIVE", "ON_LEAVE", "HOLIDAY", "SICK_LEAVE", "DND"}
    if new_status not in valid:
        return {"error": "INVALID_STATUS", "detail": f"Status must be one of {valid}"}

    staff = db.query(models.Staff).filter(
        models.Staff.id == staff_id,
        models.Staff.tenant_id == context.tenant_id,
    ).first()
    if not staff:
        return {"error": "NOT_FOUND", "detail": f"Staff member '{staff_id}' not found in tenant."}

    allowed, reason = can_user_manage_staff_availability(context.user_role, context.user_id, staff, db)
    if not allowed:
        raise PermissionError(reason)

    old_status = getattr(staff, "work_status", "ACTIVE")

    # Holiday / sick leave are leave requests: they need approval unless the caller may approve them.
    # DND / ACTIVE / ON_LEAVE are availability changes and apply immediately.
    leave_status = None
    if new_status in ("HOLIDAY", "SICK_LEAVE", "DND"):
        now = datetime.utcnow()
        days = int(args.get("duration_days") or 1)
        leave_status = "APPROVED" if new_status == "DND" else resolve_new_leave_status(
            context.user_role, context.user_id, staff, "APPROVED"
        )
        leave_rec = models.StaffLeave(
            staff_id=staff.id,
            tenant_id=context.tenant_id,
            leave_type=new_status,
            start_date=now,
            end_date=now + timedelta(days=days),
            status=leave_status,
            notes=args.get("notes") or f"Status set to {new_status} via PractiCare AI",
        )
        db.add(leave_rec)

    if leave_status != "PENDING":
        staff.work_status = new_status
        if new_status in ("HOLIDAY", "SICK_LEAVE", "DND", "ON_LEAVE"):
            staff.on_shift = False

    db.commit()
    db.refresh(staff)

    pending = leave_status == "PENDING"
    return {
        "success": True,
        "staff_id": staff.id,
        "name": staff.name,
        "previous_status": old_status,
        "new_status": staff.work_status,
        "leave_status": leave_status,
        "on_shift": staff.on_shift,
        "message": (
            f"{new_status} leave request for {staff.name} recorded as PENDING approval; work status unchanged."
            if pending
            else f"Successfully updated {staff.name}'s work status to {new_status}."
        ),
    }
