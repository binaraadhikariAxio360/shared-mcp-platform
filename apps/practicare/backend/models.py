import uuid
import json
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
    Index,
    Numeric,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

class Practice(Base):
    __tablename__ = "practices"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("prac"))
    name = Column(String(150), nullable=False)
    location = Column(String(250), nullable=False)
    room_count = Column(Integer, default=12)
    tenant_id = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    staff_members = relationship("Staff", back_populates="practice", cascade="all, delete-orphan")
    rooms = relationship("Room", back_populates="practice", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="practice", cascade="all, delete-orphan")
    checklists = relationship("Checklist", back_populates="practice", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="practice", cascade="all, delete-orphan")

class Staff(Base):
    __tablename__ = "staff"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("stf"))
    name = Column(String(120), nullable=False)
    role = Column(String(50), nullable=False)  # "Doctor", "Nurse", "Admin", etc.
    is_active = Column(Boolean, default=True)  # Account status: Active / Inactive
    on_shift = Column(Boolean, default=True)   # Shift status: On Shift / Off Duty
    department = Column(String(100), nullable=True)
    work_status = Column(String(30), default="ACTIVE")  # "ACTIVE", "ON_LEAVE", "HOLIDAY", "SICK_LEAVE", "DND"
    last_login_at = Column(DateTime, nullable=True)
    user_id = Column(String(50), ForeignKey("practicare_users.id"), nullable=True)
    practice_id = Column(String(50), ForeignKey("practices.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    practice = relationship("Practice", back_populates="staff_members")
    assigned_tasks = relationship("Task", back_populates="assigned_staff")
    assigned_checklists = relationship("Checklist", back_populates="assigned_staff")
    user = relationship("User", foreign_keys=[user_id])
    leaves = relationship("StaffLeave", back_populates="staff", cascade="all, delete-orphan")

class Room(Base):
    __tablename__ = "rooms"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("room"))
    room_number = Column(String(30), nullable=False)
    name = Column(String(100), nullable=False)
    room_type = Column(String(50), default="Exam")  # "Exam", "Surgery", "Triage", "Consultation"
    status = Column(String(30), default="Available")  # "Available", "Occupied", "Turnover"
    practice_id = Column(String(50), ForeignKey("practices.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    practice = relationship("Practice", back_populates="rooms")
    tasks = relationship("Task", back_populates="room")
    inventory_items = relationship("InventoryItem", back_populates="room")

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("tsk"))
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(30), default="Medium")  # "Low", "Medium", "High", "Critical"
    status = Column(String(30), default="Pending")  # "Pending", "In Progress", "Completed"
    due_date = Column(String(50), nullable=False)
    assigned_staff_id = Column(String(50), ForeignKey("staff.id"), nullable=True)
    room_id = Column(String(50), ForeignKey("rooms.id"), nullable=True)
    created_by_user_id = Column(String(50), nullable=True)
    created_by_role = Column(String(50), nullable=True)
    practice_id = Column(String(50), ForeignKey("practices.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    practice = relationship("Practice", back_populates="tasks")
    assigned_staff = relationship("Staff", back_populates="assigned_tasks")
    room = relationship("Room", back_populates="tasks")

class Checklist(Base):
    __tablename__ = "checklists"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("chk"))
    title = Column(String(200), nullable=False)
    category = Column(String(50), default="Sterilization")  # "Sterilization", "Hygiene", "Emergency", "Pharmacy"
    is_completed = Column(Boolean, default=False)
    frequency = Column(String(30), default="Daily")  # "Daily", "Weekly", "Monthly"
    assigned_staff_id = Column(String(50), ForeignKey("staff.id"), nullable=True)
    created_by_user_id = Column(String(50), nullable=True)
    created_by_role = Column(String(50), nullable=True)
    practice_id = Column(String(50), ForeignKey("practices.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    practice = relationship("Practice", back_populates="checklists")
    assigned_staff = relationship("Staff", back_populates="assigned_checklists")

class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("inv"))
    item_name = Column(String(150), nullable=False)
    current_stock = Column(Integer, default=0)
    min_threshold = Column(Integer, default=10)
    unit = Column(String(40), default="units")
    expiry_date = Column(String(50), nullable=True)  # e.g., "2026-11-30"
    supplier = Column(String(150), nullable=True)
    batch_number = Column(String(80), nullable=True)
    purchase_price = Column(Numeric(12, 2), nullable=True)  # unit purchase price
    room_id = Column(String(50), ForeignKey("rooms.id"), nullable=True)
    practice_id = Column(String(50), ForeignKey("practices.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    practice = relationship("Practice", back_populates="inventory_items")
    room = relationship("Room", back_populates="inventory_items")


class InventoryImport(Base):
    """One confirmed inventory import. The unique import_token makes a confirmation idempotent."""
    __tablename__ = "inventory_imports"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("imp"))
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(50), nullable=False)
    import_token = Column(String(64), nullable=False, unique=True)
    source_type = Column(String(20), nullable=False)  # "pdf", "image", "text", "chat"
    source_hash = Column(String(64), nullable=False)  # sha256 of the uploaded document / text
    created_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    result_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)

Index("idx_tasks_tenant_status", Task.tenant_id, Task.status)
Index("idx_inventory_tenant_stock", InventoryItem.tenant_id, InventoryItem.current_stock)
Index("idx_inventory_imports_source", InventoryImport.tenant_id, InventoryImport.source_hash)

class User(Base):
    __tablename__ = "practicare_users"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("usr"))
    email = Column(String(150), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)  # Account status: Active / Inactive
    membership_status = Column(String(30), default="APPROVED")  # Membership status: "APPROVED", "PENDING", "REJECTED"
    tenant_id = Column(String(50), nullable=False, index=True)
    company_name = Column(String(150), nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship("AIConversation", back_populates="user", cascade="all, delete-orphan")


class StaffInvitation(Base):
    __tablename__ = "staff_invitations"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("inv"))
    tenant_id = Column(String(50), nullable=False, index=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    role = Column(String(50), nullable=False, default="NURSE_STAFF")
    created_by_user_id = Column(String(50), nullable=False)
    max_uses = Column(Integer, default=5)
    use_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def is_active(self) -> bool:
        if self.is_revoked:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        if self.use_count >= self.max_uses:
            return False
        return True


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("conv"))
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(50), ForeignKey("practicare_users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="Clinical AI Assistant")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("AIMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="AIMessage.created_at")


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("msg"))
    conversation_id = Column(String(50), ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(30), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)
    tool_calls = Column(Text, nullable=True)  # JSON serialized list of tool calls
    metrics = Column(Text, nullable=True)     # JSON serialized metrics dict
    approval_pending = Column(Text, nullable=True)  # JSON serialized pending approval
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("AIConversation", back_populates="messages")


class AIPendingApproval(Base):
    __tablename__ = "ai_pending_approvals"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("appr"))
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(50), ForeignKey("practicare_users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_role = Column(String(50), nullable=False)
    tool_name = Column(String(100), nullable=False)
    arguments_json = Column(Text, nullable=False)
    arguments_hash = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="PENDING", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    error_detail = Column(Text, nullable=True)

    @property
    def arguments(self):
        return json.loads(self.arguments_json)


class AIAuditEvent(Base):
    __tablename__ = "ai_audit_events"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("aud"))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    user_role = Column(String(50), nullable=False)
    tool_name = Column(String(100), nullable=False, index=True)
    input_args_json = Column(Text, nullable=False, default="{}")
    status = Column(String(30), nullable=False, index=True)
    error_detail = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=False, default=0)


Index("idx_conv_tenant_user", AIConversation.tenant_id, AIConversation.user_id)
Index("idx_msg_conv_created", AIMessage.conversation_id, AIMessage.created_at)
Index("idx_ai_approval_principal", AIPendingApproval.tenant_id, AIPendingApproval.user_id, AIPendingApproval.status)
Index("idx_ai_audit_tenant_time", AIAuditEvent.tenant_id, AIAuditEvent.timestamp)


class StaffLeave(Base):
    __tablename__ = "staff_leaves"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("lev"))
    staff_id = Column(String(50), ForeignKey("staff.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    leave_type = Column(String(30), nullable=False)  # "HOLIDAY", "SICK_LEAVE", "DND", "OTHER"
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    status = Column(String(30), default="APPROVED")  # "PENDING", "APPROVED", "REJECTED", "CANCELLED"
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    staff = relationship("Staff", back_populates="leaves")


Index("idx_staff_leaves_tenant_dates", StaffLeave.tenant_id, StaffLeave.start_date, StaffLeave.end_date)
Index("idx_staff_leaves_staff_status", StaffLeave.staff_id, StaffLeave.status)
