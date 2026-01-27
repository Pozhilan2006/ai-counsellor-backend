from fastapi import FastAPI
from schemas import Context, AdvisorResponse
from service import process_counseling

app = FastAPI(title="AI Counsellor Backend")

@app.get("/")
async def root():
    return {"status": "ok", "message": "AI Counsellor Backend is running"}

@app.post("/counsel", response_model=AdvisorResponse)
async def counsel(context: Context):
    return process_counseling(context)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
