@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Postgraduate Monitoring System

echo.
echo  +------------------------------------------------------+
echo  ^|      Postgraduate Monitoring System                  ^|
echo  +------------------------------------------------------+
echo.

:: -- 1. Check Docker Desktop is running --------------------------
echo [1/5] Checking Docker Desktop...
docker info >nul 2>&1
if %errorlevel% equ 0 goto docker_ok

echo        Docker Desktop is not running. Attempting to start it...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
echo        Waiting for Docker Desktop to start (up to 60 seconds)...
set /a d=0
:wait_docker
timeout /t 3 /nobreak >nul
set /a d+=3
docker info >nul 2>&1
if %errorlevel% equ 0 goto docker_ok
if !d! geq 60 (
    echo.
    echo  ERROR: Docker Desktop did not start in time.
    echo  Please start Docker Desktop manually and try again.
    echo.
    pause
    exit /b 1
)
goto wait_docker

:docker_ok
echo        Docker Desktop is running.
echo.

:: -- 2. Start backend services ------------------------------------
echo [2/5] Starting backend services...
docker --context desktop-linux compose up -d
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: docker compose failed. Check the output above.
    echo.
    pause
    exit /b 1
)

:: Start frontend container
docker --context desktop-linux inspect datatrain-frontend >nul 2>&1
if %errorlevel% neq 0 (
    echo        Frontend container not found. Run setup.bat first.
    echo.
    pause
    exit /b 1
)
docker --context desktop-linux start datatrain-frontend >nul 2>&1
echo        All services started.
echo.

:: -- 3. Wait for Backend ------------------------------------------
echo [3/5] Waiting for Backend to be ready...
set /a tries=0
:wait_backend
set /a tries+=1
curl -sf http://localhost:8000/docs >nul 2>&1
if %errorlevel% equ 0 goto backend_ok
if !tries! geq 90 (
    echo  WARNING: Backend did not respond after 3 minutes.
    goto wait_frontend
)
if !tries! equ 1   echo        Waiting for backend to initialize...
if !tries! equ 15  echo        Still starting... (30s)
if !tries! equ 30  echo        Still starting... (1 min)
if !tries! equ 60  echo        Still starting... (2 min)
timeout /t 2 /nobreak >nul
goto wait_backend

:backend_ok
echo        Backend ready at http://localhost:8000
echo.

:: -- 4. Wait for Frontend -----------------------------------------
echo [4/5] Waiting for Frontend to be ready...
set /a tries=0
:wait_frontend
set /a tries+=1
curl -sf http://localhost:3000/ >nul 2>&1
if %errorlevel% equ 0 goto frontend_ok
if !tries! geq 150 (
    echo  WARNING: Frontend did not respond after 5 minutes.
    goto open_browsers
)
if !tries! equ 1   echo        Waiting for frontend...
if !tries! equ 30  echo        Still starting... (1 min elapsed)
if !tries! equ 60  echo        Still starting... (2 min elapsed)
if !tries! equ 90  echo        Still starting... (3 min elapsed)
timeout /t 2 /nobreak >nul
goto wait_frontend

:frontend_ok
echo        Frontend ready at http://localhost:3000
echo.

:: -- 5. Open browser ----------------------------------------------
:open_browsers
echo [5/5] Opening browser...
timeout /t 1 /nobreak >nul
start "" "http://localhost:3000"

:: -- Done ---------------------------------------------------------
echo.
echo  +------------------------------------------------------+
echo  ^|           All services are running!                  ^|
echo  +------------------------------------------------------+
echo  ^|  App          http://localhost:3000                  ^|
echo  ^|  API Docs     http://localhost:8000/docs             ^|
echo  ^|  Mailpit      http://localhost:8025                  ^|
echo  ^|  Ollama       http://localhost:11434                 ^|
echo  +------------------------------------------------------+
echo  ^|  docker compose logs -f           (stream all logs)  ^|
echo  ^|  docker compose logs -f backend   (backend only)     ^|
echo  ^|  docker compose down              (stop everything)  ^|
echo  +------------------------------------------------------+
echo.
pause
