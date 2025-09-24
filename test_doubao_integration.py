#!/usr/bin/env python3
"""
豆包API集成测试脚本
测试火山方舟豆包API的直连调用
"""

import os
import asyncio
import httpx
from openai import OpenAI

# 配置
ARK_API_KEY = os.getenv("ARK_API_KEY")
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
ARK_MODEL = "doubao-1-5-pro-32k-250115"

async def test_doubao_api():
    """测试豆包API调用"""
    if not ARK_API_KEY:
        print("❌ 请设置环境变量 ARK_API_KEY")
        return False
    
    print(f"🚀 开始测试豆包API...")
    print(f"   API Key: {ARK_API_KEY[:8]}...")
    print(f"   Base URL: {ARK_BASE_URL}")
    print(f"   Model: {ARK_MODEL}")
    
    try:
        # 初始化OpenAI客户端
        client = OpenAI(
            base_url=ARK_BASE_URL,
            api_key=ARK_API_KEY,
        )
        
        # 测试标准请求
        print("\n📝 测试标准请求...")
        completion = client.chat.completions.create(
            model=ARK_MODEL,
            messages=[
                {"role": "system", "content": "你是人工智能助手"},
                {"role": "user", "content": "你好"},
            ],
        )
        print(f"✅ 标准请求成功: {completion.choices[0].message.content}")
        
        # 测试流式请求
        print("\n🌊 测试流式请求...")
        stream = client.chat.completions.create(
            model=ARK_MODEL,
            messages=[
                {"role": "system", "content": "你是人工智能助手"},
                {"role": "user", "content": "请简单介绍一下你自己"},
            ],
            stream=True,
        )
        
        response_text = ""
        for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                response_text += content
                print(content, end="", flush=True)
        
        print(f"\n✅ 流式请求成功，共收到 {len(response_text)} 字符")
        
        # 测试信息抽取任务
        print("\n🔍 测试信息抽取任务...")
        extract_prompt = """你是专业的财政文档信息抽取专家。请从以下文本中抽取"年初预算 vs 支出决算 + 文本判断短语"的信息。

文本内容：
公安支出年初预算为232.02万元，支出决算为219.24万元，决算数小于预算数，主要原因是年中按实际需求调整预算。

请抽取信息并返回JSON格式：
{
  "pairs": [
    {
      "budget_text": "232.02",
      "final_text": "219.24", 
      "stmt_text": "决算数小于预算数",
      "reason_text": "年中按实际需求调整预算",
      "item_title": "公安"
    }
  ]
}"""
        
        completion = client.chat.completions.create(
            model=ARK_MODEL,
            messages=[{"role": "user", "content": extract_prompt}],
            temperature=0,
        )
        
        extract_result = completion.choices[0].message.content
        print(f"✅ 信息抽取成功:")
        print(extract_result)
        
        return True
        
    except Exception as e:
        print(f"❌ 豆包API调用失败: {e}")
        return False

async def test_ai_extractor_service():
    """测试AI抽取器微服务"""
    print(f"\n🔧 测试AI抽取器微服务...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 健康检查
            health_response = await client.get("http://127.0.0.1:9009/health")
            if health_response.status_code == 200:
                print("✅ AI抽取器服务健康检查通过")
            else:
                print("❌ AI抽取器服务不可用")
                return False
            
            # 测试抽取接口
            test_request = {
                "task": "R33110_pairs_v1",
                "section_text": "公安支出年初预算为232.02万元，支出决算为219.24万元，决算数小于预算数，主要原因是年中按实际需求调整预算。",
                "language": "zh",
                "doc_hash": "test_hash",
                "max_windows": 1
            }
            
            extract_response = await client.post(
                "http://127.0.0.1:9009/ai/extract/v1",
                json=test_request
            )
            
            if extract_response.status_code == 200:
                result = extract_response.json()
                print(f"✅ AI抽取器调用成功，找到 {len(result['hits'])} 个结果")
                for i, hit in enumerate(result['hits']):
                    print(f"   结果 {i+1}: {hit['budget_text']} -> {hit['final_text']} ({hit['stmt_text']})")
                return True
            else:
                print(f"❌ AI抽取器调用失败: {extract_response.status_code}")
                print(extract_response.text)
                return False
                
    except Exception as e:
        print(f"❌ AI抽取器服务测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 豆包API集成测试")
    print("=" * 60)
    
    # 测试豆包API
    api_success = await test_doubao_api()
    
    # 测试AI抽取器微服务
    service_success = await test_ai_extractor_service()
    
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    print(f"豆包API直连: {'✅ 通过' if api_success else '❌ 失败'}")
    print(f"AI抽取器服务: {'✅ 通过' if service_success else '❌ 失败'}")
    
    if api_success and service_success:
        print("\n🎉 所有测试通过！系统已准备就绪。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查配置和服务状态。")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)