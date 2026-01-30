"""
Pydantic schemas for API requests and responses.
"""

from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Generic, TypeVar
from models import StageEnum, CategoryEnum

# Generic Wrapper
T = TypeVar('T')

class ApiResponse(BaseModel, Generic[T]):
    status: str = "OK"  # OK | EMPTY | LOCKED | ERROR
    data: T

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
    name: str = ""
    email: str
    profile_complete: bool = False
    
    class Config:
        from_attributes = True

# University Schemas
class UniversityResponse(BaseModel):
    id: int
    name: str
    country: str
    rank: int = 999 # Safe default
    estimated_tuition_usd: int = 0
    competitiveness: str = "MEDIUM"
    match_percentage: int = 0 # Added match_percentage
    category: str = "TARGET" # Added category (Dream/Target/Safe)

class CategorizedUniversities(BaseModel):
    dream: List[UniversityResponse] = []
    target: List[UniversityResponse] = []
    safe: List[UniversityResponse] = []

# Profile Strength Schemas
class SectionStrength(BaseModel):
    status: str = "missing" # strong / average / weak / missing
    score: int = 0
    max_score: int = 0

class ProfileSections(BaseModel):
    academics: SectionStrength = Field(default_factory=lambda: SectionStrength(max_score=30))
    exams: SectionStrength = Field(default_factory=lambda: SectionStrength(max_score=25))
    sop: SectionStrength = Field(default_factory=lambda: SectionStrength(max_score=20))
    documents: SectionStrength = Field(default_factory=lambda: SectionStrength(max_score=15))
    preferences: SectionStrength = Field(default_factory=lambda: SectionStrength(max_score=10))

class ProfileStrengthResponse(BaseModel):
    overall_score: int = 0
    sections: ProfileSections = Field(default_factory=ProfileSections)
    next_actions: List[str] = []

    class Config:
        from_attributes = True

# Task Schemas
class TaskResponse(BaseModel):
    id: int
    title: str
    description: str = ""
    stage: StageEnum
    completed: bool = False
    
    class Config:
        from_attributes = True

# Dashboard Schema
class DashboardResponse(BaseModel):
    profile_summary: UserProfileResponse
    current_stage: StageEnum
    tasks: List[TaskResponse] = []
    universities: CategorizedUniversities = Field(default_factory=CategorizedUniversities)
    profile_strength: ProfileStrengthResponse = Field(default_factory=ProfileStrengthResponse) # Added profile strength to dashboard

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
    shortlists: List[Dict] = [] # Fallback for get_shortlist wrapper
    count: int = 0

# Lock Schema
class LockRequest(BaseModel):
    university_id: int

class LockResponse(BaseModel):
    success: bool
    message: str
    locked_university_id: Optional[int] = None

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
    matches: CategorizedUniversities = Field(default_factory=CategorizedUniversities)
    count: int = 0

# Error Schema
class ErrorResponse(BaseModel):
    status: str = "ERROR"
    error: str
    message: str
