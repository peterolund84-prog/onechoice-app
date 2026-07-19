@echo off
REM OneChoice – starta Streamlit-appen
cd /d "%~dp0"
python -m streamlit run app.py
if errorlevel 1 py -m streamlit run app.py
pause
