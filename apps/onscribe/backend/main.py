from contextlib import asynccontextmanager
from typing import Annotated, Any, Dict, List, Optional
from datetime import datetime
from fastapi import FastAPI, Header, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

import uuid
try:
    from . import models, schemas
    from .database import engine, get_db, init_db_and_seed, hash_password, verify_password
except ImportError:
    import models, schemas
    from database import engine, get_db, init_db_and_seed, hash_password, verify_password

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB & Seed initial records
    init_db_and_seed()
    yield

app = FastAPI(
    title="OnScribe Operations & Compliance Intelligence MOC",
    version="2.0.0",
    description="Enterprise operations management, deliverable SLA tracking, team capacity orchestration, and compliance auditing suite.",
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
# Security & Request Context
# -----------------------------------------------------------------------------
def get_request_context(
    x_tenant_id: Annotated[str, Header(alias="x-tenant-id", description="Tenant Identifier", min_length=1)] = "tenant-001",
    x_user_role: Annotated[Optional[str], Header(alias="x-user-role", description="Active User Role")] = "OPERATIONS_DIRECTOR",
    x_user_id: Annotated[Optional[str], Header(alias="x-user-id", description="User Identifier")] = "ops-director-default",
) -> schemas.RequestContext:
    if not x_tenant_id or not x_tenant_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header 'x-tenant-id' is required and cannot be blank.",
        )
    return schemas.RequestContext(
        tenant_id=x_tenant_id.strip(),
        user_id=(x_user_id.strip() if x_user_id and x_user_id.strip() else "ops-director-default"),
        user_role=(x_user_role.strip() if x_user_role and x_user_role.strip() else "OPERATIONS_DIRECTOR"),
    )

def require_role(context: schemas.RequestContext, allowed_roles: List[str]):
    if context.user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation not permitted for role {context.user_role}",
        )

@app.get("/api/v1/auth/roles", tags=["Auth"])
def get_auth_roles(context: Annotated[schemas.RequestContext, Depends(get_request_context)]):
    return {
        "app": "OnScribe",
        "current_tenant": context.tenant_id,
        "current_role": context.user_role,
        "current_user": context.user_id,
        "roles": [
            {
                "id": "OPERATIONS_DIRECTOR",
                "label": "Operations Director (Admin)",
                "description": "Full CRUD on projects, deliverables, team workload, and compliance controls.",
            },
            {
                "id": "PROJECT_MANAGER",
                "label": "Project Manager (Manager)",
                "description": "Full CRUD on deliverables and sprint projects; update workload; cannot alter audit docs.",
            },
            {
                "id": "TEAM_CONTRIBUTOR",
                "label": "Team Contributor (Staff)",
                "description": "Update assigned deliverable status (IN_PROGRESS -> COMPLETED); cannot delete or edit projects.",
            },
            {
                "id": "COMPLIANCE_AUDITOR",
                "label": "Compliance Auditor (Auditor)",
                "description": "Audit compliance documents (mark AUDITED); read-only on operational tasks.",
            },
        ],
        "tenants": [
            {
                "id": "tenant-001",
                "name": "Vanguard Enterprise Operations",
                "description": "Core Infrastructure & Global SOC Operations",
            },
            {
                "id": "tenant-002",
                "name": "BluePeak Global Operations",
                "description": "GovCloud & Specialized FedRAMP Operations",
            },
        ],
    }

@app.post("/api/v1/auth/login", response_model=schemas.AuthResponse, tags=["Auth"])
def auth_login(payload: schemas.UserLoginRequest, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == clean_email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    access_token = f"moc_sess_{user.id}_{user.tenant_id}"
    return schemas.AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=schemas.UserResponse(
            id=user.id,
            name=user.full_name,
            email=user.email,
            role=user.role,
            tenant_id=user.tenant_id,
            company_name=user.company_name or user.tenant_id,
        ),
    )

@app.post("/api/v1/auth/register", response_model=schemas.AuthResponse, tags=["Auth"])
def auth_register(payload: schemas.UserRegisterRequest, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    existing = db.query(models.User).filter(models.User.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )
    tenant_id = payload.tenant_id.strip() if payload.tenant_id and payload.tenant_id.strip() else None
    company_name = payload.company_name.strip() if payload.company_name and payload.company_name.strip() else "New Operations Unit"
    if not tenant_id:
        slug = company_name.lower().replace(" ", "-")[:10]
        tenant_id = f"tenant-{slug}-{str(uuid.uuid4())[:4]}"

    # Ensure initial project exists for new tenant
    project = db.query(models.OpsProject).filter(models.OpsProject.tenant_id == tenant_id).first()
    if not project:
        project = models.OpsProject(
            tenant_id=tenant_id,
            name=f"{company_name} Core Operations",
            code="OPS-01",
            status="ACTIVE",
            sprint_cycle="Sprint 24-Q4",
            target_date="2026-11-30",
        )
        db.add(project)
        member = models.OpsTeamMember(
            tenant_id=tenant_id,
            name=payload.full_name.strip(),
            role="Director",
            email=clean_email,
            max_task_threshold=5,
            active_tasks_count=0,
        )
        db.add(member)
        db.commit()

    new_user = models.User(
        email=clean_email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=(payload.role.strip() if payload.role and payload.role.strip() else "OPERATIONS_DIRECTOR"),
        tenant_id=tenant_id,
        company_name=company_name,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = f"moc_sess_{new_user.id}_{new_user.tenant_id}"
    return schemas.AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=schemas.UserResponse(
            id=new_user.id,
            name=new_user.full_name,
            email=new_user.email,
            role=new_user.role,
            tenant_id=new_user.tenant_id,
            company_name=new_user.company_name or new_user.tenant_id,
        ),
    )

@app.get("/api/v1/auth/me", response_model=schemas.UserResponse, tags=["Auth"])
def auth_me(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == context.user_id).first()
    if not user:
        user = db.query(models.User).filter(
            models.User.tenant_id == context.tenant_id,
            models.User.role == context.user_role,
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
        name=f"Operations Lead ({context.user_role})",
        email=f"{context.user_role.lower()}@{context.tenant_id}.com",
        role=context.user_role,
        tenant_id=context.tenant_id,
        company_name=f"Operations ({context.tenant_id})",
    )

# -----------------------------------------------------------------------------
# System & Health
# -----------------------------------------------------------------------------
@app.get("/", tags=["System"])
def root_index():
    return {
        "service": "OnScribe Operations API",
        "status": "operational",
        "database": "PostgreSQL 16 Connected",
        "docs_url": "/docs",
        "health_url": "/health",
        "frontend_url": "http://localhost:3004",
    }

@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    db_connected = False
    try:
        db.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False

    return {
        "status": "healthy" if db_connected else "degraded",
        "service": "onscribe-backend",
        "database_connected": db_connected,
        "database_type": "PostgreSQL 16",
        "timestamp": datetime.utcnow().isoformat(),
    }

# -----------------------------------------------------------------------------
# 1. Dashboard Summary & Operations KPIs
# -----------------------------------------------------------------------------
@app.get("/api/v1/dashboard/summary", response_model=schemas.DashboardSummary, tags=["Dashboard"])
def get_dashboard_summary(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    tenant_id = context.tenant_id

    # Active projects
    active_projects = db.query(models.OpsProject).filter(
        models.OpsProject.tenant_id == tenant_id,
        models.OpsProject.status == "ACTIVE"
    ).count()

    # Deliverables queries
    deliverables = db.query(models.OpsDeliverable).filter(models.OpsDeliverable.tenant_id == tenant_id).all()
    total_dlv = len(deliverables)

    overdue_tasks = sum(1 for d in deliverables if d.status == "OVERDUE")
    critical_overdue = sum(1 for d in deliverables if d.status == "OVERDUE" and d.priority == "CRITICAL")
    completed_count = sum(1 for d in deliverables if d.status == "COMPLETED")

    completion_rate = round((completed_count / total_dlv * 100), 1) if total_dlv > 0 else 0.0

    priority_breakdown = {
        "CRITICAL": sum(1 for d in deliverables if d.priority == "CRITICAL"),
        "HIGH": sum(1 for d in deliverables if d.priority == "HIGH"),
        "MEDIUM": sum(1 for d in deliverables if d.priority == "MEDIUM"),
        "LOW": sum(1 for d in deliverables if d.priority == "LOW"),
    }

    status_breakdown = {
        "OVERDUE": overdue_tasks,
        "IN_PROGRESS": sum(1 for d in deliverables if d.status == "IN_PROGRESS"),
        "COMPLETED": completed_count,
    }

    # Team capacity & Overburdened staff
    team = db.query(models.OpsTeamMember).filter(models.OpsTeamMember.tenant_id == tenant_id).all()
    overburdened = sum(1 for m in team if m.active_tasks_count > m.max_task_threshold)

    # Compliance audited count
    compliance_audited = db.query(models.OpsComplianceDoc).filter(
        models.OpsComplianceDoc.tenant_id == tenant_id,
        models.OpsComplianceDoc.status == "AUDITED"
    ).count()

    sla_escalation = "CRITICAL ESCALATION" if (overdue_tasks > 3 or critical_overdue > 0) else "HEALTHY"

    org_map = {
        "tenant-001": "Apex Operations Solutions Inc.",
        "tenant-002": "BluePeak Global Operations",
    }
    organization_name = org_map.get(tenant_id, f"Operations Corp ({tenant_id})")

    return schemas.DashboardSummary(
        tenant_id=tenant_id,
        organization_name=organization_name,
        active_projects_count=active_projects,
        overdue_tasks_count=overdue_tasks,
        critical_overdue_count=critical_overdue,
        overburdened_staff_count=overburdened,
        compliance_audited_count=compliance_audited,
        total_deliverables_count=total_dlv,
        completion_rate=completion_rate,
        sla_escalation_status=sla_escalation,
        priority_breakdown=priority_breakdown,
        status_breakdown=status_breakdown,
    )

# -----------------------------------------------------------------------------
# 2. Deliverables & Tasks CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/deliverables", response_model=List[schemas.OpsDeliverableRead], tags=["Deliverables"])
def list_deliverables(
    priority: Optional[str] = None,
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.OpsDeliverable).filter(models.OpsDeliverable.tenant_id == context.tenant_id)
    if priority:
        query = query.filter(models.OpsDeliverable.priority == priority.upper())
    if status:
        query = query.filter(models.OpsDeliverable.status == status.upper())
    if assignee_id:
        query = query.filter(models.OpsDeliverable.assignee_id == assignee_id)

    records = query.order_by(models.OpsDeliverable.sla_days_overdue.desc()).all()

    # Pre-fetch project and team maps for names
    projects = {p.id: p.name for p in db.query(models.OpsProject).filter(models.OpsProject.tenant_id == context.tenant_id).all()}
    team_members = {m.id: m.name for m in db.query(models.OpsTeamMember).filter(models.OpsTeamMember.tenant_id == context.tenant_id).all()}

    res = []
    for r in records:
        d_dict = schemas.OpsDeliverableRead.from_orm(r)
        d_dict.project_name = projects.get(r.project_id, "General Sprint")
        d_dict.assignee_name = team_members.get(r.assignee_id, "Unassigned")
        res.append(d_dict)
    return res

@app.post("/api/v1/deliverables", response_model=schemas.OpsDeliverableRead, status_code=status.HTTP_201_CREATED, tags=["Deliverables"])
def create_deliverable(
    payload: schemas.OpsDeliverableCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "PROJECT_MANAGER"])
    new_dlv = models.OpsDeliverable(
        tenant_id=context.tenant_id,
        title=payload.title,
        project_id=payload.project_id,
        assignee_id=payload.assignee_id,
        priority=payload.priority or "MEDIUM",
        status=payload.status or "IN_PROGRESS",
        due_date=payload.due_date or "2026-10-31",
        sla_days_overdue=payload.sla_days_overdue or 0,
    )
    db.add(new_dlv)

    # If assigned to team member, increment their active task count
    if payload.assignee_id:
        member = db.query(models.OpsTeamMember).filter(
            models.OpsTeamMember.id == payload.assignee_id,
            models.OpsTeamMember.tenant_id == context.tenant_id
        ).first()
        if member:
            member.active_tasks_count += 1

    db.commit()
    db.refresh(new_dlv)

    res = schemas.OpsDeliverableRead.from_orm(new_dlv)
    if new_dlv.project_id:
        prj = db.query(models.OpsProject).filter(models.OpsProject.id == new_dlv.project_id).first()
        res.project_name = prj.name if prj else None
    if new_dlv.assignee_id:
        tm = db.query(models.OpsTeamMember).filter(models.OpsTeamMember.id == new_dlv.assignee_id).first()
        res.assignee_name = tm.name if tm else None
    return res

@app.get("/api/v1/deliverables/{dlv_id}", response_model=schemas.OpsDeliverableRead, tags=["Deliverables"])
def get_deliverable(
    dlv_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    dlv = db.query(models.OpsDeliverable).filter(
        models.OpsDeliverable.id == dlv_id,
        models.OpsDeliverable.tenant_id == context.tenant_id
    ).first()
    if not dlv:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    res = schemas.OpsDeliverableRead.from_orm(dlv)
    if dlv.project_id:
        prj = db.query(models.OpsProject).filter(models.OpsProject.id == dlv.project_id).first()
        res.project_name = prj.name if prj else None
    if dlv.assignee_id:
        tm = db.query(models.OpsTeamMember).filter(models.OpsTeamMember.id == dlv.assignee_id).first()
        res.assignee_name = tm.name if tm else None
    return res

@app.put("/api/v1/deliverables/{dlv_id}", response_model=schemas.OpsDeliverableRead, tags=["Deliverables"])
def update_deliverable(
    dlv_id: str,
    payload: schemas.OpsDeliverableUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "PROJECT_MANAGER", "TEAM_CONTRIBUTOR"])
    dlv = db.query(models.OpsDeliverable).filter(
        models.OpsDeliverable.id == dlv_id,
        models.OpsDeliverable.tenant_id == context.tenant_id
    ).first()
    if not dlv:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    old_status = dlv.status
    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(dlv, field, val)

    # If transitioning to COMPLETED, decrement assignee active tasks
    if "status" in update_data and update_data["status"] == "COMPLETED" and old_status != "COMPLETED":
        dlv.sla_days_overdue = 0
        if dlv.assignee_id:
            member = db.query(models.OpsTeamMember).filter(
                models.OpsTeamMember.id == dlv.assignee_id,
                models.OpsTeamMember.tenant_id == context.tenant_id
            ).first()
            if member and member.active_tasks_count > 0:
                member.active_tasks_count -= 1

    db.commit()
    db.refresh(dlv)

    res = schemas.OpsDeliverableRead.from_orm(dlv)
    if dlv.project_id:
        prj = db.query(models.OpsProject).filter(models.OpsProject.id == dlv.project_id).first()
        res.project_name = prj.name if prj else None
    if dlv.assignee_id:
        tm = db.query(models.OpsTeamMember).filter(models.OpsTeamMember.id == dlv.assignee_id).first()
        res.assignee_name = tm.name if tm else None
    return res

@app.delete("/api/v1/deliverables/{dlv_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Deliverables"])
def delete_deliverable(
    dlv_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "PROJECT_MANAGER"])
    dlv = db.query(models.OpsDeliverable).filter(
        models.OpsDeliverable.id == dlv_id,
        models.OpsDeliverable.tenant_id == context.tenant_id
    ).first()
    if not dlv:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    if dlv.assignee_id and dlv.status != "COMPLETED":
        member = db.query(models.OpsTeamMember).filter(
            models.OpsTeamMember.id == dlv.assignee_id,
            models.OpsTeamMember.tenant_id == context.tenant_id
        ).first()
        if member and member.active_tasks_count > 0:
            member.active_tasks_count -= 1

    db.delete(dlv)
    db.commit()
    return None

# -----------------------------------------------------------------------------
# 3. Projects CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/projects", response_model=List[schemas.OpsProjectRead], tags=["Projects"])
def list_projects(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    return db.query(models.OpsProject).filter(models.OpsProject.tenant_id == context.tenant_id).all()

@app.post("/api/v1/projects", response_model=schemas.OpsProjectRead, status_code=status.HTTP_201_CREATED, tags=["Projects"])
def create_project(
    payload: schemas.OpsProjectCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "PROJECT_MANAGER"])
    new_prj = models.OpsProject(
        tenant_id=context.tenant_id,
        name=payload.name,
        code=payload.code,
        status=payload.status or "ACTIVE",
        sprint_cycle=payload.sprint_cycle or "Sprint 24-Q4",
        target_date=payload.target_date or "2026-11-30",
    )
    db.add(new_prj)
    db.commit()
    db.refresh(new_prj)
    return new_prj

@app.get("/api/v1/projects/{prj_id}", response_model=schemas.OpsProjectRead, tags=["Projects"])
def get_project(
    prj_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    prj = db.query(models.OpsProject).filter(
        models.OpsProject.id == prj_id,
        models.OpsProject.tenant_id == context.tenant_id
    ).first()
    if not prj:
        raise HTTPException(status_code=404, detail="Project not found")
    return prj

@app.put("/api/v1/projects/{prj_id}", response_model=schemas.OpsProjectRead, tags=["Projects"])
def update_project(
    prj_id: str,
    payload: schemas.OpsProjectUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "PROJECT_MANAGER"])
    prj = db.query(models.OpsProject).filter(
        models.OpsProject.id == prj_id,
        models.OpsProject.tenant_id == context.tenant_id
    ).first()
    if not prj:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(prj, field, val)

    db.commit()
    db.refresh(prj)
    return prj

@app.delete("/api/v1/projects/{prj_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Projects"])
def delete_project(
    prj_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "PROJECT_MANAGER"])
    prj = db.query(models.OpsProject).filter(
        models.OpsProject.id == prj_id,
        models.OpsProject.tenant_id == context.tenant_id
    ).first()
    if not prj:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(prj)
    db.commit()
    return None

# -----------------------------------------------------------------------------
# 4. Team Members & Capacity CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/team", response_model=List[schemas.OpsTeamMemberRead], tags=["Team"])
def list_team_members(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    return db.query(models.OpsTeamMember).filter(models.OpsTeamMember.tenant_id == context.tenant_id).all()

@app.post("/api/v1/team", response_model=schemas.OpsTeamMemberRead, status_code=status.HTTP_201_CREATED, tags=["Team"])
def create_team_member(
    payload: schemas.OpsTeamMemberCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "PROJECT_MANAGER"])
    new_tm = models.OpsTeamMember(
        tenant_id=context.tenant_id,
        name=payload.name,
        role=payload.role,
        email=payload.email,
        max_task_threshold=payload.max_task_threshold or 4,
        active_tasks_count=0,
    )
    db.add(new_tm)
    db.commit()
    db.refresh(new_tm)
    return new_tm

@app.get("/api/v1/team/{tm_id}", response_model=schemas.OpsTeamMemberRead, tags=["Team"])
def get_team_member(
    tm_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    tm = db.query(models.OpsTeamMember).filter(
        models.OpsTeamMember.id == tm_id,
        models.OpsTeamMember.tenant_id == context.tenant_id
    ).first()
    if not tm:
        raise HTTPException(status_code=404, detail="Team member not found")
    return tm

@app.put("/api/v1/team/{tm_id}", response_model=schemas.OpsTeamMemberRead, tags=["Team"])
def update_team_member(
    tm_id: str,
    payload: schemas.OpsTeamMemberUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "PROJECT_MANAGER"])
    tm = db.query(models.OpsTeamMember).filter(
        models.OpsTeamMember.id == tm_id,
        models.OpsTeamMember.tenant_id == context.tenant_id
    ).first()
    if not tm:
        raise HTTPException(status_code=404, detail="Team member not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(tm, field, val)

    db.commit()
    db.refresh(tm)
    return tm

@app.delete("/api/v1/team/{tm_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Team"])
def delete_team_member(
    tm_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR"])
    tm = db.query(models.OpsTeamMember).filter(
        models.OpsTeamMember.id == tm_id,
        models.OpsTeamMember.tenant_id == context.tenant_id
    ).first()
    if not tm:
        raise HTTPException(status_code=404, detail="Team member not found")

    db.delete(tm)
    db.commit()
    return None

# -----------------------------------------------------------------------------
# 5. Compliance Documents CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/compliance", response_model=List[schemas.OpsComplianceDocRead], tags=["Compliance"])
def list_compliance_docs(
    standard: Optional[str] = None,
    status: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.OpsComplianceDoc).filter(models.OpsComplianceDoc.tenant_id == context.tenant_id)
    if standard:
        query = query.filter(models.OpsComplianceDoc.standard.ilike(f"%{standard}%"))
    if status:
        query = query.filter(models.OpsComplianceDoc.status == status.upper())
    return query.order_by(models.OpsComplianceDoc.audit_date.desc()).all()

@app.post("/api/v1/compliance", response_model=schemas.OpsComplianceDocRead, status_code=status.HTTP_201_CREATED, tags=["Compliance"])
def create_compliance_doc(
    payload: schemas.OpsComplianceDocCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "COMPLIANCE_AUDITOR"])
    new_doc = models.OpsComplianceDoc(
        tenant_id=context.tenant_id,
        title=payload.title,
        standard=payload.standard or "ISO 27001",
        status=payload.status or "AUDITED",
        audit_date=payload.audit_date or "2026-10-15",
        auditor_name=payload.auditor_name or "Apex Governance Bureau",
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    return new_doc

@app.get("/api/v1/compliance/{doc_id}", response_model=schemas.OpsComplianceDocRead, tags=["Compliance"])
def get_compliance_doc(
    doc_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    doc = db.query(models.OpsComplianceDoc).filter(
        models.OpsComplianceDoc.id == doc_id,
        models.OpsComplianceDoc.tenant_id == context.tenant_id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Compliance document not found")
    return doc

@app.put("/api/v1/compliance/{doc_id}", response_model=schemas.OpsComplianceDocRead, tags=["Compliance"])
def update_compliance_doc(
    doc_id: str,
    payload: schemas.OpsComplianceDocUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "COMPLIANCE_AUDITOR"])
    doc = db.query(models.OpsComplianceDoc).filter(
        models.OpsComplianceDoc.id == doc_id,
        models.OpsComplianceDoc.tenant_id == context.tenant_id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Compliance document not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(doc, field, val)

    db.commit()
    db.refresh(doc)
    return doc

@app.delete("/api/v1/compliance/{doc_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Compliance"])
def delete_compliance_doc(
    doc_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["OPERATIONS_DIRECTOR", "COMPLIANCE_AUDITOR"])
    doc = db.query(models.OpsComplianceDoc).filter(
        models.OpsComplianceDoc.id == doc_id,
        models.OpsComplianceDoc.tenant_id == context.tenant_id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Compliance document not found")

    db.delete(doc)
    db.commit()
    return None


# -----------------------------------------------------------------------------
# 6. Live AI Copilot Tools (Direct PostgreSQL Queries)
# -----------------------------------------------------------------------------
@app.post(
    "/internal/tools/onscribe.list_overdue_tasks",
    response_model=schemas.ListOverdueTasksToolResponse,
    tags=["Tools"],
    summary="Direct database query for overdue operations deliverables and SLA violations",
)
def tool_list_overdue_tasks(
    payload: schemas.ListOverdueTasksToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    query = db.query(models.OpsDeliverable).filter(
        models.OpsDeliverable.tenant_id == context.tenant_id,
        models.OpsDeliverable.status == "OVERDUE",
    )
    if payload.priority:
        query = query.filter(models.OpsDeliverable.priority == payload.priority.upper())
    if payload.project_id:
        query = query.filter(models.OpsDeliverable.project_id == payload.project_id)

    overdue_list = query.order_by(models.OpsDeliverable.sla_days_overdue.desc()).all()

    projects = {p.id: p.name for p in db.query(models.OpsProject).filter(models.OpsProject.tenant_id == context.tenant_id).all()}
    team_members = {m.id: m.name for m in db.query(models.OpsTeamMember).filter(models.OpsTeamMember.tenant_id == context.tenant_id).all()}

    items = [
        schemas.OverdueTaskItem(
            id=d.id,
            title=d.title,
            project_name=projects.get(d.project_id, "General Sprint"),
            assignee_name=team_members.get(d.assignee_id, "Unassigned"),
            priority=d.priority,
            status=d.status,
            due_date=d.due_date,
            sla_days_overdue=d.sla_days_overdue,
        )
        for d in overdue_list
    ]

    critical_count = sum(1 for i in items if i.priority == "CRITICAL")

    return schemas.ListOverdueTasksToolResponse(
        tenant_id=context.tenant_id,
        count=len(items),
        critical_count=critical_count,
        tasks=items,
    )

@app.post(
    "/internal/tools/onscribe.analyze_team_workload",
    response_model=schemas.AnalyzeTeamWorkloadToolResponse,
    tags=["Tools"],
    summary="Compute live workload capacity ratios and identify overburdened personnel",
)
def tool_analyze_team_workload(
    payload: schemas.AnalyzeTeamWorkloadToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    team = db.query(models.OpsTeamMember).filter(models.OpsTeamMember.tenant_id == context.tenant_id).all()
    items = []

    for m in team:
        ratio = round((m.active_tasks_count / m.max_task_threshold), 2) if m.max_task_threshold > 0 else 1.0
        if payload.min_load_ratio and ratio < payload.min_load_ratio:
            continue

        if ratio > 1.0:
            status_desc = "OVERBURDENED"
        elif ratio >= 0.8:
            status_desc = "NEAR_CAPACITY"
        else:
            status_desc = "OPTIMAL"

        items.append(
            schemas.TeamWorkloadItem(
                id=m.id,
                name=m.name,
                role=m.role,
                email=m.email,
                active_tasks=m.active_tasks_count,
                max_threshold=m.max_task_threshold,
                load_ratio=ratio,
                load_status=status_desc,
            )
        )

    overburdened_count = sum(1 for i in items if i.load_status == "OVERBURDENED")

    return schemas.AnalyzeTeamWorkloadToolResponse(
        tenant_id=context.tenant_id,
        member_count=len(items),
        overburdened_count=overburdened_count,
        team=items,
    )

@app.post(
    "/internal/tools/onscribe.get_operations_summary",
    response_model=schemas.OperationsSummaryToolResponse,
    tags=["Tools"],
    summary="Compute real-time operations health, SLA risks, and compliance readiness",
)
def tool_get_operations_summary(
    payload: schemas.OperationsSummaryToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    tenant_id = payload.tenant_id or context.tenant_id

    active_projects = db.query(models.OpsProject).filter(
        models.OpsProject.tenant_id == tenant_id,
        models.OpsProject.status == "ACTIVE"
    ).count()

    deliverables = db.query(models.OpsDeliverable).filter(models.OpsDeliverable.tenant_id == tenant_id).all()
    overdue_count = sum(1 for d in deliverables if d.status == "OVERDUE")
    critical_overdue = sum(1 for d in deliverables if d.status == "OVERDUE" and d.priority == "CRITICAL")
    completed_count = sum(1 for d in deliverables if d.status == "COMPLETED")
    total_dlv = len(deliverables)

    team = db.query(models.OpsTeamMember).filter(models.OpsTeamMember.tenant_id == tenant_id).all()
    overburdened = sum(1 for m in team if m.active_tasks_count > m.max_task_threshold)

    compliance_audited = db.query(models.OpsComplianceDoc).filter(
        models.OpsComplianceDoc.tenant_id == tenant_id,
        models.OpsComplianceDoc.status == "AUDITED"
    ).count()

    sla_risk = "HIGH" if (critical_overdue > 0 or overdue_count > 3) else ("MEDIUM" if overdue_count > 0 else "LOW")

    return schemas.OperationsSummaryToolResponse(
        tenant_id=tenant_id,
        organization_name="Apex Operations Solutions Inc.",
        active_projects=active_projects,
        overdue_tasks=overdue_count,
        sla_risk_level=sla_risk,
        deliverables_summary={
            "total": total_dlv,
            "completed": completed_count,
            "in_progress": sum(1 for d in deliverables if d.status == "IN_PROGRESS"),
            "overdue": overdue_count,
            "critical_overdue": critical_overdue,
        },
        compliance_audited_count=compliance_audited,
        overburdened_staff_count=overburdened,
    )
