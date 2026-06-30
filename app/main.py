from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config.config import Settings, get_settings
from app.routers import app as research_projects_router

# 项目根目录（main.py 的上一级目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例，负责注册基础路由和初始化启动日志。"""

    settings: Settings = get_settings()
    app: FastAPI = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )

    # CORS —— 允许本地前端页面跨域调用
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(research_projects_router, prefix=settings.api_prefix)


    @app.get("/health", tags=["系统"])
    async def health_check() -> dict[str, str]:
        """返回服务健康状态，用于本地调试、容器探针和部署检查。"""

        return {"status": "ok"}


    # 静态文件放在最后挂载，确保 API 路由优先匹配
    static_dir = PROJECT_ROOT / "static"
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app: FastAPI = create_app()

if __name__ == "__main__":
    import subprocess
    import sys
    import uvicorn

    # 后台启动 Celery Worker（Windows 用 CREATE_NEW_CONSOLE 开新窗口）
    celery_cmd = [sys.executable, "-m", "celery", "-A", "app.celery_app", "worker", "--loglevel=info", "-P", "solo"]
    if sys.platform == "win32":
        subprocess.Popen(celery_cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen(celery_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
