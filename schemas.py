"""
Pydantic schemas for API requests and responses.
"""

from pydantic import BaseModel, EmailStr
from typing import List, Optional
from models import StageEnum, CategoryEnum

# User Profile Schemas
class UserProfileCreate(BaseModel):
    name: str
    email: EmailStr
    education_level: Optional[str] = None
    degree: Optional[str] = None
    graduation_year: Optional[int] = None
    gpa: Optional[float] = None
    intended_degree: Optional[str] = None
    field_of_study: Optional[str] = None
    intake_year: Optional[int] = None
    preferred_countries: List[str] = []
    budget_per_year: Optional[int] = None
    funding_plan: Optional[str] = None
    ielts_status: Optional[str] = None
    gre_gmat_status: Optional[str] = None
    sop_status: Optional[str] = None
    final_submit: Optional[bool] = False  # Flag to mark profile as complete

class UserProfileResponse(BaseModel):
    id: int
    name: Optional[str]
    email: str
    profile_complete: bool
    
    class Config:
        from_attributes = True

# University Schemas
class UniversityResponse(BaseModel):
    id: int
    name: str
    country: str
    rank: Optional[int]
    estimated_tuition_usd: int
    competitiveness: Optional[str]

class CategorizedUniversities(BaseModel):
    dream: List[UniversityResponse] = []
    target: List[UniversityResponse] = []
    safe: List[UniversityResponse] = []

# Task Schemas
class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    stage: StageEnum
    completed: bool
    
    class Config:
        from_attributes = True

# Dashboard Schema
class DashboardResponse(BaseModel):
    profile_summary: UserProfileResponse
    current_stage: StageEnum
    tasks: List[TaskResponse]
    universities: Optional[CategorizedUniversities] = None

# Onboarding Schema
class OnboardingResponse(BaseModel):
    profile_complete: bool
    current_stage: StageEnum
    user_id: int

# Shortlist Schema
class ShortlistRequest(BaseModel):
    university_id: int
    category: CategoryEnum

class ShortlistResponse(BaseModel):
    success: bool
    message: str

# Lock Schema
class LockRequest(BaseModel):
    university_id: int

class LockResponse(BaseModel):
    success: bool
    message: str
    locked_university: Optional[UniversityResponse] = None

# Application Schema
class ApplicationResponse(BaseModel):
    locked_university: UniversityResponse
    tasks: List[TaskResponse]
    timeline: List[str]

# AI Counsel Schema (Simplified)
class CounselRequest(BaseModel):
    email: str
    message: str

class CounselActions(BaseModel):
    shortlisted_added: List[int] = []
    shortlisted_removed: List[int] = []
    tasks_added: List[str] = []

class CounselResponse(BaseModel):
    message: str
    actions: CounselActions

class MatchesResponse(BaseModel):
    matches: CategorizedUniversities
    count: int # Added count field

# Error Schema
class ErrorResponse(BaseModel):
    error: str
    message: str
