from datetime import datetime, date
from typing import Annotated, Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

import uuid
import models
import schemas
from database import engine, get_db, init_db_and_seed, hash_password, verify_password

app = FastAPI(
    title="TaxSnap Enterprise Backend",
    version="2.0.0",
    description="Corporate tax filing, financial ledgering, deduction analysis, and document compliance engine with PostgreSQL 16 persistence.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003",
        "http://127.0.0.1:3004",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db_and_seed()

# -----------------------------------------------------------------------------
# Security & Request Context Dependency
# -----------------------------------------------------------------------------
def get_request_context(
    x_tenant_id: Annotated[str, Header(alias="x-tenant-id", description="Tenant Identifier", min_length=1)] = "tenant-001",
    x_user_role: Annotated[Optional[str], Header(alias="x-user-role", description="Active User Role")] = "FINANCE_DIRECTOR",
    x_user_id: Annotated[Optional[str], Header(alias="x-user-id", description="User Identifier")] = "tax-cpa-lead",
) -> schemas.RequestContext:
    if not x_tenant_id or not x_tenant_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header 'x-tenant-id' is required and cannot be blank.",
        )
    return schemas.RequestContext(
        tenant_id=x_tenant_id.strip(),
        user_id=(x_user_id.strip() if x_user_id and x_user_id.strip() else "tax-cpa-lead"),
        user_role=(x_user_role.strip() if x_user_role and x_user_role.strip() else "FINANCE_DIRECTOR"),
    )

def require_role(context: schemas.RequestContext, allowed_roles: List[str]):
    if context.user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation not permitted for role {context.user_role}",
        )

def ensure_tenant_profile(db: Session, tenant_id: str) -> models.TaxProfile:
    profile = db.query(models.TaxProfile).filter(models.TaxProfile.tenant_id == tenant_id).first()
    if not profile:
        profile = models.TaxProfile(
            business_name=f"Enterprise ({tenant_id})",
            tin_number="XX-XXX9821",
            fiscal_year="2026",
            corporate_tax_rate=0.21,
            tenant_id=tenant_id,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile

@app.get("/api/v1/auth/roles", tags=["Auth"])
def get_auth_roles(context: Annotated[schemas.RequestContext, Depends(get_request_context)]):
    return {
        "app": "TaxSnap",
        "current_tenant": context.tenant_id,
        "current_role": context.user_role,
        "current_user": context.user_id,
        "roles": [
            {
                "id": "FINANCE_DIRECTOR",
                "label": "Finance Director (Admin)",
                "description": "Full CRUD on income, expenses, tax profiles, corporate rate, and filings.",
            },
            {
                "id": "SENIOR_CPA",
                "label": "Senior CPA (Accountant)",
                "description": "Full CRUD on expenses (toggle write-offs); verify/audit tax documents; read-only profile.",
            },
            {
                "id": "BOOKKEEPER",
                "label": "Corporate Bookkeeper (Staff)",
                "description": "Create/edit income and expenses; cannot verify documents or alter rates; cannot delete.",
            },
            {
                "id": "AUDITOR_STAKEHOLDER",
                "label": "Auditor & Stakeholder (Viewer)",
                "description": "Read-only across all financial ledgers and filings; cannot create, edit, or delete.",
            },
        ],
        "tenants": [
            {
                "id": "tenant-001",
                "name": "Vanguard Global Consulting LLC",
                "description": "Primary Management Consulting Division",
            },
            {
                "id": "tenant-002",
                "name": "Horizon Capital Partners LLC",
                "description": "Private Equity & Venture Holdings",
            },
        ],
    }

@app.post("/api/v1/auth/login", response_model=schemas.AuthResponse, tags=["Auth"])
def auth_login(payload: schemas.UserLoginRequest, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == clean_email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    access_token = f"moc_sess_{user.id}_{user.tenant_id}"
    return schemas.AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=schemas.UserResponse(
            id=user.id,
            name=user.full_name,
            email=user.email,
            role=user.role,
            tenant_id=user.tenant_id,
            company_name=user.company_name or user.tenant_id,
        ),
    )

@app.post("/api/v1/auth/register", response_model=schemas.AuthResponse, tags=["Auth"])
def auth_register(payload: schemas.UserRegisterRequest, db: Session = Depends(get_db)):
    clean_email = payload.email.strip().lower()
    existing = db.query(models.User).filter(models.User.email == clean_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )
    tenant_id = payload.tenant_id.strip() if payload.tenant_id and payload.tenant_id.strip() else None
    company_name = payload.company_name.strip() if payload.company_name and payload.company_name.strip() else "New Corporate Entity"
    if not tenant_id:
        slug = company_name.lower().replace(" ", "-")[:10]
        tenant_id = f"tenant-{slug}-{str(uuid.uuid4())[:4]}"

    profile = ensure_tenant_profile(db, tenant_id)
    if profile and company_name != f"Enterprise ({tenant_id})":
        profile.business_name = company_name
        db.commit()

    new_user = models.User(
        email=clean_email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=(payload.role.strip() if payload.role and payload.role.strip() else "FINANCE_DIRECTOR"),
        tenant_id=tenant_id,
        company_name=company_name,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = f"moc_sess_{new_user.id}_{new_user.tenant_id}"
    return schemas.AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=schemas.UserResponse(
            id=new_user.id,
            name=new_user.full_name,
            email=new_user.email,
            role=new_user.role,
            tenant_id=new_user.tenant_id,
            company_name=new_user.company_name or new_user.tenant_id,
        ),
    )

@app.get("/api/v1/auth/me", response_model=schemas.UserResponse, tags=["Auth"])
def auth_me(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == context.user_id).first()
    if not user:
        user = db.query(models.User).filter(
            models.User.tenant_id == context.tenant_id,
            models.User.role == context.user_role,
        ).first()
    if user:
        return schemas.UserResponse(
            id=user.id,
            name=user.full_name,
            email=user.email,
            role=user.role,
            tenant_id=user.tenant_id,
            company_name=user.company_name or user.tenant_id,
        )
    return schemas.UserResponse(
        id=context.user_id,
        name=f"Finance Lead ({context.user_role})",
        email=f"{context.user_role.lower()}@{context.tenant_id}.com",
        role=context.user_role,
        tenant_id=context.tenant_id,
        company_name=f"Enterprise ({context.tenant_id})",
    )

# -----------------------------------------------------------------------------
# System & Health
# -----------------------------------------------------------------------------
@app.get("/", tags=["System"])
def root_index():
    return {
        "service": "TaxSnap Financial API",
        "status": "operational",
        "database": "PostgreSQL 16 Connected",
        "docs_url": "/docs",
        "health_url": "/health",
        "frontend_url": "http://localhost:3002",
    }

@app.get("/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": "taxsnap-backend",
        "version": "2.0.0",
        "database_connected": db_ok,
        "timestamp": datetime.utcnow().isoformat(),
        "port": 8000,
    }

# -----------------------------------------------------------------------------
# 1. Dashboard Analytics
# -----------------------------------------------------------------------------
@app.get("/api/v1/dashboard/summary", response_model=schemas.DashboardSummary, tags=["Dashboard"])
def get_dashboard_summary(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    profile = ensure_tenant_profile(db, context.tenant_id)
    tenant_id = context.tenant_id

    # Query Incomes
    incomes = db.query(models.IncomeRecord).filter(models.IncomeRecord.tenant_id == tenant_id).all()
    gross_income = sum(inc.amount for inc in incomes)

    # Query Expenses
    expenses = db.query(models.ExpenseRecord).filter(models.ExpenseRecord.tenant_id == tenant_id).all()
    total_expenses = sum(exp.amount for exp in expenses)
    total_deductible = sum(exp.amount for exp in expenses if exp.is_deductible)
    non_deductible = total_expenses - total_deductible

    # Categories Breakdown
    cat_breakdown: Dict[str, float] = {}
    for exp in expenses:
        cat_breakdown[exp.category] = round(cat_breakdown.get(exp.category, 0.0) + exp.amount, 2)

    # Tax Computations
    net_taxable_income = max(0.0, gross_income - total_deductible)
    corporate_tax_rate = profile.corporate_tax_rate or 0.21
    estimated_tax_liability = round(net_taxable_income * corporate_tax_rate, 2)

    # Documents & Compliance
    docs = db.query(models.TaxDocument).filter(models.TaxDocument.tenant_id == tenant_id).all()
    missing_docs = sum(1 for d in docs if d.status.upper() in ("MISSING", "PENDING_UPLOAD"))
    overdue_filings = sum(1 for d in docs if d.status.upper() == "OVERDUE")

    return schemas.DashboardSummary(
        tenant_id=tenant_id,
        business_name=profile.business_name,
        tin_number=profile.tin_number,
        fiscal_year=profile.fiscal_year,
        gross_income=round(gross_income, 2),
        total_expenses=round(total_expenses, 2),
        total_deductible_expenses=round(total_deductible, 2),
        non_deductible_expenses=round(non_deductible, 2),
        net_taxable_income=round(net_taxable_income, 2),
        corporate_tax_rate=corporate_tax_rate,
        estimated_tax_liability=estimated_tax_liability,
        missing_documents_count=missing_docs,
        overdue_filings_count=overdue_filings,
        total_documents_count=len(docs),
        income_count=len(incomes),
        expense_count=len(expenses),
        expense_by_category=cat_breakdown,
    )

# -----------------------------------------------------------------------------
# 2. Income Records CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/income", response_model=List[schemas.IncomeRecordRead], tags=["Income"])
def list_income_records(
    status: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.IncomeRecord).filter(models.IncomeRecord.tenant_id == context.tenant_id)
    if status:
        query = query.filter(models.IncomeRecord.status.ilike(f"%{status}%"))
    return query.order_by(models.IncomeRecord.date.desc()).all()

@app.post("/api/v1/income", response_model=schemas.IncomeRecordRead, status_code=status.HTTP_201_CREATED, tags=["Income"])
def create_income_record(
    payload: schemas.IncomeRecordCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR", "BOOKKEEPER", "SENIOR_CPA"])
    profile = ensure_tenant_profile(db, context.tenant_id)
    new_income = models.IncomeRecord(
        profile_id=payload.profile_id or profile.id,
        tenant_id=context.tenant_id,
        source=payload.source,
        amount=payload.amount,
        date=payload.date,
        status=payload.status or "Received",
    )
    db.add(new_income)
    db.commit()
    db.refresh(new_income)
    return new_income

@app.get("/api/v1/income/{income_id}", response_model=schemas.IncomeRecordRead, tags=["Income"])
def get_income_record(
    income_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    record = db.query(models.IncomeRecord).filter(
        models.IncomeRecord.id == income_id,
        models.IncomeRecord.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Income record not found")
    return record

@app.put("/api/v1/income/{income_id}", response_model=schemas.IncomeRecordRead, tags=["Income"])
def update_income_record(
    income_id: str,
    payload: schemas.IncomeRecordUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR", "BOOKKEEPER", "SENIOR_CPA"])
    record = db.query(models.IncomeRecord).filter(
        models.IncomeRecord.id == income_id,
        models.IncomeRecord.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Income record not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(record, field, val)

    db.commit()
    db.refresh(record)
    return record

@app.delete("/api/v1/income/{income_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Income"])
def delete_income_record(
    income_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR"])
    record = db.query(models.IncomeRecord).filter(
        models.IncomeRecord.id == income_id,
        models.IncomeRecord.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Income record not found")
    db.delete(record)
    db.commit()

# -----------------------------------------------------------------------------
# 3. Expense Records CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/expenses", response_model=List[schemas.ExpenseRecordRead], tags=["Expenses"])
def list_expense_records(
    category: Optional[str] = None,
    is_deductible: Optional[bool] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.ExpenseRecord).filter(models.ExpenseRecord.tenant_id == context.tenant_id)
    if category:
        query = query.filter(models.ExpenseRecord.category.ilike(f"%{category}%"))
    if is_deductible is not None:
        query = query.filter(models.ExpenseRecord.is_deductible == is_deductible)
    return query.order_by(models.ExpenseRecord.date.desc()).all()

@app.post("/api/v1/expenses", response_model=schemas.ExpenseRecordRead, status_code=status.HTTP_201_CREATED, tags=["Expenses"])
def create_expense_record(
    payload: schemas.ExpenseRecordCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR", "SENIOR_CPA", "BOOKKEEPER"])
    profile = ensure_tenant_profile(db, context.tenant_id)
    new_expense = models.ExpenseRecord(
        profile_id=payload.profile_id or profile.id,
        tenant_id=context.tenant_id,
        vendor=payload.vendor,
        category=payload.category,
        amount=payload.amount,
        is_deductible=payload.is_deductible if payload.is_deductible is not None else True,
        date=payload.date,
        receipt_url=payload.receipt_url,
    )
    db.add(new_expense)
    db.commit()
    db.refresh(new_expense)
    return new_expense

@app.get("/api/v1/expenses/{expense_id}", response_model=schemas.ExpenseRecordRead, tags=["Expenses"])
def get_expense_record(
    expense_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    record = db.query(models.ExpenseRecord).filter(
        models.ExpenseRecord.id == expense_id,
        models.ExpenseRecord.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Expense record not found")
    return record

@app.put("/api/v1/expenses/{expense_id}", response_model=schemas.ExpenseRecordRead, tags=["Expenses"])
def update_expense_record(
    expense_id: str,
    payload: schemas.ExpenseRecordUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR", "SENIOR_CPA", "BOOKKEEPER"])
    record = db.query(models.ExpenseRecord).filter(
        models.ExpenseRecord.id == expense_id,
        models.ExpenseRecord.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Expense record not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(record, field, val)

    db.commit()
    db.refresh(record)
    return record

@app.delete("/api/v1/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Expenses"])
def delete_expense_record(
    expense_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR", "SENIOR_CPA"])
    record = db.query(models.ExpenseRecord).filter(
        models.ExpenseRecord.id == expense_id,
        models.ExpenseRecord.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Expense record not found")
    db.delete(record)
    db.commit()

# -----------------------------------------------------------------------------
# 4. Tax Documents & Compliance CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/documents", response_model=List[schemas.TaxDocumentRead], tags=["Documents"])
def list_tax_documents(
    status: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.TaxDocument).filter(models.TaxDocument.tenant_id == context.tenant_id)
    if status:
        query = query.filter(models.TaxDocument.status.ilike(f"%{status}%"))
    return query.order_by(models.TaxDocument.deadline.asc()).all()

@app.post("/api/v1/documents", response_model=schemas.TaxDocumentRead, status_code=status.HTTP_201_CREATED, tags=["Documents"])
def create_tax_document(
    payload: schemas.TaxDocumentCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR", "SENIOR_CPA"])
    profile = ensure_tenant_profile(db, context.tenant_id)
    new_doc = models.TaxDocument(
        profile_id=payload.profile_id or profile.id,
        tenant_id=context.tenant_id,
        document_type=payload.document_type,
        status=payload.status or "PENDING_UPLOAD",
        deadline=payload.deadline,
        assigned_cpa=payload.assigned_cpa,
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    return new_doc

@app.get("/api/v1/documents/{document_id}", response_model=schemas.TaxDocumentRead, tags=["Documents"])
def get_tax_document(
    document_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    record = db.query(models.TaxDocument).filter(
        models.TaxDocument.id == document_id,
        models.TaxDocument.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Tax document not found")
    return record

@app.put("/api/v1/documents/{document_id}", response_model=schemas.TaxDocumentRead, tags=["Documents"])
def update_tax_document(
    document_id: str,
    payload: schemas.TaxDocumentUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR", "SENIOR_CPA"])
    record = db.query(models.TaxDocument).filter(
        models.TaxDocument.id == document_id,
        models.TaxDocument.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Tax document not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(record, field, val)

    db.commit()
    db.refresh(record)
    return record

@app.delete("/api/v1/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Documents"])
def delete_tax_document(
    document_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR"])
    record = db.query(models.TaxDocument).filter(
        models.TaxDocument.id == document_id,
        models.TaxDocument.tenant_id == context.tenant_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Tax document not found")
    db.delete(record)
    db.commit()

# -----------------------------------------------------------------------------
# 5. Tax Profile
# -----------------------------------------------------------------------------
@app.get("/api/v1/profile", response_model=schemas.TaxProfileRead, tags=["Profile"])
def get_tax_profile(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    return ensure_tenant_profile(db, context.tenant_id)

@app.put("/api/v1/profile", response_model=schemas.TaxProfileRead, tags=["Profile"])
def update_tax_profile(
    payload: schemas.TaxProfileUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["FINANCE_DIRECTOR"])
    profile = ensure_tenant_profile(db, context.tenant_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(profile, field, val)
    db.commit()
    db.refresh(profile)
    return profile


# -----------------------------------------------------------------------------
# 6. Live AI Copilot Tools
# -----------------------------------------------------------------------------
@app.post(
    "/internal/tools/taxsnap.get_tax_summary",
    response_model=schemas.TaxSummaryToolResponse,
    tags=["Tools"],
    summary="Compute live corporate tax liability and write-offs",
)
def tool_get_tax_summary(
    payload: schemas.TaxSummaryToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    profile = ensure_tenant_profile(db, context.tenant_id)
    tenant_id = context.tenant_id

    incomes = db.query(models.IncomeRecord).filter(models.IncomeRecord.tenant_id == tenant_id).all()
    gross_income = sum(i.amount for i in incomes)

    expenses = db.query(models.ExpenseRecord).filter(models.ExpenseRecord.tenant_id == tenant_id).all()
    total_expenses = sum(e.amount for e in expenses)
    deductible_expenses = sum(e.amount for e in expenses if e.is_deductible)
    non_deductible = total_expenses - deductible_expenses

    net_taxable = max(0.0, gross_income - deductible_expenses)
    tax_rate = profile.corporate_tax_rate or 0.21
    estimated_tax = round(net_taxable * tax_rate, 2)

    docs = db.query(models.TaxDocument).filter(models.TaxDocument.tenant_id == tenant_id).all()
    missing_count = sum(1 for d in docs if d.status.upper() in ("MISSING", "PENDING_UPLOAD"))
    overdue_count = sum(1 for d in docs if d.status.upper() == "OVERDUE")

    return schemas.TaxSummaryToolResponse(
        tenant_id=tenant_id,
        business_name=profile.business_name,
        tin_number=profile.tin_number,
        fiscal_year=profile.fiscal_year,
        gross_income=round(gross_income, 2),
        total_expenses=round(total_expenses, 2),
        deductible_expenses=round(deductible_expenses, 2),
        non_deductible_expenses=round(non_deductible, 2),
        net_taxable_income=round(net_taxable, 2),
        tax_rate=tax_rate,
        estimated_tax_liability=estimated_tax,
        missing_documents_count=missing_count,
        overdue_filings_count=overdue_count,
        timestamp=datetime.utcnow().isoformat(),
    )

@app.post(
    "/internal/tools/taxsnap.list_expenses",
    response_model=schemas.ListExpensesToolResponse,
    tags=["Tools"],
    summary="List categorized deductible expenses with filtering",
)
def tool_list_expenses(
    payload: schemas.ListExpensesToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    query = db.query(models.ExpenseRecord).filter(models.ExpenseRecord.tenant_id == context.tenant_id)
    if payload.category:
        query = query.filter(models.ExpenseRecord.category.ilike(f"%{payload.category}%"))
    if payload.only_deductible is not None:
        query = query.filter(models.ExpenseRecord.is_deductible == payload.only_deductible)

    records = query.order_by(models.ExpenseRecord.amount.desc()).all()
    items = [
        schemas.ExpenseItemDetail(
            id=r.id,
            vendor=r.vendor,
            category=r.category,
            amount=r.amount,
            is_deductible=r.is_deductible,
            date=r.date,
        )
        for r in records
    ]
    total_amt = round(sum(i.amount for i in items), 2)

    return schemas.ListExpensesToolResponse(
        tenant_id=context.tenant_id,
        count=len(items),
        total_amount=total_amt,
        expenses=items,
    )

@app.post(
    "/internal/tools/taxsnap.list_missing_documents",
    response_model=schemas.ListMissingDocumentsToolResponse,
    tags=["Tools"],
    summary="List required filings and receipts in MISSING or PENDING_UPLOAD status",
)
def tool_list_missing_documents(
    payload: schemas.ListMissingDocumentsToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    records = db.query(models.TaxDocument).filter(
        models.TaxDocument.tenant_id == context.tenant_id,
        models.TaxDocument.status.in_(["MISSING", "PENDING_UPLOAD", "OVERDUE"]),
    ).order_by(models.TaxDocument.deadline.asc()).all()

    items = [
        schemas.MissingDocumentItem(
            id=d.id,
            document_type=d.document_type,
            status=d.status,
            deadline=d.deadline,
            assigned_cpa=d.assigned_cpa,
        )
        for d in records
    ]

    return schemas.ListMissingDocumentsToolResponse(
        tenant_id=context.tenant_id,
        count=len(items),
        missing_documents=items,
    )
