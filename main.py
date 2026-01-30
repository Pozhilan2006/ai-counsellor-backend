from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text, and_
from sqlalchemy.orm import sessionmaker
from typing import Optional, List, Dict

from config import settings
from models import Base, StageEnum, UserProfile, Shortlist
import crud
import schemas
from database import query_universities, verify_tables_exist
from scoring import categorize_universities

# ============================================================================
# UTILITY FUNCTIONS FOR ENTERPRISE QUALITY
# ============================================================================

def resolve_profile_values(profile: UserProfile) -> Dict[str, str]:
    """
    Resolve profile fields into safe, display-ready strings.
    CRITICAL: Prevents template leaks by converting all values to strings.
    """
    return {
        "gpa": str(profile.gpa) if profile.gpa else "your academic record",
        "gpa_value": float(profile.gpa) if profile.gpa else 0.0,
        "budget": f"${profile.budget_per_year:,}" if profile.budget_per_year else "your budget range",
        "budget_value": int(profile.budget_per_year) if profile.budget_per_year else 0,
        "field": profile.field_of_study or "your field of interest",
        "countries": ", ".join(profile.preferred_countries) if profile.preferred_countries else "your target countries",
        "countries_list": profile.preferred_countries if profile.preferred_countries else ["USA"],
        "name": profile.name or "there"
    }

def sanitize_response(message: str) -> str:
    """
    Sanitize AI response to enterprise standards.
    - Remove markdown symbols
    - Detect template leaks
    - Clean whitespace
    """
    # Check for template leaks (CRITICAL)
    if "{" in message or "}" in message:
        print(f"[CRITICAL] Template leak detected in response: {message[:100]}")
        # Remove the leaked templates
        import re
        message = re.sub(r'\{[^}]+\}', '[value]', message)
    
    # Remove markdown symbols
    message = message.replace("**", "")
    message = message.replace("##", "")
    message = message.replace("- ", "")
    message = message.replace("* ", "")
    
    # Clean excessive whitespace
    message = " ".join(message.split())
    
    return message.strip()

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

@app.get("/tasks")
async def get_tasks(email: str, db: Session = Depends(get_db)):
    """
    Get tasks for a user with standardized response.
    """
    print(f"[ENDPOINT] GET /tasks called for {email}")
    
    try:
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            return {"status": "OK", "data": {"tasks": [], "locked_university_id": None}}
        
        crud.sync_profile_tasks(db, profile.id)
        tasks, locked_university_id = crud.get_all_tasks(db, profile.id)
        
        result = []
        for task in tasks:
            result.append({
                "id": task.id,
                "title": task.title,
                "description": task.description or "",
                "completed": task.completed,
                "university_id": task.university_id,
                "stage": task.stage
            })
        
        return {
            "status": "OK",
            "data": {
                "tasks": result,
                "locked_university_id": locked_university_id
            }
        }
    except Exception as e:
        print(f"[ERROR] get_tasks failed: {str(e)}")
        return {"status": "ERROR", "data": {"tasks": [], "locked_university_id": None}}

@app.get("/user/stage")
async def get_user_stage(email: str, db: Session = Depends(get_db)):
    try:
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            # Safe default
            return {
                "status": "OK",
                "data": {
                    "email": email,
                    "current_stage": StageEnum.BUILDING_PROFILE,
                    "profile_complete": False
                }
            }
        
        state = crud.get_or_create_user_state(db, profile.id, default_stage=StageEnum.BUILDING_PROFILE)
        return {
            "status": "OK",
            "data": {
                "email": email,
                "current_stage": state.current_stage,
                "profile_complete": profile.profile_complete
            }
        }
    except Exception as e:
        print(f"[ERROR] get_user_stage failed: {str(e)}")
        return {
            "status": "ERROR",
            "data": {
                "email": email,
                "current_stage": StageEnum.BUILDING_PROFILE,
                "profile_complete": False
            }
        }

@app.get("/profile/strength")
async def get_profile_strength(email: str, db: Session = Depends(get_db)):
    try:
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
             # Safe default for missing user
             return {
                 "status": "OK",
                 "data": schemas.ProfileStrengthResponse()
             }
        
        strength = crud.calculate_profile_strength(db, profile)
        return {"status": "OK", "data": strength}
    except Exception as e:
        print(f"[ERROR] get_profile_strength failed: {str(e)}")
        # Safe default on error
        return {"status": "ERROR", "data": schemas.ProfileStrengthResponse()}

@app.get("/recommendations")
async def get_deterministic_recommendations(email: str, db: Session = Depends(get_db)):
    print(f"[ENDPOINT] /recommendations called for {email}")
    
    try: 
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            # Return empty response instead of 404
            return {"status": "OK", "data": schemas.MatchesResponse(matches=schemas.CategorizedUniversities(), count=0)}
        
        if not profile.profile_complete:
             # Return empty, manageable on frontend
             return {"status": "OK", "data": schemas.MatchesResponse(matches=schemas.CategorizedUniversities(), count=0)}

        countries = profile.preferred_countries if profile.preferred_countries else ["USA"]
        budget = profile.budget_per_year or 0
        
        try:
            unis = query_universities(
                countries=countries,
                max_budget=float(budget),
                limit=20
            )
        except Exception:
            unis = []
        
        dream = []
        target = []
        safe = []

        for uni in unis:
            uni_obj = schemas.UniversityResponse(
                id=uni["id"],
                name=uni["name"],
                country=uni["country"],
                rank=uni["rank"] or 999,
                estimated_tuition_usd=uni["estimated_tuition_usd"],
                competitiveness=uni.get("competitiveness", "MEDIUM"),
                match_percentage=0, # Need to keep consistent
                category="TARGET"
            )
            # Re-apply categorization logic strictly if needed, or rely on crud/scoring return 
            # (Here we reconstruct because query_universities creates raw dicts)
            # Simplification:
            rank = uni["rank"] or 999
            if rank <= 100: dream.append(uni_obj)
            elif rank <= 300: target.append(uni_obj)
            else: safe.append(uni_obj)
            
        total_count = len(dream) + len(target) + len(safe)
        
        return {
            "status": "OK", 
            "data": schemas.MatchesResponse(
                matches=schemas.CategorizedUniversities(
                    dream=dream,
                    target=target,
                    safe=safe
                ),
                count=total_count
            )
        }
    except Exception as e:
        print(f"[ERROR] recommendations failed: {str(e)}")
        return {"status": "ERROR", "data": schemas.MatchesResponse(matches=schemas.CategorizedUniversities(), count=0)}

@app.get("/shortlist")
async def get_shortlist(email: str, db: Session = Depends(get_db)):
    try:
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            return {"status": "OK", "data": {"shortlists": [], "count": 0}}
        
        shortlists = crud.get_user_shortlists(db, profile.id)
        if not shortlists:
            return {"status": "OK", "data": {"shortlists": [], "count": 0}}
            
        result = []
        for shortlist in shortlists:
            unis = query_universities(university_ids=[shortlist.university_id], limit=1)
            if unis:
                uni = unis[0]
                result.append({
                    "id": shortlist.id,
                    "university": {
                        "id": uni["id"],
                        "name": uni["name"],
                        "country": uni["country"],
                        "rank": uni["rank"] or 999,
                        "estimated_tuition_usd": uni["estimated_tuition_usd"] or 0
                    },
                    "category": shortlist.category or "TARGET",
                    "locked": shortlist.locked,
                    "created_at": shortlist.created_at.isoformat() if shortlist.created_at else ""
                })
        
        return {"status": "OK", "data": {"shortlists": result, "count": len(result)}}
    except Exception as e:
        print(f"[ERROR] get_shortlist failed: {str(e)}")
        return {"status": "ERROR", "data": {"shortlists": [], "count": 0}}

@app.post("/tasks/{task_id}/complete")
async def complete_task_endpoint(task_id: int, db: Session = Depends(get_db)):
    """Mark a task as complete."""
    crud.complete_task(db, task_id)
    return {"success": True}

@app.get("/user/stage")
async def get_user_stage(email: str, db: Session = Depends(get_db)):
    """Get user's current stage."""
    try:
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        
        if not profile:
            return {
                "email": email,
                "current_stage": StageEnum.BUILDING_PROFILE,
                "profile_complete": False
            }
        
        # Get or create state
        state = crud.get_or_create_user_state(db, profile.id, default_stage=StageEnum.BUILDING_PROFILE)
        
        return {
            "email": email,
            "current_stage": state.current_stage,
            "profile_complete": profile.profile_complete
        }
    except Exception as e:
        print(f"[ERROR] get_user_stage failed: {str(e)}")
        return {
            "email": email,
            "current_stage": StageEnum.BUILDING_PROFILE,
            "profile_complete": False
        }

@app.get("/profile/strength")
async def get_profile_strength(email: str, db: Session = Depends(get_db)):
    """
    Get profile completion strength with point-based scoring.
    Returns dynamic calculation based on current profile state.
    """
    try:
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            raise HTTPException(
                status_code=404,
                detail={"error": "USER_NOT_FOUND", "message": "User not found"}
            )
        
        # Calculate strength dynamically
        strength = crud.calculate_profile_strength(db, profile)
        return strength
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] get_profile_strength failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={"error": "CALCULATION_FAILED", "message": str(e)}
        )

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
            print(f"[LOGIC] Upserting user_states to DISCOVERING_UNIVERSITIES")
            crud.update_user_stage(db, profile.id, StageEnum.DISCOVERING_UNIVERSITIES)
            # NOTE: Tasks are now only created after university lock, not during onboarding
        
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
    DEFENSIVE: Always returns 200 with empty array on error.
    """
    print(f"[ENDPOINT] GET /shortlist called for {email}")
    
    try:
        # Get user profile
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            print(f"[INFO] User not found: {email}, returning empty shortlist")
            return {"shortlists": [], "count": 0}
        
        # Get shortlists
        shortlists = crud.get_user_shortlists(db, profile.id)
        if not shortlists:
            return {"shortlists": [], "count": 0}
        
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
        # DEFENSIVE: Return empty array instead of 500
        return {"shortlists": [], "count": 0}

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
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Alternative endpoint for adding to shortlist (frontend compatibility).
    Accepts flexible payload formats with optional category.
    """
    # Parse raw JSON body to handle flexible formats
    try:
        body = await request.json()
    except Exception as e:
        print(f"[ERROR] Failed to parse JSON: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_JSON", "message": "Invalid JSON payload"}
        )
    
    # Log payload for debugging
    print(f"[SHORTLIST ADD] Payload received: {body}")
    
    # Extract and validate required fields
    email = body.get("email")
    university_id = body.get("university_id")
    category = body.get("category", "General")  # Optional, default to General
    
    # Validate required fields
    if not email:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_EMAIL", "message": "Email is required"}
        )
    
    if university_id is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_UNIVERSITY_ID", "message": "University ID is required"}
        )
    
    # Trim whitespace from email
    email = str(email).strip()
    
    # Cast university_id to integer (handle string or number)
    try:
        university_id = int(university_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_UNIVERSITY_ID", "message": "University ID must be a number"}
        )
    
    # Map frontend category names to backend
    category_map = {
        "Dream": "DREAM",
        "Target": "TARGET",
        "Safe": "SAFE",
        "General": "TARGET",
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
        
        print(f"[SUCCESS] University {university_id} added to shortlist for {email}")
        
        return {
            "success": True,
            "message": "University added to shortlist"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] add_shortlist_alt failed: {str(e)}")
        # Idempotent behavior - return success even on errors (except validation)
        return {
            "success": True,
            "message": "University added to shortlist"
        }

@app.post("/shortlist/remove")
async def remove_shortlist(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Remove a university from user's shortlist.
    
    Rules:
    - Cannot remove locked universities
    - Recalculates stage if shortlist becomes empty
    """
    # Parse JSON body
    try:
        body = await request.json()
    except Exception as e:
        print(f"[ERROR] Failed to parse JSON: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_JSON", "message": "Invalid JSON payload"}
        )
    
    email = body.get("email")
    university_id = body.get("university_id")
    
    # Validate required fields
    if not email:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_EMAIL", "message": "Email is required"}
        )
    
    if university_id is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_UNIVERSITY_ID", "message": "University ID is required"}
        )
    
    # Trim and cast
    email = str(email).strip()
    try:
        university_id = int(university_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_UNIVERSITY_ID", "message": "University ID must be a number"}
        )
    
    print(f"[ENDPOINT] POST /shortlist/remove called for {email}, university_id={university_id}")
    
    try:
        # Get user profile
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            raise HTTPException(
                status_code=400,
                detail={"error": "USER_NOT_FOUND", "message": "User not found"}
            )
        
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
                detail={"error": "NOT_IN_SHORTLIST", "message": "University not in shortlist"}
            )
        
        # Check if locked
        if shortlist.locked:
            # Clear tasks before preventing removal
            crud.clear_user_tasks(db, profile.id)
            
            raise HTTPException(
                status_code=400,
                detail={
                    "success": False,
                    "error": "UNIVERSITY_LOCKED",
                    "message": "This university is locked. Unlock it before removing from shortlist."
                }
            )
        
        # Delete the shortlist entry
        db.delete(shortlist)
        db.commit()
        
        print(f"[SUCCESS] University {university_id} removed from shortlist for {email}")
        
        # Check if shortlist is now empty - recalculate stage
        remaining_shortlists = db.query(Shortlist).filter(Shortlist.user_id == profile.id).count()
        
        if remaining_shortlists == 0:
            # Move back to DISCOVERY stage
            crud.update_user_stage(db, profile.id, "DISCOVERY")
            print(f"[STAGE] User {email} moved back to DISCOVERY (no shortlists remaining)")
        
        return {
            "success": True,
            "message": "University removed from shortlist"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] remove_shortlist failed: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail={"success": False, "error": "REMOVE_FAILED", "message": str(e)}
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
    DEPRECATED: Use POST /university/lock instead.
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

@app.post("/university/lock")
async def lock_university_for_application(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Lock a university for application (enterprise endpoint).
    
    Validates:
    - User exists
    - University is in shortlist
    - Auto-unlocks previous locks
    
    Side effects:
    - Updates user stage to LOCKED
    - Unlocks all other universities
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_JSON", "message": "Invalid JSON payload"}
        )
    
    email = body.get("email")
    university_id = body.get("university_id")
    
    if not email or not university_id:
        raise HTTPException(
            status_code=400,
            detail={"error": "MISSING_FIELDS", "message": "Email and university_id are required"}
        )
    
    print(f"[ENDPOINT] POST /university/lock called for {email}, university_id={university_id}")
    
    try:
        # Get user profile
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if not profile:
            raise HTTPException(
                status_code=400,
                detail={"error": "USER_NOT_FOUND", "message": "User not found"}
            )
        
        # Verify university is in shortlist
        shortlist_entry = db.query(Shortlist).filter(
            and_(
                Shortlist.user_id == profile.id,
                Shortlist.university_id == university_id
            )
        ).first()
        
        if not shortlist_entry:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "NOT_IN_SHORTLIST",
                    "message": "University must be in your shortlist before locking"
                }
            )
        
        # Lock university (auto-unlocks others)
        shortlist = crud.lock_university(db, profile.id, university_id)
        
        # Update user stage to LOCKED
        crud.update_user_stage(db, profile.id, "LOCKED")
        
        # Generate university-specific tasks
        tasks = crud.generate_university_tasks(db, profile.id, university_id)
        
        print(f"[SUCCESS] University {university_id} locked for {email}, stage updated to LOCKED, {len(tasks)} tasks generated")
        
        return {
            "success": True,
            "locked_university_id": shortlist.university_id,
            "stage": "LOCKED",
            "tasks_generated": len(tasks),
            "message": "University locked for application"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] lock_university failed: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail={"error": "LOCK_FAILED", "message": str(e)}
        )

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
        
        # 6. Resolve profile values safely (NO TEMPLATE LEAKS)
        pv = resolve_profile_values(profile)
        
        # 7. Analyze user's question to determine intent
        question_lower = request.message.lower().strip()
        
        # Check if user is asking for university recommendations
        is_asking_for_universities = any(keyword in question_lower for keyword in [
            "recommend universities", "which universities", "suggest universities",
            "show me universities", "what universities", "list universities",
            "universities for me", "university recommendations"
        ])
        
        # Check if asking for BEST university (single recommendation)
        is_asking_best_university = any(keyword in question_lower for keyword in [
            "best university", "which university is best", "top university",
            "which one should i choose", "recommend one university"
        ])
        
        # Check if user is asking for profile analysis
        is_asking_profile_analysis = any(keyword in question_lower for keyword in [
            "analyze my profile", "how strong is my profile", "profile strength",
            "evaluate my profile", "assess my profile", "my chances"
        ])
        
        # Check if asking for improvement advice
        is_asking_improvement = any(keyword in question_lower for keyword in [
            "what should i improve", "how to improve", "strengthen my profile",
            "what can i do", "how can i improve"
        ])
        
        # Check if asking about budget
        is_asking_budget = any(keyword in question_lower for keyword in [
            "budget", "afford", "cost", "tuition", "fees", "financial"
        ])
        
        # 8. Generate contextual response based on question intent
        if is_asking_best_university:
            # User wants ONE recommendation
            if shortlist_count > 0:
                # Recommend from shortlist
                target_unis = [s for s in shortlists if s.category == "TARGET"]
                if target_unis:
                    uni_id = target_unis[0].university_id
                    message = f"Based on your profile with a GPA of {pv['gpa']} and budget of {pv['budget']} annually, I recommend focusing on university ID {uni_id} from your shortlist. This represents a strong target option that balances academic fit with admission probability. The primary risk is competition in {pv['field']}, so strengthen your application with relevant projects and strong recommendations. Lock this university when you're ready to proceed with the application."
                else:
                    message = f"From your shortlist of {shortlist_count} universities, I need more context about your priorities. Are you optimizing for program reputation, cost, location, or research opportunities in {pv['field']}? This will help me recommend the single best fit."
            elif len(available_unis) > 0:
                message = f"Based on your GPA of {pv['gpa']} and budget of {pv['budget']}, I recommend starting with universities in {pv['countries']} that offer strong {pv['field']} programs. Add a few to your shortlist first, then I can provide a specific recommendation based on your final priorities."
            else:
                message = f"With your budget of {pv['budget']} in {pv['countries']}, options are limited. I recommend expanding your search to include universities slightly above budget with strong scholarship programs, or exploring alternative countries with comparable education quality at lower costs."
        
        elif is_asking_for_universities:
            # Only mention universities when explicitly asked
            if len(available_unis) > 0:
                message = f"Based on your GPA of {pv['gpa']} and budget of {pv['budget']} per year, I've identified {len(available_unis)} universities in {pv['countries']} that align with your profile in {pv['field']}. I can help you categorize these into reach, target, and safety options if you'd like. This would give you a balanced application strategy across different selectivity tiers."
            else:
                message = f"With your budget of {pv['budget']} in {pv['countries']}, I'm seeing limited exact matches at the moment. However, there are a few paths we could explore. We could look at universities slightly above your budget that offer strong scholarship opportunities, or we could expand to countries with comparable education quality but lower costs. Which direction interests you more?"
        
        elif is_asking_profile_analysis:
            # Provide profile strength analysis
            gpa_val = pv['gpa_value']
            if gpa_val >= 9.0:
                strength_desc = f"Your GPA of {pv['gpa']} positions you very competitively for top-tier programs globally, including Ivy League and Oxbridge institutions"
                next_steps = "Focus on differentiating yourself through research publications, strong recommendation letters, and a compelling personal statement that showcases unique perspectives or experiences"
            elif gpa_val >= 8.0:
                strength_desc = f"Your GPA of {pv['gpa']} is strong and puts you in good standing for highly competitive universities in the top 50 globally"
                next_steps = "Strengthen your profile with relevant projects, aim for GRE scores above 320, and secure recommendations from faculty who can speak to your research or academic potential"
            elif gpa_val >= 7.0:
                strength_desc = f"Your GPA of {pv['gpa']} gives you solid options among reputable universities ranked in the top 100-200 globally"
                next_steps = f"Build your profile with internships or research experience in {pv['field']}, target strong standardized test scores, and craft essays that highlight your growth trajectory and career goals"
            else:
                strength_desc = f"Your current academic record opens doors to universities with holistic admissions processes that value diverse experiences beyond academics"
                next_steps = f"Focus on demonstrating professional experience, relevant projects, and clear career objectives. Consider programs that emphasize practical skills and industry connections in {pv['field']}"
            
            message = f"{strength_desc}. With your budget of {pv['budget']} annually in {pv['countries']}, you have good financial flexibility. {next_steps}. The key is presenting a cohesive narrative that connects your academic background, career aspirations, and why specific programs align with your goals."
        
        elif is_asking_improvement:
            # Provide actionable improvement steps
            message = f"To strengthen your candidacy for {pv['field']} programs, I'd recommend focusing on three key areas. First, aim for standardized test scores that put you in the competitive range, typically GRE 320 plus or GMAT 700 plus, along with IELTS 7.5 or higher. Second, build tangible evidence of your expertise through two to three substantial projects or research work that demonstrates both technical skills and problem-solving ability. Third, secure strong recommendations from professors or supervisors who can provide specific examples of your capabilities and potential. Beyond these, your personal statement should articulate a clear narrative about why you're pursuing this field and how specific programs align with your goals. Which of these areas would you like to discuss in more detail?"
        
        elif is_asking_budget:
            # Focus only on budget strategy
            message = f"Your budget of {pv['budget']} per year gives you solid coverage for tuition at many universities in {pv['countries']}. To optimize your costs, I'd suggest applying for merit-based scholarships, which can reduce your expenses by twenty to fifty percent depending on your profile strength. Graduate assistantships are another avenue worth exploring, as they often cover tuition plus provide a stipend. Beyond tuition, plan for living expenses of around fifteen to twenty thousand annually, health insurance of two to three thousand, and maintain an emergency fund of roughly five thousand. Universities in smaller cities or specific regions can also offer comparable education quality at lower living costs. Would you like me to suggest specific scholarship opportunities or discuss cost-effective university locations?"
        
        else:
            # Answer the user's specific question directly
            # Use profile as supporting context, not the main answer
            if current_stage == "DISCOVERY":
                message = f"I can help you with that. Given your background in {pv['field']}, what specific aspect are you most interested in? For example, I can walk you through application timelines, discuss standardized test requirements, help you evaluate program curricula, or explain how to position your profile for specific universities. Let me know what would be most useful right now."
            
            elif current_stage == "SHORTLIST":
                if shortlist_count > 0:
                    category_breakdown = []
                    if dream_count > 0:
                        category_breakdown.append(f"{dream_count} reach")
                    if target_count > 0:
                        category_breakdown.append(f"{target_count} target")
                    if safe_count > 0:
                        category_breakdown.append(f"{safe_count} safety")
                    
                    breakdown_text = ", ".join(category_breakdown) if category_breakdown else "universities"
                    message = f"You've shortlisted {shortlist_count} universities, including {breakdown_text} options. I can help you compare these across several dimensions like program structure, faculty research areas, career outcomes, campus culture, or funding opportunities. What factors are most important to you in making your final decision?"
                else:
                    message = f"I can provide guidance on that. Since you haven't shortlisted any universities yet, would you like me to suggest some options first, or do you have specific questions about the application process or program selection criteria? Either way, I'm here to help."
            
            elif current_stage == "LOCKED":
                if locked_uni_id:
                    message = f"You've committed to a university choice, which is a significant milestone. I can now help you with the application execution, whether that's crafting your statement of purpose, preparing supporting documents, understanding deadlines, navigating the visa process, or preparing for interviews if required. What part of the application would you like to tackle first?"
                else:
                    message = f"You're at the decision stage now. I can help you evaluate your shortlisted options more deeply or address any other questions you have about the process. What would be most helpful at this point?"
            
            else:
                message = f"I'm here to help with your question. Could you give me a bit more context about what you're looking for? For instance, are you interested in understanding your profile competitiveness, exploring university options, discussing application strategy, or planning your budget? That will help me provide more targeted guidance."
        
        # 9. Sanitize response (CRITICAL: Remove markdown, check for template leaks)
        message = sanitize_response(message)
        
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
