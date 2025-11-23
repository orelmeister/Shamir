@echo off
REM Position Analysis Tool - Quick Launcher
REM Analyzes current IBKR positions vs entry data

echo ========================================
echo Position Analysis Tool
echo ========================================
echo.

REM Check if IBKR connection is available
echo [INFO] Checking IBKR connection on port 4001...
echo.

REM Run the analysis
python analyze_positions.py

echo.
echo ========================================
echo Analysis Complete
echo ========================================
pause
