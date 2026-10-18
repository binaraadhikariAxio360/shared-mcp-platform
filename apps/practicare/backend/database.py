import os
import logging
import hashlib
import hmac
import secrets
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from models import Base, Practice, Staff, Room, Task, Checklist, InventoryItem, User, StaffInvitation, AIConversation, AIMessage, StaffLeave, AIPendingApproval, AIAuditEvent

logger = logging.getLogger("practicare.database")

def hash_password(password: str) -> str:
    iterations = 310_000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, expected = hashed_password.split("$", 3)
            actual = hashlib.pbkdf2_hmac(
                "sha256", plain_password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
            ).hex()
            return hmac.compare_digest(actual, expected)
        except (TypeError, ValueError):
            return False
    legacy = hashlib.sha256(f"axio360_secure_salt:{plain_password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, hashed_password)

def password_needs_rehash(hashed_password: str) -> bool:
    return not hashed_password.startswith("pbkdf2_sha256$")

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
    engine = create_engine("sqlite:///./practicare_fallback.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db_and_seed():
    """Create all tables and seed default multi-tenant clinical data for tenant-001."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        return

    # Safe idempotent migration for newly added columns
    try:
        with engine.begin() as conn:
            if "postgresql" in DATABASE_URL:
                conn.execute(text("ALTER TABLE practicare_users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE practicare_users ADD COLUMN IF NOT EXISTS membership_status CHARACTER VARYING(30) DEFAULT 'APPROVED';"))
                conn.execute(text("ALTER TABLE practicare_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP WITHOUT TIME ZONE;"))
                conn.execute(text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS on_shift BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS user_id CHARACTER VARYING(50);"))
                conn.execute(text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS department CHARACTER VARYING(100);"))
                conn.execute(text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS work_status CHARACTER VARYING(30) DEFAULT 'ACTIVE';"))
                conn.execute(text("ALTER TABLE staff ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP WITHOUT TIME ZONE;"))
                # Inventory import fields (migrations/003_inventory_import_fields.sql); nullable, existing rows untouched
                conn.execute(text("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS supplier CHARACTER VARYING(150);"))
                conn.execute(text("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS batch_number CHARACTER VARYING(80);"))
                conn.execute(text("ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS purchase_price NUMERIC(12, 2);"))
                conn.execute(text("UPDATE practicare_users SET is_active = TRUE WHERE is_active IS NULL;"))
                conn.execute(text("UPDATE practicare_users SET membership_status = 'APPROVED' WHERE membership_status IS NULL;"))
                conn.execute(text("UPDATE staff SET on_shift = TRUE WHERE on_shift IS NULL;"))
                conn.execute(text("UPDATE staff SET is_active = TRUE WHERE is_active IS NULL;"))
                conn.execute(text("UPDATE staff SET work_status = 'ACTIVE' WHERE work_status IS NULL;"))
    except Exception as e:
        logger.warning(f"Database migration notice: {e}")

    db: Session = SessionLocal()
    try:
        default_tenant = "tenant-001"
        existing_practice = db.query(Practice).filter(Practice.tenant_id == default_tenant).first()
        if not existing_practice:
            logger.info("Seeding initial clinical data for tenant-001...")

            # 1. Practice
            practice = Practice(
                id="prac-01",
                name="Apex Health Medical Center",
                location="Suite 400, Chicago, IL",
                room_count=12,
                tenant_id=default_tenant,
            )
            db.add(practice)
            db.flush()

            # 2. Staff
            staff_members = [
                Staff(id="stf-01", name="Dr. Evelyn Vance", role="Doctor", is_active=True, practice_id=practice.id, tenant_id=default_tenant),
                Staff(id="stf-02", name="Marcus Chen, RN", role="Nurse", is_active=True, practice_id=practice.id, tenant_id=default_tenant),
                Staff(id="stf-03", name="Sarah Jenkins", role="Admin", is_active=True, practice_id=practice.id, tenant_id=default_tenant),
                Staff(id="stf-04", name="Dr. Aris Thorne", role="Doctor", is_active=False, practice_id=practice.id, tenant_id=default_tenant),
                Staff(id="stf-05", name="John Reynolds, RN", role="Nurse", is_active=True, practice_id=practice.id, tenant_id=default_tenant),
            ]
            db.add_all(staff_members)
            db.flush()

            # 3. Rooms
            rooms = [
                Room(id="room-101", room_number="101", name="Primary Exam Suite", room_type="Exam", status="Occupied", practice_id=practice.id, tenant_id=default_tenant),
                Room(id="room-102", room_number="102", name="Pediatric Care Room", room_type="Exam", status="Available", practice_id=practice.id, tenant_id=default_tenant),
                Room(id="room-201", room_number="201", name="Minor Procedures & Surgery", room_type="Surgery", status="Turnover", practice_id=practice.id, tenant_id=default_tenant),
                Room(id="room-202", room_number="202", name="Triage & Trauma Bay", room_type="Triage", status="Occupied", practice_id=practice.id, tenant_id=default_tenant),
                Room(id="room-301", room_number="301", name="Physician Consultation A", room_type="Consultation", status="Available", practice_id=practice.id, tenant_id=default_tenant),
            ]
            db.add_all(rooms)
            db.flush()

            today_iso = date.today().isoformat()

            # 4. Tasks
            tasks = [
                Task(
                    id="tsk-01",
                    title="Autoclave sterilization & verification cycle",
                    description="Run Bowie-Dick test and certify autoclave pressure chamber at 134°C.",
                    priority="Critical",
                    status="Pending",
                    due_date=f"{today_iso} 09:30",
                    assigned_staff_id="stf-02",
                    room_id="room-201",
                    practice_id=practice.id,
                    tenant_id=default_tenant,
                ),
                Task(
                    id="tsk-02",
                    title="Review urgent blood panel labs (Room 101)",
                    description="Evaluate elevated troponin and metabolic results for patient intake.",
                    priority="High",
                    status="In Progress",
                    due_date=f"{today_iso} 10:15",
                    assigned_staff_id="stf-01",
                    room_id="room-101",
                    practice_id=practice.id,
                    tenant_id=default_tenant,
                ),
                Task(
                    id="tsk-03",
                    title="Refill crash cart epinephrine ampoules",
                    description="Restock cardiac emergency box and verify expiration stamps.",
                    priority="Critical",
                    status="Pending",
                    due_date=f"{today_iso} 11:00",
                    assigned_staff_id="stf-03",
                    room_id="room-202",
                    practice_id=practice.id,
                    tenant_id=default_tenant,
                ),
                Task(
                    id="tsk-04",
                    title="Sanitize Room 201 surgical suite",
                    description="Full terminal clean turnover after minor suture procedure.",
                    priority="High",
                    status="In Progress",
                    due_date=f"{today_iso} 13:00",
                    assigned_staff_id="stf-02",
                    room_id="room-201",
                    practice_id=practice.id,
                    tenant_id=default_tenant,
                ),
                Task(
                    id="tsk-05",
                    title="Weekly controlled substance count log",
                    description="Dual-signature audit of Schedule II narcotics vault.",
                    priority="High",
                    status="Pending",
                    due_date=f"{today_iso} 14:30",
                    assigned_staff_id="stf-01",
                    room_id=None,
                    practice_id=practice.id,
                    tenant_id=default_tenant,
                ),
                Task(
                    id="tsk-06",
                    title="Ultrasound probe disinfection verification",
                    description="High-level disinfection documentation in electronic logbook.",
                    priority="Medium",
                    status="Completed",
                    due_date=f"{today_iso} 08:30",
                    assigned_staff_id="stf-02",
                    room_id="room-102",
                    practice_id=practice.id,
                    tenant_id=default_tenant,
                ),
                Task(
                    id="tsk-15",
                    title="Review urgent blood chemistry panel (Room 101)",
                    description="Awaiting secondary physician lab verification before clinical release.",
                    priority="High",
                    status="Pending",
                    due_date=f"{today_iso} 16:00",
                    assigned_staff_id="stf-05",
                    room_id="room-101",
                    practice_id=practice.id,
                    tenant_id=default_tenant,
                ),
            ]
            db.add_all(tasks)

            # 5. Checklists
            checklists = [
                Checklist(id="chk-01", title="Morning Biohazard Waste Inspection", category="Hygiene", is_completed=True, frequency="Daily", assigned_staff_id="stf-02", practice_id=practice.id, tenant_id=default_tenant),
                Checklist(id="chk-02", title="Crash Cart Defibrillator Battery Self-Test", category="Emergency", is_completed=True, frequency="Daily", assigned_staff_id="stf-02", practice_id=practice.id, tenant_id=default_tenant),
                Checklist(id="chk-03", title="Sterilization Chemical Indicator Log", category="Sterilization", is_completed=False, frequency="Daily", assigned_staff_id="stf-02", practice_id=practice.id, tenant_id=default_tenant),
                Checklist(id="chk-04", title="Vaccine Refrigerator Temp Monitoring (2-8°C)", category="Pharmacy", is_completed=False, frequency="Daily", assigned_staff_id="stf-03", practice_id=practice.id, tenant_id=default_tenant),
                Checklist(id="chk-05", title="Oxygen Cylinder Pressure & Flow Regulator Audit", category="Emergency", is_completed=False, frequency="Weekly", assigned_staff_id="stf-01", practice_id=practice.id, tenant_id=default_tenant),
            ]
            db.add_all(checklists)

            # 6. Inventory Items
            inventory_items = [
                InventoryItem(id="inv-01", item_name="Nitrile Exam Gloves (Medium)", current_stock=15, min_threshold=40, unit="boxes", expiry_date="2027-06-30", room_id="room-101", practice_id=practice.id, tenant_id=default_tenant),
                InventoryItem(id="inv-02", item_name="Sterile Syringes 5ml with Luer Lock", current_stock=25, min_threshold=50, unit="packs", expiry_date="2026-10-28", room_id="room-201", practice_id=practice.id, tenant_id=default_tenant),
                InventoryItem(id="inv-03", item_name="Surgical Face Masks (ASTM Level 3)", current_stock=30, min_threshold=60, unit="boxes", expiry_date="2027-12-31", room_id="room-101", practice_id=practice.id, tenant_id=default_tenant),
                InventoryItem(id="inv-04", item_name="Rapid Flu A/B Swab Test Kits", current_stock=4, min_threshold=15, unit="kits", expiry_date="2026-11-15", room_id="room-102", practice_id=practice.id, tenant_id=default_tenant),
                InventoryItem(id="inv-05", item_name="Antiseptic Chlorhexidine Solution 500ml", current_stock=45, min_threshold=20, unit="bottles", expiry_date="2028-01-15", room_id="room-201", practice_id=practice.id, tenant_id=default_tenant),
                InventoryItem(id="inv-06", item_name="Lidocaine 2% with Epinephrine 20ml", current_stock=6, min_threshold=12, unit="vials", expiry_date="2026-10-31", room_id="room-201", practice_id=practice.id, tenant_id=default_tenant),
            ]
            db.add_all(inventory_items)

            db.commit()
            logger.info("Successfully seeded tenant-001 clinical data.")

        # Seed tenant-002 (Metro Health Urgent Care)
        tenant_02 = "tenant-002"
        existing_t2 = db.query(Practice).filter(Practice.tenant_id == tenant_02).first()
        if not existing_t2:
            logger.info("Seeding initial clinical data for tenant-002 (Metro Health Urgent Care)...")
            p2 = Practice(
                id="prac-metro-02",
                name="Metro Health Urgent Care",
                location="742 North Michigan Ave, Chicago, IL",
                room_count=8,
                tenant_id=tenant_02,
            )
            db.add(p2)
            db.flush()

            staff_t2 = [
                Staff(id="stf-m01", name="Dr. Robert Hayes", role="Doctor", is_active=True, practice_id=p2.id, tenant_id=tenant_02),
                Staff(id="stf-m02", name="Elena Rostova, RN", role="Nurse", is_active=True, practice_id=p2.id, tenant_id=tenant_02),
                Staff(id="stf-m03", name="Jordan Miller", role="Admin", is_active=True, practice_id=p2.id, tenant_id=tenant_02),
            ]
            db.add_all(staff_t2)
            db.flush()

            rooms_t2 = [
                Room(id="room-m101", room_number="101", name="Rapid Triage Alpha", room_type="Triage", status="Occupied", practice_id=p2.id, tenant_id=tenant_02),
                Room(id="room-m102", room_number="102", name="Acute Exam Bay 2", room_type="Exam", status="Available", practice_id=p2.id, tenant_id=tenant_02),
                Room(id="room-m201", room_number="201", name="Digital X-Ray & Ortho", room_type="Diagnostic", status="Turnover", practice_id=p2.id, tenant_id=tenant_02),
            ]
            db.add_all(rooms_t2)

            tasks_t2 = [
                Task(id="tsk-m01", title="Rapid PCR COVID/Flu Swab Batch", priority="HIGH", status="Pending", assigned_staff_id="stf-m02", room_id="room-m101", practice_id=p2.id, tenant_id=tenant_02, due_date=str(date.today())),
                Task(id="tsk-m02", title="Autoclave Spore Testing Verification", priority="CRITICAL", status="Pending", assigned_staff_id="stf-m03", room_id="room-m201", practice_id=p2.id, tenant_id=tenant_02, due_date=str(date.today())),
                Task(id="tsk-m03", title="Daily Crash Cart Narcotics Audit", priority="MEDIUM", status="Completed", assigned_staff_id="stf-m01", room_id="room-m101", practice_id=p2.id, tenant_id=tenant_02, due_date=str(date.today())),
            ]
            db.add_all(tasks_t2)

            checklists_t2 = [
                Checklist(id="chk-m01", title="Triage Rapid Infusion Cart Audit", category="Emergency", is_completed=True, frequency="Daily", assigned_staff_id="stf-m02", practice_id=p2.id, tenant_id=tenant_02),
                Checklist(id="chk-m02", title="Lead Apron & Thyroid Shield Radiation Test", category="Safety", is_completed=False, frequency="Monthly", assigned_staff_id="stf-m01", practice_id=p2.id, tenant_id=tenant_02),
            ]
            db.add_all(checklists_t2)

            inventory_t2 = [
                InventoryItem(id="inv-m01", item_name="Pediatric Nebulizer Aerosol Masks", current_stock=8, min_threshold=20, unit="masks", expiry_date="2027-10-31", room_id="room-m101", practice_id=p2.id, tenant_id=tenant_02),
                InventoryItem(id="inv-m02", item_name="IV Cannula 20G Pink", current_stock=65, min_threshold=30, unit="packs", expiry_date="2028-04-15", room_id="room-m102", practice_id=p2.id, tenant_id=tenant_02),
                InventoryItem(id="inv-m03", item_name="EpiPen 0.3mg Auto-Injectors", current_stock=3, min_threshold=8, unit="pens", expiry_date="2026-12-15", room_id="room-m101", practice_id=p2.id, tenant_id=tenant_02),
            ]
            db.add_all(inventory_t2)

            db.commit()
            logger.info("Successfully seeded tenant-002 clinical data.")

        # Seed Default Users
        seed_users = [
            ("owner@vanguardclinic.com", "password123", "Dr. Liam Vance", "CLINIC_OWNER", "tenant-001", "Apex Health Medical Center"),
            ("doctor@vanguardclinic.com", "password123", "Dr. Rachel Kim", "ATTENDING_PHYSICIAN", "tenant-001", "Apex Health Medical Center"),
            ("nurse@vanguardclinic.com", "password123", "Nurse Sarah Jenkins", "NURSE_STAFF", "tenant-001", "Apex Health Medical Center"),
            ("inv@vanguardclinic.com", "password123", "David Miller", "INVENTORY_MANAGER", "tenant-001", "Apex Health Medical Center"),
            ("owner@metrohealth.com", "password123", "Dr. Robert Hayes", "CLINIC_OWNER", "tenant-002", "Metro Health Urgent Care"),
            ("doctor@metrohealth.com", "password123", "Dr. Alicia Patel", "ATTENDING_PHYSICIAN", "tenant-002", "Metro Health Urgent Care"),
            ("nurse@metrohealth.com", "password123", "Nurse Tom Bradley", "NURSE_STAFF", "tenant-002", "Metro Health Urgent Care"),
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
        logger.error(f"Seeding failed: {e}")
    finally:
        db.close()
