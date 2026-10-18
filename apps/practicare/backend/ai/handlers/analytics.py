"""
PractiCare AI Analytics Domain Handlers
Handles clinic operational summaries, team performance analytics, and role-based visibility.
Strictly separates account status from shift status, avoids hardcoded scores, and rejects unknown roles.
"""

from typing import Dict, Any
from datetime import date
from sqlalchemy.orm import Session

import models
from ai.context import SecurityContext
from ai.helpers import (
    is_task_overdue,
    is_staff_active,
    is_staff_on_shift,
    is_task_assigned_to_user,
)
from ai.policy import filter_visible_tasks, is_auditor, is_doctor, is_nurse, is_manager_or_above


def execute_get_team_task_performance(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Analyzes team clinical task metrics, completion turnaround, overdue bottlenecks,
    and provider workloads.
    Applies strict role-based visibility:
      - CLINICAL_AUDITOR: Zero PII, aggregate statistics over Doctor-scope tasks only.
      - NURSE_STAFF: Own assigned tasks only.
      - ATTENDING_PHYSICIAN: Doctor/Nurse scope (no Owner/Manager tasks).
      - CLINIC_OWNER / INVENTORY_MANAGER: Full transparent workload & turnaround analytics.
      - Unknown / Unauthorized: Denied with explicit error.
    """
    tenant_id = context.tenant_id
    user_role = context.user_role
    user_id = context.user_id

    tenant_tasks = db.query(models.Task).filter(models.Task.tenant_id == tenant_id).all()
    # Every role sees metrics only over the tasks it is authorized to view (Doctors/Auditors: no Owner/Manager tasks; Nurses: own tasks).
    all_tasks = filter_visible_tasks(user_role, user_id, tenant_tasks, db)
    all_staff = {s.id: s for s in db.query(models.Staff).filter(models.Staff.tenant_id == tenant_id).all()}
    all_rooms = {r.id: r for r in db.query(models.Room).filter(models.Room.tenant_id == tenant_id).all()}

    total_tasks = len(all_tasks)
    today_str = date.today().isoformat()
    completed_tasks = [t for t in all_tasks if t.status.lower() == "completed"]
    pending_tasks = [t for t in all_tasks if t.status.lower() in ("pending", "in progress")]
    overdue_tasks = [t for t in all_tasks if is_task_overdue(t.due_date, t.status, today_str)]

    completion_rate = round((len(completed_tasks) / total_tasks * 100), 1) if total_tasks > 0 else 100.0

    if is_auditor(user_role):
        category_breakdown = {}
        for t in all_tasks:
            pri = t.priority or "Normal"
            category_breakdown[pri] = category_breakdown.get(pri, 0) + 1

        pass_ratio = round((len(completed_tasks) / total_tasks * 100), 1) if total_tasks > 0 else 100.0
        overdue_ratio = round((len(overdue_tasks) / total_tasks * 100), 1) if total_tasks > 0 else 0.0

        # Calculate compliance score dynamically from real database metrics
        score_pct = round(max(0.0, 100.0 - overdue_ratio), 1)
        compliance_score = f"{score_pct}% (Pass)" if overdue_ratio < 15 else "Review Recommended"

        return {
            "tenant_id": tenant_id,
            "role_scope": "CLINICAL_AUDITOR (Aggregate Only - Zero PII)",
            "audit_metrics": {
                "total_audited_tasks": total_tasks,
                "completed_count": len(completed_tasks),
                "pending_count": len(pending_tasks),
                "overdue_count": len(overdue_tasks),
                "pass_ratio": pass_ratio,
                "overdue_ratio": overdue_ratio,
                "compliance_score": compliance_score,
                "priority_distribution": category_breakdown,
            },
            "anonymized_sample": [
                {
                    "task_hash": f"tsk-aud-{t.id[:6]}",
                    "priority": t.priority,
                    "status": t.status,
                    "is_overdue": is_task_overdue(t.due_date, t.status, today_str),
                }
                for t in all_tasks[:5]
            ],
        }

    elif is_nurse(user_role):
        operational_tasks = []
        for t in all_tasks:
            room = all_rooms.get(t.room_id)
            operational_tasks.append({
                "task_id": t.id,
                "title": t.title,
                "priority": t.priority,
                "status": t.status,
                "due_date": t.due_date,
                "room_name": room.name if room else "General Floor",
                "assigned_to": all_staff[t.assigned_staff_id].name if t.assigned_staff_id in all_staff else "Unassigned",
            })

        return {
            "tenant_id": tenant_id,
            "role_scope": "NURSE_STAFF (Own Assigned Tasks)",
            "metrics": {
                "operational_tasks_count": len(operational_tasks),
                "overall_completion_rate": completion_rate,
                "overdue_tasks_count": len(overdue_tasks),
                "my_active_tasks_count": sum(1 for t in operational_tasks if t["status"].lower() != "completed"),
            },
            "operational_tasks": operational_tasks,
            "redacted_fields": ["physician_evaluations", "contractor_rates", "executive_salaries"],
        }

    elif is_doctor(user_role):
        dept_tasks = []
        for t in all_tasks:
            room = all_rooms.get(t.room_id)
            staff_member = all_staff.get(t.assigned_staff_id)
            dept_tasks.append({
                "task_id": t.id,
                "title": t.title,
                "priority": t.priority,
                "status": t.status,
                "due_date": t.due_date,
                "room_id": t.room_id,
                "room_name": room.name if room else "Clinical Department",
                "assigned_to": staff_member.name if staff_member else "Unassigned",
                "is_assigned_to_me": is_task_assigned_to_user(t, user_id, db),
            })

        return {
            "tenant_id": tenant_id,
            "role_scope": "ATTENDING_PHYSICIAN (Clinical Department Scope)",
            "metrics": {
                "total_department_tasks": len(dept_tasks),
                "completion_rate": completion_rate,
                "pending_tasks_count": len(pending_tasks),
                "overdue_tasks_count": len(overdue_tasks),
            },
            "department_tasks": dept_tasks,
            "redacted_fields": ["administrative_finance", "executive_audit_notes"],
        }

    elif is_manager_or_above(user_role):
        # Owner / Manager: full transparent workload & turnaround analytics
        staff_workload = {}
        for s_id, s in all_staff.items():
            on_shift = is_staff_on_shift(s)
            active = is_staff_active(s)
            staff_workload[s_id] = {
                "staff_id": s.id,
                "name": s.name,
                "role": s.role,
                "assigned_tasks_count": 0,
                "completed_tasks_count": 0,
                "active_status": "On Shift" if on_shift else "Off Duty",
                "account_status": "Active" if active else "Inactive",
            }

        unassigned_count = 0
        for t in all_tasks:
            if t.assigned_staff_id and t.assigned_staff_id in staff_workload:
                staff_workload[t.assigned_staff_id]["assigned_tasks_count"] += 1
                if t.status.lower() == "completed":
                    staff_workload[t.assigned_staff_id]["completed_tasks_count"] += 1
            else:
                unassigned_count += 1

        workload_list = []
        for w in staff_workload.values():
            assigned = w["assigned_tasks_count"]
            completed = w["completed_tasks_count"]
            rate = round((completed / assigned * 100), 1) if assigned > 0 else 100.0
            w["completion_rate"] = rate
            workload_list.append(w)

        return {
            "tenant_id": tenant_id,
            "role_scope": "CLINIC_OWNER (Full Clinic Executive Analytics)",
            "metrics": {
                "total_tasks_count": total_tasks,
                "completed_tasks_count": len(completed_tasks),
                "pending_tasks_count": len(pending_tasks),
                "overdue_tasks_count": len(overdue_tasks),
                "completion_rate": completion_rate,
                "unassigned_tasks_count": unassigned_count,
            },
            "provider_workloads": workload_list,
            "bottlenecks": [
                {
                    "task_id": t.id,
                    "title": t.title,
                    "priority": t.priority,
                    "due_date": t.due_date,
                    "assigned_staff": all_staff[t.assigned_staff_id].name if t.assigned_staff_id in all_staff else "Unassigned",
                    "room": all_rooms[t.room_id].room_number if t.room_id in all_rooms else "N/A",
                }
                for t in overdue_tasks
            ],
        }

    else:
        # Deny unknown roles by default - Fail-Safe Defaults
        raise ValueError(
            f"Role '{user_role}' is not authorized to access team task performance analytics."
        )


def execute_get_practice_summary(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Returns an authorized high-level operational summary of the clinical practice.
    Aggregates room turnover, task completion metrics, staff rosters, and inventory warnings.
    Correctly counts on-shift staff independently from active staff accounts.
    """
    tenant_id = context.tenant_id

    practice = db.query(models.Practice).filter(models.Practice.tenant_id == tenant_id).first()
    practice_name = practice.name if practice else context.company_name
    location = practice.location if practice else "Main Facility"

    rooms = db.query(models.Room).filter(models.Room.tenant_id == tenant_id).all()
    room_summary = {"Available": 0, "Occupied": 0, "Turnover": 0, "Cleaning": 0}
    for r in rooms:
        st = r.status if r.status in room_summary else "Turnover"
        room_summary[st] = room_summary.get(st, 0) + 1

    # Same visibility policy as the dashboard, Tasks page and list_tasks
    tasks = filter_visible_tasks(
        context.user_role, context.user_id,
        db.query(models.Task).filter(models.Task.tenant_id == tenant_id).all(), db,
    )
    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.status.lower() == "completed")
    pending_tasks = sum(1 for t in tasks if t.status.lower() in ("pending", "in progress"))
    today_str = date.today().isoformat()
    overdue_tasks = sum(1 for t in tasks if is_task_overdue(t.due_date, t.status, today_str))
    completion_rate = round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 100.0

    staff = db.query(models.Staff).filter(models.Staff.tenant_id == tenant_id).all()
    # Correct calculation: on_shift reflects shift status, not account activation
    on_shift_staff = sum(1 for s in staff if is_staff_on_shift(s))
    active_staff = sum(1 for s in staff if is_staff_active(s))

    inventory = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == tenant_id).all()
    low_stock = sum(1 for i in inventory if i.current_stock <= i.min_threshold)

    checklists = db.query(models.Checklist).filter(models.Checklist.tenant_id == tenant_id).all()
    completed_checklists = sum(1 for c in checklists if c.is_completed)

    return {
        "tenant_id": tenant_id,
        "practice_name": practice_name,
        "location": location,
        "facility_status": {
            "total_rooms": len(rooms),
            "rooms_available": room_summary.get("Available", 0),
            "rooms_occupied": room_summary.get("Occupied", 0),
            "rooms_needs_turnover": room_summary.get("Turnover", 0) + room_summary.get("Cleaning", 0),
        },
        "clinical_operations": {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "completion_rate_pct": completion_rate,
        },
        "staffing": {
            "total_staff": len(staff),
            "on_shift_staff": on_shift_staff,
            "active_staff": active_staff,
        },
        "compliance_and_logistics": {
            "low_stock_items": low_stock,
            "checklists_total": len(checklists),
            "checklists_completed": completed_checklists,
        },
        "summary_headline": (
            f"{practice_name}: {completion_rate}% Task Completion Rate ({pending_tasks} Pending, {overdue_tasks} Overdue). "
            f"{room_summary.get('Available', 0)}/{len(rooms)} Rooms Available. {low_stock} Supplies Low."
        ),
    }
