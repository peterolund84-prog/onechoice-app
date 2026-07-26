@echo off
REM OneChoice HTML UI — same workflow as Streamlit: leave this running,
REM then `git pull` and refresh the phone. --reload picks up Python changes.
cd /d "%~dp0"
py -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
