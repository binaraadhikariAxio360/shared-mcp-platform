from datetime import datetime
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
    title="PropSights Real Estate Enterprise Backend",
    version="2.0.0",
    description="Luxury real estate deal pipeline, MLS property indexing, buyer affinity matching, and escrow management backed by PostgreSQL 16.",
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
    x_user_role: Annotated[Optional[str], Header(alias="x-user-role", description="Active User Role")] = "PRINCIPAL_BROKER",
    x_user_id: Annotated[Optional[str], Header(alias="x-user-id", description="User Identifier")] = "broker-lead-austin",
) -> schemas.RequestContext:
    if not x_tenant_id or not x_tenant_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header 'x-tenant-id' is required and cannot be blank.",
        )
    return schemas.RequestContext(
        tenant_id=x_tenant_id.strip(),
        user_id=(x_user_id.strip() if x_user_id and x_user_id.strip() else "broker-lead-austin"),
        user_role=(x_user_role.strip() if x_user_role and x_user_role.strip() else "PRINCIPAL_BROKER"),
    )

def require_role(context: schemas.RequestContext, allowed_roles: List[str]):
    if context.user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation not permitted for role {context.user_role}",
        )

@app.get("/api/v1/auth/roles", tags=["Auth"])
def get_auth_roles(context: Annotated[schemas.RequestContext, Depends(get_request_context)]):
    return {
        "app": "PropSights",
        "current_tenant": context.tenant_id,
        "current_role": context.user_role,
        "current_user": context.user_id,
        "roles": [
            {
                "id": "PRINCIPAL_BROKER",
                "label": "Principal Broker (Admin)",
                "description": "Full CRUD across listings, buyers, deals, escrow stages, and agents.",
            },
            {
                "id": "LICENSED_AGENT",
                "label": "Licensed Agent (Agent)",
                "description": "Full CRUD on listings and buyers; update listing status; read deals.",
            },
            {
                "id": "ESCROW_OFFICER",
                "label": "Escrow Officer (Compliance)",
                "description": "Full CRUD on deals/contracts and closing stages; read-only on properties.",
            },
            {
                "id": "CLIENT_BUYER",
                "label": "Client / Buyer (Viewer)",
                "description": "Read-only view on available properties; cannot modify listings, deals, or buyers.",
            },
        ],
        "tenants": [
            {
                "id": "tenant-001",
                "name": "Austin Premier Realty",
                "description": "Austin Metropolitan Commercial & Residential Brokerage",
            },
            {
                "id": "tenant-002",
                "name": "Lone Star Luxury Realty",
                "description": "Dallas / Fort Worth Luxury & Estate Advisory",
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
    company_name = payload.company_name.strip() if payload.company_name and payload.company_name.strip() else "New Brokerage Group"
    if not tenant_id:
        slug = company_name.lower().replace(" ", "-")[:10]
        tenant_id = f"tenant-{slug}-{str(uuid.uuid4())[:4]}"

    # Ensure broker agent exists for new tenant
    agent = db.query(models.BrokerAgent).filter(models.BrokerAgent.tenant_id == tenant_id).first()
    if not agent:
        agent = models.BrokerAgent(
            tenant_id=tenant_id,
            name=payload.full_name.strip(),
            email=clean_email,
            phone="(512) 555-0100",
            license_no="TREC #882190",
            active_listings_count=0,
        )
        db.add(agent)
        db.commit()

    new_user = models.User(
        email=clean_email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=(payload.role.strip() if payload.role and payload.role.strip() else "PRINCIPAL_BROKER"),
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
        name=f"Realty Principal ({context.user_role})",
        email=f"{context.user_role.lower()}@{context.tenant_id}.com",
        role=context.user_role,
        tenant_id=context.tenant_id,
        company_name=f"Brokerage ({context.tenant_id})",
    )

# -----------------------------------------------------------------------------
# System & Health
# -----------------------------------------------------------------------------
@app.get("/", tags=["System"])
def root_index():
    return {
        "service": "PropSights Realty API",
        "status": "operational",
        "database": "PostgreSQL 16 Connected",
        "docs_url": "/docs",
        "health_url": "/health",
        "frontend_url": "http://localhost:3003",
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
        "service": "propsights-backend",
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
    tenant_id = context.tenant_id

    # Properties
    props = db.query(models.PropertyListing).filter(models.PropertyListing.tenant_id == tenant_id).all()
    active_listings = sum(1 for p in props if p.status.upper() == "AVAILABLE")
    under_contract_props = sum(1 for p in props if p.status.upper() == "UNDER_CONTRACT")
    closed_props = sum(1 for p in props if p.status.upper() == "CLOSED")
    total_listings_volume = sum(p.price for p in props)

    # Buyers
    buyers = db.query(models.BuyerProfile).filter(models.BuyerProfile.tenant_id == tenant_id).all()
    matched_buyers = sum(1 for b in buyers if b.affinity_score >= 90)

    # Deals & Contracts
    deals = db.query(models.DealContract).filter(models.DealContract.tenant_id == tenant_id).all()
    pipeline_volume = sum(d.contract_price for d in deals)
    under_contract_deals = [d for d in deals if d.stage.upper() == "UNDER_CONTRACT"]
    under_contract_volume = sum(d.contract_price for d in under_contract_deals)

    avg_deal_size = (pipeline_volume / len(deals)) if deals else 0.0

    stage_breakdown: Dict[str, int] = {}
    for d in deals:
        stage_breakdown[d.stage] = stage_breakdown.get(d.stage, 0) + 1

    brokerage_map = {
        "tenant-001": "Austin Premier Realty Network",
        "tenant-002": "Lone Star Luxury Realty",
    }
    brokerage_name = brokerage_map.get(tenant_id, f"Realty Advisory ({tenant_id})")

    return schemas.DashboardSummary(
        tenant_id=tenant_id,
        brokerage_name=brokerage_name,
        active_listings_count=active_listings,
        under_contract_count=under_contract_props,
        closed_count=closed_props,
        total_listings_volume=round(total_listings_volume, 2),
        under_contract_volume=round(under_contract_volume, 2),
        matched_buyers_count=matched_buyers,
        average_deal_size=round(avg_deal_size, 2),
        stage_breakdown=stage_breakdown,
        pipeline_volume=round(pipeline_volume, 2),
    )

# -----------------------------------------------------------------------------
# 2. Property Listings CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/properties", response_model=List[schemas.PropertyListingRead], tags=["Properties"])
def list_properties(
    status: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.PropertyListing).filter(models.PropertyListing.tenant_id == context.tenant_id)
    if status:
        query = query.filter(models.PropertyListing.status.ilike(f"%{status}%"))
    return query.order_by(models.PropertyListing.price.desc()).all()

@app.post("/api/v1/properties", response_model=schemas.PropertyListingRead, status_code=status.HTTP_201_CREATED, tags=["Properties"])
def create_property(
    payload: schemas.PropertyListingCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "LICENSED_AGENT"])
    amenities_str = payload.amenities
    if isinstance(amenities_str, list):
        amenities_str = ", ".join(str(a) for a in amenities_str)
    elif amenities_str is None:
        amenities_str = "Pool, Parking, Smart Home"

    new_prop = models.PropertyListing(
        tenant_id=context.tenant_id,
        title=payload.title,
        address=payload.address,
        price=payload.price,
        beds=payload.beds,
        baths=payload.baths,
        sqft=payload.sqft,
        amenities=str(amenities_str),
        status=payload.status or "AVAILABLE",
        assigned_agent=payload.assigned_agent,
    )
    db.add(new_prop)
    db.commit()
    db.refresh(new_prop)
    return new_prop

@app.get("/api/v1/properties/{prop_id}", response_model=schemas.PropertyListingRead, tags=["Properties"])
def get_property(
    prop_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    prop = db.query(models.PropertyListing).filter(
        models.PropertyListing.id == prop_id,
        models.PropertyListing.tenant_id == context.tenant_id,
    ).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property listing not found")
    return prop

@app.put("/api/v1/properties/{prop_id}", response_model=schemas.PropertyListingRead, tags=["Properties"])
def update_property(
    prop_id: str,
    payload: schemas.PropertyListingUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "LICENSED_AGENT"])
    prop = db.query(models.PropertyListing).filter(
        models.PropertyListing.id == prop_id,
        models.PropertyListing.tenant_id == context.tenant_id,
    ).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property listing not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "amenities" in update_data and update_data["amenities"] is not None:
        if isinstance(update_data["amenities"], list):
            update_data["amenities"] = ", ".join(str(a) for a in update_data["amenities"])
        else:
            update_data["amenities"] = str(update_data["amenities"])

    for field, val in update_data.items():
        setattr(prop, field, val)

    db.commit()
    db.refresh(prop)
    return prop

@app.delete("/api/v1/properties/{prop_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Properties"])
def delete_property(
    prop_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "LICENSED_AGENT"])
    prop = db.query(models.PropertyListing).filter(
        models.PropertyListing.id == prop_id,
        models.PropertyListing.tenant_id == context.tenant_id,
    ).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property listing not found")
    db.delete(prop)
    db.commit()

# -----------------------------------------------------------------------------
# 3. Buyer Profiles CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/buyers", response_model=List[schemas.BuyerProfileRead], tags=["Buyers"])
def list_buyers(
    is_preapproved: Optional[bool] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.BuyerProfile).filter(models.BuyerProfile.tenant_id == context.tenant_id)
    if is_preapproved is not None:
        query = query.filter(models.BuyerProfile.is_preapproved == is_preapproved)

    buyers = query.order_by(models.BuyerProfile.budget.desc()).all()
    prop_map = {p.id: p.title for p in db.query(models.PropertyListing).filter(models.PropertyListing.tenant_id == context.tenant_id).all()}

    res = []
    for b in buyers:
        item = schemas.BuyerProfileRead.from_orm(b)
        item.target_property_title = prop_map.get(b.target_property_id) if b.target_property_id else None
        res.append(item)
    return res

@app.post("/api/v1/buyers", response_model=schemas.BuyerProfileRead, status_code=status.HTTP_201_CREATED, tags=["Buyers"])
def create_buyer(
    payload: schemas.BuyerProfileCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "LICENSED_AGENT"])
    new_buyer = models.BuyerProfile(
        tenant_id=context.tenant_id,
        name=payload.name,
        budget=payload.budget,
        preferred_type=payload.preferred_type,
        target_area=payload.target_area,
        is_preapproved=payload.is_preapproved,
        target_property_id=payload.target_property_id,
        affinity_score=payload.affinity_score,
    )
    db.add(new_buyer)
    db.commit()
    db.refresh(new_buyer)

    prop = db.query(models.PropertyListing).filter(models.PropertyListing.id == new_buyer.target_property_id).first() if new_buyer.target_property_id else None
    res = schemas.BuyerProfileRead.from_orm(new_buyer)
    res.target_property_title = prop.title if prop else None
    return res

@app.get("/api/v1/buyers/{buyer_id}", response_model=schemas.BuyerProfileRead, tags=["Buyers"])
def get_buyer(
    buyer_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    buyer = db.query(models.BuyerProfile).filter(
        models.BuyerProfile.id == buyer_id,
        models.BuyerProfile.tenant_id == context.tenant_id,
    ).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer profile not found")

    prop = db.query(models.PropertyListing).filter(models.PropertyListing.id == buyer.target_property_id).first() if buyer.target_property_id else None
    res = schemas.BuyerProfileRead.from_orm(buyer)
    res.target_property_title = prop.title if prop else None
    return res

@app.put("/api/v1/buyers/{buyer_id}", response_model=schemas.BuyerProfileRead, tags=["Buyers"])
def update_buyer(
    buyer_id: str,
    payload: schemas.BuyerProfileUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "LICENSED_AGENT"])
    buyer = db.query(models.BuyerProfile).filter(
        models.BuyerProfile.id == buyer_id,
        models.BuyerProfile.tenant_id == context.tenant_id,
    ).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer profile not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(buyer, field, val)

    db.commit()
    db.refresh(buyer)

    prop = db.query(models.PropertyListing).filter(models.PropertyListing.id == buyer.target_property_id).first() if buyer.target_property_id else None
    res = schemas.BuyerProfileRead.from_orm(buyer)
    res.target_property_title = prop.title if prop else None
    return res

@app.delete("/api/v1/buyers/{buyer_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Buyers"])
def delete_buyer(
    buyer_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "LICENSED_AGENT"])
    buyer = db.query(models.BuyerProfile).filter(
        models.BuyerProfile.id == buyer_id,
        models.BuyerProfile.tenant_id == context.tenant_id,
    ).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer profile not found")
    db.delete(buyer)
    db.commit()

# -----------------------------------------------------------------------------
# 4. Deals & Contracts CRUD
# -----------------------------------------------------------------------------
@app.get("/api/v1/deals", response_model=List[schemas.DealContractRead], tags=["Deals"])
def list_deals(
    stage: Optional[str] = None,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.DealContract).filter(models.DealContract.tenant_id == context.tenant_id)
    if stage:
        query = query.filter(models.DealContract.stage.ilike(f"%{stage}%"))

    deals = query.order_by(models.DealContract.contract_price.desc()).all()
    prop_map = {p.id: p.title for p in db.query(models.PropertyListing).filter(models.PropertyListing.tenant_id == context.tenant_id).all()}
    buyer_map = {b.id: b.name for b in db.query(models.BuyerProfile).filter(models.BuyerProfile.tenant_id == context.tenant_id).all()}

    res = []
    for d in deals:
        item = schemas.DealContractRead.from_orm(d)
        item.property_title = prop_map.get(d.property_id, "Property")
        item.buyer_name = buyer_map.get(d.buyer_id, "Buyer")
        res.append(item)
    return res

@app.post("/api/v1/deals", response_model=schemas.DealContractRead, status_code=status.HTTP_201_CREATED, tags=["Deals"])
def create_deal(
    payload: schemas.DealContractCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "ESCROW_OFFICER"])
    new_deal = models.DealContract(
        tenant_id=context.tenant_id,
        property_id=payload.property_id,
        buyer_id=payload.buyer_id,
        contract_price=payload.contract_price,
        closing_date=payload.closing_date,
        stage=payload.stage or "UNDER_CONTRACT",
        commission_rate=payload.commission_rate or 0.03,
    )
    db.add(new_deal)
    db.commit()
    db.refresh(new_deal)

    prop = db.query(models.PropertyListing).filter(models.PropertyListing.id == new_deal.property_id).first()
    buyer = db.query(models.BuyerProfile).filter(models.BuyerProfile.id == new_deal.buyer_id).first()

    res = schemas.DealContractRead.from_orm(new_deal)
    res.property_title = prop.title if prop else "Property"
    res.buyer_name = buyer.name if buyer else "Buyer"
    return res

@app.get("/api/v1/deals/{deal_id}", response_model=schemas.DealContractRead, tags=["Deals"])
def get_deal(
    deal_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    deal = db.query(models.DealContract).filter(
        models.DealContract.id == deal_id,
        models.DealContract.tenant_id == context.tenant_id,
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal contract not found")

    prop = db.query(models.PropertyListing).filter(models.PropertyListing.id == deal.property_id).first()
    buyer = db.query(models.BuyerProfile).filter(models.BuyerProfile.id == deal.buyer_id).first()

    res = schemas.DealContractRead.from_orm(deal)
    res.property_title = prop.title if prop else "Property"
    res.buyer_name = buyer.name if buyer else "Buyer"
    return res

@app.put("/api/v1/deals/{deal_id}", response_model=schemas.DealContractRead, tags=["Deals"])
def update_deal(
    deal_id: str,
    payload: schemas.DealContractUpdate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "ESCROW_OFFICER"])
    deal = db.query(models.DealContract).filter(
        models.DealContract.id == deal_id,
        models.DealContract.tenant_id == context.tenant_id,
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal contract not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        setattr(deal, field, val)

    db.commit()
    db.refresh(deal)

    prop = db.query(models.PropertyListing).filter(models.PropertyListing.id == deal.property_id).first()
    buyer = db.query(models.BuyerProfile).filter(models.BuyerProfile.id == deal.buyer_id).first()

    res = schemas.DealContractRead.from_orm(deal)
    res.property_title = prop.title if prop else "Property"
    res.buyer_name = buyer.name if buyer else "Buyer"
    return res

@app.delete("/api/v1/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Deals"])
def delete_deal(
    deal_id: str,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER", "ESCROW_OFFICER"])
    deal = db.query(models.DealContract).filter(
        models.DealContract.id == deal_id,
        models.DealContract.tenant_id == context.tenant_id,
    ).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal contract not found")
    db.delete(deal)
    db.commit()

# -----------------------------------------------------------------------------
# 5. Broker Agents
# -----------------------------------------------------------------------------
@app.get("/api/v1/agents", response_model=List[schemas.BrokerAgentRead], tags=["Agents"])
def list_agents(
    context: Annotated[schemas.RequestContext, Depends(get_request_context)] = None,
    db: Session = Depends(get_db),
):
    return db.query(models.BrokerAgent).filter(models.BrokerAgent.tenant_id == context.tenant_id).all()

@app.post("/api/v1/agents", response_model=schemas.BrokerAgentRead, status_code=status.HTTP_201_CREATED, tags=["Agents"])
def create_agent(
    payload: schemas.BrokerAgentCreate,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    require_role(context, ["PRINCIPAL_BROKER"])
    new_agent = models.BrokerAgent(
        tenant_id=context.tenant_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        license_no=payload.license_no,
        active_listings_count=payload.active_listings_count,
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return new_agent

# -----------------------------------------------------------------------------
# 6. Live AI Copilot Tools
# -----------------------------------------------------------------------------
@app.post(
    "/internal/tools/propsights.list_properties",
    response_model=schemas.ListPropertiesToolResponse,
    tags=["Tools"],
    summary="List available properties and active MLS inventory",
)
def tool_list_properties(
    payload: schemas.ListPropertiesToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    query = db.query(models.PropertyListing).filter(models.PropertyListing.tenant_id == context.tenant_id)
    if payload.status:
        query = query.filter(models.PropertyListing.status.ilike(f"%{payload.status}%"))
    if payload.max_price:
        query = query.filter(models.PropertyListing.price <= payload.max_price)

    props = query.order_by(models.PropertyListing.price.desc()).all()
    items = [
        schemas.PropertyDetailItem(
            id=p.id,
            title=p.title,
            address=p.address,
            price=p.price,
            beds=p.beds,
            baths=p.baths,
            sqft=p.sqft,
            status=p.status,
            assigned_agent=p.assigned_agent,
        )
        for p in props
    ]
    total_val = sum(i.price for i in items)

    return schemas.ListPropertiesToolResponse(
        tenant_id=context.tenant_id,
        count=len(items),
        total_value=round(total_val, 2),
        properties=items,
    )

@app.post(
    "/internal/tools/propsights.match_buyers",
    response_model=schemas.MatchBuyersToolResponse,
    tags=["Tools"],
    summary="Compute affinity scores between pre-approved buyers and luxury properties",
)
def tool_match_buyers(
    payload: schemas.MatchBuyersToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    min_aff = payload.min_affinity or 90
    query = db.query(models.BuyerProfile).filter(
        models.BuyerProfile.tenant_id == context.tenant_id,
        models.BuyerProfile.affinity_score >= min_aff,
    )
    if payload.property_id:
        query = query.filter(models.BuyerProfile.target_property_id == payload.property_id)

    buyers = query.order_by(models.BuyerProfile.affinity_score.desc()).all()
    prop_map = {p.id: p.title for p in db.query(models.PropertyListing).filter(models.PropertyListing.tenant_id == context.tenant_id).all()}

    matches = [
        schemas.BuyerMatchItem(
            buyer_id=b.id,
            buyer_name=b.name,
            budget=b.budget,
            preferred_type=b.preferred_type,
            target_area=b.target_area,
            is_preapproved=b.is_preapproved,
            matched_property_id=b.target_property_id,
            matched_property_title=prop_map.get(b.target_property_id),
            affinity_score=b.affinity_score,
        )
        for b in buyers
    ]

    return schemas.MatchBuyersToolResponse(
        tenant_id=context.tenant_id,
        match_count=len(matches),
        matches=matches,
    )

@app.post(
    "/internal/tools/propsights.get_pipeline_summary",
    response_model=schemas.PipelineSummaryToolResponse,
    tags=["Tools"],
    summary="Compute real-time escrow volume and deal pipeline from database",
)
def tool_get_pipeline_summary(
    payload: schemas.PipelineSummaryToolRequest,
    context: Annotated[schemas.RequestContext, Depends(get_request_context)],
    db: Session = Depends(get_db),
):
    tenant_id = context.tenant_id
    deals = db.query(models.DealContract).filter(models.DealContract.tenant_id == tenant_id).all()
    prop_map = {p.id: p.title for p in db.query(models.PropertyListing).filter(models.PropertyListing.tenant_id == tenant_id).all()}
    buyer_map = {b.id: b.name for b in db.query(models.BuyerProfile).filter(models.BuyerProfile.tenant_id == tenant_id).all()}

    pipeline_volume = sum(d.contract_price for d in deals)
    under_contract = sum(d.contract_price for d in deals if d.stage.upper() == "UNDER_CONTRACT")
    commissions = sum(d.contract_price * d.commission_rate for d in deals)

    deal_items = [
        {
            "id": d.id,
            "property_title": prop_map.get(d.property_id, "Property"),
            "buyer_name": buyer_map.get(d.buyer_id, "Buyer"),
            "contract_price": d.contract_price,
            "closing_date": d.closing_date,
            "stage": d.stage,
            "estimated_commission": round(d.contract_price * d.commission_rate, 2),
        }
        for d in deals
    ]

    return schemas.PipelineSummaryToolResponse(
        tenant_id=tenant_id,
        brokerage_name="Austin Premier Realty Network",
        total_deals_count=len(deals),
        pipeline_volume=round(pipeline_volume, 2),
        under_contract_volume=round(under_contract, 2),
        estimated_commissions=round(commissions, 2),
        deals=deal_items,
    )
