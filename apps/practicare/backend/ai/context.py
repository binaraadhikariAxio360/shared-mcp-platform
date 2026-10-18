"""
PractiCare Security Context
Defines verified execution identity strictly isolated from LLM prompt inputs.
"""

from dataclasses import dataclass, field
from typing import Set, Optional


ROLE_PERMISSIONS = {
    "CLINIC_OWNER": {
        "tasks:view_all",
        "tasks:create",
        "tasks:update",
        "tasks:delete",
        "checklists:view",
        "checklists:update",
        "checklists:delete",
        "rooms:view",
        "rooms:manage",
        "inventory:view",
        "inventory:manage",
        "staff:view_all",
        "staff:manage",
        "staff:view",
        "staff:leave_view",
        "staff:leave_manage",
        "tasks:view",
        "tasks:conflict_view",
        "practice:view_summary",
        "analytics:executive",
        "analytics:audit",
    },
    "OWNER": {
        "tasks:view_all",
        "tasks:create",
        "tasks:update",
        "tasks:delete",
        "checklists:view",
        "checklists:update",
        "checklists:delete",
        "rooms:view",
        "rooms:manage",
        "inventory:view",
        "inventory:manage",
        "staff:view_all",
        "staff:manage",
        "staff:view",
        "staff:leave_view",
        "staff:leave_manage",
        "tasks:view",
        "tasks:conflict_view",
        "practice:view_summary",
        "analytics:executive",
        "analytics:audit",
    },
    "INVENTORY_MANAGER": {
        "tasks:view_all",
        "tasks:create",
        "tasks:update",
        "tasks:delete",
        "tasks:view",
        "tasks:conflict_view",
        "checklists:view",
        "checklists:update",
        "checklists:delete",
        "rooms:view",
        "rooms:manage",
        "inventory:view",
        "inventory:manage",
        "staff:view",
        "staff:leave_view",
        "practice:view_summary",
    },
    "MANAGER": {
        "tasks:view_all",
        "tasks:create",
        "tasks:update",
        "tasks:delete",
        "tasks:view",
        "tasks:conflict_view",
        "checklists:view",
        "checklists:update",
        "checklists:delete",
        "rooms:view",
        "rooms:manage",
        "inventory:view",
        "inventory:manage",
        "staff:view",
        "staff:leave_view",
        "practice:view_summary",
    },
    "CLINIC_MANAGER": {
        "tasks:view_all",
        "tasks:create",
        "tasks:update",
        "tasks:delete",
        "tasks:view",
        "tasks:conflict_view",
        "checklists:view",
        "checklists:update",
        "checklists:delete",
        "rooms:view",
        "rooms:manage",
        "inventory:view",
        "inventory:manage",
        "staff:view",
        "staff:leave_view",
        "practice:view_summary",
    },
    "ATTENDING_PHYSICIAN": {
        "tasks:view_department",
        "tasks:create",
        "tasks:update",
        "tasks:delete",
        "checklists:view",
        "checklists:update",
        "checklists:delete",
        "rooms:view",
        "rooms:manage",
        "inventory:view",
        "analytics:clinical",
        "staff:view",
        "staff:leave_view",
        "staff:leave_manage",
        "tasks:view",
        "tasks:conflict_view",
        "practice:view_summary",
    },
    "DOCTOR": {
        "tasks:view_department",
        "tasks:create",
        "tasks:update",
        "tasks:delete",
        "checklists:view",
        "checklists:update",
        "checklists:delete",
        "rooms:view",
        "rooms:manage",
        "inventory:view",
        "analytics:clinical",
        "staff:view",
        "staff:leave_view",
        "staff:leave_manage",
        "tasks:view",
        "tasks:conflict_view",
        "practice:view_summary",
    },
    "CLINICAL_AUDITOR": {
        "tasks:view_audit",
        "checklists:view",
        "analytics:audit_aggregate",
        "staff:view",
        "staff:leave_view",
        "tasks:view",
        "tasks:conflict_view",
        "practice:view_summary",
    },
    "NURSE_STAFF": {
        "tasks:view_operational",
        "tasks:update_status",
        "checklists:view",
        "checklists:update",
        "rooms:view",
        "inventory:view",
        "analytics:operational",
        "staff:view",
        "staff:leave_view",
        "tasks:view",
        "tasks:conflict_view",
        "practice:view_summary",
    },
    "NURSE": {
        "tasks:view_operational",
        "tasks:update_status",
        "checklists:view",
        "checklists:update",
        "rooms:view",
        "inventory:view",
        "analytics:operational",
        "staff:view",
        "staff:leave_view",
        "tasks:view",
        "tasks:conflict_view",
        "practice:view_summary",
    },
}


# Stored role strings that are aliases of a canonical role. Roles are normalized once at the
# identity boundary so every downstream check (policy, registry, permissions) sees one spelling.
ROLE_ALIASES = {
    "OWNER": "CLINIC_OWNER",
    "MANAGER": "INVENTORY_MANAGER",
    "CLINIC_MANAGER": "INVENTORY_MANAGER",
    "DOCTOR": "ATTENDING_PHYSICIAN",
    "PHYSICIAN": "ATTENDING_PHYSICIAN",
    "NURSE": "NURSE_STAFF",
}


def normalize_role(role: Optional[str]) -> str:
    """Returns the canonical role for a stored role string ('' if empty)."""
    clean = str(role or "").strip().upper()
    return ROLE_ALIASES.get(clean, clean)


def is_known_role(role: Optional[str]) -> bool:
    return normalize_role(role) in ROLE_PERMISSIONS


@dataclass(frozen=True)
class SecurityContext:
    tenant_id: str
    user_id: str
    user_role: str
    company_name: str = "Vanguard Comprehensive Health Center"
    permissions: Set[str] = field(default_factory=set)

    @classmethod
    def create(
        cls,
        tenant_id: str,
        user_id: str,
        user_role: str,
        company_name: Optional[str] = None,
        custom_permissions: Optional[Set[str]] = None,
    ) -> "SecurityContext":
        if not tenant_id or not user_id or not user_role:
            raise ValueError("Verified tenant, user, and role are required")
        clean_tenant = tenant_id.strip()
        clean_role = normalize_role(user_role)
        clean_user = user_id.strip()
        if not clean_tenant or not clean_user or clean_role not in ROLE_PERMISSIONS:
            raise ValueError("Invalid verified security context")
        clean_company = company_name.strip() if company_name else "Vanguard Comprehensive Health Center"

        base_perms = set(ROLE_PERMISSIONS.get(clean_role, set()))
        if custom_permissions:
            base_perms.update(custom_permissions)

        return cls(
            tenant_id=clean_tenant,
            user_id=clean_user,
            user_role=clean_role,
            company_name=clean_company,
            permissions=base_perms,
        )

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def has_role(self, role: str) -> bool:
        return self.user_role == role.upper()
