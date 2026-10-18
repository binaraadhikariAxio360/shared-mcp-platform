from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Security & Request Context
# -----------------------------------------------------------------------------
class RequestContext(BaseModel):
    tenant_id: str
    user_id: str
    user_role: str = "PRINCIPAL_BROKER"

class UserLoginRequest(BaseModel):
    email: str
    password: str

class UserRegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: Optional[str] = "PRINCIPAL_BROKER"
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
# Property Listing Schemas
# -----------------------------------------------------------------------------
class PropertyListingBase(BaseModel):
    title: str
    address: str
    price: float
    beds: int = 3
    baths: float = 2.0
    sqft: int = 2000
    amenities: Optional[Any] = "Pool, Parking, Smart Home"
    status: str = "AVAILABLE"  # AVAILABLE, UNDER_CONTRACT, CLOSED
    assigned_agent: Optional[str] = None

class PropertyListingCreate(PropertyListingBase):
    pass

class PropertyListingUpdate(BaseModel):
    title: Optional[str] = None
    address: Optional[str] = None
    price: Optional[float] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    sqft: Optional[int] = None
    amenities: Optional[Any] = None
    status: Optional[str] = None
    assigned_agent: Optional[str] = None

class PropertyListingRead(PropertyListingBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Buyer Profile Schemas
# -----------------------------------------------------------------------------
class BuyerProfileBase(BaseModel):
    name: str
    budget: float
    preferred_type: str = "Single Family"  # Condo, Single Family, Penthouse, Modern Loft
    target_area: str = "Downtown"
    is_preapproved: bool = True
    target_property_id: Optional[str] = None
    affinity_score: int = 90

class BuyerProfileCreate(BuyerProfileBase):
    pass

class BuyerProfileUpdate(BaseModel):
    name: Optional[str] = None
    budget: Optional[float] = None
    preferred_type: Optional[str] = None
    target_area: Optional[str] = None
    is_preapproved: Optional[bool] = None
    target_property_id: Optional[str] = None
    affinity_score: Optional[int] = None

class BuyerProfileRead(BuyerProfileBase):
    id: str
    tenant_id: str
    target_property_title: Optional[str] = None

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Deal Contract Schemas
# -----------------------------------------------------------------------------
class DealContractBase(BaseModel):
    property_id: str
    buyer_id: str
    contract_price: float
    closing_date: str
    stage: str = "UNDER_CONTRACT"  # OFFER, UNDER_CONTRACT, CLOSED
    commission_rate: float = 0.03

class DealContractCreate(DealContractBase):
    pass

class DealContractUpdate(BaseModel):
    property_id: Optional[str] = None
    buyer_id: Optional[str] = None
    contract_price: Optional[float] = None
    closing_date: Optional[str] = None
    stage: Optional[str] = None
    commission_rate: Optional[float] = None

class DealContractRead(DealContractBase):
    id: str
    tenant_id: str
    property_title: Optional[str] = None
    buyer_name: Optional[str] = None

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Broker Agent Schemas
# -----------------------------------------------------------------------------
class BrokerAgentBase(BaseModel):
    name: str
    email: str
    phone: str = "(512) 555-0199"
    license_no: str = "TREC #749201"
    active_listings_count: int = 2

class BrokerAgentCreate(BrokerAgentBase):
    pass

class BrokerAgentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    license_no: Optional[str] = None
    active_listings_count: Optional[int] = None

class BrokerAgentRead(BrokerAgentBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True

# -----------------------------------------------------------------------------
# Dashboard Summary
# -----------------------------------------------------------------------------
class DashboardSummary(BaseModel):
    tenant_id: str
    brokerage_name: str
    active_listings_count: int
    under_contract_count: int
    closed_count: int
    total_listings_volume: float
    under_contract_volume: float
    matched_buyers_count: int
    average_deal_size: float
    stage_breakdown: Dict[str, int]
    pipeline_volume: float

# -----------------------------------------------------------------------------
# AI Tools Schemas
# -----------------------------------------------------------------------------
class ListPropertiesToolRequest(BaseModel):
    status: Optional[str] = None
    max_price: Optional[float] = None

class PropertyDetailItem(BaseModel):
    id: str
    title: str
    address: str
    price: float
    beds: int
    baths: float
    sqft: int
    status: str
    assigned_agent: Optional[str] = None

class ListPropertiesToolResponse(BaseModel):
    tenant_id: str
    count: int
    total_value: float
    properties: List[PropertyDetailItem]

class MatchBuyersToolRequest(BaseModel):
    min_affinity: Optional[int] = Field(default=90, ge=50, le=100)
    property_id: Optional[str] = None

class BuyerMatchItem(BaseModel):
    buyer_id: str
    buyer_name: str
    budget: float
    preferred_type: str
    target_area: str
    is_preapproved: bool
    matched_property_id: Optional[str] = None
    matched_property_title: Optional[str] = None
    affinity_score: int

class MatchBuyersToolResponse(BaseModel):
    tenant_id: str
    match_count: int
    matches: List[BuyerMatchItem]

class PipelineSummaryToolRequest(BaseModel):
    tenant_id: Optional[str] = None

class PipelineSummaryToolResponse(BaseModel):
    tenant_id: str
    brokerage_name: str
    total_deals_count: int
    pipeline_volume: float
    under_contract_volume: float
    estimated_commissions: float
    deals: List[Dict[str, Any]]
