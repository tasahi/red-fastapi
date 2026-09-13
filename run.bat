@echo off
REM Launcher script for red-fastapi using anaconda fapi environment
echo Activating Anaconda environment 'fapi'...
call C:\Programs\Python3\Scripts\activate fapi
set PYTHONPATH=src
set PORT=%1
if "%PORT%"=="" set PORT=8000

echo Starting Red-Fastapi server at http://127.0.0.1:%PORT% ...
python -m uvicorn red_fastapi.main:app --host 127.0.0.1 --port %PORT% --reload
