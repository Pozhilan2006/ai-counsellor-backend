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
    Complete user onboarding.
    Upserts user profile (IDEMPOTENT).
    """
    try:
        # Check if user already exists
        existing_user = db.query(UserProfile).filter(UserProfile.email == profile_data.email).first()
        
        if existing_user:
            # Update existing profile
            for key, value in profile_data.model_dump().items():
                setattr(existing_user, key, value)
            existing_user.profile_complete = True
            db.commit()
            db.refresh(existing_user)
            profile = existing_user
            
            # Ensure state exists
            state = crud.get_user_state(db, profile.id)
            if not state:
                crud.create_user_state(db, profile.id, StageEnum.DISCOVERY)
                
        else:
            # Create new user
            profile_dict = profile_data.model_dump()
            profile_dict["profile_complete"] = True
            profile = crud.create_user_profile(db, profile_dict)
            crud.create_user_state(db, profile.id, StageEnum.DISCOVERY)
            crud.generate_initial_tasks(db, profile.id)
        
        return schemas.OnboardingResponse(
            profile_complete=True,
            current_stage=StageEnum.DISCOVERY,
            user_id=profile.id
        )
        
    except Exception as e:
        print(f"Onboarding Error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to save profile: {str(e)}")

@app.get("/recommendations", response_model=schemas.MatchesResponse)
async def get_deterministic_recommendations(
    email: str,
    db: Session = Depends(get_db)
):
    """
    Get deterministic university recommendations.
    Strict logic: Multi-Country match + Budget fit + Rank sorting.
    """
    # 1. Fetch user profile
    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        # Return 400 as per contract if profile missing
        raise HTTPException(status_code=400, detail="Profile not found. Please complete onboarding.")

    # 2. Validate onboarding
    if not profile.profile_complete:
         raise HTTPException(status_code=400, detail="Profile incomplete. Please complete onboarding.")

    # 3. Query universities
    countries = profile.preferred_countries if profile.preferred_countries else ["USA"] # Default fallback
    budget = profile.budget_per_year or 0
    
    # Query with multi-country support
    unis = query_universities(
        countries=countries,
        max_budget=float(budget),
        limit=20 # Get top 20 to distribute
    )
    
    # 4. Determinstic Categorization by Rank
    dream = []
    target = []
    safe = []

    for uni in unis:
        # Map DB dict to schema
        uni_obj = schemas.UniversityResponse(
            id=uni["id"],
            name=uni["name"],
            country=uni["country"],
            rank=uni["rank"],
            estimated_tuition_usd=uni["estimated_tuition_usd"],
            competitiveness=uni["competitiveness"]
        )
        
        # Categorize
        rank = uni["rank"] or 999
        if rank <= 100:
            dream.append(uni_obj)
        elif rank <= 300:
            target.append(uni_obj)
        else:
            safe.append(uni_obj)

    return schemas.MatchesResponse(
        matches=schemas.CategorizedUniversities(
            dream=dream,
            target=target,
            safe=safe
        )
    )

@app.get("/universities/recommendations", response_model=schemas.CategorizedUniversities)
async def get_recommendations(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get university recommendations (NO AI).
    Filters by country and budget, scores and categorizes.
    """
    # Get user profile
    profile = crud.get_user_profile(db, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not profile.profile_complete:
        raise HTTPException(
            status_code=403,
            detail={"error": "PROFILE_INCOMPLETE", "message": "Complete onboarding first"}
        )
    
    # Query universities
    country = profile.preferred_countries[0] if profile.preferred_countries else ""
    unis = query_universities(
        country=country,
        max_budget=profile.budget_per_year or 50000,
        limit=15
    )
    
    # Categorize
    categorized = categorize_universities(
        unis,
        gpa=float(profile.gpa) if profile.gpa else 7.0,
        budget=profile.budget_per_year or 50000
    )
    
    return schemas.CategorizedUniversities(
        dream=[schemas.UniversityResponse(**uni) for uni in categorized["dream"]],
        target=[schemas.UniversityResponse(**uni) for uni in categorized["target"]],
        safe=[schemas.UniversityResponse(**uni) for uni in categorized["safe"]]
    )

@app.post("/universities/shortlist", response_model=schemas.ShortlistResponse)
async def shortlist_university(
    request: schemas.ShortlistRequest,
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Add university to shortlist.
    If first shortlist, update stage to SHORTLIST.
    """
    # Get user state
    state = crud.get_user_state(db, user_id)
    if not state:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Add to shortlist
    crud.shortlist_university(db, user_id, request.university_id, request.category)
    
    # Check if this is first shortlist
    shortlisted = crud.get_user_universities(db, user_id, shortlisted=True)
    if len(shortlisted) == 1 and state.current_stage == StageEnum.DISCOVERY:
        crud.update_user_stage(db, user_id, StageEnum.SHORTLIST)
    
    return schemas.ShortlistResponse(
        success=True,
        message="University added to shortlist"
    )

@app.post("/universities/lock", response_model=schemas.LockResponse)
async def lock_university(
    request: schemas.LockRequest,
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Lock university for application.
    Gate: Must have at least one shortlisted university.
    """
    # Check shortlist
    shortlisted = crud.get_user_universities(db, user_id, shortlisted=True)
    if not shortlisted:
        raise HTTPException(
            status_code=403,
            detail={"error": "NO_SHORTLIST", "message": "Shortlist at least one university first"}
        )
    
    # Lock university
    try:
        crud.lock_university(db, user_id, request.university_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Update stage
    crud.update_user_stage(db, user_id, StageEnum.LOCKED)
    
    # Generate application tasks
    crud.create_task(db, user_id, "Prepare SOP", "Write Statement of Purpose", StageEnum.APPLICATION)
    crud.create_task(db, user_id, "Gather documents", "Collect transcripts, certificates", StageEnum.APPLICATION)
    crud.create_task(db, user_id, "Submit application", "Complete online application", StageEnum.APPLICATION)
    
    return schemas.LockResponse(
        success=True,
        message="University locked for application"
    )

@app.get("/application", response_model=schemas.ApplicationResponse)
async def get_application(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    Get application guidance.
    Gate: current_stage == LOCKED
    """
    # Check stage
    state = crud.get_user_state(db, user_id)
    if not state or state.current_stage != StageEnum.LOCKED:
        raise HTTPException(
            status_code=403,
            detail={"error": "STAGE_LOCKED", "message": "Lock a university first"}
        )
    
    # Get locked university
    locked = crud.get_locked_university(db, user_id)
    if not locked:
        raise HTTPException(status_code=404, detail="No locked university found")
    
    # Get application tasks
    tasks = crud.get_tasks_by_stage(db, user_id, StageEnum.APPLICATION)
    
    # Timeline
    timeline = [
        "Month 1: Prepare documents",
        "Month 2: Write SOP and essays",
        "Month 3: Submit application",
        "Month 4-6: Wait for decision"
    ]
    
    return schemas.ApplicationResponse(
        locked_university=schemas.UniversityResponse(
            id=locked.university_id,
            name="University Name",  # TODO: Join with universities table
            country="Country",
            rank=0,
            estimated_tuition_usd=0,
            competitiveness="MEDIUM"
        ),
        tasks=[schemas.TaskResponse.model_validate(t) for t in tasks],
        timeline=timeline
    )

@app.post("/counsel", response_model=schemas.CounselResponse)
async def counsel(
    request: schemas.CounselRequest,
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    AI counsellor endpoint (actions, not chat).
    Gate: profile_complete == true
    """
    # Check profile
    profile = crud.get_user_profile(db, user_id)
    if not profile or not profile.profile_complete:
        raise HTTPException(
            status_code=403,
            detail={"error": "PROFILE_INCOMPLETE", "message": "Complete onboarding first"}
        )
    
    # TODO: Implement AI logic with Gemini
    # For now, return placeholder
    return schemas.CounselResponse(
        message="AI counsellor response placeholder. Implement Gemini integration.",
        actions=schemas.CounselActions()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
