from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Security & Request Context
# -----------------------------------------------------------------------------
class RequestContext(BaseModel):
    tenant_id: str
    user_id: str
    user_role: str = "FINANCE_DIRECTOR"

class UserLoginRequest(BaseModel):
    email: str
    password: str

class UserRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: Optional[str] = "FINANCE_DIRECTOR"
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
# Tax Profile Schemas
# -----------------------------------------------------------------------------
class TaxProfileBase(BaseModel):
    business_name: str
    tin_number: str
    fiscal_year: str = "2026"
    corporate_tax_rate: float = 0.21

class TaxProfileCreate(TaxProfileBase):
    pass

class TaxProfileUpdate(BaseModel):
    business_name: Optional[str] = None
    tin_number: Optional[str] = None
    fiscal_year: Optional[str] = None
    corporate_tax_rate: Optional[float] = None

class TaxProfileRead(TaxProfileBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Income Record Schemas
# -----------------------------------------------------------------------------
class IncomeRecordBase(BaseModel):
    source: str
    amount: float
    date: str
    status: str = "Received"  # Received, Pending, Invoiced

class IncomeRecordCreate(IncomeRecordBase):
    profile_id: Optional[str] = None

class IncomeRecordUpdate(BaseModel):
    source: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    status: Optional[str] = None

class IncomeRecordRead(IncomeRecordBase):
    id: str
    profile_id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Expense Record Schemas
# -----------------------------------------------------------------------------
class ExpenseRecordBase(BaseModel):
    vendor: str
    category: str  # Cloud Infrastructure, Office Lease, Legal Advisory, Software, Dining, Travel
    amount: float
    is_deductible: bool = True
    date: str
    receipt_url: Optional[str] = None

class ExpenseRecordCreate(ExpenseRecordBase):
    profile_id: Optional[str] = None

class ExpenseRecordUpdate(BaseModel):
    vendor: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    is_deductible: Optional[bool] = None
    date: Optional[str] = None
    receipt_url: Optional[str] = None

class ExpenseRecordRead(ExpenseRecordBase):
    id: str
    profile_id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Tax Document Schemas
# -----------------------------------------------------------------------------
class TaxDocumentBase(BaseModel):
    document_type: str  # Form 1099-NEC, Commercial Lease Depreciation, Q3 Sales Tax Return, Form W-2
    status: str = "PENDING_UPLOAD"  # VERIFIED, PENDING_UPLOAD, MISSING, OVERDUE
    deadline: str
    assigned_cpa: Optional[str] = None

class TaxDocumentCreate(TaxDocumentBase):
    profile_id: Optional[str] = None

class TaxDocumentUpdate(BaseModel):
    document_type: Optional[str] = None
    status: Optional[str] = None
    deadline: Optional[str] = None
    assigned_cpa: Optional[str] = None

class TaxDocumentRead(TaxDocumentBase):
    id: str
    profile_id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Dashboard Summary
# -----------------------------------------------------------------------------
class DashboardSummary(BaseModel):
    tenant_id: str
    business_name: str
    tin_number: str
    fiscal_year: str
    gross_income: float
    total_expenses: float
    total_deductible_expenses: float
    non_deductible_expenses: float
    net_taxable_income: float
    corporate_tax_rate: float
    estimated_tax_liability: float
    missing_documents_count: int
    overdue_filings_count: int
    total_documents_count: int
    income_count: int
    expense_count: int
    expense_by_category: Dict[str, float]

# -----------------------------------------------------------------------------
# AI Copilot Tools Schemas
# -----------------------------------------------------------------------------
class TaxSummaryToolRequest(BaseModel):
    profile_id: Optional[str] = None

class TaxSummaryToolResponse(BaseModel):
    tenant_id: str
    business_name: str
    tin_number: str
    fiscal_year: str
    gross_income: float
    total_expenses: float
    deductible_expenses: float
    non_deductible_expenses: float
    net_taxable_income: float
    tax_rate: float
    estimated_tax_liability: float
    missing_documents_count: int
    overdue_filings_count: int
    timestamp: str

class ListExpensesToolRequest(BaseModel):
    category: Optional[str] = None
    only_deductible: Optional[bool] = None

class ExpenseItemDetail(BaseModel):
    id: str
    vendor: str
    category: str
    amount: float
    is_deductible: bool
    date: str

class ListExpensesToolResponse(BaseModel):
    tenant_id: str
    count: int
    total_amount: float
    expenses: List[ExpenseItemDetail]

class ListMissingDocumentsToolRequest(BaseModel):
    profile_id: Optional[str] = None

class MissingDocumentItem(BaseModel):
    id: str
    document_type: str
    status: str
    deadline: str
    assigned_cpa: Optional[str] = None

class ListMissingDocumentsToolResponse(BaseModel):
    tenant_id: str
    count: int
    missing_documents: List[MissingDocumentItem]
