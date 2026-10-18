"""
PractiCare AI Domain Handlers
Exports all 11 clinical management tool handlers decomposed by business domain.
"""

from ai.handlers.tasks import (
    execute_list_tasks,
    execute_create_clinical_task,
    execute_update_task_status,
    execute_get_task_details,
)
from ai.handlers.checklists import (
    execute_update_checklist_status,
    execute_delete_clinical_checklist,
    execute_update_checklist,
    execute_get_checklist_details,
)
from ai.handlers.staff import execute_search_staff
from ai.handlers.rooms import (
    execute_search_rooms,
    execute_get_room_turnover_status,
    execute_update_room,
    execute_get_room_details,
)
from ai.handlers.inventory import execute_get_inventory_status
from ai.handlers.analytics import (
    execute_get_team_task_performance,
    execute_get_practice_summary,
)

__all__ = [
    "execute_list_tasks",
    "execute_create_clinical_task",
    "execute_update_task_status",
    "execute_get_task_details",
    "execute_update_checklist_status",
    "execute_delete_clinical_checklist",
    "execute_update_checklist",
    "execute_get_checklist_details",
    "execute_search_staff",
    "execute_search_rooms",
    "execute_get_room_turnover_status",
    "execute_update_room",
    "execute_get_room_details",
    "execute_get_inventory_status",
    "execute_get_team_task_performance",
    "execute_get_practice_summary",
]

