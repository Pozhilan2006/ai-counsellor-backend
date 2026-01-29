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
            # Query universities from database
            max_tuition = profile.budget * 1.2  # 20% buffer
            universities = query_universities(
                country=profile.preferred_country,
                max_tuition=max_tuition,
                limit=30
            )
            
            if not universities:
                return AdvisorResponse(
                    message=f"No universities found matching your criteria in {profile.preferred_country} within budget ${profile.budget}. Try adjusting your preferences.",
                    next_stage=StageEnum.DISCOVERY,
                    recommendations=RecommendationsByCategory()
                )
            
            # Classify universities into dream/target/safe
            classified = classify_universities(
                universities=universities,
                academic_score=profile.academic_score
            )
            
            # Convert to response format
            recommendations = RecommendationsByCategory(
                dream=[
                    UniversityRecommendation(
                        id=uni["id"],
                        name=uni["name"],
                        country=uni["country"],
                        tuition_fee=uni["estimated_tuition_usd"],
                        ranking=uni["rank"]
                    )
                    for uni in classified["dream"]
                ],
                target=[
                    UniversityRecommendation(
                        id=uni["id"],
                        name=uni["name"],
                        country=uni["country"],
                        tuition_fee=uni["estimated_tuition_usd"],
                        ranking=uni["rank"]
                    )
                    for uni in classified["target"]
                ],
                safe=[
                    UniversityRecommendation(
                        id=uni["id"],
                        name=uni["name"],
                        country=uni["country"],
                        tuition_fee=uni["estimated_tuition_usd"],
                        ranking=uni["rank"]
                    )
                    for uni in classified["safe"]
                ]
            )
            
            # Generate AI explanation
            try:
                message = generate_explanation(
                    user_profile={
                        "academic_score": profile.academic_score,
                        "budget": profile.budget,
                        "preferred_country": profile.preferred_country
                    },
                    classified_universities=classified
                )
            except Exception as e:
                # Fallback message if AI fails
                total = len(universities)
                message = f"Based on your profile, we've identified {total} universities in {profile.preferred_country}: {len(classified['dream'])} reach schools, {len(classified['target'])} target schools, and {len(classified['safe'])} safety schools."
            
            return AdvisorResponse(
                message=message,
                next_stage=StageEnum.DISCOVERY,
                recommendations=recommendations
            )
            
        except Exception as e:
            # Error handling
            return AdvisorResponse(
                message=f"Error retrieving recommendations: {str(e)}. Please try again.",
                next_stage=StageEnum.DISCOVERY,
                recommendations=RecommendationsByCategory()
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
