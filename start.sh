#!/bin/bash
# Render startup script
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1
