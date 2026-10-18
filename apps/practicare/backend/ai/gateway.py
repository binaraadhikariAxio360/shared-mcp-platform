"""
PractiCare Tool Gateway & Security Interceptor
Governs every tool invocation: RBAC, Multi-Tenant partitioning, Pydantic validation,
Human-in-the-Loop approvals for HIGH risk actions, Executive Data Protection, and Audit Logging.
"""

import time
import logging
import uuid
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import ValidationError

from ai.context import SecurityContext
from ai.metadata import ToolMetadata, ToolRiskLevel
from ai.registry import registry
from ai.approvals import approval_manager
import models
from ai.helpers import is_task_assigned_to_user, is_checklist_assigned_to_user, normalize_task_id_candidates
from ai.policy import (
    can_user_update_task,
    can_user_delete_task,
    can_user_create_task,
    can_user_update_checklist,
    can_user_delete_checklist,
    can_user_create_checklist,
    can_user_view_task,
    can_user_update_room,
)

logger = logging.getLogger("practicare.ai.gateway")


def _update_fields(args: Dict[str, Any], id_key: str) -> Dict[str, Any]:
    """Fields a tool call actually changes: excludes the target identifier, injected tenant and unset (None) values."""
    return {k: v for k, v in args.items() if k not in (id_key, "tenant_id") and v is not None}


class ToolGateway:
    """
    Zero-Trust Security Gateway placed between LangGraph and domain execution.
    The AI must never access the database directly; all executions pass through here.
    """

    def __init__(self):
        self._execution_history: Dict[str, float] = {}  # Rate limiting and idempotency

    def get_audit_logs(self, db: Session, tenant_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Retrieve recent recent audit records for one authenticated tenant."""
        records = db.query(models.AIAuditEvent).filter(
            models.AIAuditEvent.tenant_id == tenant_id,
        ).order_by(models.AIAuditEvent.timestamp.desc()).limit(min(max(limit, 1), 500)).all()
        return [{
            "id": row.id, "timestamp": row.timestamp.isoformat(), "tenant_id": row.tenant_id,
            "user_id": row.user_id, "user_role": row.user_role, "tool_name": row.tool_name,
            "input_args": json.loads(row.input_args_json), "status": row.status,
            "error_detail": row.error_detail, "latency_ms": row.latency_ms,
        } for row in records]

    def validate_sensitive_query(self, message: str, context: SecurityContext) -> Optional[str]:
        """
        Executive Data Protection:
        Detects if non-CLINIC_OWNER attempts to prompt or inspect salaries, contractor rates,
        doctor evaluations, or private administrative logs.
        """
        if context.has_role("CLINIC_OWNER") or context.has_role("OWNER"):
            return None

        sensitive_keywords = [
            "salary", "salaries", "compensation", "payroll", "hourly rate",
            "billing rate", "doctor evaluation", "physician evaluation",
            "doctor performance review", "physician score", "executive bonus"
        ]

        lower_msg = message.lower()
        for kw in sensitive_keywords:
            if kw in lower_msg:
                return "Access Denied: You do not have sufficient administrative privileges to view executive task analyses or compensation data."

        return None

    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: SecurityContext,
        db: Session,
        approval_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a registered tool under strict governance:
          1. Verify authenticated principal.
          2. Resolve tool metadata from Registry.
          3. Enforce Role-Based Access Control (RBAC).
          4. Force tenant partition (record.tenant_id == context.tenant_id).
          5. Validate arguments using Pydantic schemas.
          6. Enforce Human-In-The-Loop approval for HIGH risk actions.
          7. Strip sensitive parameters for non-owner roles.
          8. Execute registered handler and record immutable audit log.
        """
        start_time = time.perf_counter()
        log_id = f"aud-{uuid.uuid4().hex[:8]}"

        # 1. Resolve tool metadata
        tool: Optional[ToolMetadata] = registry.get(tool_name)
        if not tool:
            latency = round((time.perf_counter() - start_time) * 1000, 2)
            self._record_audit(
                db=db,
                log_id=log_id,
                context=context,
                tool_name=tool_name,
                input_args=arguments,
                status="BLOCKED",
                error_detail=f"Unknown tool: '{tool_name}'",
                latency_ms=latency,
            )
            return {
                "error": "NOT_FOUND",
                "detail": f"Tool '{tool_name}' is not recognized in PractiCare AI registry.",
            }

        # 2. Context Injection & Anti-Spoofing: overwrite tenant_id with verified context
        clean_args = dict(arguments or {})
        clean_args["tenant_id"] = context.tenant_id
        # Never trust caller-supplied tenant_id, user_id, user_role, or permissions in arguments
        clean_args.pop("user_id", None)
        clean_args.pop("user_role", None)
        clean_args.pop("permissions", None)

        # 3. RBAC Verification & Centralized Policy Enforcement
        # Object-level policy checks; the role and permission checks below always apply as well.

        if tool_name == "update_task_status":
            t_id = str(clean_args.get("task_id") or "").strip()
            if t_id:
                t_obj = db.query(models.Task).filter(
                    models.Task.id == t_id,
                    models.Task.tenant_id == context.tenant_id,
                ).first()
                if not t_obj:
                    for alt in normalize_task_id_candidates(t_id):
                        t_obj = db.query(models.Task).filter(
                            models.Task.id == alt,
                            models.Task.tenant_id == context.tenant_id,
                        ).first()
                        if t_obj:
                            break
                if t_obj:
                    allowed, reason = can_user_update_task(
                        context.user_role, context.user_id, t_obj, _update_fields(clean_args, "task_id"), db
                    )
                    if not allowed:
                        latency = round((time.perf_counter() - start_time) * 1000, 2)
                        refusal_msg = f"RBAC Denied: {reason}"
                        self._record_audit(
                            db=db, log_id=log_id, context=context, tool_name=tool_name,
                            input_args=clean_args, status="BLOCKED", error_detail=refusal_msg, latency_ms=latency,
                        )
                        return {"error": "FORBIDDEN", "detail": refusal_msg}

        elif tool_name in ("update_checklist_status", "update_checklist"):
            chk_id = str(clean_args.get("checklist_id") or "").strip()
            if chk_id:
                chk_obj = db.query(models.Checklist).filter(
                    models.Checklist.id == chk_id,
                    models.Checklist.tenant_id == context.tenant_id,
                ).first()
                if chk_obj:
                    allowed, reason = can_user_update_checklist(
                        context.user_role, context.user_id, chk_obj, _update_fields(clean_args, "checklist_id"), db
                    )
                    if not allowed:
                        latency = round((time.perf_counter() - start_time) * 1000, 2)
                        refusal_msg = f"RBAC Denied: {reason}"
                        self._record_audit(
                            db=db, log_id=log_id, context=context, tool_name=tool_name,
                            input_args=clean_args, status="BLOCKED", error_detail=refusal_msg, latency_ms=latency,
                        )
                        return {"error": "FORBIDDEN", "detail": refusal_msg}

        elif tool_name == "delete_clinical_task":
            t_id = str(clean_args.get("task_id") or "").strip()
            if t_id:
                t_obj = db.query(models.Task).filter(
                    models.Task.id == t_id,
                    models.Task.tenant_id == context.tenant_id,
                ).first()
                if t_obj:
                    allowed, reason = can_user_delete_task(context.user_role, context.user_id, t_obj, db)
                    if not allowed:
                        latency = round((time.perf_counter() - start_time) * 1000, 2)
                        refusal_msg = f"RBAC Denied: {reason}"
                        self._record_audit(
                            db=db, log_id=log_id, context=context, tool_name=tool_name,
                            input_args=clean_args, status="BLOCKED", error_detail=refusal_msg, latency_ms=latency,
                        )
                        return {"error": "FORBIDDEN", "detail": refusal_msg}

        elif tool_name == "delete_clinical_checklist":
            chk_id = str(clean_args.get("checklist_id") or "").strip()
            if chk_id:
                chk_obj = db.query(models.Checklist).filter(
                    models.Checklist.id == chk_id,
                    models.Checklist.tenant_id == context.tenant_id,
                ).first()
                if chk_obj:
                    allowed, reason = can_user_delete_checklist(context.user_role, context.user_id, chk_obj, db)
                    if not allowed:
                        latency = round((time.perf_counter() - start_time) * 1000, 2)
                        refusal_msg = f"RBAC Denied: {reason}"
                        self._record_audit(
                            db=db, log_id=log_id, context=context, tool_name=tool_name,
                            input_args=clean_args, status="BLOCKED", error_detail=refusal_msg, latency_ms=latency,
                        )
                        return {"error": "FORBIDDEN", "detail": refusal_msg}

        elif tool_name == "create_clinical_task":
            assigned_stf = clean_args.get("assigned_staff_id")
            allowed, reason = can_user_create_task(context.user_role, assigned_stf, db, context.tenant_id, context.user_id)
            if not allowed:
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                refusal_msg = f"RBAC Denied: {reason}"
                self._record_audit(
                    db=db, log_id=log_id, context=context, tool_name=tool_name,
                    input_args=clean_args, status="BLOCKED", error_detail=refusal_msg, latency_ms=latency,
                )
                return {"error": "FORBIDDEN", "detail": refusal_msg}

        elif tool_name == "create_checklist":
            allowed, reason = can_user_create_checklist(context.user_role)
            if not allowed:
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                refusal_msg = f"RBAC Denied: {reason}"
                self._record_audit(
                    db=db, log_id=log_id, context=context, tool_name=tool_name,
                    input_args=clean_args, status="BLOCKED", error_detail=refusal_msg, latency_ms=latency,
                )
                return {"error": "FORBIDDEN", "detail": refusal_msg}

        elif tool_name == "update_room":
            allowed, reason = can_user_update_room(context.user_role, _update_fields(clean_args, "room_id"))
            if not allowed:
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                refusal_msg = f"RBAC Denied: {reason}"
                self._record_audit(
                    db=db, log_id=log_id, context=context, tool_name=tool_name,
                    input_args=clean_args, status="BLOCKED", error_detail=refusal_msg, latency_ms=latency,
                )
                return {"error": "FORBIDDEN", "detail": refusal_msg}

        elif tool_name in ("get_task_details", "explain_task"):
            t_id = str(clean_args.get("task_id") or "").strip()
            if t_id:
                t_obj = db.query(models.Task).filter(
                    models.Task.id == t_id,
                    models.Task.tenant_id == context.tenant_id,
                ).first()
                if not t_obj:
                    for alt in normalize_task_id_candidates(t_id):
                        t_obj = db.query(models.Task).filter(
                            models.Task.id == alt,
                            models.Task.tenant_id == context.tenant_id,
                        ).first()
                        if t_obj:
                            break
                if t_obj and not can_user_view_task(context.user_role, context.user_id, t_obj, db):
                    latency = round((time.perf_counter() - start_time) * 1000, 2)
                    refusal_msg = f"RBAC Denied: Role {context.user_role} is not permitted to view restricted task details."
                    self._record_audit(
                        db=db, log_id=log_id, context=context, tool_name=tool_name,
                        input_args=clean_args, status="BLOCKED", error_detail=refusal_msg, latency_ms=latency,
                    )
                    return {"error": "FORBIDDEN", "detail": refusal_msg}

        if context.user_role not in tool.allowed_roles:
            latency = round((time.perf_counter() - start_time) * 1000, 2)
            refusal_msg = f"RBAC Denied: Role {context.user_role} is not permitted to execute {tool_name}."
            self._record_audit(
                db=db,
                log_id=log_id,
                context=context,
                tool_name=tool_name,
                input_args=clean_args,
                status="BLOCKED",
                error_detail=refusal_msg,
                latency_ms=latency,
            )
            logger.warning(
                "Security Alert: RBAC violation prevented. User '%s' with role '%s' attempted to execute '%s'",
                context.user_id,
                context.user_role,
                tool_name,
            )
            return {
                "error": "FORBIDDEN",
                "detail": refusal_msg,
            }

        # 3b. Verify declared permission requirements against authenticated context
        if tool.required_permissions:
            perm_op = getattr(tool, "permission_operator", "ALL").upper()
            if perm_op == "ANY":
                has_perm = any(context.has_permission(p) for p in tool.required_permissions)
            else:
                has_perm = all(context.has_permission(p) for p in tool.required_permissions)

            if not has_perm:
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                refusal_msg = f"Permission Denied: User role '{context.user_role}' lacks required permission(s) for '{tool_name}'."
                self._record_audit(
                    db=db,
                    log_id=log_id,
                    context=context,
                    tool_name=tool_name,
                    input_args=clean_args,
                    status="BLOCKED",
                    error_detail=refusal_msg,
                    latency_ms=latency,
                )
                return {
                    "error": "FORBIDDEN",
                    "detail": refusal_msg,
                }

        # 4. Pydantic Argument Validation
        if tool.input_schema:
            try:
                # Validate input parameters
                validated_model = tool.input_schema(**clean_args)
                clean_args.update(validated_model.model_dump())
            except ValidationError as val_err:
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                err_detail = f"Argument validation failed: {val_err.errors()}"
                self._record_audit(
                    db=db,
                    log_id=log_id,
                    context=context,
                    tool_name=tool_name,
                    input_args=clean_args,
                    status="ERROR",
                    error_detail=err_detail,
                    latency_ms=latency,
                )
                return {
                    "error": "VALIDATION_ERROR",
                    "detail": err_detail,
                }
            except Exception as e:
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                self._record_audit(
                    db=db,
                    log_id=log_id,
                    context=context,
                    tool_name=tool_name,
                    input_args=clean_args,
                    status="ERROR",
                    error_detail=str(e),
                    latency_ms=latency,
                )
                return {
                    "error": "VALIDATION_ERROR",
                    "detail": str(e),
                }

        # 5. Human-in-the-Loop Approval for HIGH Risk / Destructive Actions
        if tool.requires_confirmation or tool.risk_level == ToolRiskLevel.HIGH:
            if not approval_id:
                prepared_description = None
                if tool.prepare_approval:
                    try:
                        clean_args, prepared_description = tool.prepare_approval(db, context, clean_args)
                    except Exception as prep_err:
                        latency = round((time.perf_counter() - start_time) * 1000, 2)
                        code = {"AmbiguousItemError": "AMBIGUOUS_ITEM", "ItemNotFoundError": "NOT_FOUND",
                                "PermissionError": "FORBIDDEN"}.get(type(prep_err).__name__, "EXECUTION_ERROR")
                        self._record_audit(
                            db=db, log_id=log_id, context=context, tool_name=tool_name, input_args=clean_args,
                            status="BLOCKED" if code == "FORBIDDEN" else "ERROR", error_detail=str(prep_err), latency_ms=latency,
                        )
                        refusal = {"error": code, "detail": str(prep_err), "persisted": False}
                        if getattr(prep_err, "candidates", None):
                            refusal["candidates"] = prep_err.candidates
                        return refusal
                # Generate Pending Approval token and pause execution
                approval = approval_manager.create_pending_approval(
                    db=db,
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    user_role=context.user_role,
                    tool_name=tool_name,
                    arguments=clean_args,
                    description=(
                        prepared_description
                        or (tool.approval_description(clean_args) if tool.approval_description else None)
                        or f"Destructive action: Permanently execute '{tool_name}' on resource {clean_args}."
                    ),
                )
                latency = round((time.perf_counter() - start_time) * 1000, 2)
                self._record_audit(
                    db=db,
                    log_id=log_id,
                    context=context,
                    tool_name=tool_name,
                    input_args=clean_args,
                    status="APPROVAL_REQUIRED",
                    error_detail=f"Approval token generated: {approval.id}",
                    latency_ms=latency,
                )
                return {
                    "status": "APPROVAL_REQUIRED",
                    "approval_id": approval.id,
                    "tool_name": tool_name,
                    "description": approval.description,
                    "arguments": clean_args,
                    "requires_confirmation": True,
                }
            else:
                # Re-validate and consume approval token (prevents replay)
                check = approval_manager.claim_execution(
                    db=db,
                    approval_id=approval_id,
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    user_role=context.user_role,
                    tool_name=tool_name,
                    arguments=clean_args,
                )
                if not check.get("valid"):
                    latency = round((time.perf_counter() - start_time) * 1000, 2)
                    err_msg = check.get("error", "Invalid or consumed approval token.")
                    self._record_audit(
                        db=db,
                        log_id=log_id,
                        context=context,
                        tool_name=tool_name,
                        input_args=clean_args,
                        status="BLOCKED",
                        error_detail=err_msg,
                        latency_ms=latency,
                    )
                    return {
                        "error": "APPROVAL_INVALID",
                        "detail": err_msg,
                    }
                # Use validated approved arguments
                clean_args = check["arguments"]

        # 6. Sensitive Executive Parameter Stripping for Non-Owners
        if not context.has_role("CLINIC_OWNER"):
            for sensitive_key in ["salary", "payroll_info", "doctor_evaluation", "financial_audit_notes"]:
                if sensitive_key in clean_args:
                    clean_args.pop(sensitive_key)

        # 7. Handler Execution
        try:
            result = tool.handler(db, context, clean_args)
            latency = round((time.perf_counter() - start_time) * 1000, 2)
            result_failed = isinstance(result, dict) and bool(result.get("error"))
            if result_failed:
                db.rollback()
            self._record_audit(
                db=db,
                log_id=log_id,
                context=context,
                tool_name=tool_name,
                input_args=clean_args,
                status="ERROR" if result_failed else "ALLOWED",
                error_detail=result.get("detail") if result_failed else None,
                latency_ms=latency,
            )
            if approval_id:
                approval_manager.complete_execution(
                    db, approval_id, success=not result_failed,
                    error_detail=result.get("detail") if result_failed else None,
                )
            if isinstance(result, dict):
                result.setdefault("duration_ms", latency)
                result.setdefault("correlation_id", log_id)
                if "resource_id" not in result:
                    if "task_id" in result:
                        result["resource_id"] = result["task_id"]
                    elif "checklist_id" in result:
                        result["resource_id"] = result["checklist_id"]
                    elif "room_id" in result:
                        result["resource_id"] = result["room_id"]
                    elif "invitation_id" in result:
                        result["resource_id"] = result["invitation_id"]
            return result
        except ValueError as val_err:
            db.rollback()
            latency = round((time.perf_counter() - start_time) * 1000, 2)
            err_msg = str(val_err)
            self._record_audit(
                db=db,
                log_id=log_id,
                context=context,
                tool_name=tool_name,
                input_args=clean_args,
                status="ERROR",
                error_detail=err_msg,
                latency_ms=latency,
            )
            if approval_id:
                approval_manager.complete_execution(db, approval_id, success=False, error_detail=err_msg)
            err_resp = {
                "error": "EXECUTION_ERROR",
                "detail": err_msg,
                "duration_ms": latency,
                "correlation_id": log_id,
            }
            if getattr(val_err, "candidates", None):
                err_resp["error_type"] = "AMBIGUOUS_ITEM"
                err_resp["candidates"] = val_err.candidates
            if "Room ID" in err_msg and "not found" in err_msg:
                err_resp["error_type"] = "ROOM_NOT_FOUND"
                err_resp["failed_room_id"] = clean_args.get("room_id")
                err_resp["recovery_hint"] = "Display room numbers differ from database IDs. Call 'search_rooms' to resolve the actual database room_id."
            return err_resp

        except Exception as exc:
            db.rollback()
            latency = round((time.perf_counter() - start_time) * 1000, 2)
            err_msg = str(exc)
            self._record_audit(
                db=db,
                log_id=log_id,
                context=context,
                tool_name=tool_name,
                input_args=clean_args,
                status="ERROR",
                error_detail=err_msg,
                latency_ms=latency,
            )
            if approval_id:
                approval_manager.complete_execution(db, approval_id, success=False, error_detail=err_msg)
            logger.error("Tool '%s' execution error: %s", tool_name, err_msg, exc_info=True)
            return {
                "error": "EXECUTION_ERROR",
                "detail": err_msg,
                "duration_ms": latency,
                "correlation_id": log_id,
            }

    def _record_audit(
        self,
        db: Session,
        log_id: str,
        context: SecurityContext,
        tool_name: str,
        input_args: Dict[str, Any],
        status: str,
        error_detail: Optional[str] = None,
        latency_ms: float = 0.0,
    ):
        redacted_args = {
            key: ("[REDACTED]" if any(secret in key.lower() for secret in ("password", "token", "secret", "code")) else value)
            for key, value in (input_args or {}).items()
        }
        record = models.AIAuditEvent(
            id=log_id,
            timestamp=datetime.utcnow(),
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            user_role=context.user_role,
            tool_name=tool_name,
            input_args_json=json.dumps(redacted_args, sort_keys=True, default=str),
            status=status,
            error_detail=error_detail,
            latency_ms=int(round(latency_ms)),
        )
        db.add(record)
        db.commit()

    def record_audit_event(
        self,
        db: Session,
        tenant_id: str,
        user_id: str,
        user_role: str,
        action: str,
        details: Dict[str, Any],
        status: str = "SUCCESS",
    ):
        ctx = SecurityContext(tenant_id=tenant_id, user_id=user_id, user_role=user_role)
        self._record_audit(
            db=db,
            log_id=f"audit-{uuid.uuid4().hex[:8]}",
            context=ctx,
            tool_name=action,
            input_args=details,
            status=status,
            latency_ms=1.0,
        )


gateway = ToolGateway()
