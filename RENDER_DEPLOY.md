# Render Deployment Configuration

## Build Command
```
pip install -r requirements.txt
```

## Start Command
```
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Environment Variables
Set in Render Dashboard:
- `PORT` - Auto-set by Render (usually 10000)
- `GEMINI_API_KEY` - Your Google Gemini API key for AI counseling
- `DATABASE_URL` - Your PostgreSQL connection string (if using database)

## Health Check
Render will check: `http://your-service.onrender.com/`

The root endpoint returns:
```json
{
  "status": "ok",
  "message": "AI Counsellor Backend is running"
}
```

## Troubleshooting

### Port Binding Timeout
If deployment times out waiting for port:
1. Ensure start command uses `--host 0.0.0.0`
2. Ensure start command uses `--port $PORT`
3. Check logs for startup errors

### Python Version
Render auto-detects Python 3.13.4. To specify:
Create `runtime.txt`:
```
python-3.13.4
```
