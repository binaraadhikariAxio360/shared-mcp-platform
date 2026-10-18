import os
import logging
import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
try:
    from .models import Base, OpsProject, OpsTeamMember, OpsDeliverable, OpsComplianceDoc, User
except ImportError:
    from models import Base, OpsProject, OpsTeamMember, OpsDeliverable, OpsComplianceDoc, User

logger = logging.getLogger("onscribe-db")

def hash_password(password: str) -> str:
    salt = "axio360_secure_salt"
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://practicare_user:practicare_secure_pass@postgres-db:5432/practicare_db"
)

# Connect with pool pre-ping
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _seed_tenant_001_data(db: Session, tenant_id: str):
    try:
        logger.info("Seeding realistic initial operations and compliance dataset for tenant %s...", tenant_id)
        # 1. Team Members
        tm1 = OpsTeamMember(
            id="tm-devon-01",
            tenant_id=tenant_id,
            name="Devon Cooper",
            role="Compliance Lead",
            email="devon.cooper@apexops.internal",
            max_task_threshold=4,
            active_tasks_count=5, # Overloaded (>125%)
        )
        tm2 = OpsTeamMember(
            id="tm-alexandra-02",
            tenant_id=tenant_id,
            name="Alexandra Ramos",
            role="Operations Director",
            email="alexandra.ramos@apexops.internal",
            max_task_threshold=4,
            active_tasks_count=4, # 100% capacity
        )
        tm3 = OpsTeamMember(
            id="tm-chloe-03",
            tenant_id=tenant_id,
            name="Chloe Zhao",
            role="Senior Project Manager",
            email="chloe.zhao@apexops.internal",
            max_task_threshold=5,
            active_tasks_count=3, # 60% optimal
        )
        tm4 = OpsTeamMember(
            id="tm-julian-04",
            tenant_id=tenant_id,
            name="Julian Vance",
            role="Operations Analyst",
            email="julian.vance@apexops.internal",
            max_task_threshold=4,
            active_tasks_count=2, # 50% optimal
        )
        db.add_all([tm1, tm2, tm3, tm4])
        db.flush()

        # 2. Projects
        p1 = OpsProject(
            id="prj-iso-27k",
            tenant_id=tenant_id,
            name="ISO 27001 Security Recertification",
            code="ISO-27K",
            status="ACTIVE",
            sprint_cycle="Sprint 24-Q4",
            target_date="2026-11-15",
        )
        p2 = OpsProject(
            id="prj-erp-mig",
            tenant_id=tenant_id,
            name="Enterprise ERP Cloud Migration",
            code="ERP-MIG",
            status="ACTIVE",
            sprint_cycle="Sprint 24-Q4",
            target_date="2026-12-01",
        )
        p3 = OpsProject(
            id="prj-vra-2026",
            tenant_id=tenant_id,
            name="Vendor Risk Assessment 2026",
            code="VRA-2026",
            status="ON_HOLD",
            sprint_cycle="Sprint 25-Q1",
            target_date="2026-12-20",
        )
        db.add_all([p1, p2, p3])
        db.flush()

        # 3. Deliverables / Tasks
        d1 = OpsDeliverable(
            id="dlv-001",
            tenant_id=tenant_id,
            title="Collect third-party pen-test validation sign-off",
            project_id=p1.id,
            assignee_id=tm1.id,
            priority="CRITICAL",
            status="OVERDUE",
            due_date="2026-10-05",
            sla_days_overdue=5,
        )
        d2 = OpsDeliverable(
            id="dlv-002",
            tenant_id=tenant_id,
            title="Complete Annex A checklist",
            project_id=p1.id,
            assignee_id=tm1.id,
            priority="HIGH",
            status="OVERDUE",
            due_date="2026-10-02",
            sla_days_overdue=8,
        )
        d3 = OpsDeliverable(
            id="dlv-003",
            tenant_id=tenant_id,
            title="Legacy schema mapping sign-off",
            project_id=p2.id,
            assignee_id=tm2.id,
            priority="HIGH",
            status="OVERDUE",
            due_date="2026-10-03",
            sla_days_overdue=7,
        )
        d4 = OpsDeliverable(
            id="dlv-004",
            tenant_id=tenant_id,
            title="Review MSA terms & vendor SLA compliance",
            project_id=p3.id,
            assignee_id=tm4.id,
            priority="MEDIUM",
            status="OVERDUE",
            due_date="2026-09-29",
            sla_days_overdue=11,
        )
        d5 = OpsDeliverable(
            id="dlv-005",
            tenant_id=tenant_id,
            title="IAM Role Least Privilege Audit & Verification",
            project_id=p1.id,
            assignee_id=tm1.id,
            priority="MEDIUM",
            status="IN_PROGRESS",
            due_date="2026-10-25",
            sla_days_overdue=0,
        )
        d6 = OpsDeliverable(
            id="dlv-006",
            tenant_id=tenant_id,
            title="Kubernetes Ingress Controller Hardening",
            project_id=p2.id,
            assignee_id=tm3.id,
            priority="HIGH",
            status="IN_PROGRESS",
            due_date="2026-10-28",
            sla_days_overdue=0,
        )
        d7 = OpsDeliverable(
            id="dlv-007",
            tenant_id=tenant_id,
            title="Annual Incident Response Drill Simulation",
            project_id=p1.id,
            assignee_id=tm1.id,
            priority="MEDIUM",
            status="COMPLETED",
            due_date="2026-10-01",
            sla_days_overdue=0,
        )
        db.add_all([d1, d2, d3, d4, d5, d6, d7])
        db.flush()

        # 4. Compliance Documents (18 audited documents baseline)
        compliance_samples = [
            ("ISMS Information Security Policy Framework", "ISO 27001", "AUDITED", "2026-10-01", "Bureau Veritas"),
            ("Access Control & Password Policy A.9", "ISO 27001", "AUDITED", "2026-10-02", "Bureau Veritas"),
            ("Cryptography & Key Management Standard A.10", "ISO 27001", "AUDITED", "2026-10-03", "Bureau Veritas"),
            ("Physical & Environmental Security Controls A.11", "ISO 27001", "AUDITED", "2026-10-04", "Apex Governance Bureau"),
            ("Operations Security & Malware Protection A.12", "ISO 27001", "AUDITED", "2026-10-05", "Apex Governance Bureau"),
            ("Communications Security & Network Segmentation A.13", "ISO 27001", "AUDITED", "2026-10-06", "Apex Governance Bureau"),
            ("Supplier Relationships & Third-Party Security A.15", "ISO 27001", "AUDITED", "2026-10-07", "Bureau Veritas"),
            ("Information Security Incident Management A.16", "ISO 27001", "AUDITED", "2026-10-08", "Bureau Veritas"),
            ("Business Continuity Management ISMS A.17", "ISO 27001", "AUDITED", "2026-10-09", "Bureau Veritas"),
            ("SOC 2 Security Trust Service Criteria (CC6.1-CC6.8)", "SOC 2", "AUDITED", "2026-09-15", "Ernst & Young LLP"),
            ("SOC 2 Availability Criteria Redundancy Architecture", "SOC 2", "AUDITED", "2026-09-18", "Ernst & Young LLP"),
            ("SOC 2 Confidentiality & Data Classification Matrix", "SOC 2", "AUDITED", "2026-09-20", "Ernst & Young LLP"),
            ("SOC 2 Change Management CI/CD Approval Gate Audit", "SOC 2", "AUDITED", "2026-09-22", "Ernst & Young LLP"),
            ("SOC 2 Vendor Risk Due Diligence Protocol", "Vendor Risk", "AUDITED", "2026-09-28", "Apex Governance Bureau"),
            ("Critical Cloud Tier-1 Vendor SOC 2 Attestation Review", "Vendor Risk", "AUDITED", "2026-10-04", "Apex Governance Bureau"),
            ("Subprocessor Data Processing Agreements (DPA)", "Vendor Risk", "AUDITED", "2026-10-08", "Apex Governance Bureau"),
            ("GDPR Data Protection Impact Assessment (DPIA)", "GDPR", "AUDITED", "2026-09-10", "Apex Legal Compliance"),
            ("GDPR Subject Access Request (DSAR) Protocol", "GDPR", "AUDITED", "2026-09-12", "Apex Legal Compliance"),
        ]

        for i, (title, std, st, dt, aud) in enumerate(compliance_samples, start=1):
            doc = OpsComplianceDoc(
                id=f"cmp-{i:03d}",
                tenant_id=tenant_id,
                title=title,
                standard=std,
                status=st,
                audit_date=dt,
                auditor_name=aud,
            )
            db.add(doc)

        db.commit()
        logger.info("Successfully seeded OnScribe database tenant-001.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed tenant-001: {e}")

def init_db_and_seed():
    """Create all tables and seed initial operations and compliance data if empty."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("OnScribe tables verified/created successfully.")
    except Exception as e:
        logger.error(f"Error creating OnScribe tables: {e}")
        return

    db: Session = SessionLocal()
    try:
        tenant_id = "tenant-001"
        existing = db.query(OpsTeamMember).filter(OpsTeamMember.tenant_id == tenant_id).first()
        if not existing:
            _seed_tenant_001_data(db, tenant_id)

        # Seed Company B (tenant-002) - BluePeak Global Operations
        t2_tenant = "tenant-002"
        existing_t2 = db.query(OpsTeamMember).filter(OpsTeamMember.tenant_id == t2_tenant).first()
        if not existing_t2:
            logger.info("Seeding initial operations and compliance dataset for tenant-002 (BluePeak Global Operations)...")

            # 1. Team Members
            t2_tm1 = OpsTeamMember(
                id="tm-t2-01",
                tenant_id=t2_tenant,
                name="Sterling Archer",
                role="Operations Director",
                email="s.archer@bluepeak.internal",
                max_task_threshold=4,
                active_tasks_count=3,
            )
            t2_tm2 = OpsTeamMember(
                id="tm-t2-02",
                tenant_id=t2_tenant,
                name="Sophia Rivera",
                role="Senior Project Manager",
                email="s.rivera@bluepeak.internal",
                max_task_threshold=5,
                active_tasks_count=4,
            )
            t2_tm3 = OpsTeamMember(
                id="tm-t2-03",
                tenant_id=t2_tenant,
                name="Liam Gallagher",
                role="Systems Contributor",
                email="l.gallagher@bluepeak.internal",
                max_task_threshold=4,
                active_tasks_count=4,
            )
            t2_tm4 = OpsTeamMember(
                id="tm-t2-04",
                tenant_id=t2_tenant,
                name="Harold Finch",
                role="Compliance Auditor",
                email="h.finch@bluepeak.internal",
                max_task_threshold=3,
                active_tasks_count=2,
            )
            db.add_all([t2_tm1, t2_tm2, t2_tm3, t2_tm4])
            db.flush()

            # 2. Projects
            t2_p1 = OpsProject(
                id="prj-t2-01",
                tenant_id=t2_tenant,
                name="FedRAMP High Authorization Sprint",
                code="FEDRAMP-HIGH",
                sprint_cycle="Sprint 24-Q4",
                target_date="2026-11-30",
                status="ACTIVE",
            )
            t2_p2 = OpsProject(
                id="prj-t2-02",
                tenant_id=t2_tenant,
                name="Global Cloud Telemetry & Observability Pipeline",
                code="OBS-PIPE",
                sprint_cycle="Sprint 24-Q4",
                target_date="2026-12-15",
                status="ACTIVE",
            )
            t2_p3 = OpsProject(
                id="prj-t2-03",
                tenant_id=t2_tenant,
                name="Zero-Trust Perimeter Modernization",
                code="ZERO-TRUST",
                sprint_cycle="Sprint 25-Q1",
                target_date="2027-01-15",
                status="ON_HOLD",
            )
            db.add_all([t2_p1, t2_p2, t2_p3])
            db.flush()

            # 3. Deliverables
            t2_d1 = OpsDeliverable(
                id="dlv-t2-01",
                tenant_id=t2_tenant,
                title="Boundary Protection Architecture Review",
                project_id=t2_p1.id,
                assignee_id=t2_tm1.id,
                priority="CRITICAL",
                status="IN_PROGRESS",
                due_date="2026-10-18",
                sla_days_overdue=0,
            )
            t2_d2 = OpsDeliverable(
                id="dlv-t2-02",
                tenant_id=t2_tenant,
                title="FIPS 140-3 Cryptographic Module Verification",
                project_id=t2_p1.id,
                assignee_id=t2_tm3.id,
                priority="HIGH",
                status="IN_PROGRESS",
                due_date="2026-10-22",
                sla_days_overdue=0,
            )
            t2_d3 = OpsDeliverable(
                id="dlv-t2-03",
                tenant_id=t2_tenant,
                title="Continuous Automated Vulnerability Scanning Pipeline",
                project_id=t2_p2.id,
                assignee_id=t2_tm2.id,
                priority="HIGH",
                status="COMPLETED",
                due_date="2026-10-05",
                sla_days_overdue=0,
            )
            t2_d4 = OpsDeliverable(
                id="dlv-t2-04",
                tenant_id=t2_tenant,
                title="Third-Party Pen Test Remediation Verification",
                project_id=t2_p3.id,
                assignee_id=t2_tm3.id,
                priority="MEDIUM",
                status="PENDING",
                due_date="2026-10-29",
                sla_days_overdue=0,
            )
            db.add_all([t2_d1, t2_d2, t2_d3, t2_d4])
            db.flush()

            # 4. Compliance Docs
            t2_compliance = [
                ("FedRAMP High System Security Plan (SSP)", "FedRAMP", "AUDITED", "2026-10-02", "Coalfire Systems"),
                ("NIST SP 800-53 Rev. 5 Security Controls Assessment", "NIST 800-53", "AUDITED", "2026-10-04", "Coalfire Systems"),
                ("Continuous Monitoring (ConMon) Monthly Executive Report", "FedRAMP", "PENDING_AUDIT", "2026-10-25", "Apex Governance Bureau"),
                ("Zero-Trust Identity Provider Configuration Standard", "SOC 2", "AUDITED", "2026-09-28", "Ernst & Young LLP"),
            ]
            for i, (title, std, st, dt, aud) in enumerate(t2_compliance, start=1):
                doc = OpsComplianceDoc(
                    id=f"cmp-t2-{i:03d}",
                    tenant_id=t2_tenant,
                    title=title,
                    standard=std,
                    status=st,
                    audit_date=dt,
                    auditor_name=aud,
                )
                db.add(doc)

            db.commit()
            logger.info("Successfully seeded OnScribe database tenant-002 (BluePeak Global Operations).")

        # Seed Default Users
        seed_users = [
            ("director@apexops.com", "password123", "Evelyn Reed", "OPERATIONS_DIRECTOR", "tenant-001", "Vanguard Enterprise Operations"),
            ("pm@apexops.com", "password123", "Aaron Zhang", "PROJECT_MANAGER", "tenant-001", "Vanguard Enterprise Operations"),
            ("contributor@apexops.com", "password123", "Jordan Hayes", "TEAM_CONTRIBUTOR", "tenant-001", "Vanguard Enterprise Operations"),
            ("auditor@apexops.com", "password123", "Diana Miller", "COMPLIANCE_AUDITOR", "tenant-001", "Vanguard Enterprise Operations"),
            ("director@bluepeakops.com", "password123", "Commander Jackson Vance", "OPERATIONS_DIRECTOR", "tenant-002", "BluePeak Global Operations"),
            ("pm@bluepeakops.com", "password123", "Maya Lin", "PROJECT_MANAGER", "tenant-002", "BluePeak Global Operations"),
            ("contributor@bluepeakops.com", "password123", "Derrick Holt", "TEAM_CONTRIBUTOR", "tenant-002", "BluePeak Global Operations"),
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
        logger.error(f"Failed to seed OnScribe database: {e}")
    finally:
        db.close()
