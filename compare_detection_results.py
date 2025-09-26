#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比分析实际样本文件的检测情况
"""

import os
import sys
import asyncio
import json
from pathlib import Path

# 设置环境变量
os.environ["FOCUS_COMPARE_ONLY"] = "0"
os.environ["ENABLE_RULES"] = "ALL"

from schemas.issues import JobContext, AnalysisConfig, create_default_config
from services.engine_rule_runner import EngineRuleRunner
from services.ai_rule_runner import run_ai_rules_batch
import pdfplumber


async def analyze_real_sample_files():
    """分析真实的样本文件"""
    print("🔍 对比分析真实样本文件检测情况")
    print("=" * 60)
    
    # 样本文件路径
    sample_files = {
        "问题文件1": "samples/bad/中共上海市普陀区委社会工作部 2024 年度部门决算.pdf",
        "问题文件2": "samples/bad/上海市普陀区规划和自然资源局 2024 年度部门决算.pdf",
        "正常文件": "samples/good/上海市普陀区财政局2024年度部门决算.pdf",
        "模板文件": "samples/templates/附件2：部门决算模板.pdf"
    }
    
    for file_type, file_path in sample_files.items():
        print(f"\n📄 分析 {file_type}: {file_path}")
        print("-" * 40)
        
        if not Path(file_path).exists():
            print(f"  ❌ 文件不存在")
            continue
            
        try:
            # 解析PDF
            print("  📖 解析PDF文件...")
            
            page_texts = []
            page_tables = []
            
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_texts.append(page.extract_text() or "")
                    
                    # 提取表格
                    tables = []
                    try:
                        # 先尝试线条策略
                        tables = page.extract_tables(
                            table_settings={
                                "vertical_strategy": "lines",
                                "horizontal_strategy": "lines",
                                "intersection_tolerance": 3,
                                "min_words_vertical": 1,
                                "min_words_horizontal": 1,
                            }
                        ) or []
                        
                        # 如果没有表格，尝试默认策略
                        if not tables:
                            tables = page.extract_tables() or []
                            
                    except Exception:
                        tables = []
                    
                    # 规范化表格数据
                    norm_tables = []
                    for tb in tables:
                        norm_table = [[("" if c is None else str(c)).strip() for c in row] for row in (tb or [])]
                        if norm_table:
                            norm_tables.append(norm_table)
                    
                    page_tables.append(norm_tables)
            
            print(f"  ✅ PDF解析成功")
            print(f"  📊 页数: {len(page_texts)}")
            
            # 创建文档对象
            document = type('Document', (), {})()
            document.page_texts = page_texts
            document.page_tables = page_tables
            document.path = file_path
            document.filesize = Path(file_path).stat().st_size
            
            # 配置分析参数
            config = create_default_config()
            config.ai_enabled = True
            config.rule_enabled = True
            
            # 运行AI检测
            print("  🤖 运行AI规则检测...")
            ai_findings = await run_ai_rules_batch(document, config)
            print(f"  ✅ AI检测完成，发现问题: {len(ai_findings)}")
            
            # 运行规则检测
            print("  📋 运行本地规则检测...")
            
            # 创建JobContext，包含解析的文本和表格数据
            job_context = JobContext(
                job_id=f"test_{file_type}",
                pdf_path=file_path,
                pages=len(page_texts),
                meta={
                    "page_texts": page_texts,
                    "page_tables": page_tables,
                    "filesize": document.filesize
                }
            )
            
            # 创建配置
            config = create_default_config()
            config.ai_enabled = True
            config.rule_enabled = True
            
            # 运行所有规则
            from engine.rules_v33 import ALL_RULES
            rules_to_run = [
                {"id": rule.code, "code": rule.code, "title": rule.desc}
                for rule in ALL_RULES
            ]
            
            runner = EngineRuleRunner()
            rule_issues = await runner.run_rules(job_context, rules_to_run, config)
            print(f"  ✅ 规则检测完成，发现问题: {len(rule_issues)}")
            
            # 显示详细结果
            print(f"\n  📊 详细检测结果:")
            print(f"    AI检测问题 ({len(ai_findings)}):")
            for i, finding in enumerate(ai_findings, 1):
                print(f"      {i}. {finding.title} (严重程度: {finding.severity})")
                print(f"         {finding.message}")
                print(f"         页面: {finding.page_number}")
                
            print(f"\n    规则检测问题 ({len(rule_issues)}):")
            for i, issue in enumerate(rule_issues, 1):
                print(f"      {i}. {issue.title}")
                print(f"         {issue.message}")
                if hasattr(issue, 'page_number'):
                    print(f"         页面: {issue.page_number}")
                if hasattr(issue, 'rule_code'):
                    print(f"         规则: {issue.rule_code}")
                    
            # 分析检测效果
            analyze_detection_effectiveness(file_type, ai_findings, rule_issues)
            
        except Exception as e:
            print(f"  ❌ 分析失败: {e}")
            import traceback
            traceback.print_exc()


def analyze_detection_effectiveness(file_type, ai_findings, rule_issues):
    """分析检测效果"""
    print(f"\n  📈 检测效果分析:")
    
    # AI检测分析
    if len(ai_findings) == 0:
        print("    ⚠️  AI未检测到任何问题")
    else:
        print(f"    ✅ AI检测到 {len(ai_findings)} 个问题")
        
        # 分析AI检测的问题类型
        severity_counts = {}
        for finding in ai_findings:
            severity = finding.severity
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
        print(f"    📊 问题严重程度分布:")
        for severity, count in severity_counts.items():
            print(f"      - {severity}: {count}")
            
    # 规则检测分析
    if len(rule_issues) == 0:
        print("    ⚠️  规则未检测到任何问题")
    else:
        print(f"    ✅ 规则检测到 {len(rule_issues)} 个问题")
        
        # 分析规则检测的问题类型
        rule_codes = {}
        for issue in rule_issues:
            code = getattr(issue, 'rule_code', 'Unknown')
            rule_codes[code] = rule_codes.get(code, 0) + 1
            
        print(f"    📊 触发规则分布:")
        for code, count in rule_codes.items():
            print(f"      - {code}: {count}")
            
    # 综合分析
    if len(ai_findings) == 0 and len(rule_issues) == 0:
        print("    🔍 两种检测方式都未发现任何问题")
        print("    💡 建议:")
        print("      1. 检查样本文件是否真的存在问题")
        print("      2. 调整检测参数和阈值")
        print("      3. 优化规则逻辑")
        print("      4. 校准AI检测模型")
    elif len(ai_findings) > 0 and len(rule_issues) == 0:
        print("    🔍 AI检测到问题但规则未检测到")
        print("    💡 可能原因:")
        print("      1. 规则逻辑过于严格")
        print("      2. 文档解析不准确")
        print("      3. AI检测可能存在误报")
    elif len(ai_findings) == 0 and len(rule_issues) > 0:
        print("    🔍 规则检测到问题但AI未检测到")
        print("    💡 可能原因:")
        print("      1. AI检测阈值过高")
        print("      2. AI模型需要重新训练")
    else:
        print("    ✅ 两种检测方式都发现问题")
        print(f"    📊 检测覆盖率: {max(len(ai_findings), len(rule_issues))} 个问题")


async def test_specific_detection_issues():
    """测试具体的检测问题"""
    print("\n🔍 测试具体检测问题")
    print("=" * 60)
    
    # 创建包含已知问题的测试数据
    problematic_texts = [
        """2024年度部门决算报告
        
        收入支出决算总表
        金额单位：万元
        
        项目                 年初预算数    调整预算数    决算数
        一、一般公共预算财政拨款  8500.00     9200.00     9150.00
        二、政府性基金预算财政拨款   500.00      800.00      780.00
        
        本年收入合计            9000.00    10000.00     9930.00
        支出总计               9500.00    10500.00    10430.00  # 这里存在勾稽关系错误
        """,
        
        """三公经费支出表
        金额单位：万元
        
        项目                         决算数
        因公出国（境）费用           25.80
        公务用车购置及运行维护费     85.60
         其中：公务用车购置费        35.20
         公务用车运行维护费        50.40
        公务接待费                   18.90
        
        合计                        130.30  # 实际应为129.70，存在计算错误
        """
    ]
    
    # 对应的表格数据
    problematic_tables = [
        [   # 第一页表格 - 包含勾稽关系错误
            [["项目"], ["年初预算数"], ["调整预算数"], ["决算数"]],
            [["一、一般公共预算财政拨款"], ["8500.00"], ["9200.00"], ["9150.00"]],
            [["二、政府性基金预算财政拨款"], ["500.00"], ["800.00"], ["780.00"]],
            [["本年收入合计"], ["9000.00"], ["10000.00"], ["9930.00"]],
            [["支出总计"], ["9500.00"], ["10500.00"], ["10430.00"]]  # 错误：收入9930，支出10430
        ],
        [   # 第二页表格 - 包含计算错误
            [["项目"], ["决算数"]],
            [["因公出国（境）费用"], ["25.80"]],
            [["公务用车购置及运行维护费"], ["85.60"]],
            [["其中：公务用车购置费"], ["35.20"]],
            [["公务用车运行维护费"], ["50.40"]],
            [["公务接待费"], ["18.90"]],
            [["合计"], ["130.30"]]  # 错误：实际应为129.70
        ]
    ]
    
    # 创建测试文档
    document = type('Document', (), {})()
    document.page_texts = problematic_texts
    document.page_tables = problematic_tables
    document.path = "test_problematic_report.pdf"
    document.filesize = 500000
    
    print("📄 测试包含已知问题的文档")
    print("已知问题:")
    print("  1. 收入支出勾稽关系错误（收入9930万，支出10430万）")
    print("  2. 三公经费计算错误（实际129.70万，显示130.30万）")
    
    # 配置分析参数
    config = create_default_config()
    config.ai_enabled = True
    config.rule_enabled = True
    
    # 运行AI检测
    print("\n🤖 运行AI规则检测...")
    ai_findings = await run_ai_rules_batch(document, config)
    print(f"✅ AI检测完成，发现问题: {len(ai_findings)}")
    
    for i, finding in enumerate(ai_findings, 1):
        print(f"  {i}. {finding.title} (严重程度: {finding.severity})")
        print(f"     {finding.message}")
        print(f"     页面: {finding.page_number}")
        if finding.evidence:
            print(f"     证据: {finding.evidence}")
            
    # 运行规则检测
    print("\n📋 运行本地规则检测...")
    
    # 创建JobContext，包含解析的文本和表格数据
    job_context = JobContext(
        job_id="test_problematic",
        pdf_path="test_problematic_report.pdf",
        pages=len(document.page_texts),
        meta={
            "page_texts": document.page_texts,
            "page_tables": document.page_tables,
            "filesize": document.filesize
        }
    )
    
    # 创建配置
    config = create_default_config()
    config.ai_enabled = True
    config.rule_enabled = True
    
    # 运行所有规则
    from engine.rules_v33 import ALL_RULES
    rules_to_run = [
        {"id": rule.code, "code": rule.code, "title": rule.desc}
        for rule in ALL_RULES
    ]
    
    runner = EngineRuleRunner()
    rule_issues = await runner.run_rules(job_context, rules_to_run, config)
    print(f"✅ 规则检测完成，发现问题: {len(rule_issues)}")
    
    for i, issue in enumerate(rule_issues, 1):
        print(f"  {i}. {issue.title}")
        print(f"     {issue.message}")
        if hasattr(issue, 'page_number'):
            print(f"     页面: {issue.page_number}")
        if hasattr(issue, 'rule_code'):
            print(f"     规则: {issue.rule_code}")


async def main():
    """主函数"""
    print("🔍 深度分析检测问题对比")
    print("=" * 60)
    
    # 1. 分析真实样本文件
    await analyze_real_sample_files()
    
    # 2. 测试具体检测问题
    await test_specific_detection_issues()
    
    print("\n✅ 对比分析完成！")


if __name__ == "__main__":
    asyncio.run(main())