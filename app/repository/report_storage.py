import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config.config import Settings, get_settings


@dataclass(frozen=True)
class StoredReportObject:
    """报告 HTML 存储结果。"""

    uri: str
    """存储 URI，例如 local://reports/{project_id}/v{version}-{report_id}.html"""

    path: str | None
    """文件系统绝对路径（MinIO 模式下为 None）"""

    size: int
    """HTML 内容的字节数"""


class ReportObjectStorage(Protocol):
    """报告 HTML 对象存储接口，后续可替换为 MinIO/S3 实现。"""

    async def save_html(
        self,
        project_id: str,
        report_id: str,
        version: int,
        html: str,
    ) -> StoredReportObject:
        """保存 HTML 并返回存储元数据。"""
        ...

    async def read_html(self, uri: str) -> str:
        """根据存储 URI 读取 HTML 内容。"""
        ...


class LocalReportObjectStorage:
    """本地文件系统报告存储。

    将报告 HTML 写入本地磁盘，目录结构为:
        {root_dir}/{project_id}/v{version}-{report_id}.html
    """

    def __init__(self, root_dir: str) -> None:
        self.root_dir = Path(root_dir)

    async def save_html(
        self,
        project_id: str,
        report_id: str,
        version: int,
        html: str,
    ) -> StoredReportObject:
        """保存 HTML 到本地文件系统。

        自动创建父目录，使用 asyncio.to_thread 包装同步 I/O 避免阻塞事件循环。
        """
        relative_path = Path(project_id) / f"v{version}-{report_id}.html"
        target_path = self.root_dir / relative_path
        await asyncio.to_thread(self._write_text, target_path, html)
        return StoredReportObject(
            uri=f"local://{self.root_dir.as_posix()}/{relative_path.as_posix()}",
            path=target_path.as_posix(),
            size=len(html.encode("utf-8")),
        )

    async def read_html(self, uri: str) -> str:
        """根据 local:// URI 从本地文件系统读取 HTML。"""
        path = self._path_from_uri(uri=uri)
        return await asyncio.to_thread(path.read_text, "utf-8")

    def _path_from_uri(self, uri: str) -> Path:
        """将 local:// URI 解析为文件系统路径。"""
        prefix = "local://"
        if not uri.startswith(prefix):
            raise ValueError(f"不支持的本地报告 URI: {uri}")
        path_text = uri.removeprefix(prefix)
        return Path(path_text)

    @staticmethod
    def _write_text(path: Path, html: str) -> None:
        """同步写入文件（由 asyncio.to_thread 调度）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")


class MinioReportObjectStorage:
    """MinIO / S3 兼容对象存储占位实现。

    当前为占位实现，待后续接入 minio-py 库后替换。
    """

    async def save_html(
        self,
        project_id: str,
        report_id: str,
        version: int,
        html: str,
    ) -> StoredReportObject:
        raise NotImplementedError("MinIO 报告存储尚未接入")

    async def read_html(self, uri: str) -> str:
        raise NotImplementedError("MinIO 报告存储尚未接入")


def get_report_object_storage() -> ReportObjectStorage:
    """根据配置返回报告 HTML 对象存储实现。

    通过 settings.report_storage_backend 控制:
        - "local"  → LocalReportObjectStorage（本地文件系统）
        - "minio"  → MinioReportObjectStorage（占位，抛 NotImplementedError）
    """

    settings: Settings = get_settings()
    if settings.report_storage_backend == "local":
        return LocalReportObjectStorage(root_dir=settings.report_storage_local_dir)
    if settings.report_storage_backend == "minio":
        return MinioReportObjectStorage()
    raise ValueError(f"不支持的报告存储后端: {settings.report_storage_backend}")
