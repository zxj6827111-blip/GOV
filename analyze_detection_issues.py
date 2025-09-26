#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析检测问题 - 深入了解规则和AI检测的具体情况
"""

import os
import sys
import asyncio
import json
from pathlib import Path

# 设置环境变量
os.environ["FOCUS_COMPARE_ONLY"] = "0"
os.environ["ENABLE_RULES"] = "ALL"

from engine.rules_v33 import ALL_RULES, build_document, Issue
from schemas.issues import JobContext, AnalysisConfig, create_default_config
from services.engine_rule_runner import EngineRuleRunner
from services.ai_rule_runner import run_ai_rules_batch


def analyze_sample_files():
    """分析样本文件"""
    print("📁 分析样本文件")
    print("=" * 50)
    
    # 样本文件路径
    sample_files = {
        "问题文件1": "samples/bad/中共上海市普陀区委社会工作部 2024 年度部门决算.pdf",
        "问题文件2": "samples/bad/上海市普陀区规划和自然资源局 2024 年度部门决算.pdf",
        "正常文件": "samples/good/上海市普陀区财政局2024年度部门决算.pdf",
        "模板文件": "samples/templates/附件2：部门决算模板.pdf"
    }
    
    for file_type, file_path in sample_files.items():
        print(f"\n📄 {file_type}: {file_path}")
        
        if not Path(file_path).exists():
            print(f"  ❌ 文件不存在")
            continue
            
        # 检查文件大小和基本信息
        file_size = Path(file_path).stat().st_size
        print(f"  📊 文件大小: {file_size:,} 字节")
        
        # 尝试读取PDF内容（简单检查）
        try:
            import PyPDF2
            with open(file_path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                num_pages = len(pdf_reader.pages)
                print(f"  📄 页数: {num_pages}")
                
                # 读取第一页文本
                if num_pages > 0:
                    first_page_text = pdf_reader.pages[0].extract_text()[:200]
                    print(f"  📝 首页预览: {first_page_text}...")
                    
        except Exception as e:
            print(f"  ⚠️  PDF读取失败: {e}")


def analyze_rule_implementations():
    """分析规则实现情况"""
    print("\n🔍 分析规则实现情况")
    print("=" * 50)
    
    print(f"📊 总规则数量: {len(ALL_RULES)}")
    
    # 按规则代码分组
    rule_groups = {}
    for rule in ALL_RULES:
        code_prefix = rule.code.split('-')[0]
        if code_prefix not in rule_groups:
            rule_groups[code_prefix] = []
        rule_groups[code_prefix].append(rule)
    
    for group, rules in rule_groups.items():
        print(f"\n📋 {group} 规则组 ({len(rules)} 条):")
        for rule in rules:
            print(f"  - {rule.code}: {rule.desc}")


def test_rule_execution_detail():
    """详细测试规则执行"""
    print("\n🧪 详细测试规则执行")
    print("=" * 50)
    
    # 创建测试数据 - 模拟真实的决算报告内容
    test_page_texts = [
        """2024年度上海市普陀区财政局部门决算
单位：万元

第一部分 部门概况
一、主要职能
（一）贯彻执行国家有关财政、税收工作的方针政策和法律、法规、规章。

第二部分 2024年度部门决算表
一、收入支出决算总表
二、收入决算表
三、支出决算表
四、财政拨款收入支出决算总表
五、一般公共预算财政拨款支出决算表
六、一般公共预算财政拨款基本支出决算表
七、一般公共预算财政拨款"三公"经费支出决算表
八、政府性基金预算财政拨款收入支出决算表
九、国有资本经营预算财政拨款收入支出决算表""",
        
        """收入支出决算总表
编制单位：上海市普陀区财政局
2024年度
金额单位：万元

项目\n栏次\n年初预算数\n调整预算数\n决算数\n
一、一般公共预算财政拨款\n1\n8,500.00\n9,200.00\n9,150.00\n二、政府性基金预算财政拨款\n2\n500.00\n800.00\n780.00\n三、国有资本经营预算财政拨款\n3\n0.00\n0.00\n0.00\n
本年收入合计\n\n9,000.00\n10,000.00\n9,930.00\n\n支出总计\n\n9,000.00\n10,000.00\n9,930.00""",
        
        """三公经费支出表
2024年度
金额单位：万元

项目\n决算数\n
因公出国（境）费用\n15.20\n公务用车购置及运行维护费\n45.80\n其中：公务用车购置费\n0.00\n公务用车运行维护费\n45.80\n公务接待费\n12.50\n
合计\n73.50"""
    ]
    
    # 对应的表格数据
    test_page_tables = [
        [],  # 第一页没有表格
        [   # 第二页表格 - 收入支出决算总表
            [["项目"], ["栏次"], ["年初预算数"], ["调整预算数"], ["决算数"]],
            [["一、一般公共预算财政拨款"], ["1"], ["8,500.00"], ["9,200.00"], ["9,150.00"]],
            [["二、政府性预算财政拨款"], ["2"], ["500.00"], ["800.00"], ["780.00"]],
            [["三、国有资本经营预算财政拨款"], ["3"], ["0.00"], ["0.00"], ["0.00"]],
            [["本年收入合计"], [""], ["9,000.00"], ["10,000.00"], ["9,930.00"]],
            [["支出总计"], [""], ["9,000.00"], ["10,000.00"], ["9,930.00"]]
        ],
        [   # 第三页表格 - 三公经费支出表
            [["项目"], ["决算数"]],
            [["因公出国（境）费用"], ["15.20"]],
            [["公务用车购置及运行维护费"], ["45.80"]],
            [["其中：公务用车购置费"], ["0.00"]],
            [["公务用车运行维护费"], ["45.80"]],
            [["公务接待费"], ["12.50"]],
            [["合计"], ["73.50"]]
        ]
    ]
    
    # 构建文档
    document = build_document(
        path="test_budget_report.pdf",
        page_texts=test_page_texts,
        page_tables=test_page_tables,
        filesize=1024000
    )
    
    print(f"📄 测试文档构建完成")
    print(f"   页数: {len(test_page_texts)}")
    print(f"   表格数: {sum(len(tables) for tables in test_page_tables)}")
    
    # 测试关键规则
    key_rules = ["V33-001", "V33-002", "V33-110"]
    
    for rule_code in key_rules:
        print(f"\n🔍 测试规则 {rule_code}:")
        
        # 查找规则
        rule = None
        for r in ALL_RULES:
            if r.code == rule_code:
                rule = r
                break
        
        if not rule:
            print(f"  ❌ 规则未找到")
            continue
            
        print(f"  📋 规则描述: {rule.desc}")
        
        try:
            # 执行规则
            issues = rule.apply(document)
            print(f"  ✅ 执行成功，发现问题: {len(issues)}")
            
            for i, issue in enumerate(issues):
                print(f"    {i+1}. {issue.title}")
                if hasattr(issue, 'message'):
                    print(f"       {issue.message}")
                if hasattr(issue, 'page_number'):
                    print(f"       页面: {issue.page_number}")
                    
        except Exception as e:
            print(f"  ❌ 执行失败: {e}")
            import traceback
            traceback.print_exc()


async def test_ai_detection():
    """测试AI检测"""
    print("\n🤖 测试AI检测")
    print("=" * 50)
    
    # 创建测试文档数据
    test_doc = type('TestDoc', (), {})()
    test_doc.page_texts = [
        """2024年度上海市普陀区财政局部门决算
        
        第一部分 部门概况
        上海市普陀区财政局是主管全区财政工作的职能部门。
        
        第二部分 2024年度部门决算表
        包含收入支出决算总表、收入决算表、支出决算表等九张表格。
        
        第三部分 2024年度部门决算情况说明
        2024年度收入总计9930万元，支出总计9930万元。
        其中：基本支出850万元，项目支出9080万元。
        
        三公经费支出73.50万元，其中：因公出国15.20万元，
        公务用车45.80万元，公务接待12.50万元。""",
        
        """收入支出决算总表
        编制单位：上海市普陀区财政局
        2024年度
        金额单位：万元
        
        项目                 年初预算数    调整预算数    决算数
        一、一般公共预算财政拨款  8500.00     9200.00     9150.00
        二、政府性基金预算财政拨款   500.00      800.00      780.00
        三、国有资本经营预算财政拨款   0.00        0.00        0.00
        
        本年收入合计            9000.00    10000.00     9930.00
        支出总计               9000.00    10000.00     9930.00"""
    ]
    
    # 创建配置
    config = create_default_config()
    
    print("🧪 运行AI规则检测...")
    
    try:
        ai_findings = await run_ai_rules_batch(test_doc, config)
        print(f"✅ AI检测完成，发现问题: {len(ai_findings)}")
        
        for i, finding in enumerate(ai_findings):
            print(f"\n  {i+1}. {finding.title}")
            print(f"     严重程度: {finding.severity}")
            print(f"     消息: {finding.message}")
            print(f"     页面: {finding.page_number}")
            if finding.evidence:
                print(f"     证据: {finding.evidence}")
                
    except Exception as e:
        print(f"❌ AI检测失败: {e}")
        import traceback
        traceback.print_exc()


def analyze_detection_gap():
    """分析检测差距"""
    print("\n🔍 分析检测差距")
    print("=" * 50)
    
    print("📊 当前检测情况:")
    print("  1. AI检测: 能发现问题，但可能不够准确")
    print("  2. 规则检测: 执行正常但发现的问题较少")
    print("  3. 合并结果: 最终显示的问题数量偏少")
    
    print("\n🔍 可能的原因:")
    print("  1. 规则逻辑过于严格，导致漏检")
    print("  2. 文档解析不够准确，影响规则匹配")
    print("  3. AI检测阈值设置不当，误报或漏报")
    print("  4. 合并逻辑可能过滤了有效结果")
    
    print("\n💡 建议改进方向:")
    print("  1. 优化规则逻辑，提高检测敏感度")
    print("  2. 改进文档解析准确性")
    print("  3. 调整AI检测参数和阈值")
    print("  4. 优化结果合并算法")


async def main():
    """主函数"""
    print("🔍 深度分析检测问题")
    print("=" * 60)
    
    # 1. 分析样本文件
    analyze_sample_files()
    
    # 2. 分析规则实现
    analyze_rule_implementations()
    
    # 3. 详细测试规则执行
    test_rule_execution_detail()
    
    # 4. 测试AI检测
    await test_ai_detection()
    
    # 5. 分析检测差距
    analyze_detection_gap()
    
    print("\n✅ 分析完成！")


if __name__ == "__main__":
    asyncio.run(main())