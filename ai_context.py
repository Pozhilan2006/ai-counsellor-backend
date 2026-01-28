# AI Counsellor Context Builder
# ==============================
# Builds the complete context sent to AI, including system prompt and user data

from prompts import get_system_prompt

def build_ai_context(user_profile, current_stage, candidate_universities, shortlisted=None, locked=None):
    """
    Build complete AI context with system prompt and user data.
    
    Args:
        user_profile: User's profile data
        current_stage: Current system stage
        candidate_universities: Pre-filtered list of universities (max 30)
        shortlisted: List of shortlisted university IDs (optional)
        locked: Locked university object (optional)
    
    Returns:
        Complete context dictionary for AI
    """
    
    context = {
        "system_prompt": get_system_prompt(),
        "user_profile": {
            "name": user_profile.get("name"),
            "email": user_profile.get("email"),
            "academic_score": user_profile.get("academic_score"),
            "budget": user_profile.get("budget"),
            "preferred_countries": user_profile.get("preferred_countries", [])
        },
        "current_stage": current_stage,
        "candidate_universities": candidate_universities,
        "instructions": "Recommend universities from candidate_universities ONLY. Never invent or suggest universities outside this list."
    }
    
    # Add stage-specific context
    if shortlisted:
        context["shortlisted_universities"] = shortlisted
    
    if locked:
        context["locked_university"] = locked
        context["instructions"] = "Focus ONLY on the locked university. Do not recommend others."
    
    return context


def format_university_for_ai(university_row):
    """
    Format a database row into AI-friendly JSON.
    
    Args:
        university_row: Database row or dict with university data
    
    Returns:
        Formatted university dict
    """
    return {
        "id": university_row.get("id"),
        "name": university_row.get("name"),
        "country": university_row.get("country"),
        "rank": university_row.get("rank"),
        "ranking_band": university_row.get("ranking_band"),
        "competitiveness": university_row.get("competitiveness"),
        "avg_tuition_usd": university_row.get("avg_tuition_usd")
    }
