# Decision Engine: University Filtering Logic
# ============================================
# CRITICAL: AI never queries the database directly.
# Backend pre-filters and injects controlled data into AI context.

# Pseudo-code
# -----------

def get_filtered_universities(user_profile):
    """
    Pre-filter universities based on user constraints.
    Returns a controlled subset for AI counseling.
    """
    
    # Extract user constraints
    preferred_countries = user_profile.preferred_countries  # e.g. ["United States", "Canada"]
    user_budget = user_profile.budget  # e.g. 30000
    
    # Calculate budget ceiling (20% buffer)
    max_tuition = user_budget * 1.2
    
    # Execute SQL query with filters
    sql = """
        SELECT 
            id,
            name,
            country,
            rank,
            ranking_band,
            competitiveness,
            avg_tuition_usd
        FROM universities
        WHERE 
            country = ANY($1)  -- Filter by preferred countries
            AND avg_tuition_usd <= $2  -- Filter by budget
            AND ranking_band IN ('Top 50', '50-100', '100-300', '300+')  -- All bands allowed
        ORDER BY rank ASC
        LIMIT 30;
    """
    
    # Execute query
    results = db.execute(sql, [preferred_countries, max_tuition])
    
    # Convert to JSON
    universities_json = [
        {
            "id": row.id,
            "name": row.name,
            "country": row.country,
            "rank": row.rank,
            "ranking_band": row.ranking_band,
            "competitiveness": row.competitiveness,
            "avg_tuition_usd": row.avg_tuition_usd
        }
        for row in results
    ]
    
    return universities_json


def build_ai_prompt(user_profile, filtered_universities):
    """
    Inject filtered universities into AI context.
    AI operates ONLY on this pre-filtered data.
    """
    
    context = {
        "user_profile": {
            "name": user_profile.name,
            "budget": user_profile.budget,
            "preferred_countries": user_profile.preferred_countries,
            "academic_score": user_profile.academic_score
        },
        "available_universities": filtered_universities,  # Pre-filtered by backend
        "instructions": "Recommend universities from the available_universities list only. Do not invent or suggest universities outside this list."
    }
    
    return context


# Example Usage
# -------------

user = {
    "name": "John Doe",
    "budget": 30000,
    "preferred_countries": ["United States", "Canada"],
    "academic_score": 85
}

# Step 1: Backend filters universities
filtered_unis = get_filtered_universities(user)

# Step 2: Backend builds AI context
ai_context = build_ai_prompt(user, filtered_unis)

# Step 3: Send to AI
# AI receives ONLY the pre-filtered list
# AI cannot query database or access other universities
