#!/bin/bash
set -e

echo "========================================"
echo "  DeepResearch — AI 研究报告工作台"
echo "========================================"
echo ""

# 1. 检查 Docker
echo "[1/4] 检查 Docker 状态..."
if ! docker info > /dev/null 2>&1; then
    echo "[错误] Docker 未运行，请先启动 Docker Desktop"
    exit 1
fi
echo "[ok] Docker 运行中"

# 2. 启动 MongoDB 和 Redis
echo ""
echo "[2/4] 启动 MongoDB 和 Redis..."
docker compose -f docker-compose.services.yml up -d
echo "[ok] MongoDB (27017) 和 Redis (6379) 已启动"

# 3. 安装依赖
echo ""
echo "[3/4] 检查 Python 依赖..."
if ! command -v uv &> /dev/null; then
    echo "[错误] 未找到 uv，请先安装: pip install uv"
    exit 1
fi
uv sync
echo "[ok] 依赖已就绪"

# 4. 启动后端
echo ""
echo "[4/4] 启动后端服务 (http://localhost:8000)..."
echo ""
echo "========================================"
echo "  启动完成！浏览器打开 http://localhost:8000"
echo "  按 Ctrl+C 停止服务"
echo "========================================"
echo ""

# 后台启动 Celery Worker
uv run celery -A app.celery_app worker --loglevel=info -P solo &
CELERY_PID=$!
trap "kill $CELERY_PID 2>/dev/null; exit 0" INT TERM

# 前台启动 FastAPI
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

kill $CELERY_PID 2>/dev/null
