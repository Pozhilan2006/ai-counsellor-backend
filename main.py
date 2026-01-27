from fastapi import FastAPI

app = FastAPI(title="AI Counsellor Backend")

@app.get("/")
async def root():
    return {"status": "ok", "message": "AI Counsellor Backend is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
