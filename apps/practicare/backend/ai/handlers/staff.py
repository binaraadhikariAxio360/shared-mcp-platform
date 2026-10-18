"""
PractiCare AI Staff Domain Handlers
Handles provider search, staff identity resolution, and availability tracking.
Strictly distinguishes account activation (is_active) from shift availability (on_shift).
"""

import re
from typing import Dict, Any
from sqlalchemy.orm import Session

import models
from ai.context import SecurityContext
from ai.helpers import is_staff_active, is_staff_on_shift, format_staff_status_labels


def execute_search_staff(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Searches and resolves clinical staff members strictly scoped to context.tenant_id.
    Supports lookup by name (e.g. 'Dr. Sarah', 'Nurse Mark'), staff ID ('stf-001'), or role.
    Returns database IDs (stf-xxxx) and display labels.
    """
    tenant_id = context.tenant_id
    raw_query = str(args.get("query") or "").strip()
    role_filter = str(args.get("role") or "").strip().lower()

    staff_query = db.query(models.Staff).filter(models.Staff.tenant_id == tenant_id)
    if role_filter:
        staff_query = staff_query.filter(models.Staff.role.ilike(f"%{role_filter}%"))

    if args.get("on_shift") is not None:
        staff_query = staff_query.filter(models.Staff.on_shift == args["on_shift"])
    if args.get("is_active") is not None:
        staff_query = staff_query.filter(models.Staff.is_active == args["is_active"])

    all_staff = staff_query.all()

    if not raw_query:
        matched = all_staff
    else:
        q_lower = raw_query.lower()
        cleaned = re.sub(r"^(?:dr\.?|doctor|nurse)\s*", "", raw_query, flags=re.IGNORECASE).strip()
        c_lower = cleaned.lower()

        matched = []
        for s in all_staff:
            s_id_lower = (s.id or "").lower()
            s_name_lower = (s.name or "").lower()
            s_role_lower = (s.role or "").lower()

            if s_id_lower == q_lower or s_id_lower == c_lower:
                matched.append(s)
            elif q_lower in s_name_lower or (c_lower and c_lower in s_name_lower):
                matched.append(s)
            elif q_lower in s_role_lower or (c_lower and c_lower in s_role_lower):
                matched.append(s)

    staff_items = []
    for s in matched:
        labels = format_staff_status_labels(s)
        active = is_staff_active(s)
        on_shift = is_staff_on_shift(s)

        staff_items.append({
            "staff_id": s.id,
            "name": s.name,
            "role": s.role,
            "is_active": active,
            "on_shift": on_shift,
            "status_label": labels["shift_label"],
            "account_status": labels["account_label"],
            "display_label": labels["display_label"],
        })

    return {
        "tenant_id": tenant_id,
        "query": raw_query,
        "match_count": len(staff_items),
        "staff": staff_items,
        "message": (
            f"Found {len(staff_items)} matching staff member(s) in tenant '{tenant_id}'."
            if staff_items
            else f"No staff matched query '{raw_query}' in tenant '{tenant_id}'."
        ),
    }
