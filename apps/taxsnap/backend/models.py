import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

class TaxProfile(Base):
    __tablename__ = "tax_profiles"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("txp"))
    tenant_id = Column(String(50), nullable=False, index=True)
    business_name = Column(String(150), nullable=False)
    tin_number = Column(String(50), nullable=False)
    fiscal_year = Column(String(20), default="2026")
    corporate_tax_rate = Column(Float, default=0.21)
    created_at = Column(DateTime, default=datetime.utcnow)

    income_records = relationship("IncomeRecord", back_populates="profile", cascade="all, delete-orphan")
    expense_records = relationship("ExpenseRecord", back_populates="profile", cascade="all, delete-orphan")
    documents = relationship("TaxDocument", back_populates="profile", cascade="all, delete-orphan")

class IncomeRecord(Base):
    __tablename__ = "income_records"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("inc"))
    profile_id = Column(String(50), ForeignKey("tax_profiles.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    source = Column(String(150), nullable=False)
    amount = Column(Float, nullable=False)
    date = Column(String(30), nullable=False)
    status = Column(String(30), default="Received")  # Received, Pending, Invoiced
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("TaxProfile", back_populates="income_records")

class ExpenseRecord(Base):
    __tablename__ = "expense_records"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("exp"))
    profile_id = Column(String(50), ForeignKey("tax_profiles.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    vendor = Column(String(150), nullable=False)
    category = Column(String(80), nullable=False)  # Cloud Infrastructure, Office Lease, Legal Advisory, Software, Dining, Travel
    amount = Column(Float, nullable=False)
    is_deductible = Column(Boolean, default=True)
    date = Column(String(30), nullable=False)
    receipt_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("TaxProfile", back_populates="expense_records")

class TaxDocument(Base):
    __tablename__ = "tax_documents"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("doc"))
    profile_id = Column(String(50), ForeignKey("tax_profiles.id"), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    document_type = Column(String(100), nullable=False)  # Form 1099-NEC, Commercial Lease Depreciation, Q3 Sales Tax Return, Form W-2
    status = Column(String(30), default="PENDING_UPLOAD")  # VERIFIED, PENDING_UPLOAD, MISSING, OVERDUE
    deadline = Column(String(30), nullable=False)
    assigned_cpa = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("TaxProfile", back_populates="documents")

class User(Base):
    __tablename__ = "taxsnap_users"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("usr"))
    email = Column(String(150), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(50), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    company_name = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
