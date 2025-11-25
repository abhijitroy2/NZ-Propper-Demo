from pydantic import BaseModel, Field
from typing import Optional, List, Tuple
from datetime import datetime


class PropertyInput(BaseModel):
    """Input model matching CSV columns"""
    date_gmt: Optional[str] = Field(None, alias="Date (GMT)")
    job_link: Optional[str] = Field(None, alias="Job Link")
    origin_url: Optional[str] = Field(None, alias="Origin URL")
    auckland_property_listings_limit: Optional[int] = Field(None, alias="Auckland Property Listings Limit")
    position: Optional[int] = Field(None, alias="Position")
    open_home_status: Optional[str] = Field(None, alias="Open Home Status")
    agent_name: Optional[str] = Field(None, alias="Agent Name")
    agency_name: Optional[str] = Field(None, alias="Agency Name")
    listing_date: Optional[str] = Field(None, alias="Listing Date")
    property_title: Optional[str] = Field(None, alias="Property Title")
    property_address: Optional[str] = Field(None, alias="Property Address")
    bedrooms: Optional[str] = Field(None, alias="Bedrooms")
    bathrooms: Optional[str] = Field(None, alias="Bathrooms")
    area: Optional[str] = Field(None, alias="Area")
    price: Optional[str] = Field(None, alias="Price")
    property_link: Optional[str] = Field(None, alias="Property Link")

    class Config:
        populate_by_name = True


class CalculationResult(BaseModel):
    """Output model with all calculated values"""
    # Original fields
    date_gmt: Optional[str] = None
    job_link: Optional[str] = None
    origin_url: Optional[str] = None
    auckland_property_listings_limit: Optional[int] = None
    position: Optional[int] = None
    open_home_status: Optional[str] = None
    agent_name: Optional[str] = None
    agency_name: Optional[str] = None
    listing_date: Optional[str] = None
    property_title: Optional[str] = None
    property_address: Optional[str] = None
    bedrooms: Optional[str] = None
    bathrooms: Optional[str] = None
    area: Optional[str] = None
    price: Optional[str] = None
    property_link: Optional[str] = None
    
    # Calculated values
    potential_purchase_price: float
    renovation_budget: float
    holding_costs: float
    disposal_costs: float
    contingency: float
    potential_sale_price: float
    profit: float
    
    # Rental yield (from scraping)
    rental_yield_percentage: Optional[float] = None
    rental_yield_range: Optional[Tuple[float, float]] = None  # Weekly rent range (low, high)
    
    # Flags
    is_good_deal: bool
    has_stress_keywords: bool


class ProcessResponse(BaseModel):
    """Response model with results array and summary stats"""
    results: List[CalculationResult]
    total_properties: int
    good_deals_count: int
    stress_sales_count: int
    duplicates_removed: int


