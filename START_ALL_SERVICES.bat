@echo off
TITLE Constrained-xAIOps Service Launcher
COLOR 0A

echo ======================================================================
echo          Constrained-xAIOps: 1-Click Operational Stack Launcher
echo ======================================================================
echo.
echo [1/3] Checking Python Environment...
python --version
if %errorlevel% neq 0 (
    echo [ERROR] Python not found on PATH. Please install Python 3.11+.
    pause
    exit /b 1
)

echo.
echo [2/3] Launching FastAPI Inference Backend on http://localhost:8000 ...
start "Constrained-xAIOps FastAPI Backend (Port 8000)" cmd /k "python -m uvicorn src.dashboard.api:app --host 0.0.0.0 --port 8000 --workers 4"

echo Waiting for backend initialization (3 seconds)...
timeout /t 3 /nobreak >nul

echo.
echo [3/3] Launching Streamlit Interactive Dashboard on http://localhost:8501 ...
start "Constrained-xAIOps Streamlit Portal (Port 8501)" cmd /k "python -m streamlit run src/dashboard/app.py --server.port 8501 --server.headless false"

echo.
echo ======================================================================
echo [SUCCESS] Both services launched successfully!
echo   - FastAPI API Docs:    http://localhost:8000/docs
echo   - Streamlit Dashboard: http://localhost:8501
echo ======================================================================
echo Press any key to close this launcher window (services will remain running).
pause >nul
