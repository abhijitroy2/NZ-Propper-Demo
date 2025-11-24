import re
from typing import Dict, Any
from .models import CalculationResult, PropertyInput


class FlipCalculator:
    """Calculator for property flip profit calculations"""
    
    # Fixed values
    DEFAULT_PURCHASE_PRICE = 650000
    DEFAULT_SALE_PRICE = 730000
    
    # Percentages
    RENOVATION_PERCENTAGE = 0.15
    HOLDING_COSTS_PERCENTAGE = 0.04
    DISPOSAL_COSTS_PERCENTAGE = 0.025
    CONTINGENCY_PERCENTAGE = 0.015
    GOOD_DEAL_THRESHOLD_PERCENTAGE = 0.20
    
    # Stress keywords
    STRESS_KEYWORDS = [
        "must sell",
        "must be sold",
        "urgent sale",
        "mortgagee",
        "auction",
        "foreclosure",
        "distressed",
        "vendor relocated",
        "relationship split"
    ]
    
    @staticmethod
    def extract_asking_price(price_str: str) -> float:
        """
        Extract asking price from Price column.
        Handles formats like "Asking price $599,900" or "$599,900".
        Returns extracted price or None if not found.
        """
        if not price_str or not isinstance(price_str, str):
            return None
        
        price_str = price_str.strip()
        
        # Check if it contains "Asking price"
        if "asking price" in price_str.lower():
            # Extract number after "Asking price"
            match = re.search(r'asking\s+price\s*\$?\s*([\d,]+)', price_str, re.IGNORECASE)
            if match:
                price_value = match.group(1).replace(',', '')
                try:
                    price = float(price_value)
                    # Only return if it's a reasonable price (>= 1000)
                    if price >= 1000:
                        return price
                except ValueError:
                    pass
        
        # Try to extract dollar amounts with $ sign (most reliable)
        match = re.search(r'\$\s*([\d,]+)', price_str)
        if match:
            price_value = match.group(1).replace(',', '')
            try:
                price = float(price_value)
                # Only return if it's a reasonable price (>= 1000)
                if price >= 1000:
                    return price
            except ValueError:
                pass
        
        # Try to extract large numbers that might be prices (>= 10000)
        # This catches formats like "599900" or "599,900" without $ sign
        match = re.search(r'\b([\d]{4,}[\d,]*)\b', price_str)
        if match:
            price_value = match.group(1).replace(',', '')
            try:
                price = float(price_value)
                # Only return if it's a reasonable price (>= 10000)
                if price >= 10000:
                    return price
            except ValueError:
                pass
        
        return None
    
    @staticmethod
    def get_potential_purchase_price(price_str: str) -> float:
        """Get potential purchase price from Price column or use default"""
        asking_price = FlipCalculator.extract_asking_price(price_str)
        if asking_price:
            return asking_price
        return FlipCalculator.DEFAULT_PURCHASE_PRICE
    
    @staticmethod
    def has_stress_keywords(property_title: str) -> bool:
        """Check if Property Title contains stress keywords"""
        if not property_title or not isinstance(property_title, str):
            return False
        
        title_lower = property_title.lower()
        return any(keyword in title_lower for keyword in FlipCalculator.STRESS_KEYWORDS)
    
    @staticmethod
    def calculate(property_data: Dict[str, Any]) -> CalculationResult:
        """
        Calculate all values for a property.
        
        Args:
            property_data: Dictionary with property information
            
        Returns:
            CalculationResult with all calculated values
        """
        # Extract price
        price_str = property_data.get("Price", "")
        potential_purchase_price = FlipCalculator.get_potential_purchase_price(price_str)
        
        # Calculate components
        renovation_budget = potential_purchase_price * FlipCalculator.RENOVATION_PERCENTAGE
        holding_costs = potential_purchase_price * FlipCalculator.HOLDING_COSTS_PERCENTAGE
        potential_sale_price = FlipCalculator.DEFAULT_SALE_PRICE
        disposal_costs = potential_sale_price * FlipCalculator.DISPOSAL_COSTS_PERCENTAGE
        contingency = renovation_budget * FlipCalculator.CONTINGENCY_PERCENTAGE
        
        # Calculate profit
        profit = (
            potential_sale_price
            - potential_purchase_price
            - renovation_budget
            - holding_costs
            - disposal_costs
            - contingency
        )
        
        # Check if good deal
        profit_threshold = potential_purchase_price * FlipCalculator.GOOD_DEAL_THRESHOLD_PERCENTAGE
        is_good_deal = profit > profit_threshold
        
        # Check stress keywords
        property_title = property_data.get("Property Title", "")
        has_stress = FlipCalculator.has_stress_keywords(property_title)
        
        # Helper function to ensure string values
        def ensure_string(value):
            """Convert value to string if it's numeric, otherwise return as string or None"""
            if value is None or value == "":
                return None
            if isinstance(value, (int, float)):
                # Convert float to int string if it's a whole number
                if isinstance(value, float) and value.is_integer():
                    return str(int(value))
                return str(value)
            # Already a string, return as-is
            return str(value) if value else None
        
        # Create result with all original fields
        result = CalculationResult(
            # Original fields
            date_gmt=property_data.get("Date (GMT)"),
            job_link=property_data.get("Job Link"),
            origin_url=property_data.get("Origin URL"),
            auckland_property_listings_limit=property_data.get("Auckland Property Listings Limit"),
            position=property_data.get("Position"),
            open_home_status=property_data.get("Open Home Status"),
            agent_name=property_data.get("Agent Name"),
            agency_name=property_data.get("Agency Name"),
            listing_date=property_data.get("Listing Date"),
            property_title=property_data.get("Property Title"),
            property_address=property_data.get("Property Address"),
            bedrooms=ensure_string(property_data.get("Bedrooms")),
            bathrooms=ensure_string(property_data.get("Bathrooms")),
            area=ensure_string(property_data.get("Area")),
            price=ensure_string(property_data.get("Price")),
            property_link=property_data.get("Property Link"),
            
            # Calculated values
            potential_purchase_price=round(potential_purchase_price, 2),
            renovation_budget=round(renovation_budget, 2),
            holding_costs=round(holding_costs, 2),
            disposal_costs=round(disposal_costs, 2),
            contingency=round(contingency, 2),
            potential_sale_price=round(potential_sale_price, 2),
            profit=round(profit, 2),
            
            # Flags
            is_good_deal=is_good_deal,
            has_stress_keywords=has_stress
        )
        
        return result


