

基于多智能体协作的企业级 AI 研究报告自动生成系统。输入研究主题后，系统自动完成：**大纲设计 → 信息检索 → 逐章节撰写 → HTML 报告渲染** 的全流程。

## 核心特性

- 🧠 **多智能体协作**：研究管理 Agent 协调信息检索子 Agent，分工明确
- 📋 **智能大纲生成**：自动分析主题，生成结构化研究大纲（支持用户修改）
- 🔍 **多源信息检索**：Tavily 互联网搜索 + RAGFlow 内部知识库 + 网页内容读取
- 📝 **逐章节撰写**：Agent 逐章检索事实、构建证据链、输出完整正文
- 🎨 **HTML 报告渲染**：Markdown → 精美 HTML 报告，带目录、引用标注、来源列表
- ⚡ **异步任务架构**：FastAPI + Celery + Redis，前端轮询进度，不阻塞用户操作
- 🔌 **LLM 可替换**：支持 OpenAI / DeepSeek 等兼容接口，一键切换

---

## 系统架构

```
mermaid
graph TB
    User["🖥️ 用户浏览器"]
    Frontend["📄 前端 SPA<br/>static/index.html"]
    FastAPI["⚡ FastAPI 服务<br/>app/main.py"]
    Redis["📨 Redis 消息队列<br/>:6380"]
    Worker["🔧 Celery Worker<br/>app/background/"]
    MongoDB["🗄️ MongoDB<br/>:27017"]

    Manager["🧠 研究管理 Agent<br/>research_manager.md"]
    SearchAgent["🔍 信息检索子 Agent<br/>search_agent.md"]

    Tavily["🌐 Tavily<br/>互联网搜索"]
    RAGFlow["📚 RAGFlow<br/>内部知识库"]
    WebRead["📖 网页读取"]
    DeepSeek["🤖 DeepSeek LLM"]

    User --> Frontend
    Frontend -->|"REST API"| FastAPI
    FastAPI -->|"投递任务"| Redis
    Redis -->|"分发任务"| Worker
    FastAPI -->|"读写数据"| MongoDB
    Worker -->|"持久化结果"| MongoDB
    Worker --> Manager
    Manager -->|"委托检索"| SearchAgent
    Manager --> DeepSeek
    SearchAgent --> Tavily
    SearchAgent --> RAGFlow
    SearchAgent --> WebRead
    SearchAgent --> DeepSeek
```
---

## 用户使用流程

```
mermaid
flowchart LR
    A["📝 创建项目<br/>填写主题/目标/受众"] --> B["⏳ 等待大纲生成<br/>Celery 后台执行"]
    B --> C["📋 审阅大纲"]
    C --> D{满意?}
    D -->|"✅ 确认"| E["🚀 提交报告生成"]
    D -->|"✏️ 修改"| F["提交修改意见"]
    F --> B
    E --> G["⏳ 等待报告生成<br/>Agent 逐章节研究+撰写"]
    G --> H["📊 查看 HTML 报告"]
```
---

## Agent 内部研究流程

```
mermaid
flowchart TB
    subgraph 大纲阶段
        A1["理解研究主题"] --> A2["生成 Research Brief"]
        A2 --> A3["设计 3~4 章节大纲"]
        A3 --> A4["校验 JSON 输出"]
    end

    subgraph 研究阶段
        B1["读取已确认大纲"] --> B2["逐章节拆解检索问题"]
        B2 --> B3["委托信息检索子 Agent"]
        B3 --> B4["收集事实卡片 + 来源"]
        B4 --> B5["撰写章节完整正文"]
        B5 --> B6["构建证据链<br/>evidence_chain"]
        B6 --> B7["save_research_section<br/>保存到 MongoDB"]
        B7 --> B8{所有章节完成?}
        B8 -->|"否，下一章"| B2
        B8 -->|"是"| B9["渲染 HTML 报告"]
    end

    A4 --> B1
```
---

## 技术栈

| 层面 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | 异步高性能 API 服务 |
| 异步任务 | Celery + Redis | 后台任务队列，解耦耗时操作 |
| 数据库 | MongoDB 7.0 | 文档型存储，灵活 Schema |
| AI Agent | DeepAgents (LangChain + LangGraph) | 多智能体编排 |
| LLM | DeepSeek / OpenAI | 可切换的大模型提供商 |
| 外部搜索 | Tavily Search API | 互联网实时搜索 |
| 知识库 | RAGFlow（可选） | 企业内部知识库检索 |
| 前端 | 原生 HTML + CSS + JS | 零依赖单页应用 |
| 包管理 | uv | 极速 Python 包管理器 |
| 容器化 | Docker Compose | MongoDB + Redis 一键部署 |

---

## 环境要求

| 软件 | 最低版本 | 说明 |
|------|---------|------|
| Python | ≥ 3.12 | 后端运行环境 |
| Docker Desktop | 最新版 | 运行 MongoDB + Redis |
| uv | 最新版 | Python 包管理器（`pip install uv`） |
| DeepSeek API Key | — | LLM 调用凭证 |

---

## 快速开始

### 1. 克隆项目

```
bash
git clone <your-repo-url>
cd DeepResearch
```
### 2. 配置环境变量

```
bash
# 复制环境变量模板
cp .env.example .env
```
编辑 `.env`，必填项：

```
env
# LLM 配置（必填，二选一）
LLM_PROVIDER=deepseek
LLM_MODEL_NAME=deepseek-chat
DEEPSEEK_API_KEY=sk-your-key-here

# 外部搜索（可选，不填则跳过联网搜索）
# TAVILY_API_KEY=tvly-xxxxxxxx
```
完整配置项参考 [配置说明](#配置参考)。

### 3. 一键启动

**Windows：**
```
powershell
.\start.bat
```
**Linux / macOS：**
```
bash
bash start.sh
```
启动脚本会自动完成：
1. 检查并启动 Docker Desktop
2. 启动 MongoDB（:27017）和 Redis（:6380）
3. 安装 Python 依赖
4. 启动 Celery Worker（后台）
5. 启动 FastAPI 服务（前台，:8000）

### 4. 手动启动（分步调试）

```
bash
# 1. 安装依赖
uv sync

# 2. 启动基础设施
docker compose -f docker-compose.services.yml up -d

# 3. 启动 Celery Worker（另开终端）
uv run celery -A app.celery_app worker --loglevel=info -P solo

# 4. 启动 FastAPI
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
### 5. 访问

浏览器打开 **http://localhost:8000**

---

## 项目结构

```

DeepResearch/
├── app/
│   ├── main.py                      # FastAPI 应用入口
│   ├── celery_app.py                # Celery 实例配置
│   ├── config/
│   │   └── config.py                # 配置管理（pydantic-settings）
│   ├── routers/
│   │   └── __init__.py              # 7 个 REST API 端点
│   ├── schemas/
│   │   └── __init__.py              # Pydantic 数据模型 + 枚举
│   ├── agents/
│   │   ├── research_agent.py        # 研究管理 Agent 封装
│   │   └── prompts/
│   │       ├── research_manager.md  # 管理 Agent System Prompt
│   │       └── search_agent.md      # 检索子 Agent System Prompt
│   ├── background/
│   │   ├── celery_tasks.py          # @celery_app.task 任务注册
│   │   └── research_tasks.py        # 任务业务逻辑实现
│   ├── repository/
│   │   ├── mongodb.py               # MongoDB 连接池管理
│   │   ├── research_project_repository.py  # 项目 CRUD
│   │   ├── research_task_repository.py     # 任务状态 CRUD
│   │   ├── report_repository.py            # 报告版本管理
│   │   └── report_storage.py               # HTML 对象存储
│   └── tools/
│       ├── external_search.py       # Tavily 互联网搜索
│       ├── ragflow_search.py        # RAGFlow 知识库检索
│       ├── web_pag_read.py          # 网页正文读取
│       ├── render_html.py           # Markdown → HTML 渲染
│       ├── research_agent_tool.py   # 章节保存验证工具
│       └── storage_toll.py          # 报告存储兼容层
├── static/
│   └── index.html                   # 前端 SPA（~700 行）
├── data/                            # Docker 数据卷挂载目录
│   ├── mongo/                       # MongoDB 持久化数据
│   └── redis/                       # Redis 持久化数据
├── docker-compose.services.yml      # MongoDB + Redis 容器编排
├── start.bat                        # Windows 一键启动
├── start.sh                         # Linux/macOS 一键启动
├── stop.bat / stop.sh               # 停止脚本
├── pyproject.toml                   # 项目依赖配置
├── .env.example                     # 环境变量模板
└── README.md
```
---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/v1/research-projects` | 创建研究项目，触发大纲生成 |
| `GET` | `/api/v1/research-projects/{id}/outline` | 获取大纲草案 |
| `PUT` | `/api/v1/research-projects/{id}/outline` | 确认大纲 或 提交修改指令 |
| `POST` | `/api/v1/research-projects/{id}/report-tasks` | 提交报告生成任务 |
| `GET` | `/api/v1/tasks/{task_id}` | 查询异步任务状态 |
| `GET` | `/api/v1/research-projects/{id}/reports/latest` | 获取最新 HTML 报告 |

---

## 使用示例

### 创建研究项目

```
bash
curl -X POST http://localhost:8000/api/v1/research-projects \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "量子计算在金融风险建模中的应用",
    "research_goal": "分析技术进展、应用案例和发展趋势",
    "target_audience": "金融科技从业者",
    "region_scope": "global",
    "time_scope": {"type": "recent_years", "years": 3}
  }'
```
响应：
```
json
{
  "project_id": "d56fe00d-bb94-4098-9351-61b6e29ee677",
  "initial_task_id": "c94e2b09-a98a-4347-8b00-1f494f09a45e",
  "initial_task_type": "generate_research_brief",
  "topic": "量子计算在金融风险建模中的应用",
  "status": "brief_generating",
  "next_step": "wait_for_outline"
}
```
### 轮询任务状态

```
bash
curl http://localhost:8000/api/v1/tasks/c94e2b09-a98a-4347-8b00-1f494f09a45e
```
### 确认大纲后触发报告生成

```
bash
curl -X POST http://localhost:8000/api/v1/research-projects/{id}/report-tasks \
  -H "Content-Type: application/json" \
  -d '{
    "user_instruction": "请重点关注量子算法在风险价值(VaR)计算中的应用"
  }'
```
---

## 配置参考

`.env` 文件完整配置项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `deepseek` | LLM 提供商：`openai` / `deepseek` |
| `LLM_MODEL_NAME` | `deepseek-chat` | 模型名称 |
| `LLM_TEMPERATURE` | `0.2` | 生成温度 (0.0~2.0) |
| `DEEPSEEK_API_KEY` | — | **必填**，DeepSeek API Key |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com/v1` | DeepSeek API 地址 |
| `OPENAI_API_KEY` | — | OpenAI API Key（如使用 OpenAI） |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB 连接串 |
| `MONGODB_DATABASE` | `deep_research` | 数据库名 |
| `REDIS_URL` | `redis://localhost:6380/0` | Redis 连接串 |
| `TAVILY_API_KEY` | — | Tavily 搜索 API Key（可选） |
| `RAGFLOW_BASE_URL` | — | RAGFlow 服务地址（可选） |
| `RAGFLOW_API_KEY` | — | RAGFlow API Key（可选） |
| `LANGSMITH_TRACING` | `false` | 是否启用 LangSmith 追踪 |

---

## 常用命令

```
bash
# 停止所有服务
docker compose -f docker-compose.services.yml down

# 查看 Celery Worker 日志（另一个终端窗口）
# Windows 的 start.bat 已自动打开

# 查看 MongoDB 数据（推荐使用 DataGrip 连接 localhost:27017）

# 重新安装依赖
uv sync --reinstall

# 运行测试
uv run pytest
```
---

## 常见问题

### Docker Desktop 未运行

`start.bat` 会自动尝试启动 Docker Desktop。如果失败，请手动打开 Docker Desktop 后重试。

### Celery Worker 启动失败

检查 Redis 是否正常运行：
```
bash
docker ps | grep redis
```
### LLM API Key 配置错误

确保 `.env` 中的 `DEEPSEEK_API_KEY` 正确，且 `LLM_PROVIDER` 与 API Key 类型匹配。
