"""
PractiCare Centralized Tool Registry
Acts as the single source of truth for all clinical management tools.
Dynamically exposes tool definitions and schemas filtered by verified caller role.
"""

from typing import Dict, Any, List, Optional
from ai.metadata import (
    ToolMetadata,
    ToolRiskLevel,
    EmptyArgs,
    CreateClinicalTaskArgs,
    UpdateChecklistStatusArgs,
    DeleteClinicalChecklistArgs,
    SearchRoomsArgs,
    SearchStaffArgs,
    ListTasksArgs,
    UpdateTaskStatusArgs,
    GetInventoryStatusArgs,
    GetPracticeSummaryArgs,
    CreateRoomArgs, CreateChecklistArgs, ListChecklistsArgs, CreateStaffInvitationArgs,
    UpdateChecklistArgs, UpdateRoomArgs, GetChecklistDetailsArgs, GetRoomDetailsArgs, GetTaskDetailsArgs,
    GetStaffAvailabilityArgs, GetOperationalTaskConflictsArgs, SetStaffWorkStatusArgs,
    CreateInventoryItemArgs, UpdateInventoryItemArgs, AdjustInventoryStockArgs,
    PreviewInventoryImportArgs, ConfirmInventoryImportArgs,
)
from ai.tools import (
    execute_get_team_task_performance,
    execute_get_room_turnover_status,
    execute_create_clinical_task,
    execute_update_checklist_status,
    execute_delete_clinical_checklist,
    execute_search_rooms,
    execute_search_staff,
    execute_list_tasks,
    execute_update_task_status,
    execute_get_inventory_status,
    execute_get_practice_summary,
    execute_update_checklist,
    execute_get_checklist_details,
    execute_update_room,
    execute_get_room_details,
    execute_get_task_details,
)

from ai.handlers.operations import (execute_create_room, execute_create_checklist,
    execute_list_checklists, execute_create_staff_invitation)
from ai.handlers.inventory import (
    execute_create_inventory_item,
    execute_update_inventory_item,
    execute_adjust_inventory_stock,
    execute_preview_inventory_import,
    execute_confirm_inventory_import,
    describe_inventory_import,
    prepare_inventory_update,
    prepare_stock_adjustment,
)
from ai.handlers.conflicts import (
    execute_get_operational_task_conflicts,
    execute_get_staff_availability,
    execute_set_staff_work_status,
)

# Canonical role groups (roles are normalized at the identity boundary, so aliases are not needed here).
OWNERS = ["CLINIC_OWNER"]
MANAGERS = OWNERS + ["INVENTORY_MANAGER"]
CLINICAL_WRITERS = MANAGERS + ["ATTENDING_PHYSICIAN"]
CLINICAL_STAFF = CLINICAL_WRITERS + ["NURSE_STAFF"]
# CLINICAL_AUDITOR is read-only: it appears only in read tool groups.
ALL_READERS = CLINICAL_STAFF + ["CLINICAL_AUDITOR"]
# Roles holding 'staff:leave_manage' (see ai/context.py ROLE_PERMISSIONS).
LEAVE_MANAGERS = ["CLINIC_OWNER", "ATTENDING_PHYSICIAN"]
# Inventory writers hold 'inventory:manage' (Owner and Inventory Manager); every clinical role reads inventory.
INVENTORY_MANAGERS = MANAGERS
INVENTORY_WRITE_TOOLS = frozenset({
    "create_inventory_item", "update_inventory_item", "adjust_inventory_stock",
    "preview_inventory_import", "confirm_inventory_import",
})

class ToolRegistry:
    """Central repository and schema provider for all PractiCare AI tools."""

    def __init__(self):
        self._tools: Dict[str, ToolMetadata] = {}
        self._register_default_tools()

    def register(self, tool: ToolMetadata):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolMetadata]:
        return self._tools.get(name)

    def get_all(self) -> List[ToolMetadata]:
        return list(self._tools.values())

    def get_tools_for_role(self, role: str) -> List[ToolMetadata]:
        """Expose only tools permitted for the caller's verified role."""
        clean_role = role.upper()
        return [tool for tool in self._tools.values() if clean_role in tool.allowed_roles]

    def get_schemas_for_role(self, role: str) -> List[Dict[str, Any]]:
        """Return OpenAI / LangGraph tool schemas visible to this role."""
        return [tool.to_openai_schema() for tool in self.get_tools_for_role(role)]

    def _register_default_tools(self):
        # Additional real database tools; all go through the existing gateway.
        self.register(ToolMetadata(
            name="create_room", description="Create a room in the authenticated company. Owner and Manager only. Requires room_number and name.",
            allowed_roles=MANAGERS, required_permissions={"rooms:manage"},
            risk_level=ToolRiskLevel.MEDIUM, is_read_only=False, requires_confirmation=False,
            input_schema=CreateRoomArgs, handler=execute_create_room))
        self.register(ToolMetadata(
            name="update_room", description="Updates room status ('Available', 'Occupied', 'Turnover'), name, or room type. Requires room_id.",
            allowed_roles=CLINICAL_WRITERS,
            required_permissions={"rooms:manage"}, risk_level=ToolRiskLevel.MEDIUM,
            is_read_only=False, requires_confirmation=False, input_schema=UpdateRoomArgs, handler=execute_update_room))
        self.register(ToolMetadata(
            name="get_room_details", description="Retrieves complete details of a specific room by database room_id or room number within current tenant.",
            allowed_roles=CLINICAL_STAFF,
            required_permissions={"rooms:view"}, risk_level=ToolRiskLevel.LOW,
            is_read_only=True, requires_confirmation=False, input_schema=GetRoomDetailsArgs, handler=execute_get_room_details))
        self.register(ToolMetadata(
            name="create_checklist", description="Create a checklist in the current company; resolve optional assignee via search_staff first.",
            allowed_roles=CLINICAL_WRITERS,
            required_permissions={"checklists:update"}, risk_level=ToolRiskLevel.MEDIUM,
            is_read_only=False, requires_confirmation=False, input_schema=CreateChecklistArgs, handler=execute_create_checklist))
        self.register(ToolMetadata(
            name="update_checklist", description="Assign or reassign staff to an existing checklist, or update checklist title or category. Requires checklist_id.",
            allowed_roles=CLINICAL_WRITERS,
            required_permissions={"checklists:update"}, risk_level=ToolRiskLevel.MEDIUM,
            is_read_only=False, requires_confirmation=False, input_schema=UpdateChecklistArgs, handler=execute_update_checklist))
        self.register(ToolMetadata(
            name="get_checklist_details", description="Retrieves complete details of a specific checklist by ID within current tenant.",
            allowed_roles=ALL_READERS,
            required_permissions={"checklists:view"}, risk_level=ToolRiskLevel.LOW,
            is_read_only=True, requires_confirmation=False, input_schema=GetChecklistDetailsArgs, handler=execute_get_checklist_details))
        self.register(ToolMetadata(
            name="list_checklists", description="Read real checklists, filter completed/incomplete, category or assignee.",
            allowed_roles=ALL_READERS,
            required_permissions={"checklists:view"}, risk_level=ToolRiskLevel.LOW,
            is_read_only=True, requires_confirmation=False, input_schema=ListChecklistsArgs, handler=execute_list_checklists))
        self.register(ToolMetadata(
            name="get_task_details", description="Retrieves full clinical task details by task ID within current tenant.",
            allowed_roles=ALL_READERS,
            required_permissions={"tasks:view"}, risk_level=ToolRiskLevel.LOW,
            is_read_only=True, requires_confirmation=False, input_schema=GetTaskDetailsArgs, handler=execute_get_task_details))
        self.register(ToolMetadata(
            name="create_staff_invitation", description="Owner creates a staff invitation code. This does not directly create or approve a staff account; user must join and owner must approve.",
            allowed_roles=OWNERS, required_permissions={"staff:manage"},
            risk_level=ToolRiskLevel.MEDIUM, is_read_only=False, requires_confirmation=False,
            input_schema=CreateStaffInvitationArgs, handler=execute_create_staff_invitation))

        # 1. get_team_task_performance
        self.register(
            ToolMetadata(
                name="get_team_task_performance",
                description="Analyzes clinical task completion rates, overdue tasks, pending bottlenecks, and operational workloads for the clinic.",
                allowed_roles=ALL_READERS,
                required_permissions={"tasks:view_all", "tasks:view_department", "tasks:view_operational", "tasks:view_audit"},
                permission_operator="ANY",
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=EmptyArgs,
                handler=execute_get_team_task_performance,
            )
        )

        # 2. get_room_turnover_status
        self.register(
            ToolMetadata(
                name="get_room_turnover_status",
                description="Fetches live exam/surgery room statuses (Available, Occupied, Turnover, Cleaning needed).",
                allowed_roles=CLINICAL_STAFF,
                required_permissions={"rooms:view"},
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=EmptyArgs,
                handler=execute_get_room_turnover_status,
            )
        )

        # 3. search_rooms (Read-only room resolution tool)
        self.register(
            ToolMetadata(
                name="search_rooms",
                description="Searches and resolves clinical rooms by room number (e.g. '101'), name, or ID within the authenticated tenant. Returns actual database room_id and safe display label.",
                allowed_roles=CLINICAL_STAFF,
                required_permissions={"rooms:view"},
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=SearchRoomsArgs,
                handler=execute_search_rooms,
            )
        )

        # 4. search_staff (Read-only staff resolution tool)
        self.register(
            ToolMetadata(
                name="search_staff",
                description="List and filter real tenant staff. For off-duty names call search_staff(on_shift=false, query=''); for on-duty call on_shift=true. Supports names, roles and IDs. Never search follow-up pronouns literally.",
                allowed_roles=CLINICAL_STAFF,
                required_permissions={"staff:view"},
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=SearchStaffArgs,
                handler=execute_search_staff,
            )
        )

        # 5. list_tasks (Read-only task query and filter tool)
        self.register(
            ToolMetadata(
                name="list_tasks",
                description="Retrieves clinical tasks filtered by status ('Pending', 'In Progress', 'Completed'), priority, assigned staff ID, room ID, or overdue status.",
                allowed_roles=ALL_READERS,
                required_permissions={"tasks:view"},
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=ListTasksArgs,
                handler=execute_list_tasks,
            )
        )

        # 6. create_clinical_task
        self.register(
            ToolMetadata(
                name="create_clinical_task",
                description="Creates a new clinical task for a specific room and assigned staff member. Owner, Manager, and Doctor only.",
                allowed_roles=CLINICAL_WRITERS,
                required_permissions={"tasks:create"},
                risk_level=ToolRiskLevel.MEDIUM,
                is_read_only=False,
                requires_confirmation=False,
                input_schema=CreateClinicalTaskArgs,
                handler=execute_create_clinical_task,
            )
        )

        # 7. update_task_status
        self.register(
            ToolMetadata(
                name="update_task_status",
                description="Updates an existing clinical task: mark completed, change status ('Pending', 'In Progress', 'Completed'), update priority, or reassign to another staff ID.",
                allowed_roles=CLINICAL_STAFF,
                required_permissions={"tasks:update", "tasks:update_status"},
                permission_operator="ANY",
                risk_level=ToolRiskLevel.MEDIUM,
                is_read_only=False,
                requires_confirmation=False,
                input_schema=UpdateTaskStatusArgs,
                handler=execute_update_task_status,
            )
        )

        # 8. get_inventory_status
        self.register(
            ToolMetadata(
                name="get_inventory_status",
                description="Retrieves real medical supply inventory: stock levels, low-stock and out-of-stock alerts, expiry dates (filter expired / expiring within 7, 30 or 90 days / no expiry; sort by nearest expiry), supplier, batch and item details. Read-only; accessible by all clinical roles. Always call this before answering any inventory question.",
                allowed_roles=CLINICAL_STAFF,
                required_permissions={"inventory:view"},
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=GetInventoryStatusArgs,
                handler=execute_get_inventory_status,
            )
        )

        # 9. get_practice_summary
        self.register(
            ToolMetadata(
                name="get_practice_summary",
                description="Retrieves a high-level operational overview of the clinic: facility rooms, task completion rate, on-shift staff counts, and inventory alerts.",
                allowed_roles=ALL_READERS,
                required_permissions={"practice:view_summary"},
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=GetPracticeSummaryArgs,
                handler=execute_get_practice_summary,
            )
        )

        # 10. update_checklist_status
        self.register(
            ToolMetadata(
                name="update_checklist_status",
                description="Updates or toggles completion status for sterilization/hygiene checklists.",
                allowed_roles=CLINICAL_STAFF,
                required_permissions={"checklists:update"},
                risk_level=ToolRiskLevel.MEDIUM,
                is_read_only=False,
                requires_confirmation=False,
                input_schema=UpdateChecklistStatusArgs,
                handler=execute_update_checklist_status,
            )
        )

        # 11. delete_clinical_checklist
        self.register(
            ToolMetadata(
                name="delete_clinical_checklist",
                description="Deletes a checklist record from the database. Owner, Manager, and Doctor (within scope) only. Destructive.",
                allowed_roles=CLINICAL_WRITERS,
                required_permissions={"checklists:delete"},
                risk_level=ToolRiskLevel.HIGH,
                is_read_only=False,
                requires_confirmation=True,  # Human approval required
                input_schema=DeleteClinicalChecklistArgs,
                handler=execute_delete_clinical_checklist,
            )
        )

        # 12. get_operational_task_conflicts
        self.register(
            ToolMetadata(
                name="get_operational_task_conflicts",
                description="Identifies clinical tasks and checklists assigned to staff on holiday, sick leave, or Do Not Disturb (DND); tasks assigned to staff with no recent login events; overdue tasks; and unassigned tasks in the triage queue.",
                allowed_roles=ALL_READERS,
                required_permissions={"tasks:conflict_view"},
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=GetOperationalTaskConflictsArgs,
                handler=execute_get_operational_task_conflicts,
            )
        )

        # 13. get_staff_availability_and_leaves
        self.register(
            ToolMetadata(
                name="get_staff_availability_and_leaves",
                description="Retrieves staff availability, current work status (ACTIVE, HOLIDAY, SICK_LEAVE, DND), scheduled approved leaves, and last recorded login timestamp within the current tenant.",
                allowed_roles=ALL_READERS,
                required_permissions={"staff:leave_view"},
                risk_level=ToolRiskLevel.LOW,
                is_read_only=True,
                requires_confirmation=False,
                input_schema=GetStaffAvailabilityArgs,
                handler=execute_get_staff_availability,
            )
        )

        # 14. set_staff_work_status
        self.register(
            ToolMetadata(
                name="set_staff_work_status",
                description="Updates a staff member's work status ('ACTIVE', 'HOLIDAY', 'SICK_LEAVE', 'DND', 'ON_LEAVE') or logs scheduled holiday/leave. Owner, Manager, and Attending Physician only.",
                allowed_roles=LEAVE_MANAGERS,
                required_permissions={"staff:leave_manage"},
                risk_level=ToolRiskLevel.MEDIUM,
                is_read_only=False,
                requires_confirmation=False,
                input_schema=SetStaffWorkStatusArgs,
                handler=execute_set_staff_work_status,
            )
        )

        # 15-19. Inventory management (Owner / Inventory Manager only; Doctors and Nurses are read-only)
        self.register(ToolMetadata(
            name="create_inventory_item",
            description="Creates ONE new inventory record from values the user explicitly stated (name, quantity, unit; optional expiry YYYY-MM-DD, supplier, batch, unit price, min threshold, room). Never invent missing values. Refuses exact duplicates (same name, batch and expiry); use adjust_inventory_stock for those. Owner and Manager only.",
            allowed_roles=INVENTORY_MANAGERS, required_permissions={"inventory:manage"},
            risk_level=ToolRiskLevel.MEDIUM, is_read_only=False, requires_confirmation=False,
            input_schema=CreateInventoryItemArgs, handler=execute_create_inventory_item))
        self.register(ToolMetadata(
            name="update_inventory_item",
            description="Updates descriptive fields (name, unit, min threshold, expiry, supplier, batch, unit price, room) of ONE existing inventory record, identified by item_id from get_inventory_status or by item_query (its current name). Does not change stock. Never creates items. Requires user approval of the exact old -> new values. Owner and Manager only.",
            allowed_roles=INVENTORY_MANAGERS, required_permissions={"inventory:manage"},
            risk_level=ToolRiskLevel.MEDIUM, is_read_only=False, requires_confirmation=True,
            input_schema=UpdateInventoryItemArgs, handler=execute_update_inventory_item,
            prepare_approval=prepare_inventory_update))
        self.register(ToolMetadata(
            name="adjust_inventory_stock",
            description="Restocks (positive quantity_change) or reduces (negative) the stock of ONE existing item, identified by item_id or item_query (its name). Stock cannot go below zero. Never creates items. Requires user approval showing current quantity, change and new quantity. Owner and Manager only.",
            allowed_roles=INVENTORY_MANAGERS, required_permissions={"inventory:manage"},
            risk_level=ToolRiskLevel.MEDIUM, is_read_only=False, requires_confirmation=True,
            input_schema=AdjustInventoryStockArgs, handler=execute_adjust_inventory_stock,
            prepare_approval=prepare_stock_adjustment))
        self.register(ToolMetadata(
            name="preview_inventory_import",
            description="Step 1 of importing several inventory lines pasted into chat: AI-extracts records and returns a review preview with missing/ambiguous/low-confidence flags and duplicate matches. Saves NOTHING. Owner and Manager only. For PDF or image files, tell the user to use Inventory > Import.",
            allowed_roles=INVENTORY_MANAGERS, required_permissions={"inventory:manage"},
            risk_level=ToolRiskLevel.LOW, is_read_only=False, requires_confirmation=False,
            input_schema=PreviewInventoryImportArgs, handler=execute_preview_inventory_import))
        self.register(ToolMetadata(
            name="confirm_inventory_import",
            description="Step 2 of a chat import: saves the reviewed rows from preview_inventory_import confirm_arguments, only after the user confirms. Requires user approval of the exact rows. Owner and Manager only.",
            allowed_roles=INVENTORY_MANAGERS, required_permissions={"inventory:manage"},
            risk_level=ToolRiskLevel.HIGH, is_read_only=False, requires_confirmation=True,
            input_schema=ConfirmInventoryImportArgs, handler=execute_confirm_inventory_import,
            approval_description=describe_inventory_import))


registry = ToolRegistry()
