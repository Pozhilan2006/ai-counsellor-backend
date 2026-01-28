import os
from typing import Optional

class Settings:
    """Application settings loaded from environment variables."""
    
    # API Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    # Server
    PORT: int = int(os.getenv("PORT", "8000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    
    # CORS
    ALLOWED_ORIGINS: list = [
        "https://ai-counsellor-frontend.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    
    @classmethod
    def validate(cls):
        """Validate required environment variables."""
        if not cls.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is required")
        if not cls.DATABASE_URL:
            print("Warning: DATABASE_URL not set. Database features will be disabled.")

settings = Settings()
