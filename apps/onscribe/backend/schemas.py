from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Security & Request Context
# -----------------------------------------------------------------------------
class RequestContext(BaseModel):
    tenant_id: str
    user_id: str
    user_role: str = "OPERATIONS_DIRECTOR"

class UserLoginRequest(BaseModel):
    email: str
    password: str

class UserRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: Optional[str] = "OPERATIONS_DIRECTOR"
    company_name: Optional[str] = None
    tenant_id: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    tenant_id: str
    company_name: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# -----------------------------------------------------------------------------
# Project Schemas
# -----------------------------------------------------------------------------
class OpsProjectBase(BaseModel):
    name: str
    code: str
    status: str = "ACTIVE"  # ACTIVE, ON_HOLD, COMPLETED
    sprint_cycle: str = "Sprint 24-Q4"
    target_date: str = "2026-11-30"

class OpsProjectCreate(OpsProjectBase):
    pass

class OpsProjectUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    status: Optional[str] = None
    sprint_cycle: Optional[str] = None
    target_date: Optional[str] = None

class OpsProjectRead(OpsProjectBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Team Member Schemas
# -----------------------------------------------------------------------------
class OpsTeamMemberBase(BaseModel):
    name: str
    role: str
    email: Optional[str] = None
    max_task_threshold: int = 4
    active_tasks_count: int = 0

class OpsTeamMemberCreate(BaseModel):
    name: str
    role: str
    email: Optional[str] = None
    max_task_threshold: int = 4

class OpsTeamMemberUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    max_task_threshold: Optional[int] = None
    active_tasks_count: Optional[int] = None

class OpsTeamMemberRead(OpsTeamMemberBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Deliverable & Task Schemas
# -----------------------------------------------------------------------------
class OpsDeliverableBase(BaseModel):
    title: str
    project_id: Optional[str] = None
    assignee_id: Optional[str] = None
    priority: str = "MEDIUM"  # CRITICAL, HIGH, MEDIUM, LOW
    status: str = "IN_PROGRESS"  # OVERDUE, IN_PROGRESS, COMPLETED
    due_date: str = "2026-10-31"
    sla_days_overdue: int = 0

class OpsDeliverableCreate(BaseModel):
    title: str
    project_id: Optional[str] = None
    assignee_id: Optional[str] = None
    priority: str = "MEDIUM"
    status: Optional[str] = "IN_PROGRESS"
    due_date: Optional[str] = "2026-10-31"
    sla_days_overdue: Optional[int] = 0

class OpsDeliverableUpdate(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    assignee_id: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    sla_days_overdue: Optional[int] = None

class OpsDeliverableRead(OpsDeliverableBase):
    id: str
    tenant_id: str
    project_name: Optional[str] = None
    assignee_name: Optional[str] = None

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Compliance Document Schemas
# -----------------------------------------------------------------------------
class OpsComplianceDocBase(BaseModel):
    title: str
    standard: str = "ISO 27001"  # ISO 27001, SOC 2, Vendor Risk, GDPR
    status: str = "AUDITED"  # AUDITED, IN_REVIEW, NON_CONFORMANT
    audit_date: str = "2026-10-15"
    auditor_name: str = "Apex Governance Bureau"

class OpsComplianceDocCreate(OpsComplianceDocBase):
    pass

class OpsComplianceDocUpdate(BaseModel):
    title: Optional[str] = None
    standard: Optional[str] = None
    status: Optional[str] = None
    audit_date: Optional[str] = None
    auditor_name: Optional[str] = None

class OpsComplianceDocRead(OpsComplianceDocBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Dashboard Summary
# -----------------------------------------------------------------------------
class DashboardSummary(BaseModel):
    tenant_id: str
    organization_name: str = "Apex Operations Solutions Inc."
    active_projects_count: int
    overdue_tasks_count: int
    critical_overdue_count: int
    overburdened_staff_count: int
    compliance_audited_count: int
    total_deliverables_count: int
    completion_rate: float
    sla_escalation_status: str
    priority_breakdown: Dict[str, int]
    status_breakdown: Dict[str, int]

# -----------------------------------------------------------------------------
# AI Copilot Tool Schemas
# -----------------------------------------------------------------------------
class ListOverdueTasksToolRequest(BaseModel):
    priority: Optional[str] = None
    project_id: Optional[str] = None

class OverdueTaskItem(BaseModel):
    id: str
    title: str
    project_name: Optional[str] = "General Sprint"
    assignee_name: Optional[str] = "Unassigned"
    priority: str
    status: str
    due_date: str
    sla_days_overdue: int

class ListOverdueTasksToolResponse(BaseModel):
    tenant_id: str
    count: int
    critical_count: int
    tasks: List[OverdueTaskItem]

class AnalyzeTeamWorkloadToolRequest(BaseModel):
    min_load_ratio: Optional[float] = None

class TeamWorkloadItem(BaseModel):
    id: str
    name: str
    role: str
    email: Optional[str] = None
    active_tasks: int
    max_threshold: int
    load_ratio: float
    load_status: str  # OPTIMAL, CAPACITY, OVERBURDENED

class AnalyzeTeamWorkloadToolResponse(BaseModel):
    tenant_id: str
    member_count: int
    overburdened_count: int
    team: List[TeamWorkloadItem]

class OperationsSummaryToolRequest(BaseModel):
    tenant_id: Optional[str] = None

class OperationsSummaryToolResponse(BaseModel):
    tenant_id: str
    organization_name: str
    active_projects: int
    overdue_tasks: int
    sla_risk_level: str
    deliverables_summary: Dict[str, Any]
    compliance_audited_count: int
    overburdened_staff_count: int
