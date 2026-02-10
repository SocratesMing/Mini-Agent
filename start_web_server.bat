@echo off
REM Mini Agent Web Server Startup Script (Windows)

echo ========================================
echo   Mini Agent API Server
echo ========================================
echo.
echo   Swagger UI: http://localhost:8000/docs
echo   ReDoc:      http://localhost:8000/redoc
echo   Health:     http://localhost:8000/health
echo.
echo ========================================
echo.

REM Start server
python "%~dp0api_server.py"
