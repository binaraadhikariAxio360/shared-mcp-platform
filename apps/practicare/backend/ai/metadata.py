"""
PractiCare Tool Metadata & Risk Classification
Defines type-safe tool definitions, Pydantic input models, and governance flags.
"""

from enum import Enum
from typing import Dict, Any, List, Optional, Type, Callable, Set
from pydantic import BaseModel, Field


class ToolRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def _inline_refs(node: Any, defs: Dict[str, Any]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = dict(defs.get(ref.split("/")[-1], {}))
            target.pop("title", None)
            return _inline_refs(target, defs)
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


class ToolMetadata:
    """Explicit metadata definition for each registered AI tool."""

    def __init__(
        self,
        name: str,
        description: str,
        allowed_roles: List[str],
        required_permissions: Set[str],
        risk_level: ToolRiskLevel,
        is_read_only: bool,
        requires_confirmation: bool,
        input_schema: Type[BaseModel],
        handler: Callable,
        output_schema: Optional[Type[BaseModel]] = None,
        permission_operator: str = "ALL",
        approval_description: Optional[Callable[[Dict[str, Any]], str]] = None,
        prepare_approval: Optional[Callable[..., Any]] = None,
    ):
        self.name = name
        self.description = description
        self.allowed_roles = [r.upper() for r in allowed_roles]
        self.required_permissions = set(required_permissions)
        self.permission_operator = permission_operator.upper()
        self.risk_level = risk_level
        self.is_read_only = is_read_only
        self.requires_confirmation = requires_confirmation
        self.input_schema = input_schema
        self.handler = handler
        self.output_schema = output_schema
        # Optional human-readable text for the approval card (what exactly the user is approving)
        self.approval_description = approval_description
        # Optional (db, context, args) -> (args, description): resolves real records before an approval is created,
        # pins the values the user approves against, and may raise ValueError to refuse before any approval exists
        self.prepare_approval = prepare_approval

    def to_openai_schema(self) -> Dict[str, Any]:
        """Generate OpenAI/LangGraph compatible tool schema."""
        properties = {}
        required = []

        if self.input_schema:
            schema_json = self.input_schema.model_json_schema()
            # Nested models are emitted as $defs references; inline them so the tool schema is self-contained
            properties = _inline_refs(schema_json.get("properties", {}), schema_json.get("$defs", {}))
            required = schema_json.get("required", [])

            # Filter out tenant_id or context injections from LLM exposure
            properties = {
                k: v for k, v in properties.items()
                if k not in ["tenant_id", "user_id", "user_role", "expected_values", "expected_current_stock"]
            }
            required = [r for r in required if r in properties]

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ==============================================================================
# PYDANTIC INPUT ARGUMENT SCHEMAS
# ==============================================================================

class EmptyArgs(BaseModel):
    """Schema for tools requiring no caller arguments."""
    pass


class CreateClinicalTaskArgs(BaseModel):
    title: str = Field(..., description="Clear clinical task title")
    priority: str = Field(default="Medium", description="Priority level: Low, Medium, High, or Critical")
    due_date: str = Field(..., description="Task deadline in YYYY-MM-DD or ISO format")
    room_id: str = Field(..., description="Target exam or procedure room ID")
    assigned_staff_id: Optional[str] = Field(default=None, description="Staff member ID assigned to task")
    description: Optional[str] = Field(default=None, description="Detailed clinical instructions")


class UpdateChecklistStatusArgs(BaseModel):
    checklist_id: str = Field(..., description="Unique checklist identifier")
    is_completed: bool = Field(..., description="Completion state boolean (true/false)")


class DeleteClinicalChecklistArgs(BaseModel):
    checklist_id: str = Field(..., description="Unique checklist identifier to permanently delete")


class SearchRoomsArgs(BaseModel):
    query: Optional[str] = Field(default="", description="Search query: room number (e.g. '101'), room name (e.g. 'Exam Suite'), or exact database ID")


class SearchStaffArgs(BaseModel):
    on_shift: Optional[bool] = Field(default=None, description="Filter true for on-duty staff, false for off-duty staff; omit for all")
    is_active: Optional[bool] = Field(default=None, description="Filter account activation independently from shift status")
    query: Optional[str] = Field(default="", description="Search query: staff name (e.g. 'Dr. Sarah', 'Nurse Mark'), staff ID (e.g. 'stf-001'), role, or department")
    department: Optional[str] = Field(default=None, description="Optional filter by department")
    role: Optional[str] = Field(default=None, description="Optional filter by clinical role (e.g. 'Doctor', 'Nurse', 'Admin')")


class ListTasksArgs(BaseModel):
    task_id: Optional[str] = Field(default=None, description="Optional exact or partial task database ID (e.g. 'tsk-15', '15') to look up a specific task")
    status: Optional[str] = Field(default=None, description="Filter by status: 'Pending', 'In Progress', 'Completed'")
    priority: Optional[str] = Field(default=None, description="Filter by priority: 'Low', 'Medium', 'High', 'Critical'")
    assigned_staff_id: Optional[str] = Field(default=None, description="Filter by assigned staff ID (e.g. 'stf-001')")
    room_id: Optional[str] = Field(default=None, description="Filter by target room ID (e.g. 'room-101')")
    overdue_only: Optional[bool] = Field(default=False, description="Set to true to return only overdue tasks")
    limit: Optional[int] = Field(default=20, description="Maximum number of tasks to return (default 20)")


class UpdateTaskStatusArgs(BaseModel):
    task_id: str = Field(..., description="Unique task database ID (e.g. 'tsk-xxxx') to update")
    status: Optional[str] = Field(default=None, description="New status: 'Pending', 'In Progress', or 'Completed'")
    assigned_staff_id: Optional[str] = Field(default=None, description="Reassign task to staff database ID (e.g. 'stf-xxxx')")
    priority: Optional[str] = Field(default=None, description="New priority: 'Low', 'Medium', 'High', or 'Critical'")
    description: Optional[str] = Field(default=None, description="Updated task notes or clinical instructions")


class GetInventoryStatusArgs(BaseModel):
    low_stock_only: Optional[bool] = Field(default=False, description="Set to true to retrieve only supplies at or below minimum threshold")
    category: Optional[str] = Field(default=None, description="Filter by supply category (e.g. 'Medications', 'PPE', 'Surgical')")
    room_id: Optional[str] = Field(default=None, description="Filter by room ID where item is stored")
    search_query: Optional[str] = Field(default=None, description="Filter by item name or keyword (e.g. 'gloves', 'syringes')")
    item_id: Optional[str] = Field(default=None, description="Exact inventory item_id (e.g. 'inv-1a2b3c4d') for one item's details")
    expiry_filter: Optional[str] = Field(
        default=None,
        description="Expiry filter: 'all', 'expired' (already expired), 'within_7', 'within_30', 'within_90' (expiring within N days from today, not yet expired), or 'none' (no expiry date)",
    )
    sort_by: Optional[str] = Field(default=None, description="'expiry' to sort by nearest expiry date first")


class CreateInventoryItemArgs(BaseModel):
    item_name: str = Field(..., description="Item name exactly as the user stated it")
    quantity: int = Field(..., ge=0, description="Current stock quantity stated by the user (whole number)")
    unit: str = Field(..., description="Unit stated by the user (e.g. 'boxes', 'vials', 'units')")
    min_threshold: Optional[int] = Field(default=None, ge=0, description="Low-stock threshold, only if the user gave one")
    expiry_date: Optional[str] = Field(default=None, description="Expiry date YYYY-MM-DD, only if the user gave one")
    supplier: Optional[str] = Field(default=None, description="Supplier, only if the user gave one")
    batch_number: Optional[str] = Field(default=None, description="Batch/lot number, only if the user gave one")
    purchase_price: Optional[float] = Field(default=None, ge=0, description="Unit purchase price, only if the user gave one")
    room_id: Optional[str] = Field(default=None, description="Storage room database ID (resolve via search_rooms); omit for Central Supply")


class UpdateInventoryItemArgs(BaseModel):
    item_id: Optional[str] = Field(default=None, description="Exact inventory item_id from get_inventory_status (e.g. 'inv-1a2b3c4d')")
    item_query: Optional[str] = Field(default=None, description="Name of the existing item to update when item_id is unknown (resolved against real records; ambiguous names are refused)")
    item_name: Optional[str] = Field(default=None, description="NEW item name (only to rename the item)")
    unit: Optional[str] = Field(default=None, description="New unit")
    min_threshold: Optional[int] = Field(default=None, ge=0, description="New low-stock threshold")
    expiry_date: Optional[str] = Field(default=None, description="New expiry date YYYY-MM-DD")
    supplier: Optional[str] = Field(default=None, description="New supplier")
    batch_number: Optional[str] = Field(default=None, description="New batch/lot number")
    purchase_price: Optional[float] = Field(default=None, ge=0, description="New unit purchase price")
    room_id: Optional[str] = Field(default=None, description="New storage room database ID (resolve via search_rooms)")
    expected_values: Optional[Dict[str, Optional[str]]] = None  # server-set before approval; hidden from the model


class AdjustInventoryStockArgs(BaseModel):
    item_id: Optional[str] = Field(default=None, description="Exact inventory item_id from get_inventory_status (e.g. 'inv-1a2b3c4d')")
    item_query: Optional[str] = Field(default=None, description="Name of the existing item when item_id is unknown (resolved against real records; ambiguous names are refused)")
    quantity_change: int = Field(..., description="Positive number to add stock (received), negative to remove stock (used, discarded)")
    reason: Optional[str] = Field(default=None, description="Short reason, e.g. 'delivery received', 'used in Room 101', 'expired stock discarded'")
    expected_current_stock: Optional[int] = None  # server-set before approval; hidden from the model


class PreviewInventoryImportArgs(BaseModel):
    text: str = Field(..., description="The inventory lines exactly as the user pasted or typed them")


class InventoryImportRowArgs(BaseModel):
    row_id: str = Field(..., description="row_id from preview_inventory_import")
    action: str = Field(..., description="'create', 'restock' (add quantity to existing_item_id) or 'skip'")
    existing_item_id: Optional[str] = Field(default=None, description="Existing item to restock (from the preview match)")
    item_name: Optional[str] = None
    quantity: Optional[int] = None
    unit: Optional[str] = None
    expiry_date: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    purchase_price: Optional[float] = None
    supplier: Optional[str] = None
    batch_number: Optional[str] = None


class ConfirmInventoryImportArgs(BaseModel):
    import_token: str = Field(..., description="import_token from preview_inventory_import confirm_arguments")
    source_hash: str = Field(..., description="source_hash from preview_inventory_import confirm_arguments")
    rows: List[InventoryImportRowArgs] = Field(..., description="Rows from confirm_arguments, with only the user's explicit corrections applied")


class GetPracticeSummaryArgs(BaseModel):
    """Schema for practice summary tool requiring no caller arguments."""
    pass



class CreateRoomArgs(BaseModel):
    room_number: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=100)
    room_type: str = Field(default="Exam", description="Exam, Surgery, Triage, Consultation")
    status: str = Field(default="Available", description="Available, Occupied, Turnover")

class CreateChecklistArgs(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: str = Field(default="Sterilization")
    frequency: str = Field(default="Daily")
    assigned_staff_id: Optional[str] = Field(default=None, description="Exact staff database ID; search_staff first if name supplied")

class ListChecklistsArgs(BaseModel):
    is_completed: Optional[bool] = Field(default=None)
    category: Optional[str] = Field(default=None)
    assigned_staff_id: Optional[str] = Field(default=None)
    limit: int = Field(default=30, ge=1, le=100)

class CreateStaffInvitationArgs(BaseModel):
    role: str = Field(default="NURSE_STAFF", description="NURSE_STAFF, ATTENDING_PHYSICIAN, CLINICAL_AUDITOR, INVENTORY_MANAGER")
    expires_in_days: int = Field(default=7, ge=1, le=30)
    max_uses: int = Field(default=1, ge=1, le=50)


class UpdateChecklistArgs(BaseModel):
    checklist_id: str = Field(..., description="Unique checklist identifier (e.g. 'chk-xxxx')")
    assigned_staff_id: Optional[str] = Field(default=None, description="Staff database ID (e.g. 'stf-xxxx') to assign or reassign, or empty string to unassign")
    title: Optional[str] = Field(default=None, description="Updated checklist title")
    category: Optional[str] = Field(default=None, description="Updated checklist category (e.g. 'Sterilization', 'Hygiene')")
    is_completed: Optional[bool] = Field(default=None, description="Optional completion state boolean")


class UpdateRoomArgs(BaseModel):
    room_id: str = Field(..., description="Unique room database ID (e.g. 'room-xxxx') or room number (e.g. '101')")
    status: Optional[str] = Field(default=None, description="New room status: 'Available', 'Occupied', or 'Turnover'")
    name: Optional[str] = Field(default=None, description="Updated room name")
    room_type: Optional[str] = Field(default=None, description="Updated room type: 'Exam', 'Surgery', 'Triage', 'Consultation'")


class GetChecklistDetailsArgs(BaseModel):
    checklist_id: str = Field(..., description="Unique checklist identifier (e.g. 'chk-xxxx')")


class GetRoomDetailsArgs(BaseModel):
    room_id: str = Field(..., description="Unique room database ID (e.g. 'room-xxxx') or room number")


class GetTaskDetailsArgs(BaseModel):
    task_id: str = Field(..., description="Unique task database ID (e.g. 'tsk-xxxx')")


class GetStaffAvailabilityArgs(BaseModel):
    query: Optional[str] = Field(default=None, description="Staff member name, ID, or role to inspect")
    work_status: Optional[str] = Field(default=None, description="Filter by work status: 'ACTIVE', 'HOLIDAY', 'SICK_LEAVE', 'DND', 'ON_LEAVE'")


class GetOperationalTaskConflictsArgs(BaseModel):
    conflict_type: Optional[str] = Field(
        default=None,
        description="Filter by conflict type: 'holiday_assignment', 'dnd_assignment', 'sick_leave_assignment', 'inactive_login_staff', 'overdue_task', 'unassigned_task', or None for all conflicts"
    )


class SetStaffWorkStatusArgs(BaseModel):
    staff_id: str = Field(..., description="Staff member database ID (e.g. 'stf-xxxx')")
    work_status: str = Field(..., description="New work status: 'ACTIVE', 'HOLIDAY', 'SICK_LEAVE', 'DND', 'ON_LEAVE'")
    duration_days: Optional[int] = Field(default=1, description="Duration in days if marking holiday or leave")
    notes: Optional[str] = Field(default=None, description="Optional notes or reasons for leave")

