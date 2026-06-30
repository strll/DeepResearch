"""
TODO: 【高优先级】补充缺失功能和完善 Agent 架构
参照: app/agents/research_agent.py (参考项目) - 约900行完整实现

缺失功能清单:
1. [缺失] Pydantic 数据模型: ResearchBrief, FactCard, ConflictInfo, EvidenceItem,
   ResearchSection, ResearchSynthesis, ResearchResult, ReportResult
2. [缺失] generate_report() 方法: 调用 write_html_report() 渲染 HTML 报告
3. [缺失] _build_*_input() 辅助方法: 构建各类任务的 payload
4. [缺失] _invoke_manager_agent() 统一调用: payload -> messages + files -> JSON 响应
5. [缺失] _parse_*() 结果解析: _parse_outline_result(), _parse_report_generation_result()
6. [缺失] _expected_research_section_ids(): 从大纲叶子节点提取章节 ID
7. [缺失] _build_research_result_from_saved_sections(): 从已保存章节组装 ResearchResult
8. [需修改] generate_outline() -> generate_research_brief(): 返回结构化结果
9. [需修改] generate_research_result(): 增加补写逻辑(检测已保存章节、只补写缺失、最多重试4次)
10.[需修改] 搜索子智能体 tools: external_search, ragflow_search, web_pag_read.read_web_page
"""

import json
import pathlib
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends.utils import create_file_data
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from app.config.config import get_settings
from app.repository import research_project_repository
from app.repository.research_project_repository import get_outline, get_confirmed_outline

from app.tools import web_pag_read
from app.tools.external_search import external_search
from app.tools.ragflow_search import ragflow_search
from app.tools.research_agent_tool import save_research_sections


class ResearchAgent:

    def __init__(self, manager_agent):
        self.manager_agent: CompiledStateGraph = manager_agent

    async def generate_outline(self, project_id: str, research_project, task_id):
        # TODO: 重命名为 generate_research_brief()
        # TODO: 返回 {"research_brief": ResearchBrief, "outline": list[OutlineNode]} 结构化结果
        result = await self.manager_agent.invoke({
            "messages": [
                {"role": "user", "content": f"请基于一下的设定 {research_project.model_dump()}"}
            ]
        },
            config={"configurable": {"thread_id": f"{project_id}_{task_id}"}}  # type: ignore
        )

        ai_message = result["messages"][-1].content
        try:
            final_result = json.loads(ai_message)
        except Exception as e:

            final_result = {"error": str(e)}

        return final_result

    async def revise_outline(self, project_id: str, research_project, revision_instruction, task_id: str) -> dict:
        # TODO: 使用 _build_revise_outline_input() 和 _invoke_manager_agent() 统一调用
        # 读取当前的大纲
        outline = get_outline(project_id)

        revice = {
            "task": "revise_outline",
            "project_id": project_id,
            "outline": outline,
            "revision_instruction": revision_instruction,
            "research_project": research_project,
        }

        result = await self.manager_agent.invoke(
            {
                "messages": [
                    {"role": "user", "content": f"请完成文件 /revise_outline.json 当中描述的任务"},

                ],
                "files": {
                    "/revise_outline.json": create_file_data(json.dumps(revice))
                }
            },
            config={"configurable": {"thread_id": f"{project_id}_{task_id}"}}  # type: ignore
        )

        ai_message = result["messages"][-1].content
        try:
            final_result = json.loads(ai_message)
        except Exception as e:

            final_result = {"error": str(e)}

        return final_result

    async def generate_research_result(self, project_id: str, user_instruction, task_id) -> dict:
        """生成报告的逻辑"""
        # TODO: 添加补写逻辑:
        #   1. await research_project_repository.clear_research_sections(project_id) 清空旧章节
        #   2. 获取 expected_section_ids 和已保存的 saved_section_ids
        #   3. 只补写缺失章节，最多重试 4 次(而非 total_retry_times)
        #   4. 调用 _build_research_result_from_saved_sections() 组装最终结果
        # TODO: 返回 ResearchResult 而非 dict

        setting = get_settings()

        outline = await get_confirmed_outline(project_id=project_id)

        generate_research_result = {
            "task": "generate_research_result",
            "outline": outline,
            "user_instruction": user_instruction
        }

        await self.manager_agent.ainvoke(
            {
                "messages": [
                    {"role": "user", "content": f"请完成以下 /generate_research_result.json 当中描述的任务"},
                ],
                "files": {
                    "/generate_research_result.json": create_file_data(json.dumps(generate_research_result))
                }
            },
            config={"configurable": {"thread_id": f"{project_id}_{task_id}_titial_generate"}}  # type: ignore
        )

        save_sections_ids: list[str] = await research_project_repository.get_saved_sections(project_id)

        expected_section_ids: list[str] = await research_project_repository.get_expected_section_ids(project_id)

        messing = set(expected_section_ids) - set(save_sections_ids)
        total_retry_times = setting.total_retry_times
        if messing:
            for retry_count in range(total_retry_times):
                save_sections: dict = await research_project_repository.get_seaved_sections_detial(project_id)

                generate_research_result = {
                    "task": "generate_research_result",
                    "outline": outline,
                    "user_instruction": user_instruction,
                    "saved_sections": save_sections,
                    "missing_sections":messing
                }

                await self.manager_agent.ainvoke(
                    {
                        "messages": [
                            {"role": "user", "content": f"请完成以下 /generate_research_result.json 当中描述的任务"},
                        ],
                        "files": {
                            "/generate_research_result.json": create_file_data(json.dumps(generate_research_result))
                        }
                    },
                    config={"configurable": {"thread_id": f"{project_id}_{task_id}_retry_{retry_count}"}}
                    # type: ignore
                )
                save_sections_ids: list[str] = await research_project_repository.get_saved_sections(project_id)

                expected_section_ids: list[str] = await research_project_repository.get_expected_section_ids(project_id)

                messing = set(expected_section_ids) - set(save_sections_ids)

                if not messing:
                    break



    # TODO: [缺失] 添加 generate_report() 方法 - 渲染 HTML 报告
    # async def generate_report(self, project, outline, user_instruction) -> ReportResult:
    #     """渲染 HTML 研究报告。
    #     1. 从 project 中提取 research_result
    #     2. 调用 write_html_report(research_result, layout_plan) 确定性渲染
    #     3. 返回 ReportResult(title, html, sources, fact_cards, insight_cards)
    #     """
    #     from app.tools.render_html import write_html_report
    #     payload = self._build_generate_report_input(project, outline, user_instruction)
    #     raw_result = await write_html_report(
    #         research_result=payload["research_result"],
    #         layout_plan=self._build_default_layout_plan(payload=payload),
    #     )
    #     return ReportResult(...)

    # TODO: [缺失] 添加 _invoke_manager_agent() 统一调用方法
    # async def _invoke_manager_agent(self, task_name, payload):
    #     """将 payload 转为 messages + files，调用 manager_agent，解析 JSON 响应"""

    # TODO: [缺失] 添加 _build_*_input() 和 _parse_*_result() 辅助方法


_research_agent = None


def _load_prompt(param: Path):
    return param.read_text()


def get_research_agent():
    global _research_agent

    if _research_agent is None:
        setting = get_settings()

        # TODO: 确认 web_pag_read 的正确引用
        # 参考项目: from app.tools.web_reader import read_web_page
        # 当前项目: from app.tools import web_pag_read (需确认导出 read_web_page 函数)
        information_search_agent = {
            "name": "information_search",
            "description": "负责公开或联网检索,网页读取,RAGFlow内部知识库检索和证据整理",
            "system_prompt": _load_prompt(Path(__file__).parent / "prompt" / "search_agent.md"),
            "tools": [external_search, ragflow_search, web_pag_read],
            "model": f"{setting.llm_provider}:{setting.llm_model_name}",
        }

        # TODO: 管理智能体工具列表正确 - 只注册 save_research_sections
        # 报告渲染由 write_html_report() 确定性完成，不走 Agent
        manager_agent = create_deep_agent(
            model=f"{setting.llm_provider}:{setting.llm_model_name}",
            system_prompt=_load_prompt(Path(__file__).parent / "prompt" / "research_manager.md"),
            tools=[save_research_sections],  # 工具
            subagents=[information_search_agent],  # 子智能体
            checkpointer=InMemorySaver()
        )

        _research_agent = ResearchAgent(manager_agent=manager_agent)
        return _research_agent
