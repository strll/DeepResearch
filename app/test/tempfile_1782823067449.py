"""
DeepSeek API 连通性测试脚本
用法: python scripts/test_deepseek.py
"""

import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from app.config.config import get_settings


async def test_deepseek() -> bool:
    settings = get_settings()

    print("=" * 50)
    print("DeepSeek API 连通性测试")
    print("=" * 50)

    # 1. 打印配置
    print(f"\n📋 当前配置:")
    print(f"   LLM_PROVIDER       = {settings.llm_provider}")
    print(f"   LLM_MODEL_NAME     = {settings.llm_model_name}")
    print(f"   DEEPSEEK_API_BASE  = {settings.deepseek_api_base}")
    print(f"   DEEPSEEK_API_KEY   = {'✅ 已配置' if settings.deepseek_api_key else '❌ 未配置!'}")

    if not settings.deepseek_api_key:
        print("\n❌ 失败: DEEPSEEK_API_KEY 未设置，请检查 .env 文件。")
        return False

    api_base = str(settings.deepseek_api_base).rstrip("/")
    api_key = settings.deepseek_api_key

    # 2. 测试基础连通性
    print(f"\n🔗 测试连接: {api_base}/chat/completions")
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            response = await client.post(
                f"{api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.llm_model_name,
                    "messages": [{"role": "user", "content": "请回复: 连接测试成功"}],
                    "max_tokens": 50,
                    "temperature": 0,
                },
            )

            print(f"   HTTP 状态码: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                reply = data["choices"][0]["message"]["content"]
                token_usage = data.get("usage", {})

                print(f"\n✅ DeepSeek API 连接成功!")
                print(f"   模型回复: {reply.strip()}")
                print(f"   Token 用量: prompt={token_usage.get('prompt_tokens')}, "
                      f"completion={token_usage.get('completion_tokens')}, "
                      f"total={token_usage.get('total_tokens')}")
                return True
            else:
                print(f"\n❌ 失败: HTTP {response.status_code}")
                print(f"   响应内容: {response.text[:500]}")
                return False

        except httpx.ConnectError:
            print(f"\n❌ 连接超时或拒绝: 无法连接到 {api_base}")
            return False
        except Exception as e:
            print(f"\n❌ 异常: {type(e).__name__}: {e}")
            return False


async def test_langchain() -> bool:
    """通过 langchain-deepseek 测试"""
    print("\n" + "=" * 50)
    print("LangChain DeepSeek 集成测试")
    print("=" * 50)

    try:
        from langchain_deepseek import ChatDeepSeek
        settings = get_settings()

        llm = ChatDeepSeek(
            model=settings.llm_model_name,
            temperature=0,
            api_key=settings.deepseek_api_key,
            api_base=str(settings.deepseek_api_base) if settings.deepseek_api_base else None,
        )

        print(f"\n🔗 通过 LangChain 调用...")
        result = await llm.ainvoke("请回复: LangChain集成测试成功")
        print(f"\n✅ LangChain DeepSeek 集成正常!")
        print(f"   模型回复: {result.content.strip()}")
        return True
    except ImportError:
        print("\n⚠️  langchain-deepseek 未安装，跳过集成测试。")
        return True
    except Exception as e:
        print(f"\n❌ LangChain 集成失败: {e}")
        return False


async def main():
    ok1 = await test_deepseek()
    ok2 = await test_langchain()

    print("\n" + "=" * 50)
    if ok1 and ok2:
        print("🎉 全部测试通过！DeepSeek 配置正确。")
    else:
        print("⚠️  部分测试未通过，请根据上述日志排查。")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
