from sqlalchemy import Column, String, Integer, Enum as SAEnum
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()

class StageEnum(str, enum.Enum):
    ONBOARDING = "ONBOARDING"
    DISCOVERY = "DISCOVERY"
    SHORTLISTING = "SHORTLISTING"
    LOCKED = "LOCKED"
    APPLICATION = "APPLICATION"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    stage = Column(SAEnum(StageEnum), default=StageEnum.ONBOARDING, nullable=False)
