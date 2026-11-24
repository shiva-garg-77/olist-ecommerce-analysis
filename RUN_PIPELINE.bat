@echo off
title Olist Pipeline Runner
echo ============================================================
echo   E-commerce Analysis - Full Pipeline
echo ============================================================
echo.
echo Step 1/4: Data cleaning + master table + SQLite
python -m src.etl
if errorlevel 1 goto :error

echo.
echo Step 2/4: SQL queries (13 queries)
python -m src.sql_analysis
if errorlevel 1 goto :error

echo.
echo Step 3/4: Charts + RFM + Cohort + Pareto
python -m src.analysis
if errorlevel 1 goto :error

echo.
echo Step 4/4: Dashboard build
python -m dashboard.build_dashboard
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   DONE! Dashboard browser mein khul raha hai...
echo ============================================================
start "" "%~dp0dashboard\olist_dashboard.html"
pause
exit

:error
echo.
echo ============================================================
echo   ERROR! Upar wala message padho.
echo   Tip: kya aap project folder ke andar ho?
echo ============================================================
pause
