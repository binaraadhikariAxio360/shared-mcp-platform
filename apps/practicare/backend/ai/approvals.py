"""Persistent, principal-bound approval workflow for sensitive AI tools."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

import models

# Preserve the existing public import while moving its storage to SQLAlchemy.
PendingApproval = models.AIPendingApproval


def _canonical_arguments(arguments: Dict[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)


def _arguments_hash(arguments: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_arguments(arguments).encode("utf-8")).hexdigest()


class ApprovalManager:
    """Stores approval state in the application database and prevents replay."""

    def __init__(self, default_ttl_minutes: int = 15):
        self.default_ttl_minutes = default_ttl_minutes

    def create_pending_approval(
        self, db: Session, tenant_id: str, user_id: str, user_role: str,
        tool_name: str, arguments: Dict[str, Any], description: str,
    ) -> models.AIPendingApproval:
        now = datetime.utcnow()
        record = models.AIPendingApproval(
            id=f"appr-{uuid.uuid4().hex[:10]}", tenant_id=tenant_id, user_id=user_id,
            user_role=user_role, tool_name=tool_name,
            arguments_json=_canonical_arguments(arguments), arguments_hash=_arguments_hash(arguments),
            description=description, status="PENDING", created_at=now,
            expires_at=now + timedelta(minutes=self.default_ttl_minutes),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get_approval(self, db: Session, approval_id: str) -> Optional[models.AIPendingApproval]:
        record = db.query(models.AIPendingApproval).filter(models.AIPendingApproval.id == approval_id).first()
        if record and record.status == "PENDING" and record.expires_at <= datetime.utcnow():
            record.status = "EXPIRED"
            record.resolved_at = datetime.utcnow()
            db.commit()
            db.refresh(record)
        return record

    def resolve_action(
        self, db: Session, approval_id: str, tenant_id: str, user_id: str,
        user_role: str, action: str,
    ) -> Dict[str, Any]:
        clean_action = action.strip().lower()
        if clean_action not in {"approve", "reject"}:
            return {"success": False, "detail": "Action must be 'approve' or 'reject'."}
        record = self.get_approval(db, approval_id)
        if not record:
            return {"success": False, "detail": "Approval request not found."}
        if record.tenant_id != tenant_id or record.user_id != user_id:
            return {"success": False, "detail": "Approval request does not belong to this authenticated user."}
        if record.user_role != user_role:
            return {"success": False, "detail": "Approval role no longer matches the authenticated user."}
        if record.status != "PENDING":
            return {"success": False, "detail": f"Approval request is already {record.status}."}
        record.status = "APPROVED" if clean_action == "approve" else "REJECTED"
        record.resolved_at = datetime.utcnow()
        db.commit()
        db.refresh(record)
        return {"success": True, "status": record.status, "record": record}

    def claim_execution(
        self, db: Session, approval_id: str, tenant_id: str, user_id: str,
        user_role: str, tool_name: str, arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        record = self.get_approval(db, approval_id)
        if not record:
            return {"valid": False, "error": "Approval request not found."}
        if record.tenant_id != tenant_id or record.user_id != user_id or record.user_role != user_role:
            return {"valid": False, "error": "Approval principal mismatch."}
        if record.tool_name != tool_name or record.arguments_hash != _arguments_hash(arguments):
            return {"valid": False, "error": "Approval action or arguments mismatch."}
        if record.status != "APPROVED":
            return {"valid": False, "error": f"Approval request is {record.status}, not APPROVED."}
        updated = db.query(models.AIPendingApproval).filter(
            models.AIPendingApproval.id == approval_id,
            models.AIPendingApproval.status == "APPROVED",
        ).update({"status": "EXECUTING"}, synchronize_session=False)
        if updated != 1:
            db.rollback()
            return {"valid": False, "error": "Approval request was already claimed."}
        db.commit()
        db.refresh(record)
        return {"valid": True, "arguments": record.arguments, "approval": record}

    def complete_execution(self, db: Session, approval_id: str, success: bool, error_detail: Optional[str] = None):
        record = db.query(models.AIPendingApproval).filter(models.AIPendingApproval.id == approval_id).first()
        if not record or record.status != "EXECUTING":
            return
        record.status = "EXECUTED" if success else "FAILED"
        record.executed_at = datetime.utcnow()
        record.error_detail = error_detail
        db.commit()


approval_manager = ApprovalManager()
