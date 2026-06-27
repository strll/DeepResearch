
class ResearchAgent:

    async def generate_outline(self,project_id:str,research_project):
        pass

    async def revise_outline(self,project_id:str,research_project,revision_instruction):
        pass

    async def generate_research_result(self,project_id:str,user_instruction):
        pass


_research_agent=None

def get_research_agent():
    global  _research_agent
    if _research_agent is None:
        _research_agent=ResearchAgent()
        return _research_agent


