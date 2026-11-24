@echo off
title Olist Jupyter Notebook
echo ============================================
echo   Olist Analysis Notebook
echo ============================================
echo.
echo Jupyter notebook start ho raha hai...
echo (Browser khud khulega - band karne ke liye is
echo  black window mein Ctrl+C dabao ya window close karo)
echo.
cd /d "%~dp0notebooks"
python -m jupyter notebook 01_olist_analysis.ipynb
pause
