from schemas import Context, AdvisorResponse, UniversityRecommendation, RecommendationsByCategory
from models import StageEnum
from database import query_universities
from classifier import classify_universities
from gemini_client import generate_explanation

def process_counseling(context: Context) -> AdvisorResponse:
    """
    Process counseling request and return recommendations.
    
    Args:
        context: User context with profile and stage
    
    Returns:
        AdvisorResponse with recommendations and guidance
    """
    stage = context.current_stage
    profile = context.user_profile

    # ONBOARDING: Check for missing profile fields
    if stage == StageEnum.ONBOARDING:
        missing = []
        if not profile.name: missing.append("name")
        if not profile.email: missing.append("email")
        if not profile.academic_score: missing.append("academic_score")
        if not profile.budget: missing.append("budget")
        if not profile.preferred_country: missing.append("preferred_country")

        if missing:
            return AdvisorResponse(
                message=f"Please provide the following details to proceed: {', '.join(missing)}.",
                missing_fields=missing,
                next_stage=StageEnum.ONBOARDING
            )
        else:
            return AdvisorResponse(
                message="Profile complete. Moving to discovery phase.",
                next_stage=StageEnum.DISCOVERY
            )

    # DISCOVERY: Query and recommend universities
    elif stage == StageEnum.DISCOVERY:
        try:
            # Query universities with MINIMAL filtering
            # NO 1.2x multiplier, NO classification, NO academic score filtering
            universities = query_universities(
                country=profile.preferred_country,
                max_budget=profile.budget,  # Use exact budget, no multiplier
                limit=10  # Return top 10 only
            )
            
            print(f"[DEBUG] Found {len(universities)} universities for {profile.preferred_country}, budget {profile.budget}")
            
            if not universities:
                return AdvisorResponse(
                    message=f"No universities found in {profile.preferred_country} within budget ${profile.budget}. Try adjusting your preferences.",
                    next_stage=StageEnum.DISCOVERY,
                    recommendations=[]
                )
            
            # Convert to response format (flat array, no classification)
            recommendations = [
                UniversityRecommendation(
                    id=uni["id"],
                    name=uni["name"],
                    country=uni["country"],
                    rank=uni["rank"],
                    estimated_tuition_usd=uni["estimated_tuition_usd"],
                    competitiveness=uni["competitiveness"]
                )
                for uni in universities
            ]
            
            message = f"Based on your profile, here are {len(recommendations)} universities in {profile.preferred_country} within your budget."
            
            return AdvisorResponse(
                message=message,
                next_stage=StageEnum.DISCOVERY,
                recommendations=recommendations
            )
            
        except Exception as e:
            # Error handling with detailed logging
            print(f"[ERROR] Failed to query universities: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return AdvisorResponse(
                message=f"Error retrieving recommendations: {str(e)}. Please try again.",
                next_stage=StageEnum.DISCOVERY,
                recommendations=[]
            )

    # SHORTLISTING: Help narrow down choices
    elif stage == StageEnum.SHORTLISTING:
        if context.locked_university:
            return AdvisorResponse(
                message=f"You have locked a university. Preparing application guidance.",
                next_stage=StageEnum.LOCKED
            )
        else:
            return AdvisorResponse(
                message="Please select a university to lock from your shortlist.",
                next_stage=StageEnum.SHORTLISTING
            )

    # LOCKED: Focus on locked university
    elif stage == StageEnum.LOCKED:
        if context.locked_university:
            return AdvisorResponse(
                message=f"Assisting with application. What do you need help with?",
                next_stage=StageEnum.APPLICATION
            )
        else:
            return AdvisorResponse(
                message="No university locked. Returning to discovery.",
                next_stage=StageEnum.DISCOVERY
            )
    
    # APPLICATION: Application assistance
    elif stage == StageEnum.APPLICATION:
        return AdvisorResponse(
            message="Application assistance mode. How can I help with your application?",
            next_stage=StageEnum.APPLICATION
        )
            
    return AdvisorResponse(message="Invalid state.", next_stage=stage)
