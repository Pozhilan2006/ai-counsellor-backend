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

@app.post("/onboarding", response_model=schemas.OnboardingResponse)
async def onboarding(
    profile_data: schemas.UserProfileCreate,
    db: Session = Depends(get_db)
):
    """
    Complete user onboarding with UPSERT logic.
    If profile exists -> UPDATE
    If new -> INSERT
    If final_submit=true -> mark profile_complete=true
    """
    print(f"[ENDPOINT] /onboarding called for {profile_data.email}")
    
    try:
        # Check if user already exists
        existing_user = db.query(UserProfile).filter(UserProfile.email == profile_data.email).first()
        
        # Prepare data (exclude final_submit from DB fields)
        profile_dict = profile_data.model_dump(exclude={'final_submit'})
        
        if existing_user:
            # UPDATE existing profile
            print(f"[LOGIC] Updating existing profile for {profile_data.email}")
            for key, value in profile_dict.items():
                if hasattr(existing_user, key):
                    setattr(existing_user, key, value)
            
            # Mark complete if final_submit is true
            if profile_data.final_submit:
                existing_user.profile_complete = True
                print(f"[LOGIC] Marking profile as complete")
            
            db.commit()
            db.refresh(existing_user)
            profile = existing_user
            
            # Ensure state exists
            state = crud.get_user_state(db, profile.id)
            if not state:
                crud.create_user_state(db, profile.id, StageEnum.DISCOVERY)
                
        else:
            # INSERT new user
            print(f"[LOGIC] Creating new profile for {profile_data.email}")
            profile_dict["profile_complete"] = profile_data.final_submit
            profile = crud.create_user_profile(db, profile_dict)
            crud.create_user_state(db, profile.id, StageEnum.DISCOVERY)
            
            # Generate initial tasks only for new users
            if profile_data.final_submit:
                crud.generate_initial_tasks(db, profile.id)
        
        # Get current stage
        state = crud.get_user_state(db, profile.id)
        current_stage = state.current_stage if state else StageEnum.DISCOVERY
        
        print(f"[SUCCESS] Profile saved. Complete: {profile.profile_complete}")
        
        return schemas.OnboardingResponse(
            profile_complete=profile.profile_complete,
            current_stage=current_stage,
            user_id=profile.id
        )
        
    except Exception as e:
        print(f"[ERROR] Onboarding failed: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to save profile: {str(e)}")

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
    AI counsellor endpoint.
    Accepts: email, message
    Never fails on incomplete profile - provides guidance instead.
    Does NOT depend on OpenAI success to respond.
    """
    print(f"[ENDPOINT] /counsel called for {request.email}")
    
    # 1. Fetch user profile (optional - don't fail if missing)
    profile = db.query(UserProfile).filter(UserProfile.email == request.email).first()
    
    # 2. If profile incomplete, provide guidance
    if not profile or not profile.profile_complete:
        print(f"[LOGIC] Profile incomplete, providing guidance")
        return schemas.CounselResponse(
            message="I'd be happy to help! However, I notice your profile isn't complete yet. Please finish your onboarding so I can provide personalized university recommendations and guidance.",
            actions=schemas.CounselActions()
        )
    
    # 3. AI Logic (Placeholder - does not depend on OpenAI)
    print(f"[LOG] Message received: {request.message}")
    
    # TODO: Implement actual AI logic here
    # For now, return a helpful response
    return schemas.CounselResponse(
        message=f"Thank you for your question: '{request.message}'. As your AI counsellor, I'm here to help guide you through the university application process. Based on your profile, I can provide personalized advice.",
        actions=schemas.CounselActions()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
