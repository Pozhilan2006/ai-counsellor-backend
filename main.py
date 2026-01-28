from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from schemas import Context, AdvisorResponse
from service import process_counseling
from config import settings

app = FastAPI(title="AI Counsellor Backend")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "message": "AI Counsellor Backend is running"}

@app.post("/counsel", response_model=AdvisorResponse)
async def counsel(context: Context):
    return process_counseling(context)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
