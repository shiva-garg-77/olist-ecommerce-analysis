@echo off
title Olist Pipeline Runner
echo ============================================================
echo   E-commerce Analysis - Full Pipeline
echo ============================================================
echo.

echo Step 1/5: Dataset download (skipped if data already present)
if not exist "data\raw\olist_orders_dataset.csv" (
    python -m src.download_data
    if errorlevel 1 goto :error
) else (
    echo   data\raw\ already has the 9 CSVs - skipping download
)

echo.
echo Step 2/5: Data cleaning + master table + SQLite
python -m src.etl
if errorlevel 1 goto :error

echo.
echo Step 3/5: SQL queries (13 queries)
python -m src.sql_analysis
if errorlevel 1 goto :error

echo.
echo Step 4/5: Charts + RFM + Cohort + Pareto
python -m src.analysis
if errorlevel 1 goto :error

echo.
echo Step 5/5: Dashboard build
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
echo   Sabse common reason: Python installed nahi hai ya
echo   "pip install -r requirements.txt" nahi chalaya.
echo ============================================================
pause
