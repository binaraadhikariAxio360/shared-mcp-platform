from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

# -----------------------------------------------------------------------------
# Security & Auth Context
# -----------------------------------------------------------------------------
class RequestContext(BaseModel):
    tenant_id: str
    user_id: str
    user_role: str = "CLINIC_OWNER"

class UserLoginRequest(BaseModel):
    email: str
    password: str

class UserRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    # Deprecated compatibility fields are accepted but never trusted by the server.
    role: Optional[str] = None
    company_name: Optional[str] = None
    tenant_id: Optional[str] = None
    invitation_code: Optional[str] = None

class CompanyRegisterRequest(BaseModel):
    full_name: Optional[str] = None
    name: Optional[str] = None
    email: str
    password: str
    company_name: str

    def get_name(self) -> str:
        return self.full_name or self.name or "User"

class StaffJoinRequest(BaseModel):
    full_name: Optional[str] = None
    name: Optional[str] = None
    email: str
    password: str
    invitation_code: str

    def get_name(self) -> str:
        return self.full_name or self.name or "Staff Member"


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    is_active: bool = True
    membership_status: str = "APPROVED"
    tenant_id: str
    company_name: str

class UserStatusUpdate(BaseModel):
    is_active: bool

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class InvitationCreateRequest(BaseModel):
    role: str = "NURSE_STAFF"
    max_uses: int = 5
    expires_in_days: int = 7

class InvitationRead(BaseModel):
    id: str
    code: str
    role: str
    tenant_id: str
    max_uses: int
    use_count: int
    expires_at: Any
    is_revoked: bool
    is_active: bool = True
    created_at: Any

    class Config:
        from_attributes = True

class InvitationValidateRequest(BaseModel):
    code: str

class InvitationValidateResponse(BaseModel):
    valid: bool
    company_name: Optional[str] = None
    role: Optional[str] = None
    detail: Optional[str] = None

class PendingMemberRead(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    email: str
    role: str
    membership_status: str
    tenant_id: str
    company_name: Optional[str] = None
    created_at: Any

class MemberApprovalAction(BaseModel):
    action: str = Field(..., description="'APPROVE' or 'REJECT'")
    role: Optional[str] = None

class CompanySettingsRead(BaseModel):
    company_name: str
    tenant_id: str
    active_invitations_count: int
    pending_requests_count: int
    total_staff_count: int

# -----------------------------------------------------------------------------
# Practice Schemas
# -----------------------------------------------------------------------------
class PracticeBase(BaseModel):
    name: str
    location: str
    room_count: int = 12

class PracticeRead(PracticeBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True

class PracticeUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    room_count: Optional[int] = None

# -----------------------------------------------------------------------------
# Staff Schemas
# -----------------------------------------------------------------------------
class StaffBase(BaseModel):
    name: str
    role: str
    is_active: bool = True
    on_shift: bool = True

class StaffCreate(StaffBase):
    practice_id: Optional[str] = None
    user_id: Optional[str] = None

class StaffRead(StaffBase):
    id: str
    practice_id: str
    tenant_id: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    work_status: Optional[str] = "ACTIVE"
    last_login_at: Optional[datetime] = None
    practice_name: Optional[str] = None
    membership_status: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class StaffStatusUpdate(BaseModel):
    is_active: bool

class StaffShiftUpdate(BaseModel):
    on_shift: bool

class StaffWorkStatusUpdate(BaseModel):
    work_status: str = Field(..., description="'ACTIVE', 'ON_LEAVE', 'HOLIDAY', 'SICK_LEAVE', 'DND'")
    notes: Optional[str] = None

class StaffLeaveCreate(BaseModel):
    leave_type: str = Field(..., description="'HOLIDAY', 'SICK_LEAVE', 'DND', 'OTHER'")
    start_date: datetime
    end_date: datetime
    # Honoured only for authorized approvers; self-service requests are always created PENDING.
    status: Optional[str] = None
    notes: Optional[str] = None

class StaffLeaveStatusUpdate(BaseModel):
    status: str = Field(..., description="'APPROVED' or 'REJECTED'")

class StaffLeaveRead(BaseModel):
    id: str
    staff_id: str
    staff_name: Optional[str] = None
    tenant_id: str
    leave_type: str
    start_date: datetime
    end_date: datetime
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class OperationalConflictItem(BaseModel):
    conflict_type: str  # "HOLIDAY_ASSIGNMENT", "DND_ASSIGNMENT", "SICK_LEAVE_ASSIGNMENT", "INACTIVE_LOGIN_STAFF", "OVERDUE_TASK", "UNASSIGNED_TASK"
    item_type: str      # "TASK" or "CHECKLIST"
    item_id: str
    title: str
    priority: Optional[str] = None
    due_date: Optional[str] = None
    assigned_staff_id: Optional[str] = None
    assigned_staff_name: Optional[str] = None
    staff_work_status: Optional[str] = None
    staff_last_login_at: Optional[datetime] = None
    message: str
    recommendation: str

class OperationalConflictReport(BaseModel):
    tenant_id: str
    total_conflicts: int
    holiday_conflicts: int
    dnd_conflicts: int
    inactive_login_conflicts: int
    overdue_count: int
    unassigned_count: int
    items: List[OperationalConflictItem]

# -----------------------------------------------------------------------------
# Room Schemas
# -----------------------------------------------------------------------------
class RoomBase(BaseModel):
    room_number: str
    name: str
    room_type: str = "Exam"
    status: str = "Available"

class RoomCreate(RoomBase):
    practice_id: Optional[str] = None

class RoomUpdate(BaseModel):
    room_number: Optional[str] = None
    name: Optional[str] = None
    room_type: Optional[str] = None
    status: Optional[str] = None

class RoomRead(RoomBase):
    id: str
    practice_id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Task Schemas
# -----------------------------------------------------------------------------
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "Medium"
    status: str = "Pending"
    due_date: str
    assigned_staff_id: Optional[str] = None
    room_id: Optional[str] = None

class TaskCreate(TaskBase):
    practice_id: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None
    assigned_staff_id: Optional[str] = None
    room_id: Optional[str] = None

class TaskRead(TaskBase):
    id: str
    practice_id: str
    tenant_id: str
    assigned_staff_name: Optional[str] = None
    room_name: Optional[str] = None
    # Caller-specific permissions computed by ai.policy (None when not computed)
    can_complete: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Checklist Schemas
# -----------------------------------------------------------------------------
class ChecklistBase(BaseModel):
    title: str
    category: str = "Sterilization"
    is_completed: bool = False
    frequency: str = "Daily"
    assigned_staff_id: Optional[str] = None

class ChecklistCreate(ChecklistBase):
    practice_id: Optional[str] = None

class ChecklistUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_completed: Optional[bool] = None
    status: Optional[Any] = None
    frequency: Optional[str] = None
    assigned_staff_id: Optional[str] = None

class ChecklistRead(ChecklistBase):
    id: str
    practice_id: str
    tenant_id: str
    assigned_staff_name: Optional[str] = None
    # Caller-specific permissions computed by ai.policy (None when not computed)
    can_toggle: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Inventory Item Schemas
# -----------------------------------------------------------------------------
def _clean_expiry(value: Optional[str]) -> Optional[str]:
    """Expiry dates are stored as ISO YYYY-MM-DD; an empty value means 'no expiry date'."""
    if value is None:
        return None
    clean = str(value).strip()
    if not clean:
        return None
    try:
        return date.fromisoformat(clean).isoformat()
    except ValueError:
        raise ValueError("expiry_date must be a valid date in YYYY-MM-DD format")


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    clean = " ".join(str(value).split())
    return clean or None


class InventoryBase(BaseModel):
    item_name: str = Field(min_length=1, max_length=150)
    current_stock: int = Field(ge=0)
    min_threshold: int = Field(default=10, ge=0)
    unit: str = Field(default="units", max_length=40)
    expiry_date: Optional[str] = None
    room_id: Optional[str] = None
    supplier: Optional[str] = Field(default=None, max_length=150)
    batch_number: Optional[str] = Field(default=None, max_length=80)
    purchase_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    _expiry = field_validator("expiry_date", mode="before")(_clean_expiry)
    _texts = field_validator("supplier", "batch_number", mode="before")(_clean_optional_text)

class InventoryCreate(InventoryBase):
    practice_id: Optional[str] = None

class InventoryUpdate(BaseModel):
    item_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    current_stock: Optional[int] = Field(default=None, ge=0)
    min_threshold: Optional[int] = Field(default=None, ge=0)
    unit: Optional[str] = Field(default=None, max_length=40)
    expiry_date: Optional[str] = None
    room_id: Optional[str] = None
    supplier: Optional[str] = Field(default=None, max_length=150)
    batch_number: Optional[str] = Field(default=None, max_length=80)
    purchase_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    # Optimistic concurrency: when set, current_stock is only replaced if the stored stock still equals this value
    expected_current_stock: Optional[int] = Field(default=None, ge=0)

    _expiry = field_validator("expiry_date", mode="before")(_clean_expiry)
    _texts = field_validator("supplier", "batch_number", mode="before")(_clean_optional_text)

class InventoryAdjustRequest(BaseModel):
    """Restock (positive) or controlled reduction (negative) of one item's stock."""
    quantity_change: int = Field(ge=-1_000_000, le=1_000_000)
    expected_current_stock: Optional[int] = Field(default=None, ge=0)
    reason: Optional[str] = Field(default=None, max_length=200)

class InventoryRead(BaseModel):
    id: str
    item_name: str
    current_stock: int
    min_threshold: int = 10
    unit: Optional[str] = "units"
    expiry_date: Optional[str] = None
    room_id: Optional[str] = None
    supplier: Optional[str] = None
    batch_number: Optional[str] = None
    purchase_price: Optional[float] = None
    practice_id: str
    tenant_id: str
    room_name: Optional[str] = None
    is_low_stock: bool = False
    is_expiring_soon: bool = False
    # Server-computed expiry facts (inventory_service.expiry_info) so the UI never re-implements date logic
    is_expired: bool = False
    days_to_expiry: Optional[int] = None
    expiry_status: str = "none"  # "expired", "within_7", "within_30", "within_90", "later", "none"
    # Independent display statuses (inventory_service.stock_status / expiry_state)
    stock_status: str = "In Stock"  # "In Stock", "Low Stock", "Out of Stock"
    expiry_state: str = "No Expiry Date"  # "Expired", "Expiring Soon", "Valid", "No Expiry Date"
    shortfall: int = 0
    # Caller-specific permission computed by ai.policy so the UI never re-implements RBAC
    can_manage: bool = False

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Inventory Import (AI extraction -> editable preview -> explicit confirmation)
# -----------------------------------------------------------------------------
class InventoryImportExtractRequest(BaseModel):
    source_type: Literal["pdf", "image", "text"]
    filename: Optional[str] = Field(default=None, max_length=255)
    mime_type: Optional[str] = Field(default=None, max_length=100)
    content_base64: Optional[str] = None  # pdf / image
    text: Optional[str] = None            # text

class InventoryImportRow(BaseModel):
    """One preview row as edited by the user. Values are validated again on confirmation."""
    row_id: str = Field(min_length=1, max_length=40)
    action: Literal["create", "restock", "skip"]
    existing_item_id: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[Any] = None
    unit: Optional[str] = None
    min_threshold: Optional[Any] = None
    expiry_date: Optional[str] = None
    supplier: Optional[str] = None
    batch_number: Optional[str] = None
    purchase_price: Optional[Any] = None
    room_id: Optional[str] = None

class InventoryImportConfirmRequest(BaseModel):
    import_token: str = Field(min_length=16, max_length=64)
    source_hash: str = Field(min_length=64, max_length=64)
    source_type: Literal["pdf", "image", "text", "chat"]
    rows: List[InventoryImportRow] = Field(min_length=1, max_length=200)

# -----------------------------------------------------------------------------
# Dashboard Summary Schema
# -----------------------------------------------------------------------------
class DashboardSummary(BaseModel):
    tenant_id: str
    practice_name: str
    total_staff: int
    active_staff_count: int
    total_rooms: int
    room_occupancy: Dict[str, int]
    tasks_total: int
    tasks_completed: int
    tasks_pending: int
    checklists_total: int
    checklists_completed: int
    low_stock_count: int
    expiring_soon_count: int
    on_shift_count: int = 0

# -----------------------------------------------------------------------------
# AI Tool Compatibility Schemas (Preserving Phase 2 tool contract)
# -----------------------------------------------------------------------------
class ListTasksRequest(BaseModel):
    practice_id: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    due_today_only: Optional[bool] = False

class TaskResponseItem(BaseModel):
    id: str
    practice_id: str
    practice_name: str
    title: str
    due_date: str
    status: str
    assigned_to: str
    assigned_staff_name: Optional[str] = None

class ListTasksResponse(BaseModel):
    tenant_id: str
    total_count: int
    tasks: List[TaskResponseItem]

class GetLowStockRequest(BaseModel):
    practice_id: Optional[str] = None
    threshold_multiplier: Optional[float] = Field(default=1.0, ge=0.1, le=5.0)

class LowStockItemResponse(BaseModel):
    id: str
    practice_id: str
    practice_name: str
    item_name: str
    current_stock: int
    min_threshold: int
    unit: str
    shortfall: int
    reorder_recommended: bool

class GetLowStockResponse(BaseModel):
    tenant_id: str
    alert_count: int
    items: List[LowStockItemResponse]

class GetPracticeSummaryRequest(BaseModel):
    practice_id: Optional[str] = None

class PracticeSummaryResponse(BaseModel):
    tenant_id: str
    practice_id: str
    practice_name: str
    location: str
    total_rooms: int
    active_staff_count: int
    today_appointments: int
    pending_tasks_count: int
    low_stock_items_count: int
    staff_roster: List[Dict[str, str]]

# -----------------------------------------------------------------------------
# LangGraph Autonomous AI Schemas
# -----------------------------------------------------------------------------
class ApprovalPendingInfo(BaseModel):
    approval_id: str
    tool_name: str
    description: str
    arguments: Dict[str, Any]

class ToolCallExecution(BaseModel):
    tool: str
    status: str
    duration_ms: Optional[float] = None
    correlation_id: Optional[str] = None
    resource_id: Optional[str] = None

# -----------------------------------------------------------------------------
# Conversation & Private Message Schemas
# -----------------------------------------------------------------------------
class AIMessageRead(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metrics: Optional[Dict[str, Any]] = None
    approval_pending: Optional[Dict[str, Any]] = None
    created_at: Any

    class Config:
        from_attributes = True

class AIConversationBase(BaseModel):
    title: str = "Clinical AI Assistant"

class AIConversationCreate(BaseModel):
    title: Optional[str] = "Clinical AI Assistant"

class AIConversationUpdate(BaseModel):
    title: str

class AIConversationRead(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    title: str
    created_at: Any
    updated_at: Any
    message_count: Optional[int] = 0

    class Config:
        from_attributes = True

class AIConversationDetailRead(AIConversationRead):
    messages: List[AIMessageRead] = []

class AIChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    approval_id: Optional[str] = None
    agent_mode: Optional[str] = None  # "gemini" | "deterministic"

class AIChatResponse(BaseModel):
    reply: str
    conversation_id: Optional[str] = None
    tool_calls_executed: List[ToolCallExecution]
    status: str = "completed"
    approval_pending: Optional[ApprovalPendingInfo] = None
    metrics: Optional[Dict[str, Any]] = None

class AIApproveRequest(BaseModel):
    approval_id: str
    action: str = "approve"  # "approve" | "reject"

class AIApproveResponse(BaseModel):
    success: bool
    detail: str
    status: str
    reply: Optional[str] = None
