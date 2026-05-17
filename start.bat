@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Postgraduate Monitoring System

:: ================================================================
::  Postgraduate Monitoring System - Startup Script
:: ================================================================

echo.
echo  +------------------------------------------------------+
echo  ^|      Postgraduate Monitoring System                  ^|
echo  +------------------------------------------------------+
echo.

:: -- 1. Check Docker Desktop is running --------------------------
echo [1/5] Checking Docker Desktop...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Docker Desktop is not running.
    echo  Please start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)
echo        OK - Docker Desktop is running.
echo.

:: -- 2. Start all containers -------------------------------------
echo [2/5] Starting all services (first run may take a few minutes)...
echo        MariaDB ^| Ollama ^| MLflow ^| Backend ^| Mailpit ^| Frontend
echo.
docker compose up -d --build
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: docker compose failed. Check the output above.
    echo.
    pause
    exit /b 1
)
echo.

:: -- 3. Wait for Backend (FastAPI on :8000) ----------------------
echo [3/5] Waiting for Backend to be ready...
set /a tries=0
:wait_backend
set /a tries+=1
curl -sf http://localhost:8000/docs >nul 2>&1
if %errorlevel% equ 0 goto backend_ok
if !tries! geq 90 (
    echo.
    echo  WARNING: Backend did not respond after 3 minutes.
    echo  Check logs with:  docker compose logs backend
    echo.
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

:: -- 4. Wait for Frontend (Next.js on :3000) ---------------------
echo [4/5] Waiting for Frontend to be ready...
set /a tries=0
:wait_frontend
set /a tries+=1
curl -sf http://localhost:3000/ >nul 2>&1
if %errorlevel% equ 0 goto frontend_ok
if !tries! geq 150 (
    echo.
    echo  WARNING: Frontend did not respond after 5 minutes.
    echo  Check logs with:  docker compose logs frontend
    echo.
    goto open_browsers
)
if !tries! equ 1   echo        Waiting for frontend...
if !tries! equ 30  echo        Still building... (1 min elapsed)
if !tries! equ 60  echo        Still building... (2 min elapsed)
if !tries! equ 90  echo        Still building... (3 min elapsed)
if !tries! equ 120 echo        Still building... (4 min elapsed)
timeout /t 2 /nobreak >nul
goto wait_frontend

:frontend_ok
echo        Frontend ready at http://localhost:3000
echo.

:: -- 5. Open browsers --------------------------------------------
:open_browsers
echo [5/5] Opening browser tabs...
timeout /t 1 /nobreak >nul
start "" "http://localhost:3000"
timeout /t 1 /nobreak >nul
start "" "http://localhost:5000"
timeout /t 1 /nobreak >nul
start "" "http://localhost:8025"

:: -- Done --------------------------------------------------------
echo.
echo  +------------------------------------------------------+
echo  ^|           All services are running!                  ^|
echo  +------------------------------------------------------+
echo  ^|  App          http://localhost:3000                  ^|
echo  ^|  API Docs     http://localhost:8000/docs             ^|
echo  ^|  MLflow       http://localhost:5000                  ^|
echo  ^|  Mailpit      http://localhost:8025                  ^|
echo  ^|  Ollama       http://localhost:11434                 ^|
echo  +------------------------------------------------------+
echo  ^|  docker compose logs -f           (stream all logs)  ^|
echo  ^|  docker compose logs -f backend   (backend only)     ^|
echo  ^|  docker compose down              (stop everything)  ^|
echo  +------------------------------------------------------+
echo.
pause
