#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
详细调试引擎规则执行
分析规则执行失败的具体原因
"""

import asyncio
import logging
from pathlib import Path
import json

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from engine.v33_ruleset_loader import load_v33_ruleset, V33RuleExecutor
from engine.rules_v33 import Document, Issue, build_document, ALL_RULES
from services.engine_rule_runner import EngineRuleRunner
from schemas.issues import JobContext, AnalysisConfig


async def debug_engine_rules():
    """详细调试引擎规则执行"""
    print("=== 引擎规则执行详细调试 ===\n")
    
    # 1. 检查可用的规则
    print("1. 检查可用规则:")
    print(f"ALL_RULES 数量: {len(ALL_RULES)}")
    for rule in ALL_RULES:
        print(f"  - {rule.code}: {rule.desc}")
    
    # 2. 加载V3.3规则集
    print("\n2. 加载V3.3规则集:")
    loader = load_v33_ruleset("rules/v3_3_all_in_one.yaml")
    if loader:
        print(f"规则集加载成功: {len(loader.rules)} 条规则")
        print("规则列表:")
        for rule_id, rule in loader.rules.items():
            print(f"  - {rule_id}: {rule.name}")
    else:
        print("规则集加载失败")
        return
    
    # 3. 创建测试文档数据
    print("\n3. 创建测试文档数据:")
    
    # 模拟真实的决算文档内容
    test_page_texts = [
        # 第1页 - 封面/目录
        """
        2024年度部门决算公开报告
        
        目录
        一、收入支出决算总表..............................3
        二、收入决算表..................................4  
        三、支出决算表..................................5
        四、财政拨款收入支出决算总表......................6
        五、一般公共预算财政拨款支出决算表................7
        六、一般公共预算财政拨款基本支出决算表............8
        七、一般公共预算财政拨款"三公"经费支出决算表.......9
        八、政府性基金预算财政拨款收入支出决算表..........10
        九、国有资本经营预算财政拨款收入支出决算表........11
        
        单位：万元
        """,
        
        # 第2页 - 收入支出决算总表
        """
        收入支出决算总表
        
        项目             行次    决算数        项目            行次    决算数
        栏次                     1            栏次                   2
        一、一般公共预算财政拨款收入   1    5,000.00    一、一般公共服务支出     29   3,000.00
        二、政府性基金预算财政拨款收入  2    2,000.00    二、外交支出             30     500.00
        三、国有资本经营预算财政拨款收入 3      800.00    三、国防支出             31     200.00
        
        本年收入合计            9    7,800.00    本年支出合计            37   7,800.00
        
        单位：万元
        """,
        
        # 第3页 - 收入决算表
        """
        收入决算表
        
        项目             本年收入合计    财政拨款收入    上级补助收入
        栏次                  1             2             3
        一般公共服务支出       3,000.00      3,000.00        0.00
        外交支出               500.00        500.00        0.00
        国防支出               200.00        200.00        0.00
        
        单位：万元
        """,
        
        # 第4页 - 支出决算表  
        """
        支出决算表
        
        项目             本年支出合计    基本支出      项目支出
        栏次                  1             2             3
        一般公共服务支出       3,000.00      2,000.00      1,000.00
        外交支出               500.00        300.00        200.00
        国防支出               200.00        150.00         50.00
        
        单位：万元
        """
    ]
    
    # 创建文档对象
    document = build_document(
        path="test_document.pdf",
        page_texts=test_page_texts,
        page_tables=[[] for _ in range(len(test_page_texts))],  # 空表格数据
        filesize=1024 * 1024  # 1MB
    )
    
    print(f"创建测试文档: {document.path}")
    print(f"页数: {document.pages}")
    print(f"文件大小: {document.filesize} bytes")
    
    # 4. 测试单个规则执行
    print("\n4. 测试单个规则执行:")
    
    # 测试V33规则
    test_rules = ["V33-001", "V33-002", "V33-003", "V33-007"]
    
    executor = V33RuleExecutor(loader)
    
    for rule_id in test_rules:
        rule = loader.rules.get(rule_id)
        if rule:
            print(f"\n执行规则 {rule_id}: {rule.name}")
            
            # 准备文档数据
            document_data = {
                "pages_text": test_page_texts,
                "pages": len(test_page_texts),
                "filesize": 1024 * 1024,
                "page_tables": [[] for _ in range(len(test_page_texts))]
            }
            
            try:
                result = executor.execute_rule(rule, document_data)
                print(f"  执行状态: {result.get('status', 'unknown')}")
                print(f"  发现问题: {len(result.get('findings', []))}")
                
                for finding in result.get('findings', []):
                    print(f"    - {finding.get('message', '未知问题')}")
                    
            except Exception as e:
                print(f"  执行失败: {e}")
                import traceback
                traceback.print_exc()
    
    # 5. 测试引擎规则运行器
    print("\n5. 测试引擎规则运行器:")
    
    # 创建JobContext
    job_context = JobContext(
        job_id="test_debug_job",
        pdf_path="test_document.pdf",
        pages=len(test_page_texts),
        ocr_text="\n".join(test_page_texts),
        tables=[],
        meta={
            "page_texts": test_page_texts,
            "page_tables": [[] for _ in range(len(test_page_texts))]
        }
    )
    
    # 创建规则配置
    rules_config = [
        {"id": "R33001", "code": "R33001", "title": "封面年份单位检查"},
        {"id": "R33002", "code": "R33002", "title": "九张表检查"},
        {"id": "R33110", "code": "R33110", "title": "测试规则"}
    ]
    
    config = AnalysisConfig()
    config.record_rule_failures = True
    
    runner = EngineRuleRunner()
    
    try:
        findings = await runner.run_rules(job_context, rules_config, config)
        print(f"引擎规则执行完成，发现问题: {len(findings)}")
        
        for finding in findings:
            print(f"  - {finding.rule_id}: {finding.title}")
            if finding.message:
                print(f"    消息: {finding.message}")
                
    except Exception as e:
        print(f"引擎规则运行器执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 6. 分析失败原因
    print("\n6. 分析失败原因:")
    stats = runner.get_stats()
    print(f"总规则数: {stats.get('total_rules', 0)}")
    print(f"成功规则: {stats.get('successful_rules', 0)}")
    print(f"失败规则: {stats.get('failed_rules', 0)}")
    print(f"总发现问题: {stats.get('total_findings', 0)}")
    
    # 7. 检查规则映射问题
    print("\n7. 检查规则映射问题:")
    print("可用的规则代码:")
    for rule in ALL_RULES:
        print(f"  - {rule.code}: {rule.desc}")
    
    print("\n规则ID映射测试:")
    test_ids = ["R33001", "R33002", "V33-001", "V33-002"]
    for test_id in test_ids:
        normalized = runner._normalize_rule_code(test_id)
        print(f"  {test_id} -> {normalized}")
        
        # 检查是否存在对应的规则
        found = False
        for rule in ALL_RULES:
            if rule.code == normalized or normalized in rule.code:
                print(f"    找到对应规则: {rule.code}")
                found = True
                break
        
        if not found:
            print(f"    未找到对应规则")


if __name__ == "__main__":
    asyncio.run(debug_engine_rules())