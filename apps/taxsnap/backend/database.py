import os
import logging
import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base, TaxProfile, IncomeRecord, ExpenseRecord, TaxDocument, User

logger = logging.getLogger("taxsnap.database")

def hash_password(password: str) -> str:
    salt = "axio360_secure_salt"
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://practicare_user:practicare_secure_pass@postgres-db:5432/practicare_db"
)
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# Robust engine initialization with fallback for testing
try:
    if DATABASE_URL.startswith("postgresql"):
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    else:
        engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
        )
except Exception as e:
    logger.warning(f"Could not connect to {DATABASE_URL}: {e}. Falling back to SQLite.")
    engine = create_engine("sqlite:///./taxsnap_fallback.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db_and_seed():
    """Create all tables and seed default corporate tax data for tenant-001."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        return

    db: Session = SessionLocal()
    try:
        default_tenant = "tenant-001"
        existing_profile = db.query(TaxProfile).filter(TaxProfile.tenant_id == default_tenant).first()
        if not existing_profile:
            logger.info("Seeding initial corporate tax data for tenant-001 (Vanguard Global Consulting LLC)...")

            # 1. TaxProfile
            profile = TaxProfile(
                id="txp-001",
                tenant_id=default_tenant,
                business_name="Vanguard Global Consulting LLC",
                tin_number="XX-XXX9821",
                fiscal_year="2026",
                corporate_tax_rate=0.21,
            )
            db.add(profile)
            db.flush()

            # 2. Income Records ($620,000 Gross)
            income_records = [
                IncomeRecord(
                    id="inc-01",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    source="Enterprise AI Architecture Retainer (Fintech Corp)",
                    amount=240000.0,
                    date="2026-08-15",
                    status="Received",
                ),
                IncomeRecord(
                    id="inc-02",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    source="Cloud Migration Strategy & Governance (Healthcare Inc)",
                    amount=185000.0,
                    date="2026-09-01",
                    status="Received",
                ),
                IncomeRecord(
                    id="inc-03",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    source="Q3 Fractional CTO Advisory Services (RetailTech)",
                    amount=95000.0,
                    date="2026-09-15",
                    status="Received",
                ),
                IncomeRecord(
                    id="inc-04",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    source="Multi-Agent System Implementation Milestone 2",
                    amount=65000.0,
                    date="2026-09-28",
                    status="Received",
                ),
                IncomeRecord(
                    id="inc-05",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    source="Security & SOC2 Readiness Review",
                    amount=35000.0,
                    date="2026-10-05",
                    status="Invoiced",
                ),
            ]
            db.add_all(income_records)
            db.flush()

            # 3. Expense Records ($156,500 Total, $147,500 Deductible)
            expense_records = [
                ExpenseRecord(
                    id="exp-01",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    vendor="Amazon Web Services & GPU Compute",
                    category="Cloud Infrastructure",
                    amount=48500.0,
                    is_deductible=True,
                    date="2026-09-10",
                    receipt_url="https://s3.amazonaws.com/receipts/aws-2026-09.pdf",
                ),
                ExpenseRecord(
                    id="exp-02",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    vendor="WeWork Global HQ Lease",
                    category="Office Lease",
                    amount=42000.0,
                    is_deductible=True,
                    date="2026-09-01",
                    receipt_url="https://s3.amazonaws.com/receipts/wework-q3.pdf",
                ),
                ExpenseRecord(
                    id="exp-03",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    vendor="Cooley LLP Corporate Tax & Legal",
                    category="Legal Advisory",
                    amount=28000.0,
                    is_deductible=True,
                    date="2026-08-20",
                    receipt_url="https://s3.amazonaws.com/receipts/cooley-invoice.pdf",
                ),
                ExpenseRecord(
                    id="exp-04",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    vendor="GitHub & Datadog Enterprise Licenses",
                    category="Software",
                    amount=16500.0,
                    is_deductible=True,
                    date="2026-09-18",
                    receipt_url="https://s3.amazonaws.com/receipts/licenses-2026.pdf",
                ),
                ExpenseRecord(
                    id="exp-05",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    vendor="Delta Airlines & Marriott Client Summit",
                    category="Travel",
                    amount=12500.0,
                    is_deductible=True,
                    date="2026-09-25",
                    receipt_url="https://s3.amazonaws.com/receipts/travel-q3.pdf",
                ),
                ExpenseRecord(
                    id="exp-06",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    vendor="Michelin Partner Executive Dinner",
                    category="Dining",
                    amount=9000.0,
                    is_deductible=False,
                    date="2026-09-22",
                    receipt_url="https://s3.amazonaws.com/receipts/dinner-0922.pdf",
                ),
            ]
            db.add_all(expense_records)
            db.flush()

            # 4. Tax Documents
            tax_documents = [
                TaxDocument(
                    id="doc-01",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    document_type="Form 1099-NEC (Fintech Corp)",
                    status="VERIFIED",
                    deadline="2026-10-31",
                    assigned_cpa="Elena Rostova, CPA",
                ),
                TaxDocument(
                    id="doc-02",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    document_type="Commercial Lease Depreciation Schedule",
                    status="VERIFIED",
                    deadline="2026-11-15",
                    assigned_cpa="Elena Rostova, CPA",
                ),
                TaxDocument(
                    id="doc-03",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    document_type="Q3 Sales Tax Return & Filing",
                    status="MISSING",
                    deadline="2026-10-20",
                    assigned_cpa="David Sterling, CPA",
                ),
                TaxDocument(
                    id="doc-04",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    document_type="Form W-2 Executive Compensation Summary",
                    status="PENDING_UPLOAD",
                    deadline="2026-11-01",
                    assigned_cpa="Elena Rostova, CPA",
                ),
                TaxDocument(
                    id="doc-05",
                    profile_id=profile.id,
                    tenant_id=default_tenant,
                    document_type="R&D Tax Credit Form 6765 Worksheet",
                    status="OVERDUE",
                    deadline="2026-10-01",
                    assigned_cpa="David Sterling, CPA",
                ),
            ]
            db.add_all(tax_documents)
            db.commit()
            logger.info("TaxSnap tenant-001 seed data initialized successfully.")

        # Seed Company B (tenant-002) - Horizon Capital Partners LLC
        t2_tenant = "tenant-002"
        existing_t2 = db.query(TaxProfile).filter(TaxProfile.tenant_id == t2_tenant).first()
        if not existing_t2:
            logger.info("Seeding initial corporate tax data for tenant-002 (Horizon Capital Partners LLC)...")
            profile_t2 = TaxProfile(
                id="txp-002",
                tenant_id=t2_tenant,
                business_name="Horizon Capital Partners LLC",
                tin_number="XX-XXX4102",
                fiscal_year="2026",
                corporate_tax_rate=0.25,
            )
            db.add(profile_t2)
            db.flush()

            income_t2 = [
                IncomeRecord(
                    id="inc-t2-01",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    source="Private Equity Management Fee Q3",
                    amount=380000.0,
                    date="2026-08-01",
                    status="Received",
                ),
                IncomeRecord(
                    id="inc-t2-02",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    source="Portfolio Company Exit Advisory Retainer",
                    amount=290000.0,
                    date="2026-09-05",
                    status="Received",
                ),
                IncomeRecord(
                    id="inc-t2-03",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    source="Syndicated Debt Placement Commission",
                    amount=140000.0,
                    date="2026-09-20",
                    status="Received",
                ),
                IncomeRecord(
                    id="inc-t2-04",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    source="Growth Capital Syndication Fee",
                    amount=75000.0,
                    date="2026-10-02",
                    status="Invoiced",
                ),
            ]
            db.add_all(income_t2)
            db.flush()

            expenses_t2 = [
                ExpenseRecord(
                    id="exp-t2-01",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    vendor="Bloomberg Terminal & PitchBook Feeds",
                    category="Market Data",
                    amount=54000.0,
                    is_deductible=True,
                    date="2026-08-25",
                    receipt_url="https://s3.amazonaws.com/receipts/bloomberg-q3.pdf",
                ),
                ExpenseRecord(
                    id="exp-t2-02",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    vendor="Gibson Dunn M&A Counsel",
                    category="Legal Advisory",
                    amount=68000.0,
                    is_deductible=True,
                    date="2026-09-12",
                    receipt_url="https://s3.amazonaws.com/receipts/gibson-dunn.pdf",
                ),
                ExpenseRecord(
                    id="exp-t2-03",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    vendor="One Vanderbilt Executive Suite",
                    category="Office Lease",
                    amount=52000.0,
                    is_deductible=True,
                    date="2026-09-01",
                    receipt_url="https://s3.amazonaws.com/receipts/one-vanderbilt.pdf",
                ),
                ExpenseRecord(
                    id="exp-t2-04",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    vendor="Private Aviation Client Roadshow",
                    category="Travel",
                    amount=34000.0,
                    is_deductible=False,
                    date="2026-09-18",
                    receipt_url="https://s3.amazonaws.com/receipts/netjets-roadshow.pdf",
                ),
            ]
            db.add_all(expenses_t2)
            db.flush()

            docs_t2 = [
                TaxDocument(
                    id="doc-t2-01",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    document_type="Form 1065 Partnership Return Schedule K-1",
                    status="VERIFIED",
                    deadline="2026-10-15",
                    assigned_cpa="Nathaniel Vance, CPA",
                ),
                TaxDocument(
                    id="doc-t2-02",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    document_type="Q3 State Apportionment Filing",
                    status="PENDING_UPLOAD",
                    deadline="2026-11-15",
                    assigned_cpa="Nathaniel Vance, CPA",
                ),
                TaxDocument(
                    id="doc-t2-03",
                    profile_id=profile_t2.id,
                    tenant_id=t2_tenant,
                    document_type="Foreign Account Tax Compliance Act (FATCA) Report",
                    status="MISSING",
                    deadline="2026-12-01",
                    assigned_cpa="Nathaniel Vance, CPA",
                ),
            ]
            db.add_all(docs_t2)
            db.commit()
            logger.info("TaxSnap tenant-002 seed data initialized successfully.")

        # Seed Default Users
        seed_users = [
            ("director@vanguardtax.com", "password123", "Eleanor Sterling", "FINANCE_DIRECTOR", "tenant-001", "Vanguard Global Consulting LLC"),
            ("cpa@vanguardtax.com", "password123", "Marcus Vance, CPA", "SENIOR_CPA", "tenant-001", "Vanguard Global Consulting LLC"),
            ("bookkeeper@vanguardtax.com", "password123", "Chloe Bennett", "BOOKKEEPER", "tenant-001", "Vanguard Global Consulting LLC"),
            ("auditor@vanguardtax.com", "password123", "Devon Reed", "AUDITOR_STAKEHOLDER", "tenant-001", "Vanguard Global Consulting LLC"),
            ("director@horizoncap.com", "password123", "Julian Thorne", "FINANCE_DIRECTOR", "tenant-002", "Horizon Capital Partners LLC"),
            ("cpa@horizoncap.com", "password123", "Nathaniel Vance, CPA", "SENIOR_CPA", "tenant-002", "Horizon Capital Partners LLC"),
            ("bookkeeper@horizoncap.com", "password123", "Samantha Wu", "BOOKKEEPER", "tenant-002", "Horizon Capital Partners LLC"),
        ]
        for email, pwd, name, role, tenant, company in seed_users:
            existing_user = db.query(User).filter(User.email == email).first()
            if not existing_user:
                new_u = User(
                    email=email,
                    password_hash=hash_password(pwd),
                    full_name=name,
                    role=role,
                    tenant_id=tenant,
                    company_name=company,
                )
                db.add(new_u)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error during TaxSnap database seeding: {e}")
    finally:
        db.close()
