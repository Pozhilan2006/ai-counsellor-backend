from pydantic import BaseModel, EmailStr
from typing import List, Optional, Union
from enum import Enum
from models import StageEnum

class UniversityRecommendation(BaseModel):
    """University recommendation for API response."""
    id: int
    name: str
    country: str
    rank: Optional[int] = None
    estimated_tuition_usd: int
    competitiveness: Optional[str] = None

class RecommendationsByCategory(BaseModel):
    """Categorized university recommendations."""
    dream: List[UniversityRecommendation] = []
    target: List[UniversityRecommendation] = []
    safe: List[UniversityRecommendation] = []

class UserProfile(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    academic_score: Optional[float] = None
    budget: Optional[float] = None
    preferred_country: Optional[str] = None

class Context(BaseModel):
    user_profile: UserProfile
    current_stage: StageEnum
    shortlisted_universities: List = []
    locked_university: Optional[dict] = None

class AdvisorResponse(BaseModel):
    message: str
    next_stage: Optional[StageEnum] = None
    missing_fields: List[str] = []
    recommendations: Union[List[UniversityRecommendation], RecommendationsByCategory] = []
