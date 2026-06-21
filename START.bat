@echo off
title KCG Jewellery Order System
color 0A

echo ==========================================
echo   KCG Jewellery Order System - Starting
echo ==========================================
echo.

:: Change to the app directory (edit this path to match your PC)
cd /d "%~dp0"

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found! Please install Python first.
    pause
    exit
)

:: Install dependencies if needed
echo Checking dependencies...
pip install -r requirements.txt -q

:: Create .env if it doesn't exist
if not exist .env (
    echo Creating .env file...
    copy .env.example .env
    echo.
    echo IMPORTANT: Please edit .env file with your MySQL password!
    echo Opening .env for editing...
    notepad .env
    pause
)

:: Create uploads folder
if not exist static\uploads mkdir static\uploads

echo.
echo Starting Flask server on port 5000...
echo.
echo App will be available at:
echo   Local:   http://localhost:5000
echo   Tablet:  Use Cloudflare Tunnel URL
echo.
echo Press Ctrl+C to stop the server
echo ==========================================
echo.

:: Start Flask
python -m flask run --host=0.0.0.0 --port=5000

pause
