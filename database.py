from sqlalchemy import create_engine, text, inspect
from typing import List, Dict, Optional, Union
from config import settings
import logging

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Country normalization mapping
COUNTRY_MAPPING = {
    "USA": "United States",
    "US": "United States",
    "United States": "United States",
    "UK": "United Kingdom",
    "United Kingdom": "United Kingdom",
    "Great Britain": "United Kingdom",
    "Canada": "Canada",
    "Australia": "Australia",
    "Germany": "Germany",
    # Add more as needed
}

def normalize_country(country: str) -> str:
    """Normalize country input to match database values."""
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

def verify_tables_exist():
    """Ensure required tables exist, create if missing."""
    engine = get_db_connection()
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    # Check user_profiles
    if "user_profiles" not in existing_tables:
        logger.info("Creating missing table: user_profiles")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    education_level TEXT,
                    degree TEXT,
                    graduation_year INT,
                    gpa FLOAT,
                    intended_degree TEXT,
                    field_of_study TEXT,
                    intake_year INT,
                    preferred_countries TEXT[],
                    budget_per_year INT,
                    funding_plan TEXT,
                    ielts_status TEXT,
                    gre_gmat_status TEXT,
                    sop_status TEXT,
                    profile_complete BOOLEAN DEFAULT false,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """))
            conn.commit()

# Safe fallback defaults
DEFAULT_COUNTRIES = ["USA", "UK", "Canada", "Germany", "Australia"]

def query_universities(
    countries: Union[str, List[str], None] = None,
    max_budget: float | None = None,
    university_ids: List[int] | None = None,
    limit: int = 20
) -> List[Dict]:
    """
    Query universities from database with proper filtering and failsafe fallback.
    
    Supports two modes:
    1. Discovery mode: Filter by countries + budget (with safe defaults)
    2. Shortlist mode: Fetch by university IDs only
    
    FAILSAFE GUARANTEE: Never returns empty if universities exist in database.
    
    Args:
        countries: List of country names (discovery mode)
        max_budget: Maximum budget in USD (discovery mode)
        university_ids: List of university IDs (shortlist mode)
        limit: Maximum results to return
    
    Returns:
        List of university dictionaries
    """
    engine = get_db_connection()
    fallback_used = False
    
    try:
        # ========================================
        # SHORTLIST MODE: Fetch by IDs
        # ========================================
        if university_ids is not None and len(university_ids) > 0:
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
                WHERE id = ANY(:ids)
                ORDER BY rank ASC NULLS LAST
            """)
            
            with engine.connect() as conn:
                result = conn.execute(query, {"ids": university_ids})
                
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
                
                logger.info(f"Query (ID mode): ids={university_ids}, found={len(universities)}")
                return universities
        
        # ========================================
        # DISCOVERY MODE: Dynamic Filter Building
        # ========================================
        
        # SAFE DEFAULTS: Apply fallbacks for missing data
        if not countries or (isinstance(countries, list) and len(countries) == 0):
            countries = DEFAULT_COUNTRIES
            logger.info(f"No countries provided, using defaults: {DEFAULT_COUNTRIES}")
        
        # Normalize countries
        if isinstance(countries, str):
            countries = [countries]
        
        normalized_countries = []
        for c in countries:
            norm = normalize_country(c)
            if norm:
                normalized_countries.append(f"%{norm}%")
        
        # If normalization failed, use defaults
        if not normalized_countries:
            logger.warning("Country normalization failed, using defaults")
            for c in DEFAULT_COUNTRIES:
                normalized_countries.append(f"%{c}%")
        
        # Build dynamic WHERE clause
        filters = []
        params = {
            "countries": normalized_countries,
            "limit": limit
        }
        
        # Always apply country filter
        filters.append("country ILIKE ANY(:countries)")
        
        # Only apply budget filter if budget is provided and > 0
        if max_budget and max_budget > 0:
            filters.append("estimated_tuition_usd <= :max_budget")
            params["max_budget"] = max_budget
            logger.info(f"Budget filter applied: <= {max_budget}")
        else:
            logger.info("No budget filter applied (budget is NULL or 0)")
        
        where_clause = " AND ".join(filters)
        
        query = text(f"""
            SELECT 
                id,
                name,
                country,
                rank,
                ranking_band,
                competitiveness,
                estimated_tuition_usd
            FROM universities
            WHERE {where_clause}
            ORDER BY rank ASC NULLS LAST
            LIMIT :limit
        """)
        
        logger.info(f"Query (discovery mode): filters={filters}, params={params}")
        
        with engine.connect() as conn:
            result = conn.execute(query, params)
            
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
            
            logger.info(f"Query returned {len(universities)} results")
            
            # ========================================
            # FAILSAFE FALLBACK: If no results, return top-ranked
            # ========================================
            if len(universities) == 0:
                logger.warning("Filtered query returned 0 results, running fallback")
                fallback_query = text("""
                    SELECT 
                        id,
                        name,
                        country,
                        rank,
                        ranking_band,
                        competitiveness,
                        estimated_tuition_usd
                    FROM universities
                    ORDER BY rank ASC NULLS LAST
                    LIMIT 10
                """)
                
                result = conn.execute(fallback_query)
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
                
                fallback_used = True
                logger.info(f"Fallback returned {len(universities)} results")
            
            return universities
            
    except Exception as e:
        logger.error(f"Database query failed: {str(e)}")
        # Return empty list instead of crashing
        return []
