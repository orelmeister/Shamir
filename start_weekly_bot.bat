@echo off
REM Weekly Bot Startup Script - Modular Orchestrator Menu
REM Updated for new modular architecture (Nov 2025)

:MENU
cls
echo ================================================
echo    WEEKLY TRADING BOT - MODULAR SYSTEM
echo ================================================
echo.
echo Select execution mode:
echo.
echo [1] Full Cycle (Aggregation + Analysis + Rebalance + Monitor)
echo     - Complete workflow from data collection to monitoring
echo     - Use on Monday or when you need fresh data
echo.
echo [2] Quick Start (Skip Aggregation)
echo     - Reuse existing full_market_data.json
echo     - Run Analysis + Rebalance + Monitor
echo     - Saves ~3 minutes if data is fresh
echo.
echo [3] Analysis Only
echo     - Run LLM analysis only
echo     - No trading or monitoring
echo.
echo [4] Rebalance Only
echo     - Execute portfolio rebalancing
echo     - Requires existing analysis results
echo.
echo [5] Monitor Only
echo     - Start position monitoring daemon
echo     - Monitors existing positions
echo.
echo [6] Legacy Mode (Old main.py)
echo     - Run original monolithic system
echo     - Fallback option if needed
echo.
echo [7] Exit
echo.
echo ================================================
set /p choice="Enter your choice (1-7): "

if "%choice%"=="1" goto FULL_CYCLE
if "%choice%"=="2" goto QUICK_START
if "%choice%"=="3" goto ANALYSIS_ONLY
if "%choice%"=="4" goto REBALANCE_ONLY
if "%choice%"=="5" goto MONITOR_ONLY
if "%choice%"=="6" goto LEGACY
if "%choice%"=="7" goto END

echo Invalid choice. Please try again.
timeout /t 2 >nul
goto MENU

:FULL_CYCLE
cls
echo ================================================
echo Starting FULL CYCLE (All 4 Phases)
echo ================================================
echo Running: weekly_orchestrator.py (Option 1)
echo.
call .\.venv-weekly\Scripts\activate.bat
echo 1 | python weekly_orchestrator.py
goto END

:QUICK_START
cls
echo ================================================
echo Starting QUICK START (Skip Aggregation)
echo ================================================
echo Running: weekly_orchestrator.py (Option 2)
echo.
call .\.venv-weekly\Scripts\activate.bat
echo 2 | python weekly_orchestrator.py
goto END

:ANALYSIS_ONLY
cls
echo ================================================
echo Starting ANALYSIS ONLY
echo ================================================
echo Running: weekly_orchestrator.py (Option 3)
echo.
call .\.venv-weekly\Scripts\activate.bat
echo 3 | python weekly_orchestrator.py
goto END

:REBALANCE_ONLY
cls
echo ================================================
echo Starting REBALANCE ONLY
echo ================================================
echo Running: weekly_orchestrator.py (Option 4)
echo.
call .\.venv-weekly\Scripts\activate.bat
echo 4 | python weekly_orchestrator.py
goto END

:MONITOR_ONLY
cls
echo ================================================
echo Starting MONITOR ONLY
echo ================================================
echo Running: weekly_orchestrator.py (Option 5)
echo.
call .\.venv-weekly\Scripts\activate.bat
echo 5 | python weekly_orchestrator.py
goto END

:LEGACY
cls
echo ================================================
echo Starting LEGACY MODE (Original main.py)
echo ================================================
echo Warning: Using old monolithic system
echo.
call .\.venv-weekly\Scripts\activate.bat
python main_legacy.py --force-online
goto END

:END
echo.
echo ================================================
echo Weekly Bot execution completed
echo Check logs\ directory for details
echo ================================================
pause
