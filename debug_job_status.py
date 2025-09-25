#!/usr/bin/env python3
"""
调试任务状态
"""

import json

import requests


def debug_job_status():
    """调试任务状态"""
    job_id = "34bde7b0ceab13e8142a992639cec4e1"

    print(f"🔍 调试任务状态: {job_id}")

    try:
        # 检查任务状态
        print("\n1. 检查任务状态...")
        response = requests.get(f"http://localhost:8000/jobs/{job_id}/status")
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            status_data = response.json()
            print(f"   状态: {status_data}")
        else:
            print(f"   错误: {response.text}")

        # 检查所有任务
        print("\n2. 检查所有任务...")
        response = requests.get("http://localhost:8000/jobs")
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            jobs_data = response.json()
            print(f"   任务列表: {json.dumps(jobs_data, ensure_ascii=False, indent=2)}")
        else:
            print(f"   错误: {response.text}")

        # 尝试获取结果
        print("\n3. 尝试获取结果...")
        response = requests.get(f"http://localhost:8000/jobs/{job_id}/result")
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            result_data = response.json()
            print(f"   结果: {json.dumps(result_data, ensure_ascii=False, indent=2)}")
        else:
            print(f"   错误: {response.text}")

        # 检查健康状态
        print("\n4. 检查API健康状态...")
        response = requests.get("http://localhost:8000/health")
        print(f"   状态码: {response.status_code}")
        if response.status_code == 200:
            health_data = response.json()
            print(f"   健康状态: {json.dumps(health_data, ensure_ascii=False, indent=2)}")
        else:
            print(f"   错误: {response.text}")

    except Exception as e:
        print(f"❌ 调试过程中出现错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    debug_job_status()
