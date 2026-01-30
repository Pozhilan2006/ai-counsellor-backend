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

def get_all_tasks(db: Session, user_id: int) -> tuple[List[Task], int | None]:
    """
    Get all tasks for a user, filtered by locked university if applicable.
    
    Returns:
        (tasks, locked_university_id)
        - tasks: List of Task objects
        - locked_university_id: ID of locked university, or None
    """
    try:
        # Check if user has a locked university
        locked_shortlist = db.query(Shortlist).filter(
            Shortlist.user_id == user_id,
            Shortlist.locked == True
        ).first()
        
        locked_university_id = locked_shortlist.university_id if locked_shortlist else None
        
        if locked_university_id:
            # User has locked university - return only tasks for that university
            tasks = db.query(Task).filter(
                Task.user_id == user_id,
                Task.university_id == locked_university_id
            ).all()
            print(f"[TASKS] User {user_id} has locked university {locked_university_id}, returning {len(tasks)} tasks")
        else:
            # No locked university - return empty list (tasks only appear after lock)
            tasks = []
            print(f"[TASKS] User {user_id} has no locked university, returning empty tasks")
        
        return tasks, locked_university_id
        
    except Exception as e:
        print(f"[WARNING] get_all_tasks failed: {str(e)}")
        return [], None

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

def sync_profile_tasks(db: Session, user_id: int):
    """
    Sync tasks for BUILDING_PROFILE stage.
    Auto-generates tasks for missing profile sections.
    """
    profile = get_user_profile(db, user_id)
    if not profile: return

    # Define profile rules
    profile_rules = [
        ("Upload IELTS/TOEFL score", not profile.ielts_status or profile.ielts_status == "NOT_STARTED"),
        ("Upload GRE/GMAT score", not profile.gre_gmat_status or profile.gre_gmat_status == "NOT_STARTED"),
        ("Finalize Statement of Purpose", not profile.sop_status or profile.sop_status == "NOT_STARTED"),
        ("Set funding plan", not profile.funding_plan),
        ("Select preferred countries", not profile.preferred_countries or len(profile.preferred_countries) == 0)
    ]

    # Get current profile tasks
    current_tasks = db.query(Task).filter(
        and_(Task.user_id == user_id, Task.stage == StageEnum.BUILDING_PROFILE)
    ).all()
    current_titles = {t.title for t in current_tasks}

    for title, condition in profile_rules:
        if condition and title not in current_titles:
            # Create task if missing
            create_task(db, user_id, title, "Complete this profile section", StageEnum.BUILDING_PROFILE)
        elif not condition and title in current_titles:
            # Remove task if completed
            db.query(Task).filter(
                and_(Task.user_id == user_id, Task.title == title)
            ).delete()
    
    db.commit()

def generate_university_tasks(db: Session, user_id: int, university_id: int) -> List[Task]:
    """
    Generate university-specific tasks after lock.
    Uses PREPARING_APPLICATIONS stage.
    """
    try:
        # Clear existing tasks for this user
        db.query(Task).filter(Task.user_id == user_id).delete()
        
        tasks_data = [
            {
                "title": "Complete Statement of Purpose",
                "description": "Draft your SOP highlighting why this university aligns with your goals",
                "stage": StageEnum.PREPARING_APPLICATIONS,
                "university_id": university_id
            },
            {
                "title": "Gather Recommendation Letters",
                "description": "Request 2-3 letters from professors",
                "stage": StageEnum.PREPARING_APPLICATIONS,
                "university_id": university_id
            },
            {
                "title": "Prepare Official Transcripts",
                "description": "Get official transcripts from your institution",
                "stage": StageEnum.PREPARING_APPLICATIONS,
                "university_id": university_id
            },
            {
                "title": "Check Application Deadlines",
                "description": "Verify deadlines and set reminders",
                "stage": StageEnum.PREPARING_APPLICATIONS,
                "university_id": university_id
            },
            {
                "title": "Complete Standardized Tests",
                "description": "Ensure scores align with requirements",
                "stage": StageEnum.PREPARING_APPLICATIONS,
                "university_id": university_id
            }
        ]
        
        tasks = []
        for task_data in tasks_data:
            task = Task(user_id=user_id, **task_data)
            db.add(task)
            tasks.append(task)
        
        db.commit()
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

# Profile Strength Calculation (Standardized)
def calculate_profile_strength(db: Session, profile: UserProfile) -> Dict:
    """
    Calculate profile completion using point-based scoring (100 points total).
    Standardized Statuses: strong | average | weak | missing
    """
    print(f"\n[PROFILE_STRENGTH] Calculating for user_id={profile.id}, email={profile.email}")
    
    total_score = 0
    sections = {}
    next_actions = []
    
    # Helper to map score to standard status
    def get_status(score: int, max_score: int) -> str:
        if score == 0: return "missing"
        if score >= max_score * 0.8: return "strong"
        if score >= max_score * 0.4: return "average"
        return "weak"

    # ========================================
    # ACADEMICS (30 points)
    # ========================================
    academics_score = 0
    academics_max = 30
    
    if profile.gpa and float(profile.gpa) > 0:
        academics_score += 15
    else:
        next_actions.append("Add your GPA")
    
    if profile.degree and profile.degree.strip():
        academics_score += 10
    else:
        next_actions.append("Add your degree")
        
    if profile.graduation_year and profile.graduation_year > 0:
        academics_score += 5
    
    academics_status = get_status(academics_score, academics_max)
    sections["academics"] = {
        "status": academics_status,
        "score": academics_score,
        "max_score": academics_max
    }
    total_score += academics_score

    # ========================================
    # EXAMS (25 points)
    # ========================================
    exams_score = 0
    exams_max = 25
    
    # IELTS Logic
    ielts_norm = normalize_status(profile.ielts_status)
    if ielts_norm == "COMPLETED": exams_score += 12
    elif ielts_norm == "IN_PROGRESS": exams_score += 6
    else: next_actions.append("Complete IELTS")
    
    # GRE Logic
    gre_norm = normalize_status(profile.gre_gmat_status)
    if gre_norm == "COMPLETED": exams_score += 13
    elif gre_norm == "IN_PROGRESS": exams_score += 6
    elif gre_norm == "NOT_STARTED": next_actions.append("Complete GRE/GMAT")

    exams_status = get_status(exams_score, exams_max)
    sections["exams"] = {
        "status": exams_status,
        "score": exams_score,
        "max_score": exams_max
    }
    total_score += exams_score

    # ========================================
    # SOP (20 points)
    # ========================================
    sop_score = 0
    sop_max = 20
    sop_norm = normalize_status(profile.sop_status)
    
    if sop_norm == "COMPLETED": sop_score = 20
    elif sop_norm == "IN_PROGRESS": sop_score = 10
    else: next_actions.append("Draft your SOP")

    sop_status = get_status(sop_score, sop_max)
    sections["sop"] = {
        "status": sop_status,
        "score": sop_score,
        "max_score": sop_max
    }
    total_score += sop_score

    # ========================================
    # DOCUMENTS (15 points)
    # ========================================
    docs_score = 0
    docs_max = 15
    if profile.funding_plan: docs_score = 15
    else: next_actions.append("Add funding plan")
    
    docs_status = get_status(docs_score, docs_max)
    sections["documents"] = {
        "status": docs_status,
        "score": docs_score,
        "max_score": docs_max
    }
    total_score += docs_score

    # ========================================
    # PREFERENCES (10 points)
    # ========================================
    prefs_score = 0
    prefs_max = 10
    
    if profile.preferred_countries: prefs_score += 4
    else: next_actions.append("Select countries")
    
    if profile.budget_per_year: prefs_score += 3
    
    if profile.field_of_study: prefs_score += 3
    else: next_actions.append("Select field of study")

    prefs_status = get_status(prefs_score, prefs_max)
    sections["preferences"] = {
        "status": prefs_status,
        "score": prefs_score,
        "max_score": prefs_max
    }
    total_score += prefs_score

    return {
        "overall_score": int(total_score),
        "sections": sections,
        "next_actions": next_actions[:3]
    }
