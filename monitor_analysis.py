#!/usr/bin/env python3
"""
监控分析进度
"""
import requests
import time
import json

def monitor_analysis():
    """监控分析进度"""
    job_id = "34bde7b0ceab13e8142a992639cec4e1"
    
    print(f"🔍 监控分析进度: {job_id}")
    print("=" * 50)
    
    max_checks = 60  # 最多检查60次（3分钟）
    
    for i in range(max_checks):
        try:
            # 检查任务状态
            response = requests.get(f'http://localhost:8000/jobs/{job_id}/status')
            if response.status_code == 200:
                status_data = response.json()
                status = status_data.get('status', 'unknown')
                progress = status_data.get('progress', 0)
                stage = status_data.get('stage', '')
                
                print(f"📊 检查 {i+1:2d}: {status} ({progress}%) - {stage}")
                
                if status == 'completed':
                    print("\n✅ 分析完成！获取结果...")
                    
                    # 获取结果
                    result_response = requests.get(f'http://localhost:8000/jobs/{job_id}/result')
                    if result_response.status_code == 200:
                        result_data = result_response.json()
                        
                        print(f"\n📋 分析结果:")
                        print(f"   总问题数: {result_data.get('total_issues', 0)}")
                        print(f"   AI问题数: {result_data.get('ai_issues', 0)}")
                        print(f"   规则问题数: {result_data.get('rule_issues', 0)}")
                        
                        # 显示AI检测结果
                        ai_findings = result_data.get('ai_findings', [])
                        if ai_findings:
                            print(f"\n🤖 AI检测结果 ({len(ai_findings)}个):")
                            for j, finding in enumerate(ai_findings[:3], 1):
                                print(f"   {j}. {finding.get('title', 'Unknown')}")
                                print(f"      严重程度: {finding.get('severity', 'unknown')}")
                                print(f"      位置: 第{finding.get('location', {}).get('page', 0)}页")
                                print(f"      描述: {finding.get('message', 'No message')[:80]}...")
                        
                        # 显示规则检测结果
                        rule_findings = result_data.get('rule_findings', [])
                        if rule_findings:
                            print(f"\n📏 规则检测结果 ({len(rule_findings)}个):")
                            for j, finding in enumerate(rule_findings[:3], 1):
                                print(f"   {j}. {finding.get('title', 'Unknown')}")
                                print(f"      严重程度: {finding.get('severity', 'unknown')}")
                                print(f"      位置: 第{finding.get('location', {}).get('page', 0)}页")
                        
                        print(f"\n🎉 AI自由检测功能正常工作！")
                        return
                    else:
                        print(f"❌ 获取结果失败: {result_response.status_code} - {result_response.text}")
                        return
                        
                elif status == 'failed':
                    error = status_data.get('error', 'Unknown error')
                    print(f"\n❌ 分析失败: {error}")
                    return
                    
            else:
                print(f"⚠️  状态检查失败: {response.status_code}")
            
            time.sleep(3)  # 等待3秒
            
        except Exception as e:
            print(f"❌ 监控过程中出现错误: {e}")
            time.sleep(3)
    
    print("\n⏰ 监控超时")

if __name__ == "__main__":
    monitor_analysis()