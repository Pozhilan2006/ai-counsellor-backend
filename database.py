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
    countries: Union[str, List[str]],
    max_budget: float,
    limit: int = 20
) -> List[Dict]:
    """
    Query universities from database with proper filtering.
    Supports multiple countries.
    """
    engine = get_db_connection()
    
    # Normalize countries
    if isinstance(countries, str):
        countries = [countries]
    
    normalized_countries = []
    for c in countries:
        norm = normalize_country(c)
        if norm:
            normalized_countries.append(f"%{norm}%")
    
    # If no valid countries, default to generic or fail?
    # Requirement: "preferred_countries" from frontend.
    if not normalized_countries:
        # Fallback to wildcard if none provided (shouldn't happen with proper frontend)
        normalized_countries = ["%"]

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
    
    try:
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
            
            logger.info(f"Query: countries={normalized_countries}, budget={max_budget}, found={len(universities)}")
            return universities
            
    except Exception as e:
        logger.error(f"Database query failed: {str(e)}")
        # Return empty list instead of crashing, but verify connection first
        return []
