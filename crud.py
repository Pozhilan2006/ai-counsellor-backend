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

def generate_initial_tasks(db: Session, user_id: int) -> List[Task]:
    """Generate initial tasks for a user. Safe if table doesn't exist."""
    try:
        # Default tasks for DISCOVERY stage
        default_tasks = [
            {"title": "Complete your profile", "description": "Fill in all required information", "stage": StageEnum.DISCOVERY},
            {"title": "Review university recommendations", "description": "Browse through matched universities", "stage": StageEnum.DISCOVERY},
            {"title": "Shortlist universities", "description": "Add universities to your shortlist", "stage": StageEnum.SHORTLIST},
        ]
        
        tasks = []
        for task_data in default_tasks:
            task = Task(user_id=user_id, **task_data)
            db.add(task)
            tasks.append(task)
        
        db.commit()
        return tasks
    except Exception as e:
        print(f"[WARNING] generate_initial_tasks failed (table may not exist): {str(e)}")
        db.rollback()
        return []

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

# Profile Strength Calculation (Point-Based System)
def calculate_profile_strength(db: Session, profile: UserProfile) -> Dict:
    """
    Calculate profile completion using point-based scoring (100 points total).
    
    Scoring Breakdown:
    - Academics (30 points): GPA (20) + Degree/Field (10)
    - Exams (20 points): IELTS/TOEFL (10) + GRE/GMAT (10)
    - Documents (25 points): SOP (15 max) + Resume (10)
    - Preferences (15 points): Budget (5) + Countries (5) + Course (5)
    - Decision Progress (10 points): Shortlist (5) OR Lock (10)
    
    Returns dynamic calculation, NOT static values.
    """
    total_points = 0
    sections = {}
    
    # ========================================
    # ACADEMICS (30 points)
    # ========================================
    academics_points = 0
    
    # GPA present → +20
    if profile.gpa and float(profile.gpa) > 0:
        academics_points += 20
    
    # Degree / field present → +10
    if (profile.degree and profile.degree.strip()) or (profile.field_of_study and profile.field_of_study.strip()):
        academics_points += 10
    
    total_points += academics_points
    sections["academics"] = {
        "points": academics_points,
        "max_points": 30,
        "percentage": round((academics_points / 30) * 100, 1),
        "status": "strong" if academics_points >= 25 else "moderate" if academics_points >= 15 else "weak"
    }
    
    # ========================================
    # EXAMS (20 points)
    # ========================================
    exams_points = 0
    
    # IELTS/TOEFL status + score → +10
    if profile.ielts_status and profile.ielts_status not in ["", "Not Started", "Planning"]:
        exams_points += 10
    
    # GRE/GMAT status + score → +10
    if profile.gre_gmat_status and profile.gre_gmat_status not in ["", "Not Started", "Planning"]:
        exams_points += 10
    
    total_points += exams_points
    sections["exams"] = {
        "points": exams_points,
        "max_points": 20,
        "percentage": round((exams_points / 20) * 100, 1),
        "status": "complete" if exams_points >= 15 else "in_progress" if exams_points >= 5 else "not_started"
    }
    
    # ========================================
    # DOCUMENTS (25 points)
    # ========================================
    documents_points = 0
    
    # SOP status
    if profile.sop_status:
        if profile.sop_status.lower() in ["ready", "completed", "done"]:
            documents_points += 15
        elif profile.sop_status.lower() in ["draft", "drafting", "in progress"]:
            documents_points += 10
    
    # Resume uploaded → +10 (check if field exists, future enhancement)
    # For now, we'll use a placeholder check
    # documents_points += 10  # Add when resume field exists
    
    total_points += documents_points
    sections["documents"] = {
        "points": documents_points,
        "max_points": 25,
        "percentage": round((documents_points / 25) * 100, 1),
        "status": "complete" if documents_points >= 20 else "incomplete"
    }
    
    # ========================================
    # PREFERENCES & PLANNING (15 points)
    # ========================================
    preferences_points = 0
    
    # Budget set → +5
    if profile.budget_per_year and profile.budget_per_year > 0:
        preferences_points += 5
    
    # Country preferences set → +5
    if profile.preferred_countries and len(profile.preferred_countries) > 0:
        preferences_points += 5
    
    # Course preference set → +5
    if profile.field_of_study and profile.field_of_study.strip():
        preferences_points += 5
    
    total_points += preferences_points
    sections["preferences"] = {
        "points": preferences_points,
        "max_points": 15,
        "percentage": round((preferences_points / 15) * 100, 1),
        "status": "complete" if preferences_points >= 12 else "partial" if preferences_points >= 5 else "incomplete"
    }
    
    # ========================================
    # DECISION PROGRESS (10 points)
    # ========================================
    decision_points = 0
    
    # Check if university is locked (overrides shortlist)
    locked_uni = get_locked_university(db, profile.id)
    if locked_uni:
        decision_points = 10
    else:
        # Check shortlist count
        shortlists = get_user_shortlists(db, profile.id)
        if len(shortlists) >= 1:
            decision_points = 5
    
    total_points += decision_points
    sections["decision_progress"] = {
        "points": decision_points,
        "max_points": 10,
        "percentage": round((decision_points / 10) * 100, 1),
        "status": "locked" if decision_points == 10 else "shortlisted" if decision_points == 5 else "exploring"
    }
    
    # ========================================
    # CALCULATE FINAL PERCENTAGE
    # ========================================
    total_percentage = round(total_points, 1)  # Out of 100
    
    return {
        "percentage": total_percentage,
        "total_points": total_points,
        "max_points": 100,
        "sections": sections,
        "breakdown": {
            "academics": sections["academics"]["status"],
            "exams": sections["exams"]["status"],
            "documents": sections["documents"]["status"],
            "preferences": sections["preferences"]["status"],
            "decision": sections["decision_progress"]["status"]
        }
    }
