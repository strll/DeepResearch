"""
TODO: 【高优先级】实现完整的报告 HTML 对象存储
参照: app/repository/report_storage.py (参考项目)
当前状态: 空存根，无法将生成的 HTML 报告持久化到磁盘或对象存储

需要实现的功能:
1. 创建 app/repository/report_storage.py 文件:
   - StoredReportObject 数据类 (uri, path, size)
   - ReportObjectStorage Protocol 接口
   - LocalReportObjectStorage: 本地文件系统实现
   - MinioReportObjectStorage: MinIO/S3 实现（可先做占位）
   - get_report_object_storage() 工厂函数

2. LocalReportObjectStorage:
   - save_html(project_id, report_id, version, html) -> StoredReportObject
     * 路径: {root_dir}/{project_id}/v{version}-{report_id}.html
     * uri格式: local://{root_dir}/{project_id}/v{version}-{report_id}.html
   - read_html(uri) -> str: 从本地路径读取 HTML 内容
   - 自动创建父目录

3. MinioReportObjectStorage (占位):
   - save_html / read_html 先抛 NotImplementedError
   - 后续接入 minio-py 库

4. 配置驱动:
   - report_storage_backend: "local" | "minio"
   - report_storage_local_dir: 本地存储根目录 (默认 "reports")
"""


async def save_report_html_to_file(html: str) -> str:
    """
    把html保存到对象存储中  返回uri信息

    TODO: 替换为 get_report_object_storage().save_html() 调用
    TODO: 需要 project_id, report_id, version 参数
    TODO: 返回 StoredReportObject.uri 而非直接返回字符串
    """
    # TODO: 实现步骤:
    #   1. from app.repository.report_storage import get_report_object_storage
    #   2. storage = get_report_object_storage()
    #   3. stored = await storage.save_html(project_id, report_id, version, html)
    #   4. return stored.uri
    pass
