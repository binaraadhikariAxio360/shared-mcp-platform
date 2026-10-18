import os
import logging
import secrets
from datetime import datetime, date, timedelta
from typing import Annotated, List, Optional, Dict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db, init_db_and_seed, hash_password, verify_password, password_needs_rehash
import models
import schemas
import inventory_service
import uuid
import json
from security import create_access_token, verify_access_token
from ai.agent import agent
from ai.context import SecurityContext, normalize_role, is_known_role
from ai.gateway import gateway
from ai.approvals import approval_manager
from ai.helpers import is_task_assigned_to_user, is_checklist_assigned_to_user, get_user_staff_ids
from ai.policy import (
    get_role_rank,
    is_owner,
    is_manager,
    is_doctor,
    is_nurse,
    is_manager_or_above,
    is_doctor_or_above,
    can_user_view_task,
    can_user_create_task,
    can_user_update_task,
    can_user_delete_task,
    can_user_view_checklist,
    can_user_create_checklist,
    can_user_update_checklist,
    can_user_delete_checklist,
    can_user_manage_inventory,
    can_user_create_room,
    can_user_update_room_status,
    can_user_update_room,
    can_user_delete_room,
    can_user_manage_staff_availability,
    can_user_approve_leave,
    resolve_new_leave_status,
    filter_visible_tasks,
    task_permission_flags,
    checklist_permission_flags,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("practicare.api")

# Rate-limiting / protection against brute-force invitation code guessing
_invitation_attempt_log: Dict[str, List[float]] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing PractiCare database and schema...")
    init_db_and_seed()
    yield

app = FastAPI(
    title="PractiCare Clinical Suite Backend",
    version="2.0.0",
    description="Enterprise healthcare operations, staff management, room scheduling, and inventory control with PostgreSQL.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003",
        "http://127.0.0.1:3004",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Security & Multi-Tenancy Dependency
# -----------------------------------------------------------------------------
def get_request_context(
    authorization: Annotated[Optional[str], Header(alias="authorization", description="Bearer Session Token")] = None,
    db: Session = Depends(get_db),
) -> schemas.RequestContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is required.")
    payload = verify_access_token(authorization[7:].strip())
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session token.")
    token_uid = payload.get("sub")
    token_tid = payload.get("tenant_id")
    auth_user = db.query(models.User).filter(models.User.id == token_uid).first()
    if not auth_user or auth_user.tenant_id != token_tid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authenticated account is invalid.")
    if not auth_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive. Access disabled.")
    if auth_user.membership_status != "APPROVED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account membership is not approved.")

    return schemas.RequestContext(
        tenant_id=auth_user.tenant_id,
        user_role=normalize_role(auth_user.role),
        user_id=auth_user.id,
    )

def build_ai_security_context(context: schemas.RequestContext, company_name: Optional[str]) -> SecurityContext:
    """Builds the AI security context; unknown roles get a 403 instead of an unhandled 500."""
    try:
        return SecurityContext.create(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            user_role=context.user_role,
            company_name=company_name,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{context.user_role}' is not authorized to use the AI assistant.",
        )

def authorize_staff_availability(context: schemas.RequestContext, staff: Optional[models.Staff], db: Session):
    """Work status / leave writes: own record for any clinical role; others require staff:leave_manage."""
    allowed, reason = can_user_manage_staff_availability(context.user_role, context.user_id, staff, db)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

# Identity linking: a Staff record belongs to a user only through Staff.user_id.
# Names are never used to infer identity (a name match could hand over another person's record).
def get_linked_staff(db: Session, tenant_id: str, user_id: str) -> Optional[models.Staff]:
    return db.query(models.Staff).filter(
        models.Staff.tenant_id == tenant_id,
        models.Staff.user_id == user_id,
    ).first()

def get_linked_user(db: Session, tenant_id: str, staff: models.Staff) -> Optional[models.User]:
    if not staff or not staff.user_id:
        return None
    return db.query(models.User).filter(
        models.User.id == staff.user_id,
        models.User.tenant_id == tenant_id,
    ).first()

def get_or_create_own_staff(db: Session, tenant_id: str, user_id: str) -> Optional[models.Staff]:
    """Returns the caller's linked Staff record, creating a new linked one if none exists."""
    staff = get_linked_staff(db, tenant_id, user_id)
    if staff:
        return staff
    user = db.query(models.User).filter(models.User.id == user_id, models.User.tenant_id == tenant_id).first()
    if not user:
        return None
    role = normalize_role(user.role)
    role_display = {"ATTENDING_PHYSICIAN": "Doctor", "NURSE_STAFF": "Nurse", "INVENTORY_MANAGER": "Inventory Manager"}.get(role, "Staff")
    practice = ensure_tenant_practice(db, tenant_id)
    staff = models.Staff(
        name=user.full_name,
        role=role_display,
        is_active=user.is_active,
        on_shift=True,
        user_id=user.id,
        practice_id=practice.id,
        tenant_id=tenant_id,
    )
    db.add(staff)
    db.commit()
    db.refresh(staff)
    return staff

def apply_task_flags(item: schemas.TaskRead, task: models.Task, context: schemas.RequestContext, db: Session) -> None:
    """Attaches the caller's permissions for this task (same policy as the REST/AI write paths)."""
    for key, value in task_permission_flags(context.user_role, context.user_id, task, db).items():
        setattr(item, key, value)

def apply_checklist_flags(item: schemas.ChecklistRead, chk: models.Checklist, context: schemas.RequestContext, db: Session) -> None:
    """Attaches the caller's permissions for this checklist (same policy as the REST/AI write paths)."""
    for key, value in checklist_permission_flags(context.user_role, context.user_id, chk, db).items():
        setattr(item, key, value)

def require_role(context: schemas.RequestContext, allowed_roles: List[str]):
    if context.user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation not permitted for role {context.user_role}",
        )

def ensure_tenant_practice(db: Session, tenant_id: str) -> models.Practice:
    practice = db.query(models.Practice).filter(models.Practice.tenant_id == tenant_id).first()
    if not practice:
        name = "Apex Health Medical Center" if tenant_id == "tenant-001" else ("Metro Health Urgent Care" if tenant_id == "tenant-002" else f"Clinic ({tenant_id})")
        location = "Suite 400, Chicago, IL" if tenant_id == "tenant-001" else ("742 North Michigan Ave, Chicago, IL" if tenant_id == "tenant-002" else "Main Clinic Facility")
        practice = models.Practice(
            name=name,
            location=location,
            room_count=12 if tenant_id == "tenant-001" else (8 if tenant_id == "tenant-002" else 0),
            tenant_id=tenant_id,
        )
        db.add(practice)
        db.commit()
        db.refresh(practice)
    return practice

def ensure_user_record(db: Session, user_id: str, tenant_id: str, role: str = "CLINIC_OWNER") -> models.User:
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        clean_email = f"{user_id.lower()}@{tenant_id.lower()}.com"
        user = models.User(
            id=user_id,
            email=clean_email,
            password_hash=hash_password("password123"),
            full_name=user_id.replace("-", " ").title(),
            role=role,
            tenant_id=tenant_id,
            company_name=tenant_id,
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            user = db.query(models.User).filter(models.User.id == user_id).first()
    return user

# -----------------------------------------------------------------------------
# System, Auth & Health
# -----------------------------------------------------------------------------
@app.get("/", tags=["System"])
def root_index():
    return {
        "service": "PractiCare Clinical API",
        "status": "operational",
        "database": "PostgreSQL 16 Connected",
        "docs_url": "/docs",
        "health_url": "/health",
        "frontend_url": "http://localhost:3001",
    }

@app.get("/api/v1/auth/roles", tags=["Auth"])
def get_auth_roles(context: Annotated[schemas.RequestContext, Depends(get_request_context)]):
    roles = [
        {"id": "CLINIC_OWNER", "role": "CLINIC_OWNER", "label": "Clinic Owner", "badge": "Admin", "description": "Full clinical & administrative control"},
        {"id": "ATTENDING_PHYSICIAN", "role": "ATTENDING_PHYSICIAN", "label": "Attending Physician", "badge": "Doctor", "description": "Full task & patient care management"},
        {"id": "NURSE_STAFF", "role": "NURSE_STAFF", "label": "Nurse / Floor Staff", "badge": "Operator", "description": "Task execution and room turnover"},
        {"id": "INVENTORY_MANAGER", "role": "INVENTORY_MANAGER", "label": "Inventory Manager", "badge": "Staff", "description": "Medical supplies and inventory control"},
    ]
    tenants = [
        {"id": "tenant-001", "name": "Apex Health Medical Center", "badge": "Primary Facility", "description": "Primary Facility"},
        {"id": "tenant-002", "name": "Metro Health Urgent Care", "badge": "Downtown Branch", "description": "Downtown Branch"},
    ]
    return {
        "app": "PractiCare",
        "tenant_id": context.tenant_id,
        "current_tenant": context.tenant_id,
        "current_role": context.user_role,
        "current_user_id": context.user_id,
        "current_user": context.user_id,
        "roles": roles,
        "available_roles": roles,
        "tenants": tenants,
        "available_tenants": tenants,
    }

def check_invitation_rate_limit(client_key: str):
    """Guards against brute-force guessing of invitation codes (max 5 failed attempts per 60s)."""
    now = datetime.utcnow().timestamp()
    attempts = _invitation_attempt_log.get(client_key, [])
    valid_attempts = [t for t in attempts if now - t < 60]
    if len(valid_attempts) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many invalid invitation attempts. Please wait 60 seconds before trying again.",
        )
    _invitation_attempt_log[client_key] = valid_attempts

def record_invitation_failure(client_key: str):
    now = datetime.utcnow().timestamp()
    attempts = _invitation_attempt_log.get(client_key, [])
    attempts.append(now)
    _invitation_attempt_log[client_key] = attempts

@app.post("/api/v1/auth/login", response_model=schemas.AuthResponse, tags=["Auth"])
def auth_login(payload: schemas.UserLoginRequest, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == clean_email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if getattr(user, "is_active", True) is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Access disabled.",
        )
    if getattr(user, "membership_status", "APPROVED") == "PENDING":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your membership is currently pending approval by the clinic Owner.",
        )
    if getattr(user, "membership_status", "APPROVED") == "REJECTED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your membership request was rejected by the clinic Owner.",
        )
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    now_utc = datetime.utcnow()
    user.last_login_at = now_utc
    linked_staff = get_linked_staff(db, user.tenant_id, user.id)
    if linked_staff:
        linked_staff.last_login_at = now_utc
    db.commit()

    access_token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
    )
    return schemas.AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=schemas.UserResponse(
            id=user.id,
            name=user.full_name,
            email=user.email,
            role=user.role,
            is_active=getattr(user, "is_active", True),
            membership_status=getattr(user, "membership_status", "APPROVED"),
            tenant_id=user.tenant_id,
            company_name=user.company_name or user.tenant_id,
        ),
    )

@app.post("/api/v1/auth/register-company", response_model=schemas.AuthResponse, tags=["Auth"])
def auth_register_company(payload: schemas.CompanyRegisterRequest, db: Session = Depends(get_db)):
    """
    Path A: Registers a new Company and Owner.
    Generates a unique server-side Tenant ID (never uses company name as unique ID).
    Automatically onboards the Owner and creates the practice facility.
    """
    clean_email = payload.email.strip().lower()
    existing = db.query(models.User).filter(models.User.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )
    company_name = payload.company_name.strip() if payload.company_name and payload.company_name.strip() else "New Medical Practice"
    # Cryptographically isolated unique tenant ID
    tenant_id = f"tenant-{uuid.uuid4().hex[:8]}"

    practice = models.Practice(
        name=company_name,
        location="Main Facility",
        room_count=0,
        tenant_id=tenant_id,
    )
    db.add(practice)
    db.flush()

    new_user = models.User(
        email=clean_email,
        password_hash=hash_password(payload.password),
        full_name=payload.get_name().strip(),
        role="CLINIC_OWNER",
        is_active=True,
        membership_status="APPROVED",
        tenant_id=tenant_id,
        company_name=company_name,
    )
    db.add(new_user)
    db.flush()

    # Link initial Owner Staff record so owner appears in Staff Directory
    owner_staff = models.Staff(
        name=new_user.full_name,
        role="Doctor",
        is_active=True,
        on_shift=True,
        user_id=new_user.id,
        practice_id=practice.id,
        tenant_id=tenant_id,
    )
    db.add(owner_staff)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(
        user_id=new_user.id,
        tenant_id=new_user.tenant_id,
        role=new_user.role,
    )
    return schemas.AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=schemas.UserResponse(
            id=new_user.id,
            name=new_user.full_name,
            email=new_user.email,
            role=new_user.role,
            is_active=new_user.is_active,
            membership_status=new_user.membership_status,
            tenant_id=new_user.tenant_id,
            company_name=new_user.company_name,
        ),
    )

@app.post("/api/v1/invitations/validate", response_model=schemas.InvitationValidateResponse, tags=["Invitations"])
def validate_invitation_code(payload: schemas.InvitationValidateRequest, db: Session = Depends(get_db)):
    """Public validation endpoint to preview company and role for an invitation code."""
    clean_code = payload.code.strip().upper()
    check_invitation_rate_limit(clean_code)

    inv = db.query(models.StaffInvitation).filter(models.StaffInvitation.code == clean_code).first()
    if not inv or inv.is_revoked or inv.expires_at < datetime.utcnow() or inv.use_count >= inv.max_uses:
        record_invitation_failure(clean_code)
        return schemas.InvitationValidateResponse(
            valid=False,
            detail="Invitation code is invalid, expired, or has reached its maximum usage limit.",
        )

    practice = db.query(models.Practice).filter(models.Practice.tenant_id == inv.tenant_id).first()
    return schemas.InvitationValidateResponse(
        valid=True,
        company_name=practice.name if practice else inv.tenant_id,
        role=inv.role,
        detail="Valid invitation code.",
    )

@app.post("/api/v1/auth/join", tags=["Auth"])
def auth_join_company(payload: schemas.StaffJoinRequest, db: Session = Depends(get_db)):
    """
    Path B: Staff Registration using verified Invitation Code.
    Resolves tenant server-side, sets membership_status='PENDING', and awaits Owner approval.
    """
    clean_email = payload.email.strip().lower()
    clean_code = payload.invitation_code.strip().upper()
    check_invitation_rate_limit(clean_code)

    existing = db.query(models.User).filter(models.User.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    inv = db.query(models.StaffInvitation).filter(models.StaffInvitation.code == clean_code).first()
    if not inv:
        record_invitation_failure(clean_code)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation code.",
        )
    if inv.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation code has been revoked by the clinic Owner.",
        )
    if inv.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation code has expired.",
        )
    if inv.use_count >= inv.max_uses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation code has reached its maximum usage limit.",
        )

    target_tenant_id = inv.tenant_id
    practice = db.query(models.Practice).filter(models.Practice.tenant_id == target_tenant_id).first()
    assigned_role = inv.role if inv.role != "CLINIC_OWNER" else "NURSE_STAFF"

    new_user = models.User(
        email=clean_email,
        password_hash=hash_password(payload.password),
        full_name=payload.get_name().strip(),
        role=assigned_role,
        is_active=True,
        membership_status="PENDING",
        tenant_id=target_tenant_id,
        company_name=practice.name if practice else target_tenant_id,
    )
    db.add(new_user)
    inv.use_count += 1
    db.commit()
    db.refresh(new_user)

    return {
        "success": True,
        "detail": "Registration submitted successfully. Your membership is pending Owner approval before you can access clinical operations.",
        "membership_status": "PENDING",
        "requires_approval": True,
        "user_id": new_user.id,
        "tenant_id": new_user.tenant_id,
        "user": {
            "id": new_user.id,
            "name": new_user.full_name,
            "email": new_user.email,
            "role": new_user.role,
            "tenant_id": new_user.tenant_id,
            "company_name": new_user.company_name,
            "membership_status": "PENDING",
        },
    }

@app.post("/api/v1/auth/register", response_model=schemas.AuthResponse, tags=["Auth"])
def auth_register(payload: schemas.UserRegisterRequest, db: Session = Depends(get_db)):
    """
    Universal Registration Endpoint (maintains backward-compatibility).
    Routes to invitation join flow if invitation_code is provided,
    otherwise creates a new company and Owner account.
    """
    if payload.invitation_code and payload.invitation_code.strip():
        # Handle staff join flow
        res = auth_join_company(
            schemas.StaffJoinRequest(
                full_name=payload.full_name,
                email=payload.email,
                password=payload.password,
                invitation_code=payload.invitation_code.strip(),
            ),
            db=db,
        )
        u_info = res["user"]
        # Temporary token with pending status
        token = create_access_token(user_id=u_info["id"], tenant_id=u_info["tenant_id"], role=u_info["role"])
        return schemas.AuthResponse(
            access_token=token,
            token_type="bearer",
            user=schemas.UserResponse(
                id=u_info["id"],
                name=u_info["name"],
                email=u_info["email"],
                role=u_info["role"],
                is_active=True,
                membership_status="PENDING",
                tenant_id=u_info["tenant_id"],
                company_name=u_info["company_name"],
            ),
        )

    # Compatibility route: non-invitation registration always creates a new,
    # server-generated tenant and CLINIC_OWNER account.
    return auth_register_company(
        schemas.CompanyRegisterRequest(
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            company_name=payload.company_name or "New Medical Practice",
        ), db=db,
    )

# -----------------------------------------------------------------------------
# Company Settings & Staff Invitations (Owner Only)
# -----------------------------------------------------------------------------
@app.get("/api/v1/company/settings", response_model=schemas.CompanySettingsRead, tags=["Company Settings"])
def get_company_settings(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    practice = ensure_tenant_practice(db, context.tenant_id)
    active_invs = db.query(models.StaffInvitation).filter(
        models.StaffInvitation.tenant_id == context.tenant_id,
        models.StaffInvitation.is_revoked == False,
        models.StaffInvitation.expires_at > datetime.utcnow(),
    ).count()
    pending_reqs = db.query(models.User).filter(
        models.User.tenant_id == context.tenant_id,
        models.User.membership_status == "PENDING",
    ).count()
    total_staff = db.query(models.Staff).filter(
        models.Staff.tenant_id == context.tenant_id,
    ).count()

    return schemas.CompanySettingsRead(
        company_name=practice.name,
        tenant_id=context.tenant_id,
        active_invitations_count=active_invs,
        pending_requests_count=pending_reqs,
        total_staff_count=total_staff,
    )

@app.post("/api/v1/company/invitations", response_model=schemas.InvitationRead, tags=["Company Settings"])
def create_staff_invitation(
    payload: schemas.InvitationCreateRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    target_role = normalize_role(payload.role) if payload.role else "NURSE_STAFF"
    if target_role == "CLINIC_OWNER":
        target_role = "NURSE_STAFF"  # Never grant Owner via staff invites
    if not is_known_role(target_role):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role '{payload.role}'.")

    # Cryptographically secure random invitation code
    raw_token = secrets.token_hex(4).upper()
    invite_code = f"INV-{raw_token[:4]}-{raw_token[4:]}"

    days = max(1, min(payload.expires_in_days or 7, 30))
    expires = datetime.utcnow() + timedelta(days=days)

    inv = models.StaffInvitation(
        tenant_id=context.tenant_id,
        code=invite_code,
        role=target_role,
        created_by_user_id=context.user_id,
        max_uses=max(1, min(payload.max_uses or 5, 50)),
        use_count=0,
        expires_at=expires,
        is_revoked=False,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv

@app.get("/api/v1/company/invitations", response_model=List[schemas.InvitationRead], tags=["Company Settings"])
def list_company_invitations(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    return (
        db.query(models.StaffInvitation)
        .filter(models.StaffInvitation.tenant_id == context.tenant_id)
        .order_by(models.StaffInvitation.created_at.desc())
        .all()
    )

@app.delete("/api/v1/company/invitations/{inv_id}", tags=["Company Settings"])
def revoke_staff_invitation(
    inv_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    inv = db.query(models.StaffInvitation).filter(
        models.StaffInvitation.id == inv_id,
        models.StaffInvitation.tenant_id == context.tenant_id,
    ).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    inv.is_revoked = True
    db.commit()
    msg = f"Invitation '{inv.code}' has been revoked."
    return {"success": True, "message": msg, "detail": msg}

@app.get("/api/v1/company/pending-members", response_model=List[schemas.PendingMemberRead], tags=["Company Settings"])
def list_pending_members(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    users = db.query(models.User).filter(
        models.User.tenant_id == context.tenant_id,
        models.User.membership_status == "PENDING",
    ).order_by(models.User.created_at.desc()).all()

    return [
        schemas.PendingMemberRead(
            id=u.id,
            user_id=u.id,
            name=u.full_name,
            email=u.email,
            role=u.role,
            membership_status=u.membership_status,
            tenant_id=u.tenant_id,
            company_name=u.company_name,
            created_at=u.created_at,
        )
        for u in users
    ]

@app.post("/api/v1/company/pending-members/{user_id}/action", tags=["Company Settings"])
def resolve_pending_member(
    user_id: str,
    payload: schemas.MemberApprovalAction,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.tenant_id == context.tenant_id,
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Pending applicant not found in current clinic partition.")

    act = payload.action.strip().upper()
    if act == "REJECT":
        user.membership_status = "REJECTED"
        db.commit()
        return {"success": True, "detail": f"Join request for '{user.full_name}' was rejected."}

    if act == "APPROVE":
        final_role = normalize_role(payload.role or user.role)
        if not is_known_role(final_role):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown role '{payload.role or user.role}'.")
        user.membership_status = "APPROVED"
        user.role = final_role

        practice = ensure_tenant_practice(db, context.tenant_id)
        # Check if staff record already linked
        existing_staff = db.query(models.Staff).filter(
            models.Staff.user_id == user.id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()
        if not existing_staff:
            role_display = "Doctor" if "PHYSICIAN" in final_role else ("Nurse" if "NURSE" in final_role else ("Inventory Manager" if "INVENTORY" in final_role else "Staff"))
            new_staff = models.Staff(
                name=user.full_name,
                role=role_display,
                is_active=True,
                on_shift=True,
                user_id=user.id,
                practice_id=practice.id,
                tenant_id=context.tenant_id,
            )
            db.add(new_staff)
        else:
            existing_staff.is_active = True

        db.commit()
        db.refresh(user)
        staff_rec = db.query(models.Staff).filter(
            models.Staff.user_id == user.id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()
        return {
            "success": True,
            "membership_status": user.membership_status,
            "staff_record_id": staff_rec.id if staff_rec else None,
            "detail": f"Staff member '{user.full_name}' approved and onboarded to {practice.name}.",
        }

    raise HTTPException(status_code=400, detail="Invalid action. Permitted: 'APPROVE', 'REJECT'.")


@app.get("/api/v1/auth/me", response_model=schemas.UserResponse, tags=["Auth"])
def auth_me(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(
        models.User.id == context.user_id,
        models.User.tenant_id == context.tenant_id,
    ).first()
    if user:
        return schemas.UserResponse(
            id=user.id,
            name=user.full_name,
            email=user.email,
            role=user.role,
            tenant_id=user.tenant_id,
            company_name=user.company_name or user.tenant_id,
        )
    return schemas.UserResponse(
        id=context.user_id,
        name=f"Practitioner ({context.user_role})",
        email=f"{context.user_role.lower()}@{context.tenant_id}.com",
        role=context.user_role,
        tenant_id=context.tenant_id,
        company_name=f"Clinic ({context.tenant_id})",
    )

@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(models.Practice.__table__.select().limit(1))
    except Exception as e:
        logger.error(f"Health DB probe failed: {e}")
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "practicare-backend",
        "version": "2.0.0",
        "database_connected": db_ok,
        "timestamp": datetime.utcnow().isoformat(),
        "port": 8000,
    }

# -----------------------------------------------------------------------------
# 1. Dashboard Analytics
# -----------------------------------------------------------------------------
@app.get("/api/v1/dashboard/summary", response_model=schemas.DashboardSummary, tags=["Dashboard"])
def get_dashboard_summary(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    practice = ensure_tenant_practice(db, context.tenant_id)
    tenant_id = context.tenant_id

    # Staff metrics
    staff = db.query(models.Staff).filter(models.Staff.tenant_id == tenant_id).all()
    total_staff = len(staff)
    active_staff_count = sum(1 for s in staff if s.is_active)
    on_shift_count = sum(1 for s in staff if s.is_active and s.on_shift)

    # Room metrics
    rooms = db.query(models.Room).filter(models.Room.tenant_id == tenant_id).all()
    room_occupancy = {"Available": 0, "Occupied": 0, "Turnover": 0}
    for r in rooms:
        stat = r.status.capitalize() if r.status else "Available"
        room_occupancy[stat] = room_occupancy.get(stat, 0) + 1

    # Task metrics: same visibility policy as the Tasks page, REST and AI (role-specific counts may differ)
    tasks = filter_visible_tasks(
        context.user_role, context.user_id,
        db.query(models.Task).filter(models.Task.tenant_id == tenant_id).all(), db,
    )
    tasks_total = len(tasks)
    tasks_completed = sum(1 for t in tasks if t.status.lower() == "completed")
    tasks_pending = sum(1 for t in tasks if t.status.lower() in ("pending", "in progress"))

    # Checklist metrics
    checklists = db.query(models.Checklist).filter(models.Checklist.tenant_id == tenant_id).all()
    checklists_total = len(checklists)
    checklists_completed = sum(1 for c in checklists if c.is_completed)

    # Inventory metrics
    items = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == tenant_id).all()
    low_stock_count = sum(1 for i in items if i.current_stock <= i.min_threshold)

    # Expiring soon: within the next 30 days (same rule as the Inventory page)
    expiring_soon_count = sum(1 for i in items if inventory_service.expiry_info(i.expiry_date)["is_expiring_soon"])

    return schemas.DashboardSummary(
        tenant_id=tenant_id,
        practice_name=practice.name,
        total_staff=total_staff,
        active_staff_count=active_staff_count,
        total_rooms=len(rooms),
        room_occupancy=room_occupancy,
        tasks_total=tasks_total,
        tasks_completed=tasks_completed,
        tasks_pending=tasks_pending,
        checklists_total=checklists_total,
        checklists_completed=checklists_completed,
        low_stock_count=low_stock_count,
        expiring_soon_count=expiring_soon_count,
        on_shift_count=on_shift_count,
    )

# -----------------------------------------------------------------------------
# 1b. Practice & Location Management
# -----------------------------------------------------------------------------
@app.get("/api/v1/practice", response_model=schemas.PracticeRead, tags=["Practice"])
def get_practice(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    return ensure_tenant_practice(db, context.tenant_id)

@app.put("/api/v1/practice", response_model=schemas.PracticeRead, tags=["Practice"])
def update_practice(
    payload: schemas.PracticeUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    practice = ensure_tenant_practice(db, context.tenant_id)
    if payload.name is not None:
        practice.name = payload.name
    if payload.location is not None:
        practice.location = payload.location
    if payload.room_count is not None:
        practice.room_count = payload.room_count
    db.commit()
    db.refresh(practice)
    return practice

# -----------------------------------------------------------------------------
# 2. Tasks CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/tasks", response_model=List[schemas.TaskRead], tags=["Tasks"])
def list_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_staff_id: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Task).filter(models.Task.tenant_id == context.tenant_id)
    if status:
        query = query.filter(models.Task.status.ilike(f"%{status}%"))
    if priority:
        query = query.filter(models.Task.priority.ilike(f"%{priority}%"))
    if assigned_staff_id:
        query = query.filter(models.Task.assigned_staff_id == assigned_staff_id)

    tasks = filter_visible_tasks(
        context.user_role, context.user_id, query.order_by(models.Task.due_date.asc()).all(), db
    )

    # Pre-fetch lookup maps
    staff_map = {s.id: s.name for s in db.query(models.Staff).filter(models.Staff.tenant_id == context.tenant_id).all()}
    room_map = {r.id: r.name for r in db.query(models.Room).filter(models.Room.tenant_id == context.tenant_id).all()}

    res = []
    for t in tasks:
        item = schemas.TaskRead.from_orm(t)
        apply_task_flags(item, t, context, db)
        item.assigned_staff_name = staff_map.get(t.assigned_staff_id) if t.assigned_staff_id else "Unassigned"
        item.room_name = room_map.get(t.room_id) if t.room_id else "General"
        res.append(item)
    return res

# Declared before /api/v1/tasks/{task_id} so the static path is not captured as a task id.
@app.get("/api/v1/tasks/conflicts", response_model=schemas.OperationalConflictReport, tags=["Tasks"])
def get_operational_conflicts(
    conflict_type: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    from ai.handlers.conflicts import calculate_operational_conflicts
    return calculate_operational_conflicts(db, context.tenant_id, conflict_type, context.user_role, context.user_id)

@app.get("/api/v1/tasks/{task_id}", response_model=schemas.TaskRead, tags=["Tasks"])
def get_task(
    task_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.tenant_id == context.tenant_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if not can_user_view_task(context.user_role, context.user_id, task, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: you are not authorized to view this task.")

    staff = db.query(models.Staff).filter(models.Staff.id == task.assigned_staff_id, models.Staff.tenant_id == context.tenant_id).first() if task.assigned_staff_id else None
    room = db.query(models.Room).filter(models.Room.id == task.room_id, models.Room.tenant_id == context.tenant_id).first() if task.room_id else None
    res = schemas.TaskRead.from_orm(task)
    apply_task_flags(res, task, context, db)
    res.assigned_staff_name = staff.name if staff else "Unassigned"
    res.room_name = room.name if room else "General"
    return res

@app.post("/api/v1/tasks", response_model=schemas.TaskRead, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
def create_task(
    payload: schemas.TaskCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    allowed, reason = can_user_create_task(context.user_role, payload.assigned_staff_id, db, context.tenant_id, context.user_id)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    practice = ensure_tenant_practice(db, context.tenant_id)
    if payload.room_id:
        rm_check = db.query(models.Room).filter(
            models.Room.id == payload.room_id,
            models.Room.tenant_id == context.tenant_id,
        ).first()
        if not rm_check:
            raise HTTPException(status_code=404, detail="Room not found in this practice.")
    if payload.assigned_staff_id:
        stf_check = db.query(models.Staff).filter(
            models.Staff.id == payload.assigned_staff_id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()
        if not stf_check:
            raise HTTPException(status_code=404, detail="Assigned staff not found")
        if not stf_check.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot assign task to inactive staff member '{stf_check.name}'.",
            )
    new_task = models.Task(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        status=payload.status,
        due_date=payload.due_date,
        assigned_staff_id=payload.assigned_staff_id,
        room_id=payload.room_id,
        created_by_user_id=context.user_id,
        created_by_role=context.user_role,
        practice_id=practice.id,
        tenant_id=context.tenant_id,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    staff = db.query(models.Staff).filter(models.Staff.id == new_task.assigned_staff_id, models.Staff.tenant_id == context.tenant_id).first() if new_task.assigned_staff_id else None
    room = db.query(models.Room).filter(models.Room.id == new_task.room_id, models.Room.tenant_id == context.tenant_id).first() if new_task.room_id else None

    res = schemas.TaskRead.from_orm(new_task)
    apply_task_flags(res, new_task, context, db)
    res.assigned_staff_name = staff.name if staff else "Unassigned"
    res.room_name = room.name if room else "General"
    return res

@app.put("/api/v1/tasks/{task_id}", response_model=schemas.TaskRead, tags=["Tasks"])
def update_task(
    task_id: str,
    payload: schemas.TaskUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.tenant_id == context.tenant_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = payload.dict(exclude_unset=True)
    allowed, reason = can_user_update_task(context.user_role, context.user_id, task, update_data, db)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    if payload.room_id:
        room_check = db.query(models.Room).filter(
            models.Room.id == payload.room_id,
            models.Room.tenant_id == context.tenant_id,
        ).first()
        if not room_check:
            raise HTTPException(status_code=404, detail="Room not found in this practice.")
    if payload.assigned_staff_id and payload.assigned_staff_id != task.assigned_staff_id:
        stf_check = db.query(models.Staff).filter(
            models.Staff.id == payload.assigned_staff_id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()
        if not stf_check:
            raise HTTPException(status_code=404, detail="Assigned staff not found")
        if not stf_check.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot assign task to inactive staff member '{stf_check.name}'.",
            )

    for field, val in update_data.items():
        if field in ("room_id", "assigned_staff_id") and val == "":
            val = None
        setattr(task, field, val)

    db.commit()
    db.refresh(task)

    staff = db.query(models.Staff).filter(models.Staff.id == task.assigned_staff_id, models.Staff.tenant_id == context.tenant_id).first() if task.assigned_staff_id else None
    room = db.query(models.Room).filter(models.Room.id == task.room_id, models.Room.tenant_id == context.tenant_id).first() if task.room_id else None

    res = schemas.TaskRead.from_orm(task)
    apply_task_flags(res, task, context, db)
    res.assigned_staff_name = staff.name if staff else "Unassigned"
    res.room_name = room.name if room else "General"
    return res

@app.delete("/api/v1/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Tasks"])
def delete_task(
    task_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.tenant_id == context.tenant_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    allowed, reason = can_user_delete_task(context.user_role, context.user_id, task, db)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    db.delete(task)
    db.commit()

# -----------------------------------------------------------------------------
# 3. Checklists CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/checklists", response_model=List[schemas.ChecklistRead], tags=["Checklists"])
def list_checklists(
    category: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Checklist).filter(models.Checklist.tenant_id == context.tenant_id)
    if category:
        query = query.filter(models.Checklist.category.ilike(f"%{category}%"))
    checklists = query.all()

    staff_map = {s.id: s.name for s in db.query(models.Staff).filter(models.Staff.tenant_id == context.tenant_id).all()}

    res = []
    for c in checklists:
        item = schemas.ChecklistRead.from_orm(c)
        apply_checklist_flags(item, c, context, db)
        item.assigned_staff_name = staff_map.get(c.assigned_staff_id) if c.assigned_staff_id else "Unassigned"
        res.append(item)
    return res

@app.get("/api/v1/checklists/{chk_id}", response_model=schemas.ChecklistRead, tags=["Checklists"])
def get_checklist(
    chk_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    chk = db.query(models.Checklist).filter(models.Checklist.id == chk_id, models.Checklist.tenant_id == context.tenant_id).first()
    if not chk:
        raise HTTPException(status_code=404, detail="Checklist not found")

    staff = db.query(models.Staff).filter(models.Staff.id == chk.assigned_staff_id, models.Staff.tenant_id == context.tenant_id).first() if chk.assigned_staff_id else None
    res = schemas.ChecklistRead.from_orm(chk)
    apply_checklist_flags(res, chk, context, db)
    res.assigned_staff_name = staff.name if staff else "Unassigned"
    return res

@app.post("/api/v1/checklists", response_model=schemas.ChecklistRead, status_code=status.HTTP_201_CREATED, tags=["Checklists"])
def create_checklist(
    payload: schemas.ChecklistCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    allowed, reason = can_user_create_checklist(context.user_role)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    practice = ensure_tenant_practice(db, context.tenant_id)
    if payload.assigned_staff_id:
        stf_check = db.query(models.Staff).filter(
            models.Staff.id == payload.assigned_staff_id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()
        if not stf_check:
            raise HTTPException(status_code=404, detail="Assigned staff not found")
        if not stf_check.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot assign checklist to inactive staff member '{stf_check.name}'.",
            )
    new_chk = models.Checklist(
        title=payload.title,
        category=payload.category,
        is_completed=payload.is_completed,
        frequency=payload.frequency,
        assigned_staff_id=payload.assigned_staff_id,
        created_by_user_id=context.user_id,
        created_by_role=context.user_role,
        practice_id=practice.id,
        tenant_id=context.tenant_id,
    )
    db.add(new_chk)
    db.commit()
    db.refresh(new_chk)

    staff = db.query(models.Staff).filter(models.Staff.id == new_chk.assigned_staff_id, models.Staff.tenant_id == context.tenant_id).first() if new_chk.assigned_staff_id else None
    res = schemas.ChecklistRead.from_orm(new_chk)
    apply_checklist_flags(res, new_chk, context, db)
    res.assigned_staff_name = staff.name if staff else "Unassigned"
    return res

@app.put("/api/v1/checklists/{chk_id}", response_model=schemas.ChecklistRead, tags=["Checklists"])
def update_checklist(
    chk_id: str,
    payload: schemas.ChecklistUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    chk = db.query(models.Checklist).filter(models.Checklist.id == chk_id, models.Checklist.tenant_id == context.tenant_id).first()
    if not chk:
        raise HTTPException(status_code=404, detail="Checklist not found")

    update_data = payload.dict(exclude_unset=True)
    allowed, reason = can_user_update_checklist(context.user_role, context.user_id, chk, update_data, db)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    if payload.assigned_staff_id and payload.assigned_staff_id != chk.assigned_staff_id:
        stf_check = db.query(models.Staff).filter(
            models.Staff.id == payload.assigned_staff_id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()
        if not stf_check:
            raise HTTPException(status_code=404, detail="Assigned staff not found")
        if not stf_check.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot assign checklist to inactive staff member '{stf_check.name}'.",
            )

    if "description" in update_data and update_data["description"] and not update_data.get("title"):
        chk.title = update_data["description"]
    if "status" in update_data and update_data["status"] is not None:
        if isinstance(update_data["status"], bool):
            chk.is_completed = update_data["status"]
        elif isinstance(update_data["status"], str):
            chk.is_completed = update_data["status"].lower() in ("completed", "done", "true", "1")

    for field in ("title", "category", "is_completed", "frequency", "assigned_staff_id"):
        if field in update_data:
            val = update_data[field]
            if field == "assigned_staff_id" and val == "":
                val = None
            setattr(chk, field, val)

    db.commit()
    db.refresh(chk)

    staff = db.query(models.Staff).filter(models.Staff.id == chk.assigned_staff_id, models.Staff.tenant_id == context.tenant_id).first() if chk.assigned_staff_id else None
    res = schemas.ChecklistRead.from_orm(chk)
    apply_checklist_flags(res, chk, context, db)
    res.assigned_staff_name = staff.name if staff else "Unassigned"
    return res

@app.delete("/api/v1/checklists/{chk_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Checklists"])
def delete_checklist(
    chk_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    chk = db.query(models.Checklist).filter(models.Checklist.id == chk_id, models.Checklist.tenant_id == context.tenant_id).first()
    if not chk:
        raise HTTPException(status_code=404, detail="Checklist not found")

    allowed, reason = can_user_delete_checklist(context.user_role, context.user_id, chk, db)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    db.delete(chk)
    db.commit()

# -----------------------------------------------------------------------------
# 4. Inventory CRUD
# -----------------------------------------------------------------------------
def serialize_inventory(item: models.InventoryItem, room_name: Optional[str], today: Optional[date] = None,
                        context: Optional[schemas.RequestContext] = None) -> schemas.InventoryRead:
    """InventoryRead with server-computed stock and expiry facts (inventory_service is the single status authority)."""
    res = schemas.InventoryRead.model_validate(item)
    res.room_name = room_name or "Central Supply"
    res.is_low_stock = item.current_stock <= item.min_threshold
    info = inventory_service.expiry_info(item.expiry_date, today)
    res.is_expired = info["is_expired"]
    res.days_to_expiry = info["days_to_expiry"]
    res.expiry_status = info["expiry_status"]
    res.is_expiring_soon = info["is_expiring_soon"]
    res.stock_status = inventory_service.stock_status(item.current_stock, item.min_threshold)
    res.expiry_state = inventory_service.expiry_state(item.expiry_date, today)
    res.shortfall = max((item.min_threshold or 0) - (item.current_stock or 0), 0)
    res.can_manage = bool(context and can_user_manage_inventory(context.user_role))
    return res

def audit_inventory_write(db: Session, context: schemas.RequestContext, action: str, args: Dict, status_value: str,
                          detail: Optional[str] = None) -> None:
    """Audit trail for manual (REST) inventory writes, in the same table as AI tool calls. Call after commit/rollback."""
    try:
        gateway._record_audit(db=db, log_id=f"aud-{uuid.uuid4().hex[:8]}", context=context, tool_name=f"rest:{action}",
                              input_args=args, status=status_value, error_detail=detail)
    except Exception as exc:  # auditing must never turn a completed write into a reported failure
        db.rollback()
        logger.error("Inventory audit write failed: %s", exc)

def require_inventory_manager(context: schemas.RequestContext, action: str, db: Optional[Session] = None,
                              args: Optional[Dict] = None) -> None:
    if not can_user_manage_inventory(context.user_role):
        if db is not None:
            audit_inventory_write(db, context, f"inventory.{action}", args or {}, "BLOCKED",
                                  f"Role {context.user_role} is not permitted to {action} inventory.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Only Owner and Manager can {action} inventory.")

def validate_inventory_room(db: Session, tenant_id: str, room_id: Optional[str]) -> None:
    if room_id:
        rm_check = db.query(models.Room).filter(
            models.Room.id == room_id,
            models.Room.tenant_id == tenant_id,
        ).first()
        if not rm_check:
            raise HTTPException(status_code=404, detail="Room not found in this practice.")

@app.get("/api/v1/inventory", response_model=List[schemas.InventoryRead], tags=["Inventory"])
def list_inventory(
    low_stock_only: Optional[bool] = False,
    expiry: Optional[str] = None,
    sort: Optional[str] = None,
    search: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    """
    expiry: all | expired | within_7 | within_30 | within_90 | none (windows are cumulative, relative to today)
    sort:   stock (default, lowest first) | expiry (nearest expiry first, no-expiry last) | name
    search: case-insensitive match on item name, supplier or batch number
    """
    needle = inventory_service.name_key(search)
    try:
        expiry_filter = inventory_service.normalize_expiry_filter(expiry)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    sort_key = (sort or "stock").strip().lower()
    if sort_key not in ("stock", "expiry", "name"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="sort must be one of: stock, expiry, name.")

    query = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == context.tenant_id)
    items = query.order_by(models.InventoryItem.current_stock.asc()).all()
    if sort_key == "expiry":
        items.sort(key=inventory_service.expiry_sort_key)
    elif sort_key == "name":
        items.sort(key=lambda i: (i.item_name or "").lower())

    room_map = {r.id: r.name for r in db.query(models.Room).filter(models.Room.tenant_id == context.tenant_id).all()}
    today = date.today()

    res = []
    for i in items:
        if low_stock_only and not i.current_stock <= i.min_threshold:
            continue
        if not inventory_service.matches_expiry_filter(i.expiry_date, expiry_filter, today):
            continue
        if needle and not any(needle in inventory_service.name_key(v) for v in (i.item_name, i.supplier, i.batch_number)):
            continue
        res.append(serialize_inventory(i, room_map.get(i.room_id) if i.room_id else None, today, context))
    return res

@app.post("/api/v1/inventory/import/extract", tags=["Inventory"])
def extract_inventory_import(
    payload: schemas.InventoryImportExtractRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    """
    AI extraction for the import workflow. Reads a PDF, image or text with Gemini and returns an editable
    preview with per-field confidence, issues and duplicate matches. Nothing is written to the database.
    """
    require_inventory_manager(context, "import", db, {"source_type": payload.source_type})
    try:
        source = inventory_service.prepare_source(
            payload.source_type, content_base64=payload.content_base64, mime_type=payload.mime_type, text=payload.text,
        )
    except inventory_service.ExtractionInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    try:
        extracted = inventory_service.extract_inventory_records(source)
    except inventory_service.ExtractionUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    return {
        "import_token": inventory_service.new_import_token(),
        "source_hash": source["source_hash"],
        "source_type": source["source_type"],
        "filename": payload.filename,
        "model": extracted["model"],
        "notes": extracted["notes"],
        "truncated": extracted["truncated"],
        "previous_imports": inventory_service.prior_imports(db, context.tenant_id, source["source_hash"]),
        "rows": inventory_service.build_preview(db, context.tenant_id, extracted["items"]),
    }

@app.post("/api/v1/inventory/import/confirm", tags=["Inventory"])
def confirm_inventory_import(
    payload: schemas.InventoryImportConfirmRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    """
    Saves the rows the user reviewed and confirmed. Every row is re-validated; the import runs in one
    transaction and the single-use import_token prevents the same import from being applied twice.
    """
    require_inventory_manager(context, "import", db, {"source_type": payload.source_type, "rows": len(payload.rows)})
    practice = ensure_tenant_practice(db, context.tenant_id)
    try:
        result = inventory_service.apply_import(
            db,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            practice_id=practice.id,
            import_token=payload.import_token,
            source_hash=payload.source_hash,
            source_type=payload.source_type,
            rows=[r.model_dump() for r in payload.rows],
        )
        audit_inventory_write(db, context, "inventory.import", {"source_type": payload.source_type, **result["counts"]},
                              "ALLOWED" if result["status"] == "IMPORTED" else "ERROR",
                              None if result["status"] == "IMPORTED" else "Nothing imported: all rows skipped or rejected.")
        return result
    except inventory_service.ImportAlreadyProcessedError as exc:
        audit_inventory_write(db, context, "inventory.import", {"source_type": payload.source_type}, "BLOCKED",
                              "Import token already used; nothing imported again.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "This import was already confirmed; nothing was imported again.", "previous_result": exc.result},
        )

@app.get("/api/v1/inventory/{item_id}", response_model=schemas.InventoryRead, tags=["Inventory"])
def get_inventory_item(
    item_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id, models.InventoryItem.tenant_id == context.tenant_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    room = db.query(models.Room).filter(models.Room.id == item.room_id, models.Room.tenant_id == context.tenant_id).first() if item.room_id else None
    return serialize_inventory(item, room.name if room else None, context=context)

@app.post("/api/v1/inventory", response_model=schemas.InventoryRead, status_code=status.HTTP_201_CREATED, tags=["Inventory"])
def create_inventory_item(
    payload: schemas.InventoryCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_inventory_manager(context, "add", db, {"item_name": payload.item_name})

    practice = ensure_tenant_practice(db, context.tenant_id)
    validate_inventory_room(db, context.tenant_id, payload.room_id)
    new_item = models.InventoryItem(
        item_name=payload.item_name,
        current_stock=payload.current_stock,
        min_threshold=payload.min_threshold,
        unit=payload.unit,
        expiry_date=payload.expiry_date,
        supplier=payload.supplier,
        batch_number=payload.batch_number,
        purchase_price=payload.purchase_price,
        room_id=payload.room_id,
        practice_id=practice.id,
        tenant_id=context.tenant_id,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    audit_inventory_write(db, context, "inventory.create", {"item_id": new_item.id, **payload.model_dump(exclude_none=True)}, "ALLOWED")

    room = db.query(models.Room).filter(models.Room.id == new_item.room_id, models.Room.tenant_id == context.tenant_id).first() if new_item.room_id else None
    return serialize_inventory(new_item, room.name if room else None, context=context)

@app.put("/api/v1/inventory/{item_id}", response_model=schemas.InventoryRead, tags=["Inventory"])
def update_inventory_item(
    item_id: str,
    payload: schemas.InventoryUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    update_data = payload.model_dump(exclude_unset=True)
    require_inventory_manager(context, "update", db, {"item_id": item_id, **update_data})

    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id, models.InventoryItem.tenant_id == context.tenant_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    expected_stock = update_data.pop("expected_current_stock", None)
    validate_inventory_room(db, context.tenant_id, payload.room_id)
    changes = {}
    for field, val in update_data.items():
        if field in ("item_name", "current_stock", "min_threshold", "unit") and val is None:
            continue  # required columns are never nulled by a partial update
        if field == "room_id" and val == "":
            val = None
        if str(getattr(item, field)) != str(val):
            changes[field] = val

    table = models.InventoryItem.__table__
    cond = [table.c.id == item.id, table.c.tenant_id == context.tenant_id]
    if "current_stock" in changes and expected_stock is not None:
        cond.append(table.c.current_stock == expected_stock)  # never silently overwrite a concurrent stock change
    if changes:
        if db.execute(table.update().where(*cond).values(**changes)).rowcount != 1:
            db.rollback()
            current = db.query(models.InventoryItem).filter(models.InventoryItem.id == item.id).first()
            audit_inventory_write(db, context, "inventory.update", {"item_id": item.id, **update_data}, "BLOCKED",
                                  "Stock changed since the form was opened.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Stock of '{current.item_name}' changed to {current.current_stock} {current.unit} since you opened it. "
                       f"Nothing was saved; reload and try again.",
            )
        db.commit()
        audit_inventory_write(db, context, "inventory.update", {"item_id": item.id, **{k: str(v) for k, v in changes.items()}}, "ALLOWED")
    db.expire_all()
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id, models.InventoryItem.tenant_id == context.tenant_id).first()

    room = db.query(models.Room).filter(models.Room.id == item.room_id, models.Room.tenant_id == context.tenant_id).first() if item.room_id else None
    return serialize_inventory(item, room.name if room else None, context=context)

@app.post("/api/v1/inventory/{item_id}/adjust", response_model=schemas.InventoryRead, tags=["Inventory"])
def adjust_inventory_stock(
    item_id: str,
    payload: schemas.InventoryAdjustRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    """
    Restock (positive quantity_change) or controlled reduction (negative). Applied atomically; stock never goes
    below zero. With expected_current_stock, the change applies only if the stock is still the value the user saw.
    """
    args = {"item_id": item_id, **payload.model_dump(exclude_none=True)}
    require_inventory_manager(context, "adjust", db, args)
    try:
        previous, new_stock = inventory_service.adjust_stock(
            db, context.tenant_id, item_id, payload.quantity_change, expected_current_stock=payload.expected_current_stock)
    except inventory_service.ItemNotFoundError:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    except inventory_service.StockConflictError as exc:
        audit_inventory_write(db, context, "inventory.adjust", args, "BLOCKED", str(exc))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    audit_inventory_write(db, context, "inventory.adjust", {**args, "previous_stock": previous, "new_stock": new_stock}, "ALLOWED")
    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id, models.InventoryItem.tenant_id == context.tenant_id).first()
    room = db.query(models.Room).filter(models.Room.id == item.room_id, models.Room.tenant_id == context.tenant_id).first() if item.room_id else None
    return serialize_inventory(item, room.name if room else None, context=context)

@app.delete("/api/v1/inventory/{item_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Inventory"])
def delete_inventory_item(
    item_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_inventory_manager(context, "delete", db, {"item_id": item_id})

    item = db.query(models.InventoryItem).filter(models.InventoryItem.id == item_id, models.InventoryItem.tenant_id == context.tenant_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")
    snapshot = {"item_id": item.id, "item_name": item.item_name, "current_stock": item.current_stock}
    db.delete(item)
    db.commit()
    audit_inventory_write(db, context, "inventory.delete", snapshot, "ALLOWED")

# -----------------------------------------------------------------------------
# 5. Rooms CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/rooms", response_model=List[schemas.RoomRead], tags=["Rooms"])
def list_rooms(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    rooms = db.query(models.Room).filter(models.Room.tenant_id == context.tenant_id).order_by(models.Room.room_number.asc()).all()
    return rooms

@app.get("/api/v1/rooms/{room_id}", response_model=schemas.RoomRead, tags=["Rooms"])
def get_room(
    room_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    room = db.query(models.Room).filter(models.Room.id == room_id, models.Room.tenant_id == context.tenant_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room

@app.post("/api/v1/rooms", response_model=schemas.RoomRead, status_code=status.HTTP_201_CREATED, tags=["Rooms"])
def create_room(
    payload: schemas.RoomCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    if not can_user_create_room(context.user_role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Owner and Manager can add rooms.")

    practice = ensure_tenant_practice(db, context.tenant_id)
    new_room = models.Room(
        room_number=payload.room_number,
        name=payload.name,
        room_type=payload.room_type,
        status=payload.status,
        practice_id=practice.id,
        tenant_id=context.tenant_id,
    )
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return new_room

@app.put("/api/v1/rooms/{room_id}", response_model=schemas.RoomRead, tags=["Rooms"])
def update_room(
    room_id: str,
    payload: schemas.RoomUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    update_data = payload.dict(exclude_unset=True)
    allowed, reason = can_user_update_room(context.user_role, update_data)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    room = db.query(models.Room).filter(models.Room.id == room_id, models.Room.tenant_id == context.tenant_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    for field, val in update_data.items():
        setattr(room, field, val)

    db.commit()
    db.refresh(room)
    return room

@app.delete("/api/v1/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Rooms"])
def delete_room(
    room_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    if not can_user_delete_room(context.user_role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Clinic Owner can delete rooms.")

    room = db.query(models.Room).filter(models.Room.id == room_id, models.Room.tenant_id == context.tenant_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    db.delete(room)
    db.commit()

# -----------------------------------------------------------------------------
# 6. Staff List & Profiles
# -----------------------------------------------------------------------------
def serialize_staff(s: models.Staff, db: Session = None) -> schemas.StaffRead:
    user_email = s.user.email if s.user else None
    mem_status = s.user.membership_status if s.user else "APPROVED"
    prac_name = s.practice.name if s.practice else None
    dept = s.department if s.department else (s.role if s.role else "General Practice")
    w_status = s.work_status or "ACTIVE"
    last_login = s.last_login_at or (s.user.last_login_at if s.user else None)
    return schemas.StaffRead(
        id=s.id,
        name=s.name,
        role=s.role,
        is_active=s.is_active,
        on_shift=s.on_shift,
        practice_id=s.practice_id,
        tenant_id=s.tenant_id,
        user_id=s.user_id,
        email=user_email,
        department=dept,
        work_status=w_status,
        last_login_at=last_login,
        practice_name=prac_name,
        membership_status=mem_status,
        created_at=s.created_at,
    )

@app.get("/api/v1/staff", response_model=List[schemas.StaffRead], tags=["Staff"])
def list_staff(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    staff_list = db.query(models.Staff).filter(models.Staff.tenant_id == context.tenant_id).order_by(models.Staff.name.asc()).all()
    return [serialize_staff(s, db) for s in staff_list]

@app.get("/api/v1/staff/me", response_model=schemas.StaffRead, tags=["Staff"])
def get_my_staff_profile(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    staff = get_or_create_own_staff(db, context.tenant_id, context.user_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff profile not found for authenticated user.")
    return serialize_staff(staff, db)

@app.get("/api/v1/staff/{staff_id}", response_model=schemas.StaffRead, tags=["Staff"])
def get_staff_detail(
    staff_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    if staff_id == "me":
        return get_my_staff_profile(context=context, db=db)
    staff = db.query(models.Staff).filter(
        models.Staff.id == staff_id,
        models.Staff.tenant_id == context.tenant_id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return serialize_staff(staff, db)

@app.put("/api/v1/staff/{staff_id}/status", response_model=schemas.StaffRead, tags=["Staff"])
def update_staff_account_status(
    staff_id: str,
    payload: schemas.StaffStatusUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    staff = db.query(models.Staff).filter(
        models.Staff.id == staff_id,
        models.Staff.tenant_id == context.tenant_id,
    ).first()
    if not staff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    # Avoid locking out the last active Clinic Owner
    if not payload.is_active:
        is_owner = False
        if staff.role and ("OWNER" in staff.role.upper()):
            is_owner = True
        linked_user = get_linked_user(db, context.tenant_id, staff)
        if linked_user and linked_user.role and ("OWNER" in linked_user.role.upper()):
            is_owner = True
        if staff.id == context.user_id or (staff.user_id and staff.user_id == context.user_id):
            if context.user_role == "CLINIC_OWNER":
                is_owner = True

        if is_owner:
            active_owners = db.query(models.User).filter(
                models.User.tenant_id == context.tenant_id,
                models.User.role == "CLINIC_OWNER",
                models.User.is_active == True,
            ).count()
            is_self_owner = (staff.user_id and staff.user_id == context.user_id) or (linked_user and linked_user.id == context.user_id)
            if active_owners <= 1 or is_self_owner:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot deactivate the Clinic Owner account (protected from self-deactivation and last active owner lockout).",
                )

    old_status = staff.is_active
    # Shift status is preserved (Requirement 9: Do not automatically change On Shift / Off Duty)
    staff.is_active = payload.is_active

    # Sync the linked user account (explicit Staff.user_id link only)
    linked_user = get_linked_user(db, context.tenant_id, staff)
    if linked_user:
        linked_user.is_active = payload.is_active

    db.commit()
    db.refresh(staff)

    gateway.record_audit_event(
        db=db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        user_role=context.user_role,
        action="STAFF_ACCOUNT_STATUS_CHANGE",
        details={
            "staff_id": staff.id,
            "staff_name": staff.name,
            "previous_status": "Active" if old_status else "Inactive",
            "new_status": "Active" if payload.is_active else "Inactive",
            "linked_user_id": linked_user.id if linked_user else None,
        },
    )
    return serialize_staff(staff, db)

@app.post("/api/v1/staff/me/shift", response_model=schemas.StaffRead, tags=["Staff"])
def set_my_shift_status(
    payload: schemas.StaffShiftUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    return update_staff_shift_status(
        staff_id="me",
        payload=payload,
        context=context,
        db=db,
    )

@app.put("/api/v1/staff/{staff_id}/shift", response_model=schemas.StaffRead, tags=["Staff"])
def update_staff_shift_status(
    staff_id: str,
    payload: schemas.StaffShiftUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER", "ATTENDING_PHYSICIAN", "NURSE_STAFF", "INVENTORY_MANAGER"])
    if staff_id == "me":
        staff = get_or_create_own_staff(db, context.tenant_id, context.user_id)
    else:
        staff = db.query(models.Staff).filter(
            models.Staff.id == staff_id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()

    if not staff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")

    is_self = bool(staff.user_id) and staff.user_id == context.user_id

    is_owner_override = False
    if not is_self:
        if context.user_role == "CLINIC_OWNER":
            is_owner_override = True
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff members can only manage their own shift status. Contact Clinic Owner for assistance.",
            )

    # Inactive or pending users cannot start a shift
    if payload.on_shift:
        if not staff.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot start shift: Staff account for '{staff.name}' is inactive.",
            )
        if staff.user_id:
            u = db.query(models.User).filter(
                models.User.id == staff.user_id, models.User.tenant_id == context.tenant_id,
            ).first()
            if u and (not u.is_active or getattr(u, "membership_status", "APPROVED") != "APPROVED"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot start shift: User account is pending approval or inactive.",
                )

    old_shift = staff.on_shift
    staff.on_shift = payload.on_shift
    db.commit()
    db.refresh(staff)

    gateway.record_audit_event(
        db=db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        user_role=context.user_role,
        action="STAFF_SHIFT_STATUS_CHANGE",
        details={
            "staff_id": staff.id,
            "staff_name": staff.name,
            "previous_shift": "On Shift" if old_shift else "Off Duty",
            "new_shift": "On Shift" if payload.on_shift else "Off Duty",
            "is_administrative_override": is_owner_override,
            "performed_by_user_id": context.user_id,
        },
    )
    return serialize_staff(staff, db)

# -----------------------------------------------------------------------------
# 6b. Staff Work Status, Leaves & Operational Conflict Endpoints
# -----------------------------------------------------------------------------
@app.put("/api/v1/staff/{staff_id}/work-status", response_model=schemas.StaffRead, tags=["Staff"])
def update_staff_work_status(
    staff_id: str,
    payload: schemas.StaffWorkStatusUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    clean_status = payload.work_status.strip().upper()
    valid_statuses = {"ACTIVE", "ON_LEAVE", "HOLIDAY", "SICK_LEAVE", "DND"}
    if clean_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid work status '{payload.work_status}'. Allowed: {', '.join(sorted(valid_statuses))}",
        )
    if staff_id == "me":
        staff = db.query(models.Staff).filter(
            models.Staff.tenant_id == context.tenant_id,
            models.Staff.user_id == context.user_id,
        ).first()
    else:
        staff = db.query(models.Staff).filter(
            models.Staff.id == staff_id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    authorize_staff_availability(context, staff, db)

    staff.work_status = clean_status
    if clean_status in ("HOLIDAY", "SICK_LEAVE", "DND", "ON_LEAVE"):
        staff.on_shift = False

    db.commit()
    db.refresh(staff)
    return serialize_staff(staff, db)

@app.get("/api/v1/staff/{staff_id}/leaves", response_model=List[schemas.StaffLeaveRead], tags=["Staff Leaves"])
def list_staff_leaves(
    staff_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    if staff_id == "me":
        staff = db.query(models.Staff).filter(
            models.Staff.tenant_id == context.tenant_id,
            models.Staff.user_id == context.user_id,
        ).first()
        if not staff:
            return []
        resolved_staff_id = staff.id
    else:
        resolved_staff_id = staff_id

    leaves = db.query(models.StaffLeave).filter(
        models.StaffLeave.tenant_id == context.tenant_id,
        models.StaffLeave.staff_id == resolved_staff_id,
    ).order_by(models.StaffLeave.start_date.desc()).all()

    staff_obj = db.query(models.Staff).filter(
        models.Staff.id == resolved_staff_id,
        models.Staff.tenant_id == context.tenant_id,
    ).first()
    staff_name = staff_obj.name if staff_obj else None

    res = []
    for lev in leaves:
        item = schemas.StaffLeaveRead.from_orm(lev)
        item.staff_name = staff_name
        res.append(item)
    return res

@app.post("/api/v1/staff/{staff_id}/leaves", response_model=schemas.StaffLeaveRead, status_code=status.HTTP_201_CREATED, tags=["Staff Leaves"])
def create_staff_leave(
    staff_id: str,
    payload: schemas.StaffLeaveCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    if staff_id == "me":
        staff = db.query(models.Staff).filter(
            models.Staff.tenant_id == context.tenant_id,
            models.Staff.user_id == context.user_id,
        ).first()
    else:
        staff = db.query(models.Staff).filter(
            models.Staff.id == staff_id,
            models.Staff.tenant_id == context.tenant_id,
        ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    authorize_staff_availability(context, staff, db)

    clean_type = payload.leave_type.strip().upper()
    new_leave = models.StaffLeave(
        staff_id=staff.id,
        tenant_id=context.tenant_id,
        leave_type=clean_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=resolve_new_leave_status(context.user_role, context.user_id, staff, payload.status),
        notes=payload.notes,
    )
    apply_approved_leave(staff, new_leave)

    db.add(new_leave)
    db.commit()
    db.refresh(new_leave)

    res = schemas.StaffLeaveRead.from_orm(new_leave)
    res.staff_name = staff.name
    return res

def apply_approved_leave(staff: models.Staff, leave: models.StaffLeave) -> None:
    """An APPROVED leave covering the current time takes the staff member off shift."""
    if leave.status != "APPROVED":
        return
    if leave.start_date <= datetime.utcnow() <= leave.end_date:
        staff.work_status = leave.leave_type if leave.leave_type in ("HOLIDAY", "SICK_LEAVE", "DND") else "ON_LEAVE"
        staff.on_shift = False

@app.put("/api/v1/staff/{staff_id}/leaves/{leave_id}/status", response_model=schemas.StaffLeaveRead, tags=["Staff Leaves"])
def review_staff_leave(
    staff_id: str,
    leave_id: str,
    payload: schemas.StaffLeaveStatusUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    new_status = payload.status.strip().upper()
    if new_status not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status must be APPROVED or REJECTED.")
    leave = db.query(models.StaffLeave).filter(
        models.StaffLeave.id == leave_id,
        models.StaffLeave.staff_id == staff_id,
        models.StaffLeave.tenant_id == context.tenant_id,
    ).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave record not found")
    staff = db.query(models.Staff).filter(
        models.Staff.id == leave.staff_id,
        models.Staff.tenant_id == context.tenant_id,
    ).first()
    allowed, reason = can_user_approve_leave(context.user_role, context.user_id, staff)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    leave.status = new_status
    if staff:
        apply_approved_leave(staff, leave)
    db.commit()
    db.refresh(leave)

    gateway.record_audit_event(
        db=db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        user_role=context.user_role,
        action="STAFF_LEAVE_REVIEW",
        details={"leave_id": leave.id, "staff_id": leave.staff_id, "new_status": new_status},
    )
    res = schemas.StaffLeaveRead.from_orm(leave)
    res.staff_name = staff.name if staff else None
    return res

@app.delete("/api/v1/staff/{staff_id}/leaves/{leave_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Staff Leaves"])
def delete_staff_leave(
    staff_id: str,
    leave_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    leave = db.query(models.StaffLeave).filter(
        models.StaffLeave.id == leave_id,
        models.StaffLeave.tenant_id == context.tenant_id,
    ).first()
    if not leave:
        raise HTTPException(status_code=404, detail="Leave record not found")
    staff = db.query(models.Staff).filter(
        models.Staff.id == leave.staff_id,
        models.Staff.tenant_id == context.tenant_id,
    ).first()
    if staff_id != "me" and staff_id != leave.staff_id:
        raise HTTPException(status_code=404, detail="Leave record not found")
    authorize_staff_availability(context, staff, db)
    db.delete(leave)
    db.commit()

@app.put("/api/v1/users/{user_id}/status", response_model=schemas.UserResponse, tags=["Users"])
def update_user_account_status(
    user_id: str,
    payload: schemas.UserStatusUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    target_user = db.query(models.User).filter(
        models.User.id == user_id,
        models.User.tenant_id == context.tenant_id,
    ).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User account not found")

    if not payload.is_active and target_user.role == "CLINIC_OWNER":
        if target_user.id == context.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Administrators cannot deactivate their own account.",
            )
        active_owners = db.query(models.User).filter(
            models.User.tenant_id == context.tenant_id,
            models.User.role == "CLINIC_OWNER",
            models.User.is_active == True,
        ).count()
        if active_owners <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active Clinic Owner in this tenant.",
            )

    old_status = target_user.is_active
    target_user.is_active = payload.is_active

    # Sync staff record if linked
    linked_staff = get_linked_staff(db, context.tenant_id, target_user.id)
    if linked_staff:
        linked_staff.is_active = payload.is_active

    db.commit()
    db.refresh(target_user)

    gateway.record_audit_event(
        db=db,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        user_role=context.user_role,
        action="USER_ACCOUNT_STATUS_CHANGE",
        details={
            "target_user_id": target_user.id,
            "target_email": target_user.email,
            "previous_status": "Active" if old_status else "Inactive",
            "new_status": "Active" if payload.is_active else "Inactive",
        },
    )

    return schemas.UserResponse(
        id=target_user.id,
        name=target_user.full_name,
        email=target_user.email,
        role=target_user.role,
        is_active=target_user.is_active,
        tenant_id=target_user.tenant_id,
        company_name=target_user.company_name or target_user.tenant_id,
    )

# -----------------------------------------------------------------------------
# 7. AI Copilot Tool Endpoints (Connecting to Live Database)
# -----------------------------------------------------------------------------
@app.post(
    "/internal/tools/practicare.list_tasks",
    response_model=schemas.ListTasksResponse,
    tags=["Tools"],
    summary="List tasks due today or pending querying live DB",
)
def tool_list_tasks(
    payload: schemas.ListTasksRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    practice = ensure_tenant_practice(db, context.tenant_id)
    query = db.query(models.Task).filter(models.Task.tenant_id == context.tenant_id)

    if payload.practice_id:
        query = query.filter(models.Task.practice_id == payload.practice_id)
    if payload.status:
        query = query.filter(models.Task.status.ilike(f"%{payload.status}%"))
    if payload.assigned_to:
        query = query.filter(models.Task.assigned_staff_id == payload.assigned_to)

    today_str = date.today().isoformat()
    if payload.due_today_only:
        query = query.filter(models.Task.due_date.startswith(today_str))

    tasks = filter_visible_tasks(context.user_role, context.user_id, query.all(), db)
    staff_map = {s.id: s.name for s in db.query(models.Staff).filter(models.Staff.tenant_id == context.tenant_id).all()}

    items = [
        schemas.TaskResponseItem(
            id=t.id,
            practice_id=t.practice_id,
            practice_name=practice.name,
            title=t.title,
            due_date=t.due_date,
            status=t.status.lower(),
            assigned_to=t.assigned_staff_id or "unassigned",
            assigned_staff_name=staff_map.get(t.assigned_staff_id, "Unassigned"),
        )
        for t in tasks
    ]

    return schemas.ListTasksResponse(
        tenant_id=context.tenant_id,
        total_count=len(items),
        tasks=items,
    )

@app.post(
    "/internal/tools/practicare.get_low_stock",
    response_model=schemas.GetLowStockResponse,
    tags=["Tools"],
    summary="Retrieve inventory items whose stock is at or below threshold from live DB",
)
def tool_get_low_stock(
    payload: schemas.GetLowStockRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    practice = ensure_tenant_practice(db, context.tenant_id)
    multiplier = payload.threshold_multiplier or 1.0

    items = db.query(models.InventoryItem).filter(models.InventoryItem.tenant_id == context.tenant_id).all()
    low_stock = []
    for item in items:
        effective_threshold = int(item.min_threshold * multiplier)
        if item.current_stock <= effective_threshold:
            shortfall = max(0, item.min_threshold - item.current_stock)
            low_stock.append(
                schemas.LowStockItemResponse(
                    id=item.id,
                    practice_id=item.practice_id,
                    practice_name=practice.name,
                    item_name=item.item_name,
                    current_stock=item.current_stock,
                    min_threshold=item.min_threshold,
                    unit=item.unit,
                    shortfall=shortfall,
                    reorder_recommended=item.current_stock < item.min_threshold,
                )
            )

    return schemas.GetLowStockResponse(
        tenant_id=context.tenant_id,
        alert_count=len(low_stock),
        items=low_stock,
    )

@app.post(
    "/internal/tools/practicare.get_practice_summary",
    response_model=schemas.PracticeSummaryResponse,
    tags=["Tools"],
    summary="Return clinic operational overview from live DB",
)
def tool_get_practice_summary(
    payload: schemas.GetPracticeSummaryRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    practice = ensure_tenant_practice(db, context.tenant_id)
    staff_list = db.query(models.Staff).filter(models.Staff.tenant_id == context.tenant_id).all()
    rooms = db.query(models.Room).filter(models.Room.tenant_id == context.tenant_id).all()
    pending_tasks = db.query(models.Task).filter(
        models.Task.tenant_id == context.tenant_id,
        models.Task.status.ilike("%Pending%")
    ).all()
    low_stock = db.query(models.InventoryItem).filter(
        models.InventoryItem.tenant_id == context.tenant_id,
        models.InventoryItem.current_stock <= models.InventoryItem.min_threshold
    ).all()

    today_str = date.today().isoformat()
    today_due_tasks = db.query(models.Task).filter(
        models.Task.tenant_id == context.tenant_id,
        models.Task.due_date == today_str,
    ).count()

    return schemas.PracticeSummaryResponse(
        tenant_id=context.tenant_id,
        practice_id=practice.id,
        practice_name=practice.name,
        location=practice.location,
        total_rooms=len(rooms),
        active_staff_count=sum(1 for s in staff_list if s.is_active),
        today_appointments=today_due_tasks,
        pending_tasks_count=len(pending_tasks),
        low_stock_items_count=len(low_stock),
        staff_roster=[{"id": s.id, "name": s.name, "role": s.role} for s in staff_list],
    )

# -----------------------------------------------------------------------------
# AI Conversation Management & Isolation Endpoints
# -----------------------------------------------------------------------------
@app.get(
    "/api/v1/ai/conversations",
    response_model=List[schemas.AIConversationRead],
    tags=["AI Agent"],
    summary="List all private conversations for authenticated user and tenant",
)
def list_ai_conversations(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    convs = (
        db.query(models.AIConversation)
        .filter(
            models.AIConversation.tenant_id == context.tenant_id,
            models.AIConversation.user_id == context.user_id,
        )
        .order_by(models.AIConversation.updated_at.desc())
        .all()
    )
    return [
        schemas.AIConversationRead(
            id=c.id,
            tenant_id=c.tenant_id,
            user_id=c.user_id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in convs
    ]

@app.post(
    "/api/v1/ai/conversations",
    response_model=schemas.AIConversationRead,
    tags=["AI Agent"],
    summary="Create a new private AI conversation for authenticated user and tenant",
)
def create_ai_conversation(
    payload: schemas.AIConversationCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    ensure_user_record(db, context.user_id, context.tenant_id, context.user_role)
    title = payload.title.strip() if payload.title and payload.title.strip() else "New Clinical Consultation"
    conv = models.AIConversation(
        id=f"conv-{uuid.uuid4().hex[:12]}",
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        title=title,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return schemas.AIConversationRead(
        id=conv.id,
        tenant_id=conv.tenant_id,
        user_id=conv.user_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )

@app.get(
    "/api/v1/ai/conversations/{conversation_id}",
    response_model=schemas.AIConversationDetailRead,
    tags=["AI Agent"],
    summary="Get conversation detail and history strictly scoped to owner",
)
def get_ai_conversation(
    conversation_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    conv = (
        db.query(models.AIConversation)
        .filter(
            models.AIConversation.id == conversation_id,
            models.AIConversation.tenant_id == context.tenant_id,
            models.AIConversation.user_id == context.user_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )

    msgs = (
        db.query(models.AIMessage)
        .filter(models.AIMessage.conversation_id == conv.id)
        .order_by(models.AIMessage.created_at.asc())
        .all()
    )

    def _safe_parse_json(val):
        if not val:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val

    return schemas.AIConversationDetailRead(
        id=conv.id,
        tenant_id=conv.tenant_id,
        user_id=conv.user_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            schemas.AIMessageRead(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                tool_calls=_safe_parse_json(m.tool_calls),
                metrics=_safe_parse_json(m.metrics),
                approval_pending=_safe_parse_json(m.approval_pending),
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )

@app.put(
    "/api/v1/ai/conversations/{conversation_id}",
    response_model=schemas.AIConversationRead,
    tags=["AI Agent"],
    summary="Rename an owned conversation",
)
def update_ai_conversation(
    conversation_id: str,
    payload: schemas.AIConversationUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    conv = (
        db.query(models.AIConversation)
        .filter(
            models.AIConversation.id == conversation_id,
            models.AIConversation.tenant_id == context.tenant_id,
            models.AIConversation.user_id == context.user_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )
    if payload.title and payload.title.strip():
        conv.title = payload.title.strip()
    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)
    return schemas.AIConversationRead(
        id=conv.id,
        tenant_id=conv.tenant_id,
        user_id=conv.user_id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )

@app.delete(
    "/api/v1/ai/conversations/{conversation_id}",
    tags=["AI Agent"],
    summary="Delete an owned conversation and its messages",
)
def delete_ai_conversation(
    conversation_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    conv = (
        db.query(models.AIConversation)
        .filter(
            models.AIConversation.id == conversation_id,
            models.AIConversation.tenant_id == context.tenant_id,
            models.AIConversation.user_id == context.user_id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied.",
        )
    db.delete(conv)
    db.commit()
    return {"success": True, "detail": "Conversation deleted successfully."}

# -----------------------------------------------------------------------------
# LangGraph Autonomous Agentic AI Endpoints
# -----------------------------------------------------------------------------
@app.post(
    "/api/v1/ai/chat",
    response_model=schemas.AIChatResponse,
    tags=["AI Agent"],
    summary="LangGraph autonomous clinical operations reasoning and execution endpoint",
)
def ai_chat_endpoint(
    payload: schemas.AIChatRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    practice = ensure_tenant_practice(db, context.tenant_id)
    user = ensure_user_record(db, context.user_id, context.tenant_id, context.user_role)
    company_name = (
        user.company_name
        if (user and user.company_name)
        else (practice.name if practice else context.tenant_id)
    )

    sec_context = build_ai_security_context(context, company_name)

    # Step 1.3: Enforce conversation ownership or create owned persistent conversation
    active_conv = None
    if payload.conversation_id:
        active_conv = (
            db.query(models.AIConversation)
            .filter(
                models.AIConversation.id == payload.conversation_id,
                models.AIConversation.tenant_id == context.tenant_id,
                models.AIConversation.user_id == context.user_id,
            )
            .first()
        )
        if not active_conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found or access denied.",
            )
    else:
        # Auto-create new conversation belonging strictly to authenticated tenant + user
        title_snippet = payload.message.strip().split("\n")[0][:45]
        active_conv = models.AIConversation(
            id=f"conv-{uuid.uuid4().hex[:12]}",
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            title=title_snippet if title_snippet else "Clinical Consultation",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(active_conv)
        db.commit()
        db.refresh(active_conv)

    # Save incoming user message in PostgreSQL
    user_msg = models.AIMessage(
        id=f"msg-{uuid.uuid4().hex[:12]}",
        conversation_id=active_conv.id,
        role="user",
        content=payload.message,
        created_at=datetime.utcnow(),
    )
    db.add(user_msg)
    db.commit()

    # Load persistent conversation history from database
    stored_msgs = (
        db.query(models.AIMessage)
        .filter(models.AIMessage.conversation_id == active_conv.id)
        .order_by(models.AIMessage.created_at.asc())
        .all()
    )
    # Pass previous messages as history to agent
    history = [
        {"role": m.role, "content": m.content}
        for m in stored_msgs[:-1]
    ]

    # Step 6 Security: Restrict client-controlled agent_mode overrides to dev/test environments
    env = os.getenv("ENVIRONMENT", "development").lower()
    effective_agent_mode = payload.agent_mode if env in ("development", "test", "dev") else None

    # Unhandled exceptions surface as CORS-less 500s (browser shows "Failed to fetch"),
    # so agent failures are converted into an explicit, honest HTTP error.
    try:
        result = agent.run(
            message=payload.message,
            conversation_history=history,
            context=sec_context,
            db=db,
            approval_id=payload.approval_id,
            agent_mode=effective_agent_mode,
            conversation_id=active_conv.id,
        )
    except Exception:
        db.rollback()
        logger.exception("AI agent run failed for conversation %s", active_conv.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "The AI assistant failed to process this request. No result can be confirmed; "
                "if you requested a change, verify the record before retrying."
            ),
        )

    approval_pending = None
    if result.get("approval_pending"):
        ap = result["approval_pending"]
        approval_pending = schemas.ApprovalPendingInfo(
            approval_id=ap["approval_id"],
            tool_name=ap["tool_name"],
            description=ap["description"],
            arguments=ap["arguments"],
        )

    # Save assistant message to PostgreSQL
    asst_msg = models.AIMessage(
        id=f"msg-{uuid.uuid4().hex[:12]}",
        conversation_id=active_conv.id,
        role="assistant",
        content=result.get("reply", ""),
        tool_calls=(
            json.dumps(result.get("tool_calls_executed", []))
            if result.get("tool_calls_executed")
            else None
        ),
        metrics=(
            json.dumps(result.get("metrics"))
            if result.get("metrics")
            else None
        ),
        approval_pending=(
            json.dumps(approval_pending.model_dump())
            if approval_pending
            else None
        ),
        created_at=datetime.utcnow(),
    )
    active_conv.updated_at = datetime.utcnow()
    db.add(asst_msg)
    db.commit()

    return schemas.AIChatResponse(
        conversation_id=active_conv.id,
        reply=result.get("reply", ""),
        tool_calls_executed=[
            schemas.ToolCallExecution(
                tool=tc.get("tool", "unknown"),
                status=tc.get("status", "UNKNOWN"),
                duration_ms=tc.get("duration_ms"),
                correlation_id=tc.get("correlation_id"),
                resource_id=tc.get("resource_id"),
            )
            for tc in result.get("tool_calls_executed", [])
        ],
        status=result.get("status", "completed"),
        approval_pending=approval_pending,
        metrics=result.get("metrics"),
    )

@app.post(
    "/api/v1/ai/approve",
    response_model=schemas.AIApproveResponse,
    tags=["AI Agent"],
    summary="Approve or reject a pending human-in-the-loop authorization request",
)
def ai_approve_endpoint(
    payload: schemas.AIApproveRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    practice = ensure_tenant_practice(db, context.tenant_id)
    user = db.query(models.User).filter(models.User.id == context.user_id).first()
    company_name = (
        user.company_name
        if (user and user.company_name)
        else (practice.name if practice else context.tenant_id)
    )

    sec_context = build_ai_security_context(context, company_name)

    res = approval_manager.resolve_action(
        db=db,
        approval_id=payload.approval_id,
        tenant_id=context.tenant_id,
        user_id=context.user_id,
        user_role=context.user_role,
        action=payload.action,
    )

    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.get("detail", "Failed to resolve approval request."),
        )

    if payload.action.lower() == "reject":
        return schemas.AIApproveResponse(
            success=True,
            detail="Action rejected by user.",
            status="REJECTED",
            reply="The sensitive clinical operation was cancelled by user rejection.",
        )

    # If approved, execute immediately through ToolGateway
    rec = res.get("record")
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing approval record.",
        )

    exec_result = gateway.execute(
        tool_name=rec.tool_name,
        arguments=rec.arguments,
        context=sec_context,
        db=db,
        approval_id=payload.approval_id,
    )

    if "error" in exec_result:
        return schemas.AIApproveResponse(
            success=False,
            detail=exec_result.get("detail", "Execution error."),
            status="FAILED",
            reply=f"Approval execution failed: {exec_result.get('detail')}",
        )

    return schemas.AIApproveResponse(
        success=True,
        detail=f"Successfully executed {rec.tool_name}.",
        status="EXECUTED",
        reply=f"Action confirmed: {exec_result.get('message', 'Operation completed.')}",
    )

@app.get(
    "/api/v1/ai/audit",
    tags=["AI Agent"],
    summary="Retrieve AI governance audit records for current tenant",
)
def get_ai_audit_logs(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["CLINIC_OWNER"])
    return {
        "tenant_id": context.tenant_id,
        "logs": gateway.get_audit_logs(db=db, tenant_id=context.tenant_id),
    }
