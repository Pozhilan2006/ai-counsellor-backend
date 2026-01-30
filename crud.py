"""
CRUD operations for database models.
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from models import UserProfile, UserState, Shortlist, Task, StageEnum, CategoryEnum
from typing import List, Optional, Dict
from datetime import datetime

# User Profile operations
def get_or_create_user_profile(db: Session, email: str, profile_data: Optional[Dict] = None) -> UserProfile:
    """
    Get or create user profile (UPSERT pattern).
    Never crashes - always returns a profile.
    """
    try:
        profile = db.query(UserProfile).filter(UserProfile.email == email).first()
        if profile:
            return profile
        
        # Create new profile
        profile_dict = profile_data or {}
        profile_dict["email"] = email
        profile = UserProfile(**profile_dict)
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile
    except Exception as e:
        print(f"[ERROR] get_or_create_user_profile failed: {str(e)}")
        db.rollback()
        raise

def create_user_profile(db: Session, profile_data: dict) -> UserProfile:
    """Create a new user profile."""
    profile = UserProfile(**profile_data)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile

def get_user_profile(db: Session, user_id: int) -> Optional[UserProfile]:
    """Get user profile by ID."""
    return db.query(UserProfile).filter(UserProfile.id == user_id).first()

def get_user_by_email(db: Session, email: str) -> Optional[UserProfile]:
    """Get user profile by email."""
    return db.query(UserProfile).filter(UserProfile.email == email).first()

def update_profile_complete(db: Session, user_id: int, complete: bool = True):
    """Mark profile as complete."""
    db.query(UserProfile).filter(UserProfile.id == user_id).update(
        {"profile_complete": complete}
    )
    db.commit()

# UserState operations (GET-OR-CREATE pattern)
def get_or_create_user_state(db: Session, user_id: int, default_stage: str = "ONBOARDING") -> UserState:
    """
    Get user state, create if doesn't exist (UPSERT pattern).
    This is self-healing - never assumes the table or row exists.
    """
    try:
        state = db.query(UserState).filter(UserState.user_id == user_id).first()
        if state:
            return state
        
        # Create new state
        state = UserState(user_id=user_id, current_stage=default_stage)
        db.add(state)
        db.commit()
        db.refresh(state)
        return state
    except Exception as e:
        print(f"[ERROR] get_or_create_user_state failed: {str(e)}")
        db.rollback()
        # Return a temporary state object (not persisted)
        return UserState(user_id=user_id, current_stage=default_stage)

def update_user_stage(db: Session, user_id: int, stage: str):
    """Update user's current stage (UPSERT)."""
    try:
        state = db.query(UserState).filter(UserState.user_id == user_id).first()
        if state:
            state.current_stage = stage
            state.updated_at = datetime.utcnow()
        else:
            # Create if doesn't exist
            state = UserState(user_id=user_id, current_stage=stage)
            db.add(state)
        db.commit()
    except Exception as e:
        print(f"[ERROR] update_user_stage failed: {str(e)}")
        db.rollback()

# Shortlist operations
def get_user_shortlists(db: Session, user_id: int) -> List[Shortlist]:
    """Get all shortlisted universities for a user. Returns empty list if table doesn't exist."""
    try:
        return db.query(Shortlist).filter(Shortlist.user_id == user_id).all()
    except Exception as e:
        print(f"[WARNING] get_user_shortlists failed (table may not exist): {str(e)}")
        return []

def add_to_shortlist(db: Session, user_id: int, university_id: int, category: Optional[str] = "TARGET") -> Shortlist:
    """Add university to user's shortlist (UPSERT)."""
    try:
        # Check if already exists
        existing = db.query(Shortlist).filter(
            and_(
                Shortlist.user_id == user_id,
                Shortlist.university_id == university_id
            )
        ).first()
        
        if existing:
            # Update category if provided
            if category:
                existing.category = category
            db.commit()
            db.refresh(existing)
            return existing
        
        # Create new entry with default category
        shortlist = Shortlist(
            user_id=user_id,
            university_id=university_id,
            category=category or "TARGET"
        )
        db.add(shortlist)
        db.commit()
        db.refresh(shortlist)
        return shortlist
    except Exception as e:
        print(f"[ERROR] add_to_shortlist failed: {str(e)}")
        db.rollback()
        raise

def lock_university(db: Session, user_id: int, university_id: int) -> Shortlist:
    """Lock a university for application (unlock others)."""
    try:
        # Unlock all previously locked universities
        db.query(Shortlist).filter(
            and_(
                Shortlist.user_id == user_id,
                Shortlist.locked == True
            )
        ).update({"locked": False})
        
        # Lock the selected university
        shortlist = db.query(Shortlist).filter(
            and_(
                Shortlist.user_id == user_id,
                Shortlist.university_id == university_id
            )
        ).first()
        
        if not shortlist:
            raise ValueError("University not in shortlist")
        
        shortlist.locked = True
        db.commit()
        db.refresh(shortlist)
        return shortlist
    except Exception as e:
        print(f"[ERROR] lock_university failed: {str(e)}")
        db.rollback()
        raise

def get_locked_university(db: Session, user_id: int) -> Optional[Shortlist]:
    """Get user's locked university."""
    return db.query(Shortlist).filter(
        and_(
            Shortlist.user_id == user_id,
            Shortlist.locked == True
        )
    ).first()

# Task operations
def create_task(db: Session, user_id: int, title: str, description: str, stage: StageEnum) -> Task:
    """Create a new task."""
    task = Task(
        user_id=user_id,
        title=title,
        description=description,
        stage=stage
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

def get_tasks_by_stage(db: Session, user_id: int, stage: StageEnum) -> List[Task]:
    """Get all tasks for a user in a specific stage."""
    return db.query(Task).filter(
        and_(
            Task.user_id == user_id,
            Task.stage == stage
        )
    ).all()

def get_all_tasks(db: Session, user_id: int) -> List[Task]:
    """Get all tasks for a user. Returns empty list if table doesn't exist."""
    try:
        return db.query(Task).filter(Task.user_id == user_id).all()
    except Exception as e:
        print(f"[WARNING] get_all_tasks failed (table may not exist): {str(e)}")
        return []

def complete_task(db: Session, task_id: int):
    """Mark a task as completed."""
    db.query(Task).filter(Task.id == task_id).update({"completed": True})
    db.commit()

# DEPRECATED: Do not create tasks during DISCOVERY
# Tasks should only be created after university is locked
# def generate_initial_tasks(db: Session, user_id: int) -> List[Task]:
#     """Generate initial tasks for a user. Safe if table doesn't exist."""
#     # This function is deprecated - tasks are now only created after lock
#     return []

def generate_university_tasks(db: Session, user_id: int, university_id: int) -> List[Task]:
    """
    Generate university-specific tasks after lock.
    Tasks are stage-aware and actionable.
    Clears existing tasks before generating new ones.
    """
    try:
        # Clear existing tasks for this user
        db.query(Task).filter(Task.user_id == user_id).delete()
        
        # University-specific tasks for APPLICATION stage
        tasks_data = [
            {
                "title": "Complete Statement of Purpose",
                "description": "Draft your SOP highlighting why this university aligns with your goals",
                "stage": StageEnum.APPLICATION,
                "university_id": university_id
            },
            {
                "title": "Gather Recommendation Letters",
                "description": "Request 2-3 letters from professors or supervisors who know your work well",
                "stage": StageEnum.APPLICATION,
                "university_id": university_id
            },
            {
                "title": "Prepare Official Transcripts",
                "description": "Get official transcripts from your institution, sealed and stamped",
                "stage": StageEnum.APPLICATION,
                "university_id": university_id
            },
            {
                "title": "Check Application Deadlines",
                "description": "Verify all deadlines for this university and set calendar reminders",
                "stage": StageEnum.APPLICATION,
                "university_id": university_id
            },
            {
                "title": "Prepare Financial Documents",
                "description": "Gather bank statements and financial proof for visa application",
                "stage": StageEnum.APPLICATION,
                "university_id": university_id
            },
            {
                "title": "Complete Standardized Tests",
                "description": "Ensure GRE/GMAT and IELTS/TOEFL scores meet university requirements",
                "stage": StageEnum.APPLICATION,
                "university_id": university_id
            },
            {
                "title": "Prepare Resume/CV",
                "description": "Update your resume highlighting relevant experience and achievements",
                "stage": StageEnum.APPLICATION,
                "university_id": university_id
            }
        ]
        
        tasks = []
        for task_data in tasks_data:
            task = Task(user_id=user_id, **task_data)
            db.add(task)
            tasks.append(task)
        
        db.commit()
        print(f"[TASKS] Generated {len(tasks)} university-specific tasks for user {user_id}, university {university_id}")
        return tasks
    except Exception as e:
        print(f"[ERROR] generate_university_tasks failed: {str(e)}")
        db.rollback()
        return []

def clear_user_tasks(db: Session, user_id: int):
    """Clear all tasks when university is unlocked or changed."""
    try:
        deleted_count = db.query(Task).filter(Task.user_id == user_id).delete()
        db.commit()
        print(f"[TASKS] Cleared {deleted_count} tasks for user {user_id}")
    except Exception as e:
        print(f"[ERROR] clear_user_tasks failed: {str(e)}")
        db.rollback()

# Status Normalization Helper
def normalize_status(status: str | None) -> str:
    """
    Normalize status values to enum: NOT_STARTED | IN_PROGRESS | COMPLETED
    Handles all common variations and NULL values.
    """
    if not status or status.strip() == "":
        return "NOT_STARTED"
    
    status_lower = status.lower().strip()
    
    # Completed variations
    if status_lower in ["completed", "done", "ready", "finished"]:
        return "COMPLETED"
    
    # In progress variations
    if status_lower in ["in progress", "in_progress", "draft", "drafting", "started", "planning"]:
        return "IN_PROGRESS"
    
    # Not started variations
    if status_lower in ["not started", "not_started", "pending", "todo", "none"]:
        return "NOT_STARTED"
    
    # Default to IN_PROGRESS if unknown
    print(f"[WARNING] Unknown status value: '{status}', defaulting to IN_PROGRESS")
    return "IN_PROGRESS"

# Profile Strength Calculation (Enhanced with Debug Logging)
def calculate_profile_strength(db: Session, profile: UserProfile) -> Dict:
    """
    Calculate profile completion using point-based scoring (100 points total).
    
    Scoring Model:
    - Academics (30%): GPA, degree, graduation year
    - Exams (25%): IELTS/GRE status + scores
    - SOP (20%): SOP status
    - Documents (15%): Funding plan, transcripts
    - Preferences (10%): Countries, budget, field
    
    Returns structured breakdown with scores, statuses, and next actions.
    """
    print(f"\n[PROFILE_STRENGTH] Calculating for user_id={profile.id}, email={profile.email}")
    
    total_score = 0
    sections = {}
    next_actions = []
    
    # ========================================
    # ACADEMICS (30 points)
    # ========================================
    academics_score = 0
    academics_max = 30
    
    # GPA → 15 points
    if profile.gpa and float(profile.gpa) > 0:
        academics_score += 15
        print(f"  [ACADEMICS] GPA present: {profile.gpa} → +15")
    else:
        print(f"  [ACADEMICS] GPA missing → +0")
        next_actions.append("Add your GPA")
    
    # Degree → 10 points
    if profile.degree and profile.degree.strip():
        academics_score += 10
        print(f"  [ACADEMICS] Degree present: {profile.degree} → +10")
    else:
        print(f"  [ACADEMICS] Degree missing → +0")
        next_actions.append("Add your degree")
    
    # Graduation year → 5 points
    if profile.graduation_year and profile.graduation_year > 0:
        academics_score += 5
        print(f"  [ACADEMICS] Graduation year present: {profile.graduation_year} → +5")
    else:
        print(f"  [ACADEMICS] Graduation year missing → +0")
    
    total_score += academics_score
    
    # Determine status
    if academics_score == 0:
        academics_status = "missing"
    elif academics_score >= 25:
        academics_status = "strong"
    elif academics_score >= 15:
        academics_status = "partial"
    else:
        academics_status = "weak"
    
    sections["academics"] = {
        "score": academics_score,
        "max": academics_max,
        "status": academics_status
    }
    print(f"  [ACADEMICS] Total: {academics_score}/{academics_max} → {academics_status}")
    
    # ========================================
    # EXAMS (25 points)
    # ========================================
    exams_score = 0
    exams_max = 25
    
    # IELTS → 12 points
    ielts_normalized = normalize_status(profile.ielts_status)
    if ielts_normalized == "COMPLETED":
        exams_score += 12
        print(f"  [EXAMS] IELTS completed: {profile.ielts_status} → +12")
    elif ielts_normalized == "IN_PROGRESS":
        exams_score += 6
        print(f"  [EXAMS] IELTS in progress: {profile.ielts_status} → +6")
    else:
        print(f"  [EXAMS] IELTS not started → +0")
        next_actions.append("Complete IELTS exam")
    
    # GRE/GMAT → 13 points
    gre_normalized = normalize_status(profile.gre_gmat_status)
    if gre_normalized == "COMPLETED":
        exams_score += 13
        print(f"  [EXAMS] GRE/GMAT completed: {profile.gre_gmat_status} → +13")
    elif gre_normalized == "IN_PROGRESS":
        exams_score += 6
        print(f"  [EXAMS] GRE/GMAT in progress: {profile.gre_gmat_status} → +6")
    else:
        print(f"  [EXAMS] GRE/GMAT not started → +0")
        next_actions.append("Complete GRE/GMAT exam")
    
    total_score += exams_score
    
    # Determine status
    if exams_score == 0:
        exams_status = "missing"
    elif exams_score >= 20:
        exams_status = "complete"
    elif exams_score >= 10:
        exams_status = "partial"
    else:
        exams_status = "weak"
    
    sections["exams"] = {
        "score": exams_score,
        "max": exams_max,
        "status": exams_status
    }
    print(f"  [EXAMS] Total: {exams_score}/{exams_max} → {exams_status}")
    
    # ========================================
    # SOP (20 points)
    # ========================================
    sop_score = 0
    sop_max = 20
    
    sop_normalized = normalize_status(profile.sop_status)
    if sop_normalized == "COMPLETED":
        sop_score = 20
        print(f"  [SOP] Completed: {profile.sop_status} → +20")
    elif sop_normalized == "IN_PROGRESS":
        sop_score = 10
        print(f"  [SOP] In progress: {profile.sop_status} → +10")
    else:
        print(f"  [SOP] Not started → +0")
        next_actions.append("Complete your SOP")
    
    total_score += sop_score
    
    # Determine status
    if sop_score == 0:
        sop_status = "missing"
    elif sop_score >= 15:
        sop_status = "ready"
    else:
        sop_status = "drafting"
    
    sections["sop"] = {
        "score": sop_score,
        "max": sop_max,
        "status": sop_status
    }
    print(f"  [SOP] Total: {sop_score}/{sop_max} → {sop_status}")
    
    # ========================================
    # DOCUMENTS (15 points)
    # ========================================
    documents_score = 0
    documents_max = 15
    
    # Funding plan → 15 points
    if profile.funding_plan and profile.funding_plan.strip():
        documents_score += 15
        print(f"  [DOCUMENTS] Funding plan present → +15")
    else:
        print(f"  [DOCUMENTS] Funding plan missing → +0")
        next_actions.append("Define your funding plan")
    
    total_score += documents_score
    
    # Determine status
    if documents_score == 0:
        documents_status = "missing"
    elif documents_score >= 10:
        documents_status = "complete"
    else:
        documents_status = "partial"
    
    sections["documents"] = {
        "score": documents_score,
        "max": documents_max,
        "status": documents_status
    }
    print(f"  [DOCUMENTS] Total: {documents_score}/{documents_max} → {documents_status}")
    
    # ========================================
    # PREFERENCES (10 points)
    # ========================================
    preferences_score = 0
    preferences_max = 10
    
    # Countries → 4 points
    if profile.preferred_countries and len(profile.preferred_countries) > 0:
        preferences_score += 4
        print(f"  [PREFERENCES] Countries present: {profile.preferred_countries} → +4")
    else:
        print(f"  [PREFERENCES] Countries missing → +0")
        next_actions.append("Select preferred countries")
    
    # Budget → 3 points
    if profile.budget_per_year and profile.budget_per_year > 0:
        preferences_score += 3
        print(f"  [PREFERENCES] Budget present: {profile.budget_per_year} → +3")
    else:
        print(f"  [PREFERENCES] Budget missing → +0")
    
    # Field of study → 3 points
    if profile.field_of_study and profile.field_of_study.strip():
        preferences_score += 3
        print(f"  [PREFERENCES] Field present: {profile.field_of_study} → +3")
    else:
        print(f"  [PREFERENCES] Field missing → +0")
    
    total_score += preferences_score
    
    # Determine status
    if preferences_score == 0:
        preferences_status = "missing"
    elif preferences_score >= 8:
        preferences_status = "complete"
    else:
        preferences_status = "partial"
    
    sections["preferences"] = {
        "score": preferences_score,
        "max": preferences_max,
        "status": preferences_status
    }
    print(f"  [PREFERENCES] Total: {preferences_score}/{preferences_max} → {preferences_status}")
    
    # ========================================
    # CALCULATE FINAL PERCENTAGE
    # ========================================
    overall = round(total_score, 1)
    
    print(f"\n[PROFILE_STRENGTH] FINAL SCORE: {overall}/100")
    print(f"[PROFILE_STRENGTH] Next actions: {next_actions}\n")
    
    return {
        "overall": overall,
        "sections": sections,
        "next_actions": next_actions[:3]  # Limit to top 3 actions
    }
