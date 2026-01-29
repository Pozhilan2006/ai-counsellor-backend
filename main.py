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
    Strict logic: Country match + Budget fit + Rank sorting.
    """
    print(f"[ENDPOINT] /recommendations called for {email}")
    
    # 1. Fetch user profile
    profile = db.query(UserProfile).filter(UserProfile.email == email).first()
    if not profile:
        print(f"[ERROR] User not found: {email}")
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Query universities (Deterministic)
    countries = profile.preferred_countries if profile.preferred_countries else ["USA"]
    budget = profile.budget_per_year or 0
    
    print(f"[LOGIC] Querying: countries={countries}, budget={budget}")
    
    unis = query_universities(
        countries=countries,
        max_budget=float(budget),
        limit=20
    )
    
    # 3. Determinstic Categorization by Rank
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
    AI counsellor endpoint (actions, not chat).
    STRICTLY AI-DRIVEN and REACTIVE.
    """
    print(f"[ENDPOINT] /counsel called")
    
    # 1. Strict Validation
    if not request.question or not request.question.strip():
        print("[ERROR] Validation failed: Missing question")
        raise HTTPException(
            status_code=400,
            detail="Question is required to talk to counsellor"
        )
        
    print(f"[LOG] Question received: {request.question}")
    
    # 2. AI Logic (Placeholder for Gemini integration)
    # In a real implementation, call Gemini here using request.question and context
    
    return schemas.CounselResponse(
        message=f"I received your question: '{request.question}'. As an AI counsellor, I can help you with that based on your profile and shortlisted universities.",
        actions=schemas.CounselActions()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
