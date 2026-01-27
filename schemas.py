from pydantic import BaseModel, EmailStr
from typing import List, Optional
from enum import Enum
from models import StageEnum

class University(BaseModel):
    id: int
    name: str
    location: str
    description: Optional[str] = None

class UserProfile(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    academic_score: Optional[float] = None
    budget: Optional[float] = None
    preferred_country: Optional[str] = None

class Context(BaseModel):
    user_profile: UserProfile
    current_stage: StageEnum
    shortlisted_universities: List[University] = []
    locked_university: Optional[University] = None

class AdvisorResponse(BaseModel):
    message: str
    next_stage: Optional[StageEnum] = None
    missing_fields: List[str] = []
    recommendations: List[University] = []
