from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import Optional, List

from config import settings
from models import Base, StageEnum, UserProfile
import crud
import schemas
from database import query_universities, verify_tables_exist
from scoring import categorize_universities

# Create FastAPI app
app = FastAPI(title="AI Counsellor Backend")

# Ensure database tables exist on startup
@app.on_event("startup")
def startup_event():
    verify_tables_exist()

# Global Custom Error Handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert 422 to 400 for frontend compatibility."""
    return JSONResponse(
        status_code=400,
        content={"error": "VALIDATION_ERROR", "message": f"Invalid data format: {str(exc)}"},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions."""
    print(f"Global Error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred. Please try again."},
    )

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================
# ENDPOINTS
# ============================================

@app.get("/")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "ai-counsellor-backend"}

@app.get("/user/stage")
async def get_user_stage(email: str, db: Session = Depends(get_db)):
    """
    Get user's current stage by email.
    Returns 404 if user not found.
    """
    print(f"[ENDPOINT] /user/stage called for {email}")
    
    try:
        # Look up user
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        
        if not profile:
            raise HTTPException(
                status_code=404,
                detail={"error": "USER_NOT_FOUND", "message": "User not found"}
            )
        
        # Get or create state
        state = crud.get_or_create_user_state(db, profile.id)
        
        return {
            "email": email,
            "current_stage": state.current_stage,
            "profile_complete": profile.profile_complete
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] get_user_stage failed: {str(e)}")
        raise HTTPException(status_code=500, detail={"error": "STAGE_FETCH_FAILED", "message": str(e)})

@app.post("/onboarding", response_model=schemas.OnboardingResponse)
async def onboarding(
    profile_data: schemas.UserProfileCreate,
    db: Session = Depends(get_db)
):
    """
    Deterministic onboarding with state management (UPSERT).
    - If user exists: UPDATE profile data
    - If user doesn't exist: CREATE new user
    - Sets profile_complete = true on final_submit
    - UPSERTS user_states to DISCOVERY stage
    """
    print(f"[ENDPOINT] /onboarding called for {profile_data.email}")
    
    try:
        # Look up user by email
        profile = db.query(UserProfile).filter(UserProfile.email == profile_data.email).first()
        
        # Prepare data (exclude final_submit from DB fields)
        profile_dict = profile_data.model_dump(exclude={'final_submit'})
        
        if profile:
            # UPDATE existing profile
            print(f"[LOGIC] Updating existing profile for {profile_data.email}")
            for key, value in profile_dict.items():
                if hasattr(profile, key):
                    setattr(profile, key, value)
            
            # Mark complete on final submit
            if profile_data.final_submit:
                profile.profile_complete = True
                print(f"[LOGIC] Marking profile as complete")
            
            db.commit()
            db.refresh(profile)
        else:
            # CREATE new user
            print(f"[LOGIC] Creating new user for {profile_data.email}")
            profile_dict["profile_complete"] = profile_data.final_submit
            profile = crud.create_user_profile(db, profile_dict)
        
        # UPSERT user_states (get-or-create pattern)
        if profile.profile_complete:
            print(f"[LOGIC] Upserting user_states to DISCOVERY")
            crud.update_user_stage(db, profile.id, "DISCOVERY")
            
            # Generate initial tasks for newly completed profiles
            existing_tasks = crud.get_all_tasks(db, profile.id)
            if not existing_tasks:
                crud.generate_initial_tasks(db, profile.id)
        
        # Get current stage
        state = crud.get_or_create_user_state(db, profile.id)
        current_stage = state.current_stage
        
        print(f"[SUCCESS] Profile saved. Complete: {profile.profile_complete}, Stage: {current_stage}")
        
        return schemas.OnboardingResponse(
            profile_complete=profile.profile_complete,
            current_stage=current_stage,
            user_id=profile.id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Onboarding failed: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ONBOARDING_FAILED",
                "message": str(e)
            }
        )

@app.get("/recommendations", response_model=schemas.MatchesResponse)
async def get_deterministic_recommendations(
    email: str,
    db: Session = Depends(get_db)
):
    """
    Get deterministic university recommendations.
    Returns 404 if user not found.
    Returns 400 if profile incomplete.
    Returns empty arrays if no matches (NOT an error).
    """
    print(f"[ENDPOINT] /recommendations called for {email}")
    
    # 1. Fetch user profile
    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        print(f"[ERROR] User not found: {email}")
        raise HTTPException(status_code=404, detail="User not found")
    
    # 2. Check if profile is complete
    if not profile.profile_complete:
        print(f"[ERROR] Profile incomplete for {email}")
        raise HTTPException(status_code=400, detail="Profile incomplete. Please complete onboarding.")

    # 3. Query universities (Deterministic)
    countries = profile.preferred_countries if profile.preferred_countries else ["USA"]
    budget = profile.budget_per_year or 0
    
    print(f"[LOGIC] Querying: countries={countries}, budget={budget}")
    
    try:
        unis = query_universities(
            countries=countries,
            max_budget=float(budget),
            limit=20
        )
    except Exception as e:
        print(f"[ERROR] Database query failed: {str(e)}")
        # Return empty results instead of crashing
        unis = []
    
    # 4. Deterministic Categorization by Rank
    dream = []
    target = []
    safe = []

    for uni in unis:
        uni_obj = schemas.UniversityResponse(
            id=uni["id"],
            name=uni["name"],
            country=uni["country"],
            rank=uni["rank"],
            estimated_tuition_usd=uni["estimated_tuition_usd"],
            competitiveness=uni["competitiveness"]
        )
        
        rank = uni["rank"] or 999
        if rank <= 100:
            dream.append(uni_obj)
        elif rank <= 300:
            target.append(uni_obj)
        else:
            safe.append(uni_obj)
            
    total_count = len(dream) + len(target) + len(safe)
    print(f"[SUCCESS] Returning {total_count} matches")

    return schemas.MatchesResponse(
        matches=schemas.CategorizedUniversities(
            dream=dream,
            target=target,
            safe=safe
        ),
        count=total_count
    )

@app.post("/counsel", response_model=schemas.CounselResponse)
async def counsel(
    request: schemas.CounselRequest,
    db: Session = Depends(get_db)
):
    """
    Deterministic AI counsellor endpoint.
    - Loads user profile and state
    - Classifies intent
    - Returns stage-aware, context-specific responses
    """
    print(f"[ENDPOINT] /counsel called for {request.email}")
    
    try:
        # 1. Load user profile
        profile = db.query(UserProfile).filter(UserProfile.email == request.email).first()
        
        if not profile:
            raise HTTPException(
                status_code=404,
                detail={"error": "USER_NOT_FOUND", "message": "User not found"}
            )
        
        # 2. Check profile completeness
        if not profile.profile_complete:
            return schemas.CounselResponse(
                message="I'd be happy to help! However, I notice your profile isn't complete yet. Please finish your onboarding so I can provide personalized university recommendations and guidance.",
                actions=schemas.CounselActions()
            )
        
        # 3. Load user state
        state = crud.get_or_create_user_state(db, profile.id)
        current_stage = state.current_stage
        
        # 4. Get universities for context
        countries = profile.preferred_countries if profile.preferred_countries else ["USA"]
        budget = profile.budget_per_year or 0
        
        try:
            unis = query_universities(
                countries=countries,
                max_budget=float(budget),
                limit=10
            )
        except Exception:
            unis = []
        
        # 5. Build AI context
        context = {
            "profile": {
                "name": profile.name,
                "gpa": float(profile.gpa) if profile.gpa else None,
                "budget": profile.budget_per_year,
                "countries": profile.preferred_countries,
                "field": profile.field_of_study
            },
            "current_stage": current_stage,
            "available_universities": len(unis),
            "question": request.message
        }
        
        print(f"[LOGIC] Stage: {current_stage}, Universities: {len(unis)}")
        
        # 6. Generate stage-aware response
        # TODO: Replace with actual Gemini AI call
        if current_stage == "DISCOVERY":
            message = f"Based on your profile (GPA: {profile.gpa}, Budget: ${profile.budget_per_year}), I found {len(unis)} universities that match your criteria. {request.message}"
        elif current_stage == "SHORTLIST":
            message = f"Great question! As you're in the shortlisting phase, let me help you evaluate your options. {request.message}"
        else:
            message = f"I'm here to help with your question: '{request.message}'. Based on your current stage ({current_stage}), I can provide specific guidance."
        
        return schemas.CounselResponse(
            message=message,
            actions=schemas.CounselActions()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Counsel failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": "COUNSEL_FAILED", "message": "Failed to process your question"}
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
