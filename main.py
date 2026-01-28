from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from schemas import Context, AdvisorResponse
from service import process_counseling

app = FastAPI(title="AI Counsellor Backend")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ai-counsellor-frontend.vercel.app",
        "http://localhost:3000",  # For local development
        "http://localhost:5173",  # For Vite local development
    ],
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
