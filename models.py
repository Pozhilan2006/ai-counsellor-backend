from sqlalchemy import Column, Integer, String, Boolean, Enum, ARRAY, DECIMAL, ForeignKey, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()

# Enums
class StageEnum(str, enum.Enum):
    ONBOARDING = "ONBOARDING"
    DISCOVERY = "DISCOVERY"
    SHORTLIST = "SHORTLIST"
    LOCKED = "LOCKED"
    APPLICATION = "APPLICATION"

class CategoryEnum(str, enum.Enum):
    DREAM = "DREAM"
    TARGET = "TARGET"
    SAFE = "SAFE"

# Models
class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    email = Column(String(255), unique=True, nullable=False, index=True)
    education_level = Column(String(100))
    degree = Column(String(255))
    graduation_year = Column(Integer)
    gpa = Column(DECIMAL(3, 2))
    intended_degree = Column(String(255))
    field_of_study = Column(String(255))
    intake_year = Column(Integer)
    preferred_countries = Column(ARRAY(String))
    budget_per_year = Column(Integer)
    funding_plan = Column(String(255))
    ielts_status = Column(String(50))
    gre_gmat_status = Column(String(50))
    sop_status = Column(String(50))
    profile_complete = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserState(Base):
    __tablename__ = "user_states"
    
    user_id = Column(Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), primary_key=True)
    current_stage = Column(String(50), nullable=False, default="ONBOARDING")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Shortlist(Base):
    __tablename__ = "shortlists"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False)
    university_id = Column(Integer, nullable=False)
    category = Column(String(50), default="TARGET")  # DREAM | TARGET | SAFE
    locked = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    stage = Column(Enum(StageEnum))
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
