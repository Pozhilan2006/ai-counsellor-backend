from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text, and_
from sqlalchemy.orm import sessionmaker
from typing import Optional, List

from config import settings
from models import Base, StageEnum, UserProfile, Shortlist
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
    Returns default ONBOARDING stage if user not found (graceful fallback).
    """
    print(f"[ENDPOINT] /user/stage called for {email}")
    
    try:
        # Look up user
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        
        if not profile:
            # Graceful fallback - return default stage
            return {
                "email": email,
                "current_stage": "ONBOARDING",
                "profile_complete": False
            }
        
        # Get or create state
        state = crud.get_or_create_user_state(db, profile.id)
        
        return {
            "email": email,
            "current_stage": state.current_stage,
            "profile_complete": profile.profile_complete
        }
    except Exception as e:
        print(f"[ERROR] get_user_stage failed: {str(e)}")
        # Graceful fallback even on error
        return {
            "email": email,
            "current_stage": "ONBOARDING",
            "profile_complete": False
        }

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

# ============================================
# SHORTLIST ENDPOINTS
# ============================================

@app.get("/shortlist")
async def get_shortlist(email: str, db: Session = Depends(get_db)):
    """
    Get user's shortlisted universities.
    Returns empty list if user not found or no shortlists.
    """
    print(f"[ENDPOINT] GET /shortlist called for {email}")
    
    try:
        # Get user profile
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            return {"shortlists": [], "count": 0}
        
        # Get shortlists
        shortlists = crud.get_user_shortlists(db, profile.id)
        
        # Fetch university details for each shortlist
        result = []
        for shortlist in shortlists:
            # Query university details
            unis = query_universities(university_ids=[shortlist.university_id], limit=1)
            if unis:
                uni = unis[0]
                result.append({
                    "id": shortlist.id,
                    "university": {
                        "id": uni["id"],
                        "name": uni["name"],
                        "country": uni["country"],
                        "rank": uni["rank"],
                        "estimated_tuition_usd": uni["estimated_tuition_usd"]
                    },
                    "category": shortlist.category,
                    "locked": shortlist.locked,
                    "created_at": shortlist.created_at.isoformat() if shortlist.created_at else None
                })
        
        return {"shortlists": result, "count": len(result)}
    except Exception as e:
        print(f"[ERROR] get_shortlist failed: {str(e)}")
        raise HTTPException(status_code=500, detail={"error": "SHORTLIST_FETCH_FAILED", "message": str(e)})

@app.post("/shortlist")
async def add_shortlist(
    email: str,
    university_id: int,
    category: str = "TARGET",
    db: Session = Depends(get_db)
):
    """
    Add university to user's shortlist.
    Category must be one of: DREAM, TARGET, SAFE (default: TARGET)
    """
    print(f"[ENDPOINT] POST /shortlist called for {email}, university_id={university_id}, category={category}")
    
    # Validate category
    valid_categories = ["DREAM", "TARGET", "SAFE"]
    if category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_CATEGORY",
                "message": f"Category must be one of: {', '.join(valid_categories)}"
            }
        )
    
    try:
        # Get user profile
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            raise HTTPException(status_code=404, detail={"error": "USER_NOT_FOUND", "message": "User not found"})
        
        # Add to shortlist
        shortlist = crud.add_to_shortlist(db, profile.id, university_id, category)
        
        return {
            "success": True,
            "message": "University added to shortlist",
            "shortlist_id": shortlist.id,
            "category": shortlist.category
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] add_shortlist failed: {str(e)}")
        raise HTTPException(status_code=400, detail={"error": "SHORTLIST_ADD_FAILED", "message": str(e)})

@app.post("/shortlist/add")
async def add_shortlist_alt(
    email: str,
    university_id: int,
    category: str = "General",
    db: Session = Depends(get_db)
):
    """
    Alternative endpoint for adding to shortlist (frontend compatibility).
    Maps category names: Dream/Target/Safe → DREAM/TARGET/SAFE
    """
    print(f"[ENDPOINT] POST /shortlist/add called for {email}, university_id={university_id}, category={category}")
    
    # Map frontend category names to backend
    category_map = {
        "Dream": "DREAM",
        "Target": "TARGET",
        "Safe": "SAFE",
        "General": "TARGET",  # Default mapping
        "DREAM": "DREAM",
        "TARGET": "TARGET",
        "SAFE": "SAFE"
    }
    
    backend_category = category_map.get(category, "TARGET")
    
    try:
        # Get user profile
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            raise HTTPException(
                status_code=400,
                detail={"error": "USER_NOT_FOUND", "message": "User not found"}
            )
        
        # Add to shortlist (idempotent - won't fail on duplicates)
        shortlist = crud.add_to_shortlist(db, profile.id, university_id, backend_category)
        
        return {
            "success": True,
            "message": "University added to shortlist"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] add_shortlist_alt failed: {str(e)}")
        # Never return 500 - always return success or 400
        raise HTTPException(
            status_code=400,
            detail={"error": "SHORTLIST_ADD_FAILED", "message": str(e)}
        )

@app.patch("/shortlist")
async def update_shortlist(
    email: str,
    university_id: int,
    category: Optional[str] = None,
    locked: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    Update shortlist entry (category and/or locked status).
    """
    print(f"[ENDPOINT] PATCH /shortlist called for {email}, university_id={university_id}")
    
    # Validate category if provided
    if category:
        valid_categories = ["DREAM", "TARGET", "SAFE"]
        if category not in valid_categories:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "INVALID_CATEGORY",
                    "message": f"Category must be one of: {', '.join(valid_categories)}"
                }
            )
    
    try:
        # Get user profile
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            raise HTTPException(status_code=404, detail={"error": "USER_NOT_FOUND", "message": "User not found"})
        
        # Find shortlist entry
        shortlist = db.query(Shortlist).filter(
            and_(
                Shortlist.user_id == profile.id,
                Shortlist.university_id == university_id
            )
        ).first()
        
        if not shortlist:
            raise HTTPException(
                status_code=404,
                detail={"error": "SHORTLIST_NOT_FOUND", "message": "University not in shortlist"}
            )
        
        # Update fields
        if category:
            shortlist.category = category
        if locked is not None:
            # If locking this one, unlock all others
            if locked:
                db.query(Shortlist).filter(
                    and_(
                        Shortlist.user_id == profile.id,
                        Shortlist.locked == True
                    )
                ).update({"locked": False})
                crud.update_user_stage(db, profile.id, "LOCKED")
            shortlist.locked = locked
        
        db.commit()
        db.refresh(shortlist)
        
        return {
            "success": True,
            "message": "Shortlist updated",
            "category": shortlist.category,
            "locked": shortlist.locked
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] update_shortlist failed: {str(e)}")
        raise HTTPException(status_code=400, detail={"error": "SHORTLIST_UPDATE_FAILED", "message": str(e)})

@app.patch("/shortlist/lock")
async def lock_shortlist(
    email: str,
    university_id: int,
    db: Session = Depends(get_db)
):
    """
    Lock a university for application (unlocks all others).
    DEPRECATED: Use PATCH /shortlist with locked=true instead.
    """
    print(f"[ENDPOINT] PATCH /shortlist/lock called for {email}, university_id={university_id}")
    
    try:
        # Get user profile
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            raise HTTPException(status_code=404, detail={"error": "USER_NOT_FOUND", "message": "User not found"})
        
        # Lock university
        shortlist = crud.lock_university(db, profile.id, university_id)
        
        # Update user stage to LOCKED
        crud.update_user_stage(db, profile.id, "LOCKED")
        
        return {
            "success": True,
            "message": "University locked for application",
            "locked_university_id": shortlist.university_id
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"error": "LOCK_FAILED", "message": str(e)})
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] lock_shortlist failed: {str(e)}")
        raise HTTPException(status_code=500, detail={"error": "LOCK_FAILED", "message": str(e)})

@app.post("/counsel", response_model=schemas.CounselResponse)
async def counsel(
    request: schemas.CounselRequest,
    db: Session = Depends(get_db)
):
    """
    Context-aware AI counsellor endpoint.
    NEVER CRASHES - always returns a helpful response even if data is missing.
    """
    print(f"[ENDPOINT] /counsel called for {request.email}")
    
    try:
        # 1. Load user profile (graceful fallback)
        try:
            profile = db.query(UserProfile).filter(UserProfile.email == request.email).first()
        except Exception as e:
            print(f"[WARNING] Failed to load profile: {str(e)}")
            profile = None
        
        if not profile:
            return schemas.CounselResponse(
                message=f"I'd be happy to help with your question: '{request.message}'. However, I don't have your profile information yet. Please complete your onboarding first so I can provide personalized guidance.",
                actions=schemas.CounselActions()
            )
        
        # 2. Check profile completeness
        if not profile.profile_complete:
            return schemas.CounselResponse(
                message="I'd be happy to help! However, I notice your profile isn't complete yet. Please finish your onboarding so I can provide personalized university recommendations and guidance.",
                actions=schemas.CounselActions()
            )
        
        # 3. Load user state (graceful fallback)
        try:
            state = crud.get_or_create_user_state(db, profile.id)
            current_stage = state.current_stage
        except Exception as e:
            print(f"[WARNING] Failed to load state: {str(e)}")
            current_stage = "DISCOVERY"
        
        # 4. Load shortlisted universities (graceful fallback - empty list OK)
        try:
            shortlists = crud.get_user_shortlists(db, profile.id)
            shortlist_count = len(shortlists)
            
            # Group by category
            dream_count = len([s for s in shortlists if s.category == "DREAM"])
            target_count = len([s for s in shortlists if s.category == "TARGET"])
            safe_count = len([s for s in shortlists if s.category == "SAFE"])
        except Exception as e:
            print(f"[WARNING] Failed to load shortlists: {str(e)}")
            shortlists = []
            shortlist_count = 0
            dream_count = target_count = safe_count = 0
        
        # Get locked university if any (graceful fallback)
        try:
            locked = crud.get_locked_university(db, profile.id)
            locked_uni_id = locked.university_id if locked else None
        except Exception as e:
            print(f"[WARNING] Failed to load locked university: {str(e)}")
            locked_uni_id = None
        
        # 5. Get available universities for context (graceful fallback)
        try:
            countries = profile.preferred_countries if profile.preferred_countries else ["USA"]
            budget = profile.budget_per_year or 0
            
            available_unis = query_universities(
                countries=countries,
                max_budget=float(budget),
                limit=10
            )
        except Exception as e:
            print(f"[WARNING] Failed to load universities: {str(e)}")
            available_unis = []
        
        print(f"[LOGIC] Stage: {current_stage}, Shortlists: {shortlist_count} (D:{dream_count}, T:{target_count}, S:{safe_count}), Available: {len(available_unis)}")
        
        # 6. Generate stage-aware, context-specific response (NO STATIC TEXT)
        if current_stage == "DISCOVERY":
            if len(available_unis) > 0:
                message = f"Based on your profile (GPA: {profile.gpa}, Budget: ${profile.budget_per_year:,}), I found {len(available_unis)} universities matching your criteria in {', '.join(countries)}. Regarding your question: '{request.message}' - I can help you understand which universities align best with your goals in {profile.field_of_study}."
            else:
                message = f"I notice there are limited universities matching your budget of ${profile.budget_per_year:,} in {', '.join(countries)}. About your question: '{request.message}' - Let me help you explore alternative options or adjust your search criteria."
        
        elif current_stage == "SHORTLIST":
            if shortlist_count > 0:
                category_breakdown = []
                if dream_count > 0:
                    category_breakdown.append(f"{dream_count} dream")
                if target_count > 0:
                    category_breakdown.append(f"{target_count} target")
                if safe_count > 0:
                    category_breakdown.append(f"{safe_count} safe")
                
                breakdown_text = ", ".join(category_breakdown) if category_breakdown else "universities"
                message = f"Great! You've shortlisted {shortlist_count} universities ({breakdown_text}). Regarding '{request.message}' - I can help you compare these options and determine which ones best fit your profile in {profile.field_of_study}. What specific aspects would you like to evaluate?"
            else:
                message = f"You're in the shortlisting phase but haven't added any universities yet. About '{request.message}' - I recommend reviewing the {len(available_unis)} universities I found for you and shortlisting your top choices across dream, target, and safe categories."
        
        elif current_stage == "LOCKED":
            if locked_uni_id:
                message = f"You've locked a university for your application! Regarding '{request.message}' - I can guide you through the application requirements, deadlines, and preparation steps for your chosen university."
            else:
                if shortlist_count > 0:
                    message = f"You're ready to lock in your final choice. About '{request.message}' - Let me help you make this important decision from your {shortlist_count} shortlisted universities."
                else:
                    message = f"About '{request.message}' - You'll need to shortlist some universities first before locking one for application. Let me help you find the right options."
        
        else:
            message = f"I'm here to help with your question: '{request.message}'. Based on your current stage ({current_stage}) and profile, I can provide specific guidance tailored to your situation."
        
        return schemas.CounselResponse(
            message=message,
            actions=schemas.CounselActions()
        )
        
    except Exception as e:
        # Ultimate fallback - NEVER crash
        print(f"[ERROR] Counsel failed catastrophically: {str(e)}")
        return schemas.CounselResponse(
            message=f"I'm here to help with your question: '{request.message}'. However, I'm experiencing some technical difficulties accessing your data. Please try again in a moment, or contact support if the issue persists.",
            actions=schemas.CounselActions()
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
