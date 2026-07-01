@echo off
chcp 65001 >nul
title DeepResearch 一键启动

echo ========================================
echo   DeepResearch — AI 研究报告工作台
echo ========================================
echo.

:: 1. 检查 Docker 是否运行
echo [1/4] 检查 Docker 状态...
docker info >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [提示] Docker Desktop 未运行，正在尝试启动...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo 等待 Docker 启动（最多 60 秒）...
    timeout /t 10 /nobreak >nul
    :wait_docker
    docker info >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        timeout /t 5 /nobreak >nul
        goto wait_docker
    )
    echo Docker 已就绪
)
echo [ok] Docker 运行中

:: 2. 启动 MongoDB 和 Redis
echo.
echo [2/4] 启动 MongoDB 和 Redis...
docker compose -f docker-compose.services.yml up -d
if %ERRORLEVEL% NEQ 0 (
    echo [错误] Docker 服务启动失败
    pause
    exit /b 1
)
echo [ok] MongoDB (27017) 和 Redis (6379) 已启动

:: 3. 安装依赖
echo.
echo [3/4] 检查 Python 依赖...
where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 uv，请先安装: pip install uv
    pause
    exit /b 1
)
uv sync
echo [ok] 依赖已就绪

:: 4. 启动后端（前端内嵌在 FastAPI 中）
echo.
echo [4/4] 启动后端服务 (http://localhost:8000)...
echo.
echo ========================================
echo   启动完成！浏览器打开 http://localhost:8000
echo   按 Ctrl+C 停止服务
echo ========================================
echo.

:: 需要的话另开一个终端启动 Celery Worker
start "Celery Worker" cmd /c "uv run celery -A app.celery_app worker --loglevel=info -P solo"

:: 启动 FastAPI（当前终端）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
