"""
CRUD operations for database models.
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from models import UserProfile, UserState, UserUniversity, Task, StageEnum, CategoryEnum
from typing import List, Optional, Dict
from datetime import datetime

# UserProfile operations
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

# UserUniversity operations
def get_user_universities(db: Session, user_id: int, shortlisted: Optional[bool] = None) -> List[UserUniversity]:
    """Get user's universities, optionally filtered by shortlist status."""
    query = db.query(UserUniversity).filter(UserUniversity.user_id == user_id)
    if shortlisted is not None:
        query = query.filter(UserUniversity.shortlisted == shortlisted)
    return query.all()

def shortlist_university(db: Session, user_id: int, university_id: int, category: CategoryEnum) -> UserUniversity:
    """Add university to user's shortlist."""
    # Check if already exists
    existing = db.query(UserUniversity).filter(
        and_(
            UserUniversity.user_id == user_id,
            UserUniversity.university_id == university_id
        )
    ).first()
    
    if existing:
        existing.shortlisted = True
        existing.category = category
        db.commit()
        db.refresh(existing)
        return existing
    
    # Create new entry
    user_uni = UserUniversity(
        user_id=user_id,
        university_id=university_id,
        category=category,
        shortlisted=True
    )
    db.add(user_uni)
    db.commit()
    db.refresh(user_uni)
    return user_uni

def lock_university(db: Session, user_id: int, university_id: int) -> UserUniversity:
    """Lock a university for application."""
    # Unlock any previously locked universities
    db.query(UserUniversity).filter(
        and_(
            UserUniversity.user_id == user_id,
            UserUniversity.locked == True
        )
    ).update({"locked": False})
    
    # Lock the selected university
    user_uni = db.query(UserUniversity).filter(
        and_(
            UserUniversity.user_id == user_id,
            UserUniversity.university_id == university_id
        )
    ).first()
    
    if user_uni:
        user_uni.locked = True
        db.commit()
        db.refresh(user_uni)
        return user_uni
    
    raise ValueError("University not found in user's list")

def get_locked_university(db: Session, user_id: int) -> Optional[UserUniversity]:
    """Get user's locked university."""
    return db.query(UserUniversity).filter(
        and_(
            UserUniversity.user_id == user_id,
            UserUniversity.locked == True
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
    """Get all tasks for a user."""
    return db.query(Task).filter(Task.user_id == user_id).all()

def complete_task(db: Session, task_id: int):
    """Mark a task as completed."""
    db.query(Task).filter(Task.id == task_id).update({"completed": True})
    db.commit()

def generate_initial_tasks(db: Session, user_id: int):
    """Generate initial tasks for a new user."""
    initial_tasks = [
        {
            "title": "Explore university recommendations",
            "description": "Review the personalized university recommendations based on your profile",
            "stage": StageEnum.DISCOVERY
        },
        {
            "title": "Research universities",
            "description": "Learn more about the recommended universities and their programs",
            "stage": StageEnum.DISCOVERY
        },
        {
            "title": "Shortlist universities",
            "description": "Select universities that best match your goals and preferences",
            "stage": StageEnum.DISCOVERY
        }
    ]
    
    for task_data in initial_tasks:
        create_task(db, user_id, **task_data)
