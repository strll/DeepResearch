import argparse
import asyncio
import sys
from pathlib import Path
from textwrap import shorten

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config.config import get_settings
from app.tools.ragflow_search import ragflow_search


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test the RAGFlow search tool locally.")
    parser.add_argument("query", nargs="?", default="国家政策", help="Search query.")
    parser.add_argument("--page-size", type=int, default=3, help="Number of chunks to return.")
    parser.add_argument("--max-chars", type=int, default=300, help="Max chars to print per chunk.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = get_settings()

    print("RAGFlow config:")
    print(f"  enable_ragflow={settings.enable_ragflow}")
    print(f"  ragflow_base_url={settings.ragflow_base_url}")
    print(f"  ragflow_default_dataset_ids={settings.ragflow_default_dataset_ids}")
    print(f"  ragflow_api_key_configured={bool(settings.ragflow_api_key)}")
    print()

    result = await ragflow_search(args.query, page_size=args.page_size)
    print(f"status={result.get('status')}")
    if result.get("error"):
        print(f"error={result.get('error')}")
    print(f"query={result.get('query')}")
    print(f"chunks={len(result.get('chunks', []))}")
    print()

    for index, chunk in enumerate(result.get("chunks", []), start=1):
        content = shorten(chunk.get("content") or "", width=args.max_chars, placeholder="...")
        print(f"[{index}] document={chunk.get('document_name')}")
        print(f"    score={chunk.get('score')}")
        print(f"    dataset_id={chunk.get('dataset_id')}")
        print(f"    document_id={chunk.get('document_id')}")
        print(f"    content={content}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
