@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Postgraduate Monitoring System - Setup

echo.
echo  +------------------------------------------------------+
echo  ^|   Postgraduate Monitoring System - First-time Setup  ^|
echo  +------------------------------------------------------+
echo  ^|  This will:                                          ^|
echo  ^|  1. Check Docker Desktop is installed and running    ^|
echo  ^|  2. Build backend and frontend Docker images         ^|
echo  ^|  3. Pull Qwen3:8b AI model (~5 GB, may take a while) ^|
echo  ^|  4. Initialise the database                          ^|
echo  ^|                                                      ^|
echo  ^|  Run this ONCE. Use start.bat for daily launches.    ^|
echo  +------------------------------------------------------+
echo.
pause

:: ================================================================
:: STEP 1 — Check Docker is installed
:: ================================================================
echo.
echo [1/6] Checking Docker installation...
where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Docker is not installed or not in PATH.
    echo.
    echo  Please install Docker Desktop from:
    echo  https://www.docker.com/products/docker-desktop
    echo.
    echo  After installing, restart this setup.
    echo.
    pause
    exit /b 1
)
echo        Docker CLI found.

:: ================================================================
:: STEP 2 — Check Docker Desktop is running (start it if needed)
:: ================================================================
echo.
echo [2/6] Checking Docker Desktop is running...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo        Docker Desktop is not running. Attempting to start it...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo        Waiting for Docker Desktop to start (up to 60 seconds)...
    set /a d=0
    :wait_docker
    timeout /t 3 /nobreak >nul
    set /a d+=3
    docker info >nul 2>&1
    if %errorlevel% equ 0 goto docker_ready
    if !d! geq 60 (
        echo.
        echo  ERROR: Docker Desktop did not start in time.
        echo  Please start Docker Desktop manually and run setup again.
        echo.
        pause
        exit /b 1
    )
    goto wait_docker
)
:docker_ready
echo        Docker Desktop is running.

:: ================================================================
:: STEP 3 — Build backend image
:: ================================================================
echo.
echo [3/6] Building backend image (FastAPI)...
echo        This may take a few minutes on first run...
docker compose build backend
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Backend build failed. Check output above.
    echo.
    pause
    exit /b 1
)
echo        Backend image built successfully.

:: ================================================================
:: STEP 4 — Build frontend image
:: ================================================================
echo.
echo [4/6] Building frontend image (Next.js)...
echo        This may take several minutes (npm install + build)...
docker build -t datatrain-frontend ./frontend
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Frontend build failed. Check output above.
    echo.
    pause
    exit /b 1
)
echo        Frontend image built successfully.

:: ================================================================
:: STEP 5 — Start all services and initialise database
:: ================================================================
echo.
echo [5/6] Starting all services and initialising database...
docker compose up -d
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Failed to start services. Check output above.
    echo.
    pause
    exit /b 1
)

:: Start frontend container
docker rm -f datatrain-frontend >nul 2>&1
docker run -d --name datatrain-frontend ^
    --network agent_default ^
    -p 3000:3000 ^
    -e NEXT_PUBLIC_API_URL=http://localhost:8000 ^
    -e NEXT_PUBLIC_WS_URL=ws://localhost:8000 ^
    --restart unless-stopped ^
    datatrain-frontend
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Failed to start frontend container.
    echo.
    pause
    exit /b 1
)
echo        All services started.

:: Wait for DB to be healthy before pulling model
echo        Waiting for database to initialise...
set /a d=0
:wait_db
timeout /t 3 /nobreak >nul
set /a d+=3
docker exec datatrain-db healthcheck.sh --connect --innodb_initialized >nul 2>&1
if %errorlevel% equ 0 goto db_ready
if !d! geq 60 (
    echo        WARNING: Database health check timed out, continuing anyway...
    goto pull_model
)
goto wait_db
:db_ready
echo        Database is ready.

:: ================================================================
:: STEP 6 — Pull Qwen3:8b AI model
:: ================================================================
:pull_model
echo.
echo [6/6] Pulling Qwen3:8b AI model (~5 GB)...
echo        This will take several minutes depending on your internet speed.
echo        Do not close this window.
echo.
docker exec datatrain-ollama ollama pull qwen3:8b
if %errorlevel% neq 0 (
    echo.
    echo  WARNING: Qwen3:8b model pull failed or was interrupted.
    echo  You can retry manually with:
    echo    docker exec datatrain-ollama ollama pull qwen3:8b
    echo.
) else (
    echo        Qwen3:8b model downloaded successfully.
)

:: ================================================================
:: DONE
:: ================================================================
echo.
echo  +------------------------------------------------------+
echo  ^|              Setup Complete!                         ^|
echo  +------------------------------------------------------+
echo  ^|  App          http://localhost:3000                  ^|
echo  ^|  API Docs     http://localhost:8000/docs             ^|
echo  ^|  Mailpit      http://localhost:8025                  ^|
echo  +------------------------------------------------------+
echo  ^|  From now on, just double-click start.bat to launch. ^|
echo  +------------------------------------------------------+
echo.
start "" "http://localhost:3000"
pause
