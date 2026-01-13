@echo off
REM Form 4 Insider Strategy - Weekly Runner
REM Run every Sunday at 8:00 PM

echo ================================================================================
echo FORM 4 INSIDER CLUSTER STRATEGY - WEEKLY ANALYSIS
echo ================================================================================
echo.
echo Time: %date% %time%
echo.

set /p USER_CAPITAL=Enter capital (blank = use ALL buying power): 

if "%USER_CAPITAL%"=="" (
	set RUN_ARGS=--use-buying-power
	rem Escape parentheses inside code blocks to avoid breaking the IF/ELSE
	echo Using full buying power ^(ExcessLiquidity^)
) else (
	rem Quote the value to pass cleanly to argparse
	set RUN_ARGS=--capital "%USER_CAPITAL%"
	echo Using explicit capital: $%USER_CAPITAL%
)
echo.

cd /d "C:\Users\orelm\OneDrive\Documents\GitHub\trade"

REM Activate virtual environment and run strategy
call .venv-weekly\Scripts\activate.bat
python weekly_bot\05_form4_strategy.py %RUN_ARGS%

echo.
echo ================================================================================
echo Form 4 analysis complete. Check form4_strategy\ folder for results.
echo ================================================================================
echo.

pause
