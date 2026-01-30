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

def query_universities(
    countries: Union[str, List[str], None] = None,
    max_budget: float | None = None,
    university_ids: List[int] | None = None,
    limit: int = 20
) -> List[Dict]:
    """
    Query universities from database with proper filtering.
    
    Supports two modes:
    1. Discovery mode: Filter by countries + budget
    2. Shortlist mode: Fetch by university IDs only
    
    Args:
        countries: List of country names (discovery mode)
        max_budget: Maximum budget in USD (discovery mode)
        university_ids: List of university IDs (shortlist mode)
        limit: Maximum results to return
    
    Returns:
        List of university dictionaries
    """
    engine = get_db_connection()
    
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
        # DISCOVERY MODE: Filter by countries + budget
        # ========================================
        if countries is None or max_budget is None:
            logger.warning("query_universities called without countries/budget or university_ids")
            return []
        
        # Normalize countries
        if isinstance(countries, str):
            countries = [countries]
        
        normalized_countries = []
        for c in countries:
            norm = normalize_country(c)
            if norm:
                normalized_countries.append(f"%{norm}%")
        
        # If no valid countries, return empty
        if not normalized_countries:
            logger.warning("No valid countries provided")
            return []

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
                country ILIKE ANY(:countries)
                AND estimated_tuition_usd <= :max_budget
            ORDER BY rank ASC NULLS LAST
            LIMIT :limit
        """)
        
        with engine.connect() as conn:
            result = conn.execute(
                query,
                {
                    "countries": normalized_countries,
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
            
            logger.info(f"Query (discovery mode): countries={normalized_countries}, budget={max_budget}, found={len(universities)}")
            return universities
            
    except Exception as e:
        logger.error(f"Database query failed: {str(e)}")
        # Return empty list instead of crashing
        return []
