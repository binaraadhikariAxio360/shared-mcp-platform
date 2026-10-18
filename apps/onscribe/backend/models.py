import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

def gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

class OpsProject(Base):
    __tablename__ = "ops_projects"

    id = Column(String, primary_key=True, default=lambda: gen_id("prj"), index=True)
    tenant_id = Column(String, index=True, nullable=False, default="tenant-001")
    name = Column(String, nullable=False)
    code = Column(String, nullable=False)
    status = Column(String, default="ACTIVE")  # ACTIVE, ON_HOLD, COMPLETED
    sprint_cycle = Column(String, default="Sprint 24-Q4")
    target_date = Column(String, default="2026-11-30")
    created_at = Column(DateTime, default=datetime.utcnow)

class OpsTeamMember(Base):
    __tablename__ = "ops_team_members"

    id = Column(String, primary_key=True, default=lambda: gen_id("tm"), index=True)
    tenant_id = Column(String, index=True, nullable=False, default="tenant-001")
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    email = Column(String, nullable=True)
    max_task_threshold = Column(Integer, default=4)
    active_tasks_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class OpsDeliverable(Base):
    __tablename__ = "ops_deliverables"

    id = Column(String, primary_key=True, default=lambda: gen_id("dlv"), index=True)
    tenant_id = Column(String, index=True, nullable=False, default="tenant-001")
    title = Column(String, nullable=False)
    project_id = Column(String, index=True, nullable=True)
    assignee_id = Column(String, index=True, nullable=True)
    priority = Column(String, default="MEDIUM")  # CRITICAL, HIGH, MEDIUM, LOW
    status = Column(String, default="IN_PROGRESS")  # OVERDUE, IN_PROGRESS, COMPLETED
    due_date = Column(String, default="2026-10-31")
    sla_days_overdue = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class OpsComplianceDoc(Base):
    __tablename__ = "ops_compliance_docs"

    id = Column(String, primary_key=True, default=lambda: gen_id("cmp"), index=True)
    tenant_id = Column(String, index=True, nullable=False, default="tenant-001")
    title = Column(String, nullable=False)
    standard = Column(String, default="ISO 27001")  # ISO 27001, SOC 2, Vendor Risk, GDPR
    status = Column(String, default="AUDITED")  # AUDITED, IN_REVIEW, NON_CONFORMANT
    audit_date = Column(String, default="2026-10-15")
    auditor_name = Column(String, default="Apex Governance Bureau")
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "onscribe_users"

    id = Column(String, primary_key=True, default=lambda: gen_id("usr"), index=True)
    email = Column(String(150), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(50), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    company_name = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
