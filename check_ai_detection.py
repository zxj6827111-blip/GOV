#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查AI检测功能
"""

import time

import requests


def check_ai_detection():
    print("🔍 检查AI检测功能")
    print("=" * 50)

    # 1. 上传一个测试文件
    test_file = "samples/bad/中共上海市普陀区委社会工作部 2024 年度部门决算.pdf"

    try:
        print("📤 上传测试文件...")
        with open(test_file, "rb") as f:
            files = {"file": f}
            response = requests.post("http://localhost:8000/upload", files=files, timeout=30)

        if response.status_code != 200:
            print(f"❌ 上传失败: {response.status_code}")
            return

        result = response.json()
        job_id = result["job_id"]
        print(f"✅ 上传成功: {job_id}")

        # 2. 启动分析
        print("🔬 启动AI+规则双模式分析...")
        analyze_data = {"use_local_rules": True, "use_ai_assist": True, "mode": "dual"}

        response = requests.post(
            f"http://localhost:8000/analyze/{job_id}", json=analyze_data, timeout=30
        )
        if response.status_code != 200:
            print(f"❌ 启动分析失败: {response.status_code}")
            return

        print("✅ 分析任务已启动")

        # 3. 等待完成
        print("⏳ 等待分析完成...")
        for i in range(30):  # 最多等待60秒
            time.sleep(2)
            response = requests.get(f"http://localhost:8000/jobs/{job_id}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                if status["status"] == "done":
                    print("✅ 分析完成!")

                    # 4. 获取结果
                    response = requests.get(
                        f"http://localhost:8000/jobs/{job_id}/result", timeout=10
                    )
                    if response.status_code == 200:
                        result = response.json()

                        ai_findings = result.get("ai_findings", [])
                        rule_findings = result.get("rule_findings", [])
                        merged_issues = result.get("merged", {}).get("issues", [])

                        print("📊 分析结果:")
                        print(f"   - AI检测问题: {len(ai_findings)} 个")
                        print(f"   - 规则检测问题: {len(rule_findings)} 个")
                        print(f"   - 合并后问题: {len(merged_issues)} 个")

                        # 显示性能统计
                        meta = result.get("meta", {})
                        if "performance" in meta:
                            perf = meta["performance"]
                            print("⏱️ 性能统计:")
                            ai_time = perf.get("ai_elapsed_ms", 0)
                            rule_time = perf.get("rule_elapsed_ms", 0)
                            total_time = perf.get("total_elapsed_ms", 0)
                            print(f"   - AI检测耗时: {ai_time}ms")
                            print(f"   - 规则检测耗时: {rule_time}ms")
                            print(f"   - 总耗时: {total_time}ms")

                        # 显示AI检测详情
                        if "ai_meta" in meta:
                            ai_meta = meta["ai_meta"]
                            print("🔍 AI检测详情:")
                            model_used = ai_meta.get("model_used", "未知")
                            ai_status = ai_meta.get("status", "未知")
                            print(f"   - 使用模型: {model_used}")
                            print(f"   - 处理状态: {ai_status}")
                            if "error" in ai_meta:
                                error_msg = ai_meta["error"]
                                print(f"   - 错误信息: {error_msg}")

                        # 如果AI检测时间为0，说明可能有问题
                        if ai_time == 0:
                            print("⚠️  警告: AI检测耗时为0ms，可能AI检测没有正常执行")

                        return result
                    else:
                        print(f"❌ 获取结果失败: {response.status_code}")
                        return None
                elif status["status"] == "error":
                    error_msg = status.get("error", "未知错误")
                    print(f"❌ 分析失败: {error_msg}")
                    return None
                else:
                    progress = status.get("progress", 0)
                    print(f"   [{i * 2:3d}s] {status['status']} - {progress}%")
        else:
            print("⏰ 分析超时")
            return None

    except FileNotFoundError:
        print(f"❌ 测试文件不存在: {test_file}")
        return None
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return None


if __name__ == "__main__":
    result = check_ai_detection()
    if result:
        print("\n✅ AI检测功能测试完成")
    else:
        print("\n❌ AI检测功能测试失败")
