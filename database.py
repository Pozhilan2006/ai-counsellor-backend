from sqlalchemy import create_engine, text
from typing import List, Dict, Optional
from config import settings

def get_db_connection():
    """Create and return database engine."""
    if not settings.DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable not set")
    return create_engine(settings.DATABASE_URL)

def query_universities(
    country: str,
    max_tuition: float,
    limit: int = 30
) -> List[Dict]:
    """
    Query universities from database with filters.
    
    Args:
        country: Preferred country
        max_tuition: Maximum tuition (budget * 1.2)
        limit: Maximum number of results
    
    Returns:
        List of university dictionaries
    """
    engine = get_db_connection()
    
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
            country = :country
            AND estimated_tuition_usd <= :max_tuition
        ORDER BY rank ASC
        LIMIT :limit
    """)
    
    with engine.connect() as conn:
        result = conn.execute(
            query,
            {
                "country": country,
                "max_tuition": max_tuition,
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
        
        return universities
