import google.generativeai as genai
from typing import Dict, List
from config import settings
import json

def get_gemini_client():
    """Initialize and return Gemini client."""
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set")
    
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel('gemini-pro')

def generate_explanation(
    user_profile: Dict,
    classified_universities: Dict[str, List[Dict]]
) -> str:
    """
    Generate AI explanation for university recommendations.
    
    Args:
        user_profile: User's profile data
        classified_universities: Dict with dream/target/safe lists
    
    Returns:
        AI-generated explanation message
    """
    model = get_gemini_client()
    
    # Count universities in each category
    dream_count = len(classified_universities.get("dream", []))
    target_count = len(classified_universities.get("target", []))
    safe_count = len(classified_universities.get("safe", []))
    
    # Build prompt
    prompt = f"""
You are an AI study-abroad counselor. Generate a brief explanation (2-3 sentences) for the following university recommendations.

User Profile:
- Academic Score: {user_profile.get('academic_score')}
- Budget: ${user_profile.get('budget')}
- Preferred Country: {user_profile.get('preferred_country')}

Recommendations:
- {dream_count} DREAM universities (highly competitive, reach schools)
- {target_count} TARGET universities (good match for profile)
- {safe_count} SAFE universities (strong likelihood of admission)

Generate a concise explanation of the overall strategy. Focus on why this mix is appropriate for the student's profile.
Return ONLY the explanation text, no JSON, no formatting.
"""
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        # Fallback message if AI fails
        return f"Based on your profile, we've identified {dream_count + target_count + safe_count} universities: {dream_count} reach schools, {target_count} target schools, and {safe_count} safety schools in {user_profile.get('preferred_country')}."
