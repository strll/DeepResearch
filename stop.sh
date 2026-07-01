#!/bin/bash

echo "========================================"
echo "  DeepResearch — 停止所有服务"
echo "========================================"
echo ""

# 1. 停止 Celery Worker
echo "[1/3] 停止 Celery Worker..."
pkill -f "celery.*worker" 2>/dev/null && echo "[ok] Celery Worker 已停止" || echo "[跳过] Celery Worker 未运行"

# 2. 停止 Uvicorn (FastAPI)
echo "[2/3] 停止后端服务..."
pkill -f "uvicorn.*app.main" 2>/dev/null && echo "[ok] 后端服务已停止" || echo "[跳过] 后端服务未运行"

# 3. 停止 Docker 服务
echo "[3/3] 停止 MongoDB 和 Redis..."
docker compose -f docker-compose.services.yml down
echo "[ok] Docker 服务已停止"

echo ""
echo "========================================"
echo "  所有服务已停止"
echo "========================================"
