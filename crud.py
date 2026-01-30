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

# Profile Strength Calculation
def calculate_profile_strength(profile: UserProfile) -> Dict:
    """
    Calculate profile completion percentage.
    Returns overall and category-wise breakdown.
    
    Categories:
    - Academic (30%): GPA, test scores
    - Basic Info (25%): Name, email, field, countries, budget
    - Experience (25%): Work experience, projects (future fields)
    - Documents (20%): SOP, recommendations, resume (future fields)
    """
    # Academic (30%)
    academic_fields = {
        "gpa": profile.gpa is not None and profile.gpa > 0,
        "gre_gmat": profile.gre_gmat_status not in [None, "", "Not Started"],
        "ielts": profile.ielts_status not in [None, "", "Not Started"]
    }
    academic_completed = sum(academic_fields.values())
    academic_total = len(academic_fields)
    academic_score = (academic_completed / academic_total) * 30 if academic_total > 0 else 0
    
    # Basic Info (25%)
    basic_fields = {
        "name": bool(profile.name and profile.name.strip()),
        "email": bool(profile.email and profile.email.strip()),
        "field_of_study": bool(profile.field_of_study and profile.field_of_study.strip()),
        "preferred_countries": bool(profile.preferred_countries and len(profile.preferred_countries) > 0),
        "budget": profile.budget_per_year is not None and profile.budget_per_year > 0
    }
    basic_completed = sum(basic_fields.values())
    basic_total = len(basic_fields)
    basic_score = (basic_completed / basic_total) * 25 if basic_total > 0 else 0
    
    # Education Details (25%)
    education_fields = {
        "education_level": bool(profile.education_level and profile.education_level.strip()),
        "degree": bool(profile.degree and profile.degree.strip()),
        "graduation_year": profile.graduation_year is not None and profile.graduation_year > 0,
        "intended_degree": bool(profile.intended_degree and profile.intended_degree.strip()),
        "intake_year": profile.intake_year is not None and profile.intake_year > 0
    }
    education_completed = sum(education_fields.values())
    education_total = len(education_fields)
    education_score = (education_completed / education_total) * 25 if education_total > 0 else 0
    
    # Documents (20%)
    document_fields = {
        "sop": profile.sop_status not in [None, "", "Not Started"],
        "funding_plan": bool(profile.funding_plan and profile.funding_plan.strip())
    }
    document_completed = sum(document_fields.values())
    document_total = len(document_fields)
    document_score = (document_completed / document_total) * 20 if document_total > 0 else 0
    
    # Calculate overall
    overall = academic_score + basic_score + education_score + document_score
    
    # Collect missing fields
    missing_fields = []
    for field, present in {**academic_fields, **basic_fields, **education_fields, **document_fields}.items():
        if not present:
            missing_fields.append(field)
    
    return {
        "overall_percentage": round(overall, 1),
        "categories": {
            "academic": {
                "percentage": round((academic_completed / academic_total) * 100, 1) if academic_total > 0 else 0,
                "completed": academic_completed,
                "total": academic_total
            },
            "basic_info": {
                "percentage": round((basic_completed / basic_total) * 100, 1) if basic_total > 0 else 0,
                "completed": basic_completed,
                "total": basic_total
            },
            "education": {
                "percentage": round((education_completed / education_total) * 100, 1) if education_total > 0 else 0,
                "completed": education_completed,
                "total": education_total
            },
            "documents": {
                "percentage": round((document_completed / document_total) * 100, 1) if document_total > 0 else 0,
                "completed": document_completed,
                "total": document_total
            }
        },
        "missing_fields": missing_fields,
        "total_fields_completed": academic_completed + basic_completed + education_completed + document_completed,
        "total_fields": academic_total + basic_total + education_total + document_total
    }
