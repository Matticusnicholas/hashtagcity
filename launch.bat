@echo off
title HashtagCity Launcher
color 0A

echo ============================================
echo        #HashtagCity - AI Video Analyzer
echo ============================================
echo.

:: ---- Configuration ----
set OLLAMA_PORT=11434
set BACKEND_PORT=8000
set FRONTEND_PORT=3000

:: ---- Step 1: Check Python ----
echo [1/6] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Download from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo       Python found.

:: ---- Step 2: Check Node.js ----
echo [2/6] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js is not installed or not in PATH.
    echo Download from https://nodejs.org/
    pause
    exit /b 1
)
echo       Node.js found.

:: ---- Step 3: Start Ollama ----
echo [3/6] Starting Ollama...

:: Check if Ollama is already running
curl -s http://localhost:%OLLAMA_PORT%/api/tags >nul 2>&1
if %errorlevel% equ 0 (
    echo       Ollama is already running.
) else (
    :: Try to start Ollama serve in background
    echo       Starting Ollama serve...
    start /min "Ollama" ollama serve

    :: Wait up to 30 seconds for Ollama to start
    set /a TRIES=0
    :wait_ollama
    if %TRIES% geq 15 (
        echo ERROR: Ollama failed to start after 30 seconds.
        echo Make sure Ollama is installed: https://ollama.com/download
        pause
        exit /b 1
    )
    timeout /t 2 /nobreak >nul
    curl -s http://localhost:%OLLAMA_PORT%/api/tags >nul 2>&1
    if %errorlevel% neq 0 (
        set /a TRIES+=1
        goto wait_ollama
    )
    echo       Ollama started successfully.
)

:: ---- Step 4: Install backend dependencies ----
echo [4/6] Setting up Python backend...
if not exist "backend\venv" (
    echo       Creating virtual environment...
    python -m venv backend\venv
)
echo       Installing dependencies...
call backend\venv\Scripts\activate.bat
pip install -r backend\requirements.txt -q 2>nul

:: ---- Step 5: Install frontend dependencies ----
echo [5/6] Setting up Next.js frontend...
cd frontend
if not exist "node_modules" (
    echo       Installing npm packages (first run takes a moment)...
    call npm install --silent 2>nul
) else (
    echo       Dependencies already installed.
)
cd ..

:: ---- Step 6: Launch everything ----
echo [6/6] Launching application...
echo.
echo ============================================
echo   Backend:  http://localhost:%BACKEND_PORT%
echo   Frontend: http://localhost:%FRONTEND_PORT%
echo ============================================
echo.
echo   Open http://localhost:%FRONTEND_PORT% in your browser
echo   Press Ctrl+C in any window to stop
echo.

:: Start backend
start "HashtagCity Backend" cmd /k "cd backend && call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload"

:: Wait a moment for backend to start
timeout /t 3 /nobreak >nul

:: Start frontend
start "HashtagCity Frontend" cmd /k "cd frontend && npm run dev"

:: Wait then open browser
timeout /t 5 /nobreak >nul
start http://localhost:%FRONTEND_PORT%

echo.
echo All services launched! You can close this window.
echo To stop: close the Backend and Frontend terminal windows.
pause
