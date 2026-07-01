@echo off
chcp 65001 >nul
title DeepResearch 一键停止

echo ========================================
echo   DeepResearch — 停止所有服务
echo ========================================
echo.

:: 1. 停止 Celery Worker
echo [1/3] 停止 Celery Worker...
taskkill /f /fi "WINDOWTITLE eq Celery Worker*" >nul 2>&1
echo [ok] Celery Worker 已停止

:: 2. 停止 Uvicorn (FastAPI)
echo [2/3] 停止后端服务...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo [ok] 后端服务已停止

:: 3. 停止 Docker 服务
echo [3/3] 停止 MongoDB 和 Redis...
docker compose -f docker-compose.services.yml down
echo [ok] Docker 服务已停止

echo.
echo ========================================
echo   所有服务已停止
echo ========================================
pause
