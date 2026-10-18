import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_id(prefix: str = "id") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

class PropertyListing(Base):
    __tablename__ = "property_listings"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("prp"))
    tenant_id = Column(String(50), nullable=False, index=True)
    title = Column(String(150), nullable=False)
    address = Column(String(200), nullable=False)
    price = Column(Float, nullable=False)
    beds = Column(Integer, default=3)
    baths = Column(Float, default=2.0)
    sqft = Column(Integer, default=2000)
    amenities = Column(Text, default="Balcony, Pool, Parking, Smart Home")
    status = Column(String(30), default="AVAILABLE")  # AVAILABLE, UNDER_CONTRACT, CLOSED
    assigned_agent = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    deals = relationship("DealContract", back_populates="property", cascade="all, delete-orphan")

class BuyerProfile(Base):
    __tablename__ = "buyer_profiles"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("byr"))
    tenant_id = Column(String(50), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    budget = Column(Float, nullable=False)
    preferred_type = Column(String(80), default="Single Family")  # Condo, Single Family, Penthouse, Modern Loft
    target_area = Column(String(100), default="Downtown")
    is_preapproved = Column(Boolean, default=True)
    target_property_id = Column(String(50), ForeignKey("property_listings.id"), nullable=True)
    affinity_score = Column(Integer, default=95)
    created_at = Column(DateTime, default=datetime.utcnow)

    deals = relationship("DealContract", back_populates="buyer", cascade="all, delete-orphan")

class DealContract(Base):
    __tablename__ = "deal_contracts"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("del"))
    tenant_id = Column(String(50), nullable=False, index=True)
    property_id = Column(String(50), ForeignKey("property_listings.id"), nullable=False)
    buyer_id = Column(String(50), ForeignKey("buyer_profiles.id"), nullable=False)
    contract_price = Column(Float, nullable=False)
    closing_date = Column(String(30), nullable=False)
    stage = Column(String(30), default="UNDER_CONTRACT")  # OFFER, UNDER_CONTRACT, CLOSED
    commission_rate = Column(Float, default=0.03)
    created_at = Column(DateTime, default=datetime.utcnow)

    property = relationship("PropertyListing", back_populates="deals")
    buyer = relationship("BuyerProfile", back_populates="deals")

class BrokerAgent(Base):
    __tablename__ = "broker_agents"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("agt"))
    tenant_id = Column(String(50), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(120), nullable=False)
    phone = Column(String(50), default="(512) 555-0199")
    license_no = Column(String(50), default="TREC #749201")
    active_listings_count = Column(Integer, default=2)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "propsights_users"

    id = Column(String(50), primary_key=True, default=lambda: generate_id("usr"))
    email = Column(String(150), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(50), nullable=False)
    tenant_id = Column(String(50), nullable=False, index=True)
    company_name = Column(String(150), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
