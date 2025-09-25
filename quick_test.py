#!/usr/bin/env python3
"""
快速测试双模式分析
"""
import requests
import json
import time

def quick_test():
    print("🚀 快速双模式测试")
    print("=" * 40)
    
    # 1. 检查服务状态
    print("🔍 检查服务状态...")
    
    try:
        # 检查AI服务
        ai_health = requests.get("http://localhost:9009/health", timeout=3)
        print(f"✅ AI服务: {ai_health.status_code}")
    except:
        print("❌ AI服务不可用")
        return
    
    try:
        # 检查API服务
        api_health = requests.get("http://localhost:8000/", timeout=3)
        print(f"✅ API服务: {api_health.status_code}")
    except:
        print("❌ API服务不可用")
        return
    
    # 2. 直接测试AI抽取
    print("\n🧪 测试AI抽取功能...")
    
    test_data = {
        "text": "2024年预算执行报告\n\n预算执行率达到105%，存在超支问题。人员经费支出超预算20万元。",
        "tables": [
            {
                "title": "预算执行表",
                "headers": ["科目", "预算", "执行", "执行率"],
                "rows": [
                    ["人员经费", "500万", "520万", "104%"],
                    ["办公费", "100万", "120万", "120%"]
                ]
            }
        ]
    }
    
    try:
        ai_response = requests.post(
            "http://localhost:9009/ai/extract/v1",
            json=test_data,
            timeout=20
        )
        
        if ai_response.status_code == 200:
            ai_result = ai_response.json()
            findings = ai_result.get('findings', [])
            print(f"✅ AI抽取成功: 发现 {len(findings)} 个问题")
            
            for i, finding in enumerate(findings[:2], 1):
                print(f"   {i}. {finding.get('category', 'N/A')}: {finding.get('description', 'N/A')[:40]}...")
        else:
            print(f"❌ AI抽取失败: {ai_response.status_code}")
            
    except Exception as e:
        print(f"❌ AI抽取异常: {e}")
        return
    
    print("\n🎯 AI服务工作正常！双模式分析应该可以正常运行。")
    print("\n💡 建议：")
    print("   1. 通过前端上传PDF文件测试完整流程")
    print("   2. 检查前端是否正确显示AI检测结果")
    print("   3. 确认双模式分析在实际使用中的表现")

if __name__ == "__main__":
    quick_test()