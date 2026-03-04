@echo off
TITLE Quantix Multi-Agent System v4.0
echo ============================================================
echo 🌌 QUANTIX MULTI-AGENT V4.0 - LOCAL ORCHESTRATOR
echo ============================================================
echo.
echo [1/3] Checking environment...
if not exist .env (
    echo [ERR] .env file not found! Please copy .env.example to .env and fill it.
    pause
    exit /b
)

echo [2/3] Setting PYTHONPATH...
set PYTHONPATH=.

echo [3/3] Starting All Agents and Web API...
echo Dashboard will be available at: http://localhost:8000
echo.
echo Press Ctrl+C to shutdown all services safely.
echo ------------------------------------------------------------

python start_quantix.py

pause
