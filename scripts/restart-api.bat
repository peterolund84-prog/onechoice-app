@echo off
setlocal
cd /d "%~dp0\.."

echo Stopping anything on port 8001...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr :8001 ^| findstr LISTENING') do (
  echo Killing PID %%P
  taskkill /PID %%P /F >nul 2>&1
)

echo Pulling latest...
git pull

echo Starting API on 0.0.0.0:8001 ...
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
endlocal
