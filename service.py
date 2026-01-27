from schemas import Context, AdvisorResponse
from models import StageEnum

def process_counseling(context: Context) -> AdvisorResponse:
    stage = context.current_stage
    profile = context.user_profile

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

    elif stage == StageEnum.DISCOVERY:
        # Mock recommendation logic
        rec_unis = []
        if not context.shortlisted_universities:
            # logic to recommend unversities would go here
            return AdvisorResponse(
                message="Based on your profile, here are some recommendations.",
                recommendations=[], # Populate with real data or mock
                next_stage=StageEnum.DISCOVERY
            )
        else:
             return AdvisorResponse(
                message="You have shortlisted universities. Would you like to lock one?",
                next_stage=StageEnum.SHORTLISTING
            )

    elif stage == StageEnum.SHORTLISTING:
        if context.locked_university:
             return AdvisorResponse(
                message=f"You have locked {context.locked_university.name}. Preparing application.",
                next_stage=StageEnum.LOCKED
            )
        else:
            return AdvisorResponse(
                message="Please select a university to lock.",
                next_stage=StageEnum.SHORTLISTING
            )

    elif stage == StageEnum.LOCKED:
        if context.locked_university:
             return AdvisorResponse(
                message=f"Assisting with application for {context.locked_university.name}. what do you need help with?",
                next_stage=StageEnum.APPLICATION
            )
        else:
            # Fallback if state is inconsistent
            return AdvisorResponse(
                message="No university determined. Returning to discovery.",
                next_stage=StageEnum.DISCOVERY
            )
            
    return AdvisorResponse(message="Invalid state.", next_stage=stage)
