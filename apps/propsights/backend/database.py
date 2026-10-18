import os
import logging
import hashlib
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import Base, PropertyListing, BuyerProfile, DealContract, BrokerAgent, User

logger = logging.getLogger("propsights.database")

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
    engine = create_engine("sqlite:///./propsights_fallback.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db_and_seed():
    """Create all tables and seed default real estate records for tenant-001 (Austin Premier Realty)."""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        return

    db: Session = SessionLocal()
    try:
        default_tenant = "tenant-001"
        existing_prop = db.query(PropertyListing).filter(PropertyListing.tenant_id == default_tenant).first()
        if not existing_prop:
            logger.info("Seeding initial real estate data for tenant-001 (Austin Premier Realty)...")

            # 1. Agents
            agents = [
                BrokerAgent(
                    id="agt-01",
                    tenant_id=default_tenant,
                    name="Marcus Vance",
                    email="marcus.vance@austinpremier.com",
                    phone="(512) 555-0199",
                    license_no="TREC #749201",
                    active_listings_count=2,
                ),
                BrokerAgent(
                    id="agt-02",
                    tenant_id=default_tenant,
                    name="Sarah Sterling",
                    email="sarah.sterling@austinpremier.com",
                    phone="(512) 555-0144",
                    license_no="TREC #812304",
                    active_listings_count=2,
                ),
            ]
            db.add_all(agents)
            db.flush()

            # 2. Property Listings
            properties = [
                PropertyListing(
                    id="prp-01",
                    tenant_id=default_tenant,
                    title="Skyline View Penthouse",
                    address="300 Colorado St #4201, Austin, TX 78701",
                    price=875000.0,
                    beds=2,
                    baths=2.5,
                    sqft=1850,
                    amenities="Sky Lounge, Concierge, Private Elevator, Heated Pool",
                    status="AVAILABLE",
                    assigned_agent="Sarah Sterling",
                ),
                PropertyListing(
                    id="prp-02",
                    tenant_id=default_tenant,
                    title="Heritage Craftsman Bungalow",
                    address="1408 S Congress Ave, Austin, TX 78704",
                    price=1150000.0,
                    beds=3,
                    baths=2.0,
                    sqft=2200,
                    amenities="Wrap-around Porch, Chef Kitchen, EV Charger, Solar Panels",
                    status="AVAILABLE",
                    assigned_agent="Marcus Vance",
                ),
                PropertyListing(
                    id="prp-03",
                    tenant_id=default_tenant,
                    title="The Domain Modern Loft",
                    address="11600 Century Oaks Ter, Austin, TX 78758",
                    price=495000.0,
                    beds=1,
                    baths=1.5,
                    sqft=1100,
                    amenities="Floor-to-Ceiling Windows, Smart Thermostat, Fitness Studio",
                    status="AVAILABLE",
                    assigned_agent="Sarah Sterling",
                ),
                PropertyListing(
                    id="prp-04",
                    tenant_id=default_tenant,
                    title="Barton Hills Hillside Estate",
                    address="2810 Barton Creek Blvd, Austin, TX 78735",
                    price=2400000.0,
                    beds=5,
                    baths=5.5,
                    sqft=5200,
                    amenities="Infinity Pool, Wine Cellar, Hill Country Views, Tennis Court",
                    status="UNDER_CONTRACT",
                    assigned_agent="Marcus Vance",
                ),
            ]
            db.add_all(properties)
            db.flush()

            # 3. Buyers
            buyers = [
                BuyerProfile(
                    id="byr-01",
                    tenant_id=default_tenant,
                    name="Claire Robertson",
                    budget=920000.0,
                    preferred_type="Penthouse",
                    target_area="Downtown Austin",
                    is_preapproved=True,
                    target_property_id="prp-01",
                    affinity_score=95,
                ),
                BuyerProfile(
                    id="byr-02",
                    tenant_id=default_tenant,
                    name="David & Lauren Vance",
                    budget=1200000.0,
                    preferred_type="Single Family",
                    target_area="South Congress",
                    is_preapproved=True,
                    target_property_id="prp-02",
                    affinity_score=90,
                ),
                BuyerProfile(
                    id="byr-03",
                    tenant_id=default_tenant,
                    name="Kenneth Wu",
                    budget=550000.0,
                    preferred_type="Modern Loft",
                    target_area="The Domain / North Austin",
                    is_preapproved=True,
                    target_property_id="prp-03",
                    affinity_score=95,
                ),
                BuyerProfile(
                    id="byr-04",
                    tenant_id=default_tenant,
                    name="Austin Tech Syndicate LLC",
                    budget=2500000.0,
                    preferred_type="Hillside Estate",
                    target_area="Barton Hills",
                    is_preapproved=True,
                    target_property_id="prp-04",
                    affinity_score=98,
                ),
            ]
            db.add_all(buyers)
            db.flush()

            # 4. Deals
            deals = [
                DealContract(
                    id="del-01",
                    tenant_id=default_tenant,
                    property_id="prp-04",
                    buyer_id="byr-04",
                    contract_price=2400000.0,
                    closing_date="2026-11-05",
                    stage="UNDER_CONTRACT",
                    commission_rate=0.03,
                ),
                DealContract(
                    id="del-02",
                    tenant_id=default_tenant,
                    property_id="prp-01",
                    buyer_id="byr-01",
                    contract_price=865000.0,
                    closing_date="2026-11-20",
                    stage="OFFER",
                    commission_rate=0.03,
                ),
            ]
            db.add_all(deals)
            db.commit()
            logger.info("PropSights tenant-001 seed data initialized successfully.")

        # Seed Company B (tenant-002) - Lone Star Luxury Realty
        t2_tenant = "tenant-002"
        existing_t2 = db.query(PropertyListing).filter(PropertyListing.tenant_id == t2_tenant).first()
        if not existing_t2:
            logger.info("Seeding initial real estate data for tenant-002 (Lone Star Luxury Realty)...")

            # 1. Agents
            agents_t2 = [
                BrokerAgent(
                    id="agt-t2-01",
                    tenant_id=t2_tenant,
                    name="Victoria Sterling",
                    email="v.sterling@lonestarluxury.com",
                    phone="(214) 555-0320",
                    license_no="TREC #910245",
                    active_listings_count=2,
                ),
                BrokerAgent(
                    id="agt-t2-02",
                    tenant_id=t2_tenant,
                    name="Brandon Hayes",
                    email="b.hayes@lonestarluxury.com",
                    phone="(214) 555-0388",
                    license_no="TREC #845112",
                    active_listings_count=2,
                ),
            ]
            db.add_all(agents_t2)
            db.flush()

            # 2. Properties
            properties_t2 = [
                PropertyListing(
                    id="prp-t2-01",
                    tenant_id=t2_tenant,
                    title="Preston Hollow Modern Estate",
                    address="4920 Deloache Ave, Dallas, TX 75220",
                    price=3850000.0,
                    beds=5,
                    baths=5.5,
                    sqft=6200,
                    amenities="Sub-Zero Kitchen, Infinity Pool, Wine Cellar, 4-Car Garage",
                    status="AVAILABLE",
                    assigned_agent="Victoria Sterling",
                ),
                PropertyListing(
                    id="prp-t2-02",
                    tenant_id=t2_tenant,
                    title="Uptown Dallas Sky Villa",
                    address="2555 N Pearl St #2802, Dallas, TX 75201",
                    price=1650000.0,
                    beds=3,
                    baths=3.5,
                    sqft=2850,
                    amenities="Private Concierge, Valet, Downtown Views, Balcony",
                    status="UNDER_CONTRACT",
                    assigned_agent="Brandon Hayes",
                ),
                PropertyListing(
                    id="prp-t2-03",
                    tenant_id=t2_tenant,
                    title="Highland Park Classic Tudor",
                    address="3508 Lexington Ave, Dallas, TX 75205",
                    price=4200000.0,
                    beds=6,
                    baths=6.0,
                    sqft=7100,
                    amenities="Tennis Court, Guest House, Slate Roof, Library",
                    status="AVAILABLE",
                    assigned_agent="Victoria Sterling",
                ),
            ]
            db.add_all(properties_t2)
            db.flush()

            # 3. Buyers
            buyers_t2 = [
                BuyerProfile(
                    id="byr-t2-01",
                    tenant_id=t2_tenant,
                    name="Eleanor Vance",
                    budget=4500000.0,
                    preferred_type="Estate Manor",
                    target_area="Highland Park",
                    is_preapproved=True,
                    target_property_id="prp-t2-03",
                    affinity_score=97,
                ),
                BuyerProfile(
                    id="byr-t2-02",
                    tenant_id=t2_tenant,
                    name="Dallas Ventures Capital Group",
                    budget=2000000.0,
                    preferred_type="Luxury Penthouse",
                    target_area="Uptown",
                    is_preapproved=True,
                    target_property_id="prp-t2-02",
                    affinity_score=92,
                ),
            ]
            db.add_all(buyers_t2)
            db.flush()

            # 4. Deals
            deals_t2 = [
                DealContract(
                    id="del-t2-01",
                    tenant_id=t2_tenant,
                    property_id="prp-t2-02",
                    buyer_id="byr-t2-02",
                    contract_price=1625000.0,
                    closing_date="2026-11-18",
                    stage="UNDER_CONTRACT",
                    commission_rate=0.03,
                ),
            ]
            db.add_all(deals_t2)
            db.commit()
            logger.info("PropSights tenant-002 seed data initialized successfully.")

        # Seed Default Users
        seed_users = [
            ("broker@austinrealty.com", "password123", "Victoria Sterling", "PRINCIPAL_BROKER", "tenant-001", "Austin Premier Realty"),
            ("agent@austinrealty.com", "password123", "Lucas Hayes", "LICENSED_AGENT", "tenant-001", "Austin Premier Realty"),
            ("escrow@austinrealty.com", "password123", "Camila Rodriguez", "ESCROW_OFFICER", "tenant-001", "Austin Premier Realty"),
            ("buyer@austinrealty.com", "password123", "David Chen", "CLIENT_BUYER", "tenant-001", "Austin Premier Realty"),
            ("broker@lonestarrealty.com", "password123", "Harrison Ford Vance", "PRINCIPAL_BROKER", "tenant-002", "Lone Star Luxury Realty"),
            ("agent@lonestarrealty.com", "password123", "Savannah Belle", "LICENSED_AGENT", "tenant-002", "Lone Star Luxury Realty"),
            ("escrow@lonestarrealty.com", "password123", "Wyatt Earp", "ESCROW_OFFICER", "tenant-002", "Lone Star Luxury Realty"),
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
        logger.error(f"Error during PropSights database seeding: {e}")
    finally:
        db.close()
