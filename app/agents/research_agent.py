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
        """
        生成报告的逻辑
        :param self:
        :param project_id:
        :param user_instruction:
        :return:
        """

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




_research_agent = None


def _load_prompt(param: Path):
    return param.read_text()


def get_research_agent():
    global _research_agent

    if _research_agent is None:
        setting = get_settings()

        information_search_agent = {
            "name": "information_search",
            "description": "负责公开或联网检索,网页读取,RAGFlow内部知识库检索和证据整理",
            "system_prompt": _load_prompt(Path(__file__).parent / "prompt" / "search_agent.md"),
            "tools": [external_search, ragflow_search, web_pag_read],
            "model": f"{setting.llm_provider}:{setting.llm_model_name}",
        }

        manager_agent = create_deep_agent(
            model=f"{setting.llm_provider}:{setting.llm_model_name}",
            system_prompt=_load_prompt(Path(__file__).parent / "prompt" / "research_manager.md"),
            tools=[save_research_sections],  # 工具
            subagents=[information_search_agent],  # 子智能体
            checkpointer=InMemorySaver()
        )

        _research_agent = ResearchAgent(manager_agent=manager_agent)
        return _research_agent
