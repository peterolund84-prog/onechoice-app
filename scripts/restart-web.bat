@echo off
setlocal
cd /d "%~dp0\.."

echo Stopping Vite on 5173/5174...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173 :5174" ^| findstr LISTENING') do (
  echo Killing PID %%P
  taskkill /PID %%P /F >nul 2>&1
)

echo Pulling latest...
git pull

cd web
echo Starting Vite on 0.0.0.0:5173 ...
call npm run dev -- --host 0.0.0.0 --port 5173
endlocal
