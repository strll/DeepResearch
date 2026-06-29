from app.config.config import get_settings


async def save_research_sections(project_id:str,section)->dict:
    """
    模型调用 并且把section保存到mongodb里面  返回保存是否成功 失败要报错
    :param project_id:
    :param section:
    :return:
    """

