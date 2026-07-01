import json
import time
from datetime import datetime, date
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends.utils import create_file_data
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from loguru import logger
from pydantic import BaseModel, Field

from app.config.config import get_settings
from app.repository import research_project_repository
from app.repository.research_project_repository import get_outline, get_confirmed_outline
from app.tools.web_pag_read import read_web_page
from app.tools.external_search import external_search
from app.tools.ragflow_search import ragflow_search
from app.tools.research_agent_tool import save_research_sections


class ResearchBrief(BaseModel):
    topic: str
    research_goal: str
    target_audience: str
    scope_summary: str
    key_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class FactCard(BaseModel):
    fact_id: str
    statement: str
    source_ids: list[str] = Field(default_factory=list)


class ResearchSection(BaseModel):
    section_id: str
    title: str
    summary: str
    body: str
    evidence_chain: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)


class ResearchResult(BaseModel):
    title: str
    sections: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    fact_cards: list[dict] = Field(default_factory=list)
    insight_cards: list[dict] = Field(default_factory=list)


class ReportResult(BaseModel):
    title: str
    html: str
    sources: list[dict] = Field(default_factory=list)
    fact_cards: list[dict] = Field(default_factory=list)
    insight_cards: list[dict] = Field(default_factory=list)


class ResearchAgent:

    def __init__(self, manager_agent):
        self.manager_agent: CompiledStateGraph = manager_agent
        self._step_counter = 0

    # ========================================================================
    #  思考过程展示
    # ========================================================================

    def _reset_step_counter(self):
        """每次新任务调用前重置步骤计数器。"""
        self._step_counter = 0

    def _next_step(self) -> int:
        self._step_counter += 1
        return self._step_counter

    def _log_thinking_process(self, messages: list, tag: str = "Agent") -> None:
        """遍历 ainvoke 返回的 messages，打印 LLM 完整思考过程。

        LangGraph 的 StateGraph 在执行过程中会将每一步交互都追加到 messages 列表中，
        包括：用户输入、AI 思考/回复、工具调用请求、工具执行结果、子智能体消息等。
        此方法遍历并结构化输出这些消息，使开发者可以追溯智能体的每一步决策。
        """
        for i, msg in enumerate(messages):
            if isinstance(msg, HumanMessage):
                content = self._truncate(msg.content, 200)
                logger.info("[{}:步骤{}] 👤 用户输入: {}", tag, self._next_step(), content)

            elif isinstance(msg, AIMessage):
                # AI 的文本回复（推理/规划/总结）
                if msg.content:
                    content = self._truncate(str(msg.content), 300)
                    logger.info("[{}:步骤{}] 🤖 AI 思考: {}", tag, self._next_step(), content)

                # AI 发起的工具调用
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc.get("name", "unknown")
                        tool_args = self._truncate(json.dumps(tc.get("args", {}), ensure_ascii=False), 200)
                        logger.info("[{}:步骤{}] 🔧 调用工具: {}，参数={}", tag, self._next_step(), tool_name, tool_args)

            elif isinstance(msg, ToolMessage):
                # 工具执行结果
                result_preview = self._truncate(str(msg.content), 200)
                logger.info("[{}:步骤{}] 📋 工具返回 ({}): {}", tag, self._next_step(), msg.name, result_preview)

    async def _invoke_and_log(self, input_data: dict, config: dict, tag: str = "Agent"):
        """调用 agent 并自动打印思考过程。

        封装 ainvoke，在返回前将所有 messages 通过 _log_thinking_process 输出，
        同时对整体耗时进行汇总日志。
        """
        logger.info("[{}] ═══ 开始执行任务 ═══", tag)
        t0 = time.perf_counter()
        result = await self.manager_agent.ainvoke(input_data, config)
        elapsed = time.perf_counter() - t0

        messages = result.get("messages", [])
        self._log_thinking_process(messages, tag=tag)
        logger.info("[{}] ═══ 任务执行完成，总消息数={}，总耗时={:.1f}s ═══", tag, len(messages), elapsed)
        return result

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """截断过长文本用于日志展示。"""
        if not text or len(text) <= max_len:
            return str(text) if text else ""
        return str(text)[:max_len] + f"...(共{len(text)}字符)"

    # ========================================================================
    #  业务方法
    # ========================================================================

    async def generate_outline(self, project_id: str, research_project, task_id):
        self._reset_step_counter()
        payload = {
            "task_name": "generate_research_brief",
            "project": research_project,
            "expected_output": "ResearchBriefResult",
        }
        task_json = _safe_json_dumps(payload)
        logger.info("[Agent.大纲] 开始调用 LLM，topic={}，payload_size={} chars",
                    research_project.get("topic", "未知"), len(task_json))

        result = await self._invoke_and_log(
            input_data={
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "请执行 /research/task_payload.json 中的研究任务。"
                            "只生成 3~4 个章节的简洁大纲，每个章节一个核心问题即可。"
                            "最终只返回严格 JSON，不要添加任何解释文字。"
                        ),
                    }
                ],
                "files": {
                    "/research/task_payload.json": create_file_data(task_json),
                },
            },
            config={"configurable": {"thread_id": f"research:{project_id}:{task_id}"}},
            tag="Agent.大纲",
        )

        ai_message = result["messages"][-1].content
        final_result = self._parse_json_response(ai_message)
        logger.info("[Agent.大纲] LLM 返回，响应长度={} chars，has_outline={}，nodes={}",
                    len(ai_message), bool(final_result.get("outline")),
                    len(final_result.get("outline", [])))
        return final_result

    def _parse_json_response(self, text: str) -> dict:
        """容错解析 LLM 输出的 JSON"""
        stripped = text.strip()
        if not stripped:
            return {}
        # 去掉代码块标记
        if stripped.startswith("``"):
            stripped = stripped.removeprefix("``json").removeprefix("``").strip()
            stripped = stripped.removesuffix("```").strip()
        try:
            parsed = json.loads(stripped)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            # 如果整体解析失败，尝试提取 {...} 部分
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(stripped[start:end + 1])
                    return parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    pass
        return {"error": "JSON解析失败", "raw": text[:500]}

    async def revise_outline(self, project_id: str, research_project, revision_instruction, task_id: str) -> dict:
        self._reset_step_counter()
        outline =await get_outline(project_id)
        logger.info("[Agent.修改大纲] 开始调用 LLM，project_id={}，nodes={}，指令长度={}",
                    project_id, len(outline), len(revision_instruction))

        revice = {
            "task": "revise_outline",
            "project_id": project_id,
            "outline": outline,
            "revision_instruction": revision_instruction,
            "research_project": research_project,
        }

        result = await self._invoke_and_log(
            input_data={
                "messages": [
                    {"role": "user", "content": "请完成文件 /revise_outline.json 当中描述的任务。先使用 todo 规划步骤；最终只返回严格 JSON，不要添加任何解释文字。"},
                ],
                "files": {
                    "/revise_outline.json": create_file_data(_safe_json_dumps(revice))
                }
            },
            config={"configurable": {"thread_id": f"research:{project_id}:{task_id}"}},
            tag="Agent.修改大纲",
        )

        ai_message = result["messages"][-1].content
        parsed = self._parse_json_response(ai_message)
        logger.info("[Agent.修改大纲] LLM 返回，响应长度={} chars，new_nodes={}",
                    len(ai_message), len(parsed.get("outline", [])))
        return parsed

    async def generate_research_result(self, project_id: str, user_instruction, task_id) -> dict:
        setting = get_settings()
        outline = await get_confirmed_outline(project_id=project_id)
        logger.info("[Agent.研究] 开始执行研究，project_id={}，outline_nodes={}，retry_limit={}",
                    project_id, len(outline), setting.total_retry_times)

        payload = {
            "task_name": "generate_report",
            "outline": outline,
            "user_instruction": user_instruction
        }

        JSON_HINT = (
            "请严格按 /research/task_payload.json 中的任务描述执行。"
            "先使用 todo 规划步骤；大规模中间结果写入 /research/workspace/ 文件；"
            "最终只返回严格 JSON 摘要，不要添加任何解释文字。"
        )

        t0 = time.perf_counter()
        result = await self._invoke_and_log(
            input_data={
                "messages": [{"role": "user", "content": JSON_HINT}],
                "files": {
                    "/research/task_payload.json": create_file_data(_safe_json_dumps(payload)),
                    "/research/workspace/README.md": create_file_data("该目录用于保存检索摘要、来源整理、事实卡片和报告草稿。"),
                }
            },
            config={"configurable": {"thread_id": f"research:{project_id}:{task_id}_initial"}},
            tag="Agent.研究:首轮",
        )

        logger.info("[Agent.研究] 首轮 LLM 调用完成，耗时={:.1f}s", time.perf_counter() - t0)

        save_sections_ids: list[str] = await research_project_repository.get_saved_sections(project_id)
        expected_section_ids: list[str] = await research_project_repository.get_expected_section_ids(project_id)

        missing = set(expected_section_ids) - set(save_sections_ids)
        logger.info("[Agent.研究] 章节状态: expected={}, saved={}, missing={}",
                    len(expected_section_ids), len(save_sections_ids), len(missing))

        total_retry_times = setting.total_retry_times
        if missing:
            logger.info("[Agent.研究] 开始重试补写缺失章节，missing={}", sorted(missing))
            for retry_count in range(total_retry_times):
                save_sections: dict = await research_project_repository.get_seaved_sections_detial(project_id)

                payload = {
                    "task_name": "generate_report",
                    "outline": outline,
                    "user_instruction": user_instruction,
                    "saved_sections": save_sections,
                    "missing_sections": list(missing),
                }

                t_retry = time.perf_counter()
                await self._invoke_and_log(
                    input_data={
                        "messages": [{"role": "user", "content": JSON_HINT}],
                        "files": {
                            "/research/task_payload.json": create_file_data(_safe_json_dumps(payload)),
                        }
                    },
                    config={"configurable": {"thread_id": f"research:{project_id}:{task_id}_retry_{retry_count}"}},
                    tag=f"Agent.研究:重试{retry_count + 1}/{total_retry_times}",
                )
                elapsed_retry = time.perf_counter() - t_retry

                save_sections_ids = await research_project_repository.get_saved_sections(project_id)
                expected_section_ids = await research_project_repository.get_expected_section_ids(project_id)
                missing = set(expected_section_ids) - set(save_sections_ids)
                logger.info("[Agent.研究] 重试 {}/{} 完成，耗时={:.1f}s，剩余missing={}",
                            retry_count + 1, total_retry_times, elapsed_retry, len(missing))

                if not missing:
                    logger.info("[Agent.研究] 所有章节已补写完成！")
                    break
            else:
                logger.warning("[Agent.研究] 重试耗尽，仍有 {} 个章节缺失: {}", len(missing), sorted(missing))
        else:
            logger.info("[Agent.研究] 所有章节首轮即已完成，无需重试")

    async def generate_report(self, project, outline, user_instruction) -> dict:
        from app.tools.render_html import write_html_report

        research_result = (project or {}).get("research_result", {})
        if not isinstance(research_result, dict):
            research_result = {}

        topic = (project or {}).get("topic", "未知")
        sections_count = len(research_result.get("sections", []))
        logger.info("[Agent.报告] 开始渲染 HTML，topic={}，sections={}", topic, sections_count)

        t0 = time.perf_counter()
        result = write_html_report(research_result)
        html_len = len(result.get("html", "")) if isinstance(result, dict) else 0
        logger.info("[Agent.报告] HTML 渲染完成，耗时={:.1f}s，html_size={} chars",
                    time.perf_counter() - t0, html_len)
        return result


_research_agent = None


def _load_prompt(param: Path):
    return param.read_text(encoding="utf-8")


def _json_default(o):
    """JSON 序列化兼容函数：Pydantic → dict，datetime → isoformat"""
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="python")
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _safe_json_dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


def get_research_agent():
    global _research_agent

    if _research_agent is None:
        setting = get_settings()

        information_search_agent = {
            "name": "information_search",
            "description": "负责公开或联网检索,网页读取,RAGFlow内部知识库检索和证据整理",
            "system_prompt": _load_prompt(Path(__file__).parent / "prompts" / "search_agent.md"),
            "tools": [external_search, ragflow_search, read_web_page],
            "model": f"{setting.llm_provider}:{setting.llm_model_name}",
        }

        manager_agent = create_deep_agent(
            model=f"{setting.llm_provider}:{setting.llm_model_name}",
            system_prompt=_load_prompt(Path(__file__).parent / "prompts" / "research_manager.md"),
            tools=[save_research_sections],
            subagents=[information_search_agent],
            checkpointer=InMemorySaver()
        )

        _research_agent = ResearchAgent(manager_agent)

    return _research_agent

