@echo off
REM Launcher script for fastapi-red using anaconda fapi environment
echo Activating Anaconda environment 'fapi'...
call C:\Programs\Python3\Scripts\activate fapi
set PYTHONPATH=src
echo Starting FastAPI-Red server at http://127.0.0.1:8000 ...
python -m uvicorn fastapi_red.main:app --host 127.0.0.1 --port 8000 --reload

