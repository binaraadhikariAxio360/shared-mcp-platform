"""Tenant-scoped AI operations matching existing PractiCare REST behavior."""
import secrets
from datetime import datetime, timedelta
from sqlalchemy import func
import models

CHECKLIST_IDEMPOTENCY_MINUTES = 10


def _practice(db, tenant_id):
    practice = db.query(models.Practice).filter(models.Practice.tenant_id == tenant_id).first()
    if practice is None:
        raise ValueError("No practice registered for the authenticated tenant")
    return practice


def execute_create_room(db, context, args):
    from ai.policy import can_user_create_room
    if not can_user_create_room(context.user_role):
        raise PermissionError(f"Role '{context.user_role}' is not permitted to create rooms.")

    tenant = context.tenant_id
    practice = _practice(db, tenant)
    number = args["room_number"].strip()
    if not number:
        raise ValueError("Room number is required")
    if db.query(models.Room).filter(models.Room.tenant_id == tenant, models.Room.room_number == number).first():
        raise ValueError("Room number already exists in this company")
    if args.get("status", "Available") not in {"Available", "Occupied", "Turnover"}:
        raise ValueError("Invalid room status")
    room = models.Room(room_number=number, name=args["name"].strip(), room_type=args.get("room_type", "Exam"),
                       status=args.get("status", "Available"), practice_id=practice.id, tenant_id=tenant)
    try:
        db.add(room); db.commit(); db.refresh(room)
    except Exception:
        db.rollback(); raise
    return {"status":"SUCCESS", "action":"CREATE_ROOM", "room_id":room.id,
            "room_number":room.room_number,"name":room.name,"tenant_id":tenant}


def execute_create_checklist(db, context, args):
    from ai.policy import can_user_create_checklist
    allowed, reason = can_user_create_checklist(context.user_role)
    if not allowed:
        raise PermissionError(reason)

    tenant = context.tenant_id
    practice = _practice(db, tenant)
    title = args["title"].strip()
    staff_id = args.get("assigned_staff_id") or None
    staff = None
    if staff_id:
        staff = db.query(models.Staff).filter(models.Staff.id == staff_id, models.Staff.tenant_id == tenant).first()
        if not staff or not staff.is_active:
            raise ValueError("Assigned staff not found or inactive in this company")

    # Idempotency: a retried request (same creator, title and assignee within the window) returns the
    # checklist that was already persisted instead of creating a duplicate.
    window_start = datetime.utcnow() - timedelta(minutes=CHECKLIST_IDEMPOTENCY_MINUTES)
    chk = db.query(models.Checklist).filter(
        models.Checklist.tenant_id == tenant,
        models.Checklist.created_by_user_id == context.user_id,
        func.lower(models.Checklist.title) == title.lower(),
        models.Checklist.assigned_staff_id == staff_id if staff_id else models.Checklist.assigned_staff_id.is_(None),
        models.Checklist.is_completed == False,  # noqa: E712
        models.Checklist.created_at >= window_start,
    ).order_by(models.Checklist.created_at.desc()).first()
    duplicate_prevented = chk is not None

    if not chk:
        chk = models.Checklist(
            title=title,
            category=args.get("category", "Sterilization"),
            frequency=args.get("frequency", "Daily"),
            is_completed=False,
            assigned_staff_id=staff_id,
            practice_id=practice.id,
            tenant_id=tenant,
            created_by_user_id=context.user_id,
            created_by_role=context.user_role,
        )
        try:
            db.add(chk); db.commit(); db.refresh(chk)
        except Exception:
            db.rollback(); raise

    return {"status":"SUCCESS", "action":"CREATE_CHECKLIST", "persisted": True, "checklist_id":chk.id,
            "title":chk.title, "category":chk.category, "assigned_staff_id":chk.assigned_staff_id,
            "assigned_staff_name": staff.name if staff else None, "tenant_id":tenant,
            "duplicate_prevented": duplicate_prevented,
            "note": ("An identical checklist was already created moments ago; it was returned instead of creating a duplicate. "
                     if duplicate_prevented else "")
                    + "Individual checklist line items are not stored by this data model; only the checklist title, "
                      "category, frequency and assignee were saved."}


def execute_list_checklists(db, context, args):
    from ai.helpers import is_checklist_assigned_to_user, parse_bool_arg
    q = db.query(models.Checklist).filter(models.Checklist.tenant_id == context.tenant_id)
    if args.get("is_completed") is not None:
        is_comp = parse_bool_arg(args["is_completed"])
        q = q.filter(models.Checklist.is_completed == is_comp)
    if args.get("category"):
        q = q.filter(models.Checklist.category.ilike(args["category"]))

    assigned_staff_id = str(args.get("assigned_staff_id") or "").strip()
    my_checklists_only = parse_bool_arg(args.get("my_checklists_only"), default=False) or (assigned_staff_id in ("me", "self", "mine"))

    if assigned_staff_id and not my_checklists_only:
        q = q.filter(models.Checklist.assigned_staff_id == assigned_staff_id)

    records = q.order_by(models.Checklist.created_at.desc()).limit(args.get("limit", 50)).all()
    staff_map = {s.id: s.name for s in db.query(models.Staff).filter(models.Staff.tenant_id == context.tenant_id).all()}

    res_list = []
    for c in records:
        is_assigned = is_checklist_assigned_to_user(c, context.user_id, db)
        if my_checklists_only and not is_assigned:
            continue
        # Checklists are viewable by all company staff members
        res_list.append({
            "checklist_id": c.id,
            "title": c.title,
            "category": c.category,
            "frequency": c.frequency,
            "is_completed": c.is_completed,
            "assigned_staff_id": c.assigned_staff_id,
            "assigned_staff_name": staff_map.get(c.assigned_staff_id) if c.assigned_staff_id else "Unassigned",
        })

    return {
        "tenant_id": context.tenant_id,
        "count": len(res_list),
        "total_returned": len(res_list),
        "checklists": res_list,
    }


def execute_create_staff_invitation(db, context, args):
    # Staff registration and owner approval remain separate authenticated steps.
    role = args.get("role", "NURSE_STAFF").upper()
    if role not in {"NURSE_STAFF", "ATTENDING_PHYSICIAN", "CLINICAL_AUDITOR", "INVENTORY_MANAGER"}:
        raise ValueError("Unsupported invite role")
    token = secrets.token_hex(4).upper()
    invite = models.StaffInvitation(tenant_id=context.tenant_id, code=f"INV-{token[:4]}-{token[4:]}",
             role=role, created_by_user_id=context.user_id, max_uses=args.get("max_uses",1),
             use_count=0, expires_at=datetime.utcnow()+timedelta(days=args.get("expires_in_days",7)), is_revoked=False)
    try:
        db.add(invite); db.commit(); db.refresh(invite)
    except Exception:
        db.rollback(); raise
    return {"status":"SUCCESS", "action":"CREATE_STAFF_INVITATION", "invitation_id":invite.id,
            "invitation_code":invite.code, "role":invite.role,
            "message":"Invitation created. The staff member must join and be approved through the existing workflow."}
