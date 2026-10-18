"""
PractiCare AI Rooms Domain Handlers
Handles exam/procedure room searches, resolution, and turnover status monitoring.
Enforces tenant isolation and role-scoped read operations.
"""

import re
from typing import Dict, Any
from sqlalchemy.orm import Session

import models
from ai.context import SecurityContext


def execute_search_rooms(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Searches and resolves clinical rooms scoped strictly to the authenticated tenant (context.tenant_id).
    Supports lookup by room number (e.g. '101'), room name (e.g. 'Primary Exam Suite'),
    or exact database primary key (e.g. 'room-101').
    Returns the actual database ID and safe display label for seamless resolution.
    """
    tenant_id = context.tenant_id
    raw_query = str(args.get("query") or "").strip()

    tenant_rooms = (
        db.query(models.Room)
        .filter(models.Room.tenant_id == tenant_id)
        .order_by(models.Room.room_number)
        .all()
    )

    if not raw_query:
        matched = tenant_rooms
    else:
        q_lower = raw_query.lower()
        cleaned = re.sub(r"^(?:room|suite|bay|exam\s*room)\s*#?", "", raw_query, flags=re.IGNORECASE).strip()
        c_lower = cleaned.lower()
        num_match = re.search(r"\d+", raw_query)
        extracted_num = num_match.group(0) if num_match else ""

        matched = []
        for r in tenant_rooms:
            r_id_lower = (r.id or "").lower()
            r_num_lower = (r.room_number or "").lower()
            r_name_lower = (r.name or "").lower()

            if r_id_lower == q_lower or r_id_lower == c_lower:
                matched.append(r)
                continue

            if r_num_lower == q_lower or r_num_lower == c_lower:
                matched.append(r)
                continue
            if extracted_num and r_num_lower == extracted_num:
                matched.append(r)
                continue

            if q_lower in r_name_lower or (c_lower and c_lower in r_name_lower):
                matched.append(r)
                continue

            if q_lower in r_num_lower:
                matched.append(r)
                continue

    room_items = []
    for r in matched:
        display_label = f"Room {r.room_number} — {r.name} (DB ID: {r.id})"
        room_items.append({
            "room_id": r.id,
            "room_number": r.room_number,
            "name": r.name,
            "display_label": display_label,
            "room_type": r.room_type,
            "status": r.status,
        })

    return {
        "tenant_id": tenant_id,
        "query": raw_query,
        "match_count": len(room_items),
        "rooms": room_items,
        "message": (
            f"Found {len(room_items)} matching room(s) in tenant '{tenant_id}'."
            if room_items
            else f"No rooms matched query '{raw_query}' in tenant '{tenant_id}'."
        ),
    }


def execute_get_room_turnover_status(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Fetches live exam/surgery room statuses (Available, Occupied, Turnover, Cleaning needed)."""
    tenant_id = context.tenant_id

    rooms = db.query(models.Room).filter(models.Room.tenant_id == tenant_id).all()
    turnover_summary = {"Available": 0, "Occupied": 0, "Turnover": 0}
    room_list = []

    for r in rooms:
        status_key = r.status if r.status in turnover_summary else "Turnover"
        turnover_summary[status_key] = turnover_summary.get(status_key, 0) + 1
        room_list.append({
            "room_id": r.id,
            "room_number": r.room_number,
            "name": r.name,
            "room_type": r.room_type,
            "status": r.status,
        })

    return {
        "tenant_id": tenant_id,
        "total_rooms": len(rooms),
        "status_breakdown": turnover_summary,
        "rooms": room_list,
        "needs_turnover_count": turnover_summary.get("Turnover", 0),
    }


def execute_update_room(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Updates room status ('Available', 'Occupied', 'Turnover'), name, or room type.
    Validates room exists in authenticated tenant, enforces supported enum values,
    commits the transaction, reads back the record from PostgreSQL and verifies persistence.
    """
    tenant_id = context.tenant_id
    raw_room_id = str(args.get("room_id") or "").strip()
    if not raw_room_id:
        raise ValueError("room_id is required.")

    has_status = "status" in args and args["status"] is not None and str(args["status"]).strip() != ""
    has_name = "name" in args and args["name"] is not None and str(args["name"]).strip() != ""
    has_type = "room_type" in args and args["room_type"] is not None and str(args["room_type"]).strip() != ""

    if not (has_status or has_name or has_type):
        raise ValueError("At least one field to update (status, name, room_type) is required.")

    # Locate room by exact ID or room number within current tenant
    room = (
        db.query(models.Room)
        .filter(models.Room.id == raw_room_id, models.Room.tenant_id == tenant_id)
        .first()
    )
    if not room:
        # Check by room_number
        cleaned_num = re.sub(r"^(?:room|suite|bay)\s*#?", "", raw_room_id, flags=re.IGNORECASE).strip()
        room = (
            db.query(models.Room)
            .filter(
                (models.Room.room_number == raw_room_id) | (models.Room.room_number == cleaned_num),
                models.Room.tenant_id == tenant_id,
            )
            .first()
        )

    if not room:
        raise ValueError(
            f"Room '{raw_room_id}' not found in current clinic partition. "
            f"Please verify the room number or ID using 'search_rooms'."
        )

    if has_status:
        raw_status = str(args["status"]).strip()
        # Case-insensitive normalization
        status_map = {"available": "Available", "occupied": "Occupied", "turnover": "Turnover"}
        normalized_status = status_map.get(raw_status.lower())
        if not normalized_status:
            raise ValueError(
                f"Invalid room status '{raw_status}'. "
                f"Supported room statuses are: Available, Occupied, Turnover."
            )
        room.status = normalized_status

    if has_name:
        room.name = str(args["name"]).strip()

    if has_type:
        raw_type = str(args["room_type"]).strip()
        type_map = {
            "exam": "Exam",
            "surgery": "Surgery",
            "triage": "Triage",
            "consultation": "Consultation",
        }
        room.room_type = type_map.get(raw_type.lower(), raw_type.title())

    try:
        db.commit()
        db.refresh(room)
    except Exception:
        db.rollback()
        raise

    # Verify persistence by reading back from PostgreSQL
    persisted = (
        db.query(models.Room)
        .filter(models.Room.id == room.id, models.Room.tenant_id == tenant_id)
        .first()
    )
    if not persisted:
        db.rollback()
        raise RuntimeError(f"Database persistence verification failed for room '{room.id}'.")

    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "update_room",
        "action": "UPDATE_ROOM",
        "room_id": persisted.id,
        "resource_id": persisted.id,
        "tenant_id": persisted.tenant_id,
        "room_number": persisted.room_number,
        "name": persisted.name,
        "room_type": persisted.room_type,
        "room_status": persisted.status,
        "persisted": True,
        "message": f"Successfully updated room '{persisted.room_number} — {persisted.name}' status to '{persisted.status}' in tenant '{tenant_id}'.",
    }


def execute_get_room_details(
    db: Session,
    context: SecurityContext,
    args: Dict[str, Any],
) -> Dict[str, Any]:
    """Retrieves tenant-scoped details for a specific room."""
    tenant_id = context.tenant_id
    raw_room_id = str(args.get("room_id") or "").strip()
    if not raw_room_id:
        raise ValueError("room_id is required.")

    room = (
        db.query(models.Room)
        .filter(models.Room.id == raw_room_id, models.Room.tenant_id == tenant_id)
        .first()
    )
    if not room:
        cleaned_num = re.sub(r"^(?:room|suite|bay)\s*#?", "", raw_room_id, flags=re.IGNORECASE).strip()
        room = (
            db.query(models.Room)
            .filter(
                (models.Room.room_number == raw_room_id) | (models.Room.room_number == cleaned_num),
                models.Room.tenant_id == tenant_id,
            )
            .first()
        )

    if not room:
        raise ValueError(f"Room '{raw_room_id}' not found in current clinic partition.")

    return {
        "status": "SUCCESS",
        "execution_status": "SUCCESS",
        "tool_name": "get_room_details",
        "room_id": room.id,
        "resource_id": room.id,
        "tenant_id": room.tenant_id,
        "room_number": room.room_number,
        "name": room.name,
        "room_type": room.room_type,
        "status": room.status,
        "display_label": f"Room {room.room_number} — {room.name} (DB ID: {room.id})",
        "created_at": room.created_at.isoformat() if room.created_at else None,
    }

