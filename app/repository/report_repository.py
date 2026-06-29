import uuid
from datetime import datetime

from pymongo.synchronous import settings

from app.config.config import get_settings
from app.repository.mongodb import get_mongodb_database
from app.tools.storage_toll import save_report_html_to_file

COLLECTION_NAME = "report_versions"


async def save_html_result(html_result, project_id):
    setting = get_settings()
    result = await get_mongodb_database()[COLLECTION_NAME].find_one(
        {"project_id": project_id},
        sort=[{"version": -1}]

    )

    uri = save_report_html_to_file(html_result["html"])

    next_version = result["version"] + 1 if result else 1
    report_id = str(uuid.uuid4())
    report_version = {
        "_id": report_id,
        "project_id": project_id,
        "version": next_version,
        "html_uri": uri,
        "sources": html_result["sources"],
        "create_at": datetime.now()
    }
    await get_mongodb_database()[COLLECTION_NAME].insert_one(
        report_version
    )
