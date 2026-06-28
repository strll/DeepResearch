# ============================================================================
# Celery 简介
# ============================================================================
# Celery 是 Python 生态中最成熟的分布式异步任务队列框架。
# 它的核心思想是：将耗时操作（如 AI 研究、报告生成）从 Web 请求中剥离出来，
# 交给独立的后台 Worker 进程异步执行，从而避免阻塞 API 响应。
#
# 核心架构（三要素）：
#   ┌──────────┐       ┌──────────────┐       ┌──────────┐
#   │ Producer │──────▶│   Broker     │──────▶│  Worker  │
#   │ (API端)  │ 投递   │ (消息代理)    │ 分发   │ (消费端)  │
#   └──────────┘       └──────────────┘       └──────────┘
#
# - Producer（生产者）：即 FastAPI 接口，调用 task.delay() 或 task.apply_async()
#   将任务消息序列化后发送到 Broker。
# - Broker（消息代理）：负责存储和分发任务消息，常用 Redis 或 RabbitMQ。
#   本项目使用 Redis 作为 Broker。
# - Worker（消费者）：独立的后台进程，从 Broker 中拉取任务并执行。
#   启动命令示例：celery -A app.celery_app worker --loglevel=info
#
# 在本项目中的使用流程：
#   1. API 接收到用户请求（如创建研究项目）后，将耗时任务投递到 Broker；
#   2. API 立即返回任务 ID 给前端，前端通过轮询 /tasks/{task_id} 获取进度；
#   3. Worker 从 Broker 取出任务，执行 AI 研究、大纲生成、报告渲染等逻辑；
#   4. Worker 将执行结果写入 MongoDB，前端轮询时即可读到最新状态。
#
# 相关模块：
#   - app.background.celery_tasks : 定义 @celery_app.task 装饰的后台任务函数
#   - app.background.research_tasks : 实际的业务逻辑实现（AI Agent 调用等）
# ============================================================================

from celery import Celery

from app.config.config import Settings, get_settings


def create_celery_app() -> Celery:
    """创建 Celery 应用实例，供 API 进程投递任务和 worker 进程消费任务。"""

    # 加载项目配置
    settings: Settings = get_settings()

    # 初始化 Celery 实例
    # - broker: 消息代理地址，优先使用 celery_broker_url，否则回退到 redis_url
    # - include: 自动导入包含任务定义的模块，使 worker 启动时能发现并注册任务
    app = Celery(
        "deep_research",
        broker=settings.celery_broker_url or settings.redis_url,
        # backend="",
        include=["app.background.celery_tasks"],
    )

    # Celery 配置项说明：
    # - broker_connection_retry_on_startup: 启动时自动重试连接 broker，避免因 broker 短暂不可用导致启动失败
    # - task_acks_late: 任务执行完毕后才确认（ack），确保 worker 异常崩溃时任务能被重新分配
    # - task_reject_on_worker_lost: worker 进程被杀死时将任务拒绝回队列，配合 acks_late 保证任务不丢失
    # - task_track_started: 记录任务 "已启动" 状态，方便在前端或监控中查看任务执行进度
    # - worker_prefetch_multiplier: 每个 worker 每次只预取 1 个任务，适用于长时间运行的研究任务，避免任务分配不均
    # - timezone: 设置时区为亚洲/上海，确保定时任务（如 crontab）按北京时间执行
    app.conf.update(
        broker_connection_retry_on_startup=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        timezone="Asia/Shanghai",
    )
    return app


# 创建全局 Celery 实例，供整个应用使用：
# - API 端通过该实例发送（delay/apply_async）任务到 broker
# - Worker 进程通过该实例消费并执行任务
#
# 使用示例（在 celery_tasks.py 中定义任务）：
#   @celery_app.task
#   def generate_outline(task_id: str, project_id: str):
#       ...
#
# 使用示例（在 API 路由中投递任务）：
#   from app.celery_app import celery_app
#   celery_app.send_task("app.background.celery_tasks.generate_outline", args=[task_id, project_id])
#   或者：generate_outline.delay(task_id, project_id)
celery_app = create_celery_app()
