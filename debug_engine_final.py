#!/usr/bin/env python3
"""
最终调试脚本 - 修复规则加载和执行问题
"""
import os
import sys
import asyncio
from pathlib import Path

# 将项目根目录添加到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 关键：在导入任何模块之前设置环境变量
os.environ["FOCUS_COMPARE_ONLY"] = "0"  # 禁用聚焦模式
os.environ["ENABLE_RULES"] = "ALL"       # 启用所有规则

from engine.rules_v33 import ALL_RULES_BASE, ALL_RULES
from services.engine_rule_runner import EngineRuleRunner
from models.job import JobContext
from models.analysis import AnalysisConfig
from engine.build_document import build_document
from models.document import Document

def test_rule_loading():
    """测试规则加载"""
    print("=== 最终规则加载测试 ===")
    
    print(f"\n1. 环境变量设置:")
    print(f"   FOCUS_COMPARE_ONLY: {os.environ.get('FOCUS_COMPARE_ONLY')}")
    print(f"   ENABLE_RULES: {os.environ.get('ENABLE_RULES')}")
    
    print(f"\n2. 加载的规则数量: {len(ALL_RULES)}")
    print("   可用规则:")
    for rule in ALL_RULES:
        print(f"     - {rule.code}: {rule.desc}")

def create_test_document():
    """创建测试文档"""
    # 模拟文档数据
    page_texts = [
        "2024年度部门决算报告\n单位：万元\n目录\n一、收入支出决算总表\n二、收入决算表",
        "收入支出决算总表\n项目\n年初预算数\n调整预算数\n决算数\n支出总计\n1000.00\n1200.00\n1300.00",
        "三公经费支出表\n因公出国(境)费\n0.00\n公务用车购置及运行维护费\n50.00\n公务接待费\n20.00",
    ]
    
    page_tables = [
        # 第1页表格
        [
            [["项目"], ["年初预算数"], ["调整预算数"], ["决算数"]],
            [["支出总计"], ["1000.00"], ["1200.00"], ["1300.00"]],
        ],
        # 第2页表格
        [
            [["三公经费项目"], ["决算数"]],
            [["因公出国(境)费"], ["0.00"]],
            [["公务用车购置及运行维护费"], ["50.00"]],
            [["公务接待费"], ["20.00"]],
        ],
    ]
    
    # 确保page_tables与page_texts长度一致
    while len(page_tables) < len(page_texts):
        page_tables.append([])
    
    return build_document(
        path="test_document.pdf",
        page_texts=page_texts,
        page_tables=page_tables,
        filesize=1024000
    )

async def test_engine_rule_runner():
    """测试引擎规则运行器"""
    print("\n=== 引擎规则运行器测试 ===")
    
    # 创建测试文档
    document = create_test_document()
    print(f"\n1. 创建测试文档: {document.path}")
    print(f"   页数: {document.pages}")
    print(f"   主要年份: {document.dominant_year}")
    print(f"   主要单位: {document.dominant_unit}")
    
    # 创建任务上下文
    job_context = JobContext(
        pdf_path="test_document.pdf",
        filesize=1024000,
        meta={"page_texts": document.page_texts}
    )
    
    # 创建分析配置
    config = AnalysisConfig(
        rules=[
            {"id": "R33001", "code": "R33001", "title": "封面年份单位检查"},
            {"id": "R33002", "code": "R33002", "title": "九张表完整性检查"},
            {"id": "R33110", "code": "R33110", "title": "预算决算一致性检查"},
        ]
    )
    
    # 创建规则运行器
    runner = EngineRuleRunner()
    
    print(f"\n2. 测试规则执行:")
    
    # 测试单个规则
    test_rules = [
        {"id": "R33001", "code": "R33001"},
        {"id": "R33002", "code": "R33002"},
        {"id": "R33110", "code": "R33110"},
    ]
    
    for rule_config in test_rules:
        print(f"\n   测试规则 {rule_config['code']}:")
        result = await runner._execute_rule(rule_config, document, job_context, config)
        print(f"     成功: {result.success}")
        print(f"     问题数量: {len(result.findings)}")
        if not result.success:
            print(f"     失败原因: {result.why_not}")
        elif result.findings:
            for finding in result.findings:
                print(f"     发现问题: {finding.message}")
    
    # 测试批量规则执行
    print(f"\n3. 测试批量规则执行:")
    results = await runner.run_rules(config.rules, job_context)
    
    print(f"   总规则数量: {len(results)}")
    success_count = sum(1 for r in results if r.success)
    print(f"   成功规则数量: {success_count}")
    
    for result in results:
        print(f"   规则 {result.rule_id}: {'成功' if result.success else '失败'} ({len(result.findings)} 个问题)")
        if not result.success:
            print(f"     原因: {result.why_not}")

async def main():
    """主函数"""
    test_rule_loading()
    await test_engine_rule_runner()

if __name__ == "__main__":
    asyncio.run(main())