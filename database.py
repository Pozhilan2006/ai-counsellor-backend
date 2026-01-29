from sqlalchemy import create_engine, text
from typing import List, Dict, Optional
from config import settings

# Country normalization mapping
COUNTRY_MAPPING = {
    "USA": "United States",
    "US": "United States",
    "United States": "United States",
    "UK": "United Kingdom",
    "United Kingdom": "United Kingdom",
    "Canada": "Canada",
    "Australia": "Australia",
    "Germany": "Germany",
}

def normalize_country(country: str) -> str:
    """
    Normalize country input to match database values.
    
    Args:
        country: User input country (e.g., "USA", "UK")
    
    Returns:
        Normalized country name (e.g., "United States", "United Kingdom")
    """
    if not country:
        return ""
    
    # Try exact match first
    normalized = COUNTRY_MAPPING.get(country.strip())
    if normalized:
        return normalized
    
    # Try case-insensitive match
    for key, value in COUNTRY_MAPPING.items():
        if key.lower() == country.lower():
            return value
    
    # Return original if no mapping found
    return country.strip()

def get_db_connection():
    """Create and return database engine."""
    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable not set")
    return create_engine(settings.DATABASE_URL)

def query_universities(
    country: str,
    max_budget: float,
    limit: int = 10
) -> List[Dict]:
    """
    Query universities from database with MINIMAL filtering.
    
    ONLY filters by:
    - Country (case-insensitive, partial match)
    - Budget (estimated_tuition_usd <= max_budget)
    
    Args:
        country: User's preferred country (will be normalized)
        max_budget: Maximum budget (NOT multiplied by 1.2)
        limit: Maximum number of results (default 10)
    
    Returns:
        List of university dictionaries
    """
    engine = get_db_connection()
    
    # Normalize country input
    normalized_country = normalize_country(country)
    
    # Use ILIKE for case-insensitive partial matching
    query = text("""
        SELECT 
            id,
            name,
            country,
            rank,
            ranking_band,
            competitiveness,
            estimated_tuition_usd
        FROM universities
        WHERE 
            country ILIKE :country_pattern
            AND estimated_tuition_usd <= :max_budget
        ORDER BY rank ASC NULLS LAST
        LIMIT :limit
    """)
    
    with engine.connect() as conn:
        result = conn.execute(
            query,
            {
                "country_pattern": f"%{normalized_country}%",
                "max_budget": max_budget,
                "limit": limit
            }
        )
        
        universities = []
        for row in result:
            universities.append({
                "id": row.id,
                "name": row.name,
                "country": row.country,
                "rank": row.rank,
                "ranking_band": row.ranking_band,
                "competitiveness": row.competitiveness,
                "estimated_tuition_usd": row.estimated_tuition_usd
            })
        
        # Debug logging
        print(f"[DEBUG] Query params: country={normalized_country}, budget={max_budget}")
        print(f"[DEBUG] Matched universities: {len(universities)}")
        
        return universities
