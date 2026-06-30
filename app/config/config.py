from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AnyUrl, BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _empty_str_to_none(v: object) -> object:
    """将空字符串转换为 None，避免 AnyUrl 等类型校验失败。"""
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


#: 项目根目录（基于本文件位置推算：app/config/config.py → 上三级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_dotenv_to_os() -> None:
    """手动把 .env 文件内容注入到 os.environ。

    langchain / deepagents 内部通过 os.environ 读取 API Key，
    而 pydantic-settings 的 env_file 只会加载到自身 model 中，
    不会注入系统环境变量，因此需要额外加载一次。
    """
    import os

    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


#: 可选 URL 类型 —— 当环境变量为空字符串时自动转为 None
OptionalUrl = Annotated[AnyUrl | None, BeforeValidator(_empty_str_to_none)]


class Settings(BaseSettings):
    """系统配置对象，负责从环境变量读取后端运行所需的基础配置。

    输入来自默认值、环境变量和项目根目录的 ``.env`` 文件；输出为业务模块可
    直接读取的类型化配置。该类只维护基础设施和模型参数，不保存任何业务状态。

    所有字段均可通过大写环境变量覆盖，例如 ``MONGODB_URI`` 对应
    ``mongodb_uri``。``.env`` 文件中的空值会被安全地解析为 ``None``。
    """
    total_retry_times: int = 5
    app_name: str = "AI 研究报告工作台"
    app_version: str = "0.1.0"
    environment: str = "local"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "deep_research"
    redis_url: str = "redis://localhost:6380/0"
    celery_broker_url: str | None = None

    llm_provider: str = "deepseek"
    llm_model_name: str = "deepseek-v4-flash"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    openai_api_base: OptionalUrl = None
    openai_api_key: str | None = None
    deepseek_api_base: OptionalUrl = "https://api.deepseek.com/v1"
    deepseek_api_key: str = Field(default="")
    enable_ragflow: bool = False
    ragflow_base_url: OptionalUrl = None
    ragflow_api_key: str | None = None
    ragflow_default_dataset_ids: str | None = None
    tavily_api_key: str | None = None

    object_storage_endpoint: str | None = None
    object_storage_bucket: str = "deep-research"
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    report_storage_backend: str = "local"
    report_storage_local_dir: str = "reports"
    external_search_timeout: int = 30

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取系统配置，负责为应用生命周期提供缓存后的配置对象。

    该函数没有输入参数，返回当前进程内唯一的 Settings 实例，避免每次请求重复读取
    环境变量和 `.env` 文件。
    """

    _load_dotenv_to_os()
    return Settings()
