#!/usr/bin/env python3
"""
规则引擎详细调试工具
分析规则执行失败的具体原因
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from engine.core_rules_engine import CoreRulesEngine
from engine.table_name_matcher import TableNameMatcher, match_nine_tables
from engine.rules_v33 import ALL_RULES
from engine.v33_ruleset_loader import V33RuleExecutor, load_v33_ruleset
from services.engine_rule_runner import EngineRuleRunner
from schemas.issues import JobContext, AnalysisConfig

# 设置日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def debug_table_matcher():
    """调试表格匹配器"""
    print("=== 表格名称匹配器调试 ===")
    
    matcher = TableNameMatcher()
    
    # 测试文本（模拟实际的决算文档内容）
    test_texts = [
        # 第1页 - 目录
        """
        目录
        第一部分 部门概况
        第二部分 2024年度部门决算表
        一、收入支出决算总表
        二、收入决算表
        三、支出决算表
        四、财政拨款收入支出决算总表
        五、一般公共预算财政拨款支出决算表
        六、一般公共预算财政拨款基本支出决算表
        七、一般公共预算财政拨款"三公"经费支出决算表
        八、政府性基金预算财政拨款收入支出决算表
        九、国有资本经营预算财政拨款支出决算表
        """,
        # 第2页 - 收入支出决算总表
        """
        收入支出决算总表
        金额单位：万元
        
        项目 行次 金额
        一、收入合计 1 1000.00
        其中：财政拨款收入 2 800.00
        上级补助收入 3 0.00
        事业收入 4 150.00
        经营收入 5 0.00
        附属单位上缴收入 6 0.00
        其他收入 7 50.00
        
        二、支出合计 30 1000.00
        """,
        # 第3页 - 收入决算表
        """
        收入决算表
        金额单位：万元
        
        项目 行次 金额
        税收收入 1 800.00
        非税收入 2 150.00
        政府性基金收入 3 0.00
        国有资本经营收入 4 0.00
        社会保险基金收入 5 0.00
        其他收入 6 50.00
        
        本年收入合计 10 1000.00
        """
    ]
    
    print(f"测试文档页数: {len(test_texts)}")
    
    # 使用匹配器分析
    result = match_nine_tables(test_texts)
    
    print(f"\n找到表格数量: {result['summary']['total_found']}")
    print(f"完整度: {result['completeness']['completion_rate']:.2%}")
    print(f"缺失表格: {result['completeness']['missing_tables']}")
    
    print("\n找到的具体表格:")
    for table in result['found_tables']:
        match_type = table.get('match_type', 'unknown')
        print(f"  - {table['standard_name']} (置信度: {table['confidence']:.1f}%, 匹配方式: {match_type})")
    
    print("\n按类别统计:")
    for category, stats in result['completeness']['category_stats'].items():
        print(f"  {category}: {stats['found']}/{stats['total']} ({stats['found']/stats['total']:.1%})")


async def debug_core_rules():
    """调试核心规则引擎"""
    print("\n=== 核心规则引擎调试 ===")
    
    engine = CoreRulesEngine()
    
    # 模拟文档数据
    document_data = {
        "pages_text": [
            """
            目录
            第一部分 部门概况
            第二部分 2024年度部门决算表
            一、收入支出决算总表
            二、收入决算表
            三、支出决算表
            """,
            """
            收入支出决算总表
            金额单位：万元
            
            项目 行次 金额
            一、收入合计 1 1000.00
            其中：财政拨款收入 2 800.00
            上级补助收入 3 0.00
            事业收入 4 150.00
            经营收入 5 0.00
            附属单位上缴收入 6 0.00
            其他收入 7 50.00
            
            二、支出合计 30 1000.00
            """
        ],
        "tables": [
            {
                "name": "收入支出决算总表",
                "page": 2,
                "data": [
                    ["项目", "行次", "金额"],
                    ["一、收入合计", "1", "1000.00"],
                    ["其中：财政拨款收入", "2", "800.00"],
                    ["事业收入", "4", "150.00"],
                    ["其他收入", "7", "50.00"],
                    ["二、支出合计", "30", "1000.00"]
                ]
            }
        ]
    }
    
    print("执行核心规则验证...")
    results = engine.validate_all(document_data)
    
    print(f"\n核心规则验证结果数量: {len(results)}")
    for result in results:
        print(f"\n规则: {result.rule_id} - {result.rule_name}")
        print(f"  有效性: {result.is_valid}")
        print(f"  严重程度: {result.severity}")
        print(f"  消息: {result.message}")
        print(f"  证据: {result.evidence}")
        print(f"  页码: {result.page_numbers}")


async def debug_all_rules():
    """调试所有规则"""
    print("\n=== 所有规则调试 ===")
    
    print(f"总规则数量: {len(ALL_RULES)}")
    
    # 显示所有可用规则
    print("\n可用规则列表:")
    for rule in ALL_RULES:
        print(f"  - {rule.code}: {getattr(rule, 'title', '无标题')}")
        if hasattr(rule, 'description'):
            print(f"    描述: {rule.description}")


async def debug_engine_rule_runner():
    """调试引擎规则运行器"""
    print("\n=== 引擎规则运行器调试 ===")
    
    runner = EngineRuleRunner()
    
    # 创建测试上下文
    job_context = JobContext(
        job_id="test_job_001",
        pdf_path="test_sample.pdf",
        user_id="test_user"
    )
    
    # 创建测试配置
    config = AnalysisConfig(
        exclude_budget_content=True,
        record_rule_failures=True
    )
    
    # 测试规则列表（模拟实际规则）
    test_rules = [
        {
            "id": "R33002",
            "code": "V33-002",
            "title": "九张表完整性检查",
            "description": "检查是否包含所有必要的决算表格"
        },
        {
            "id": "R33110", 
            "code": "V33-110",
            "title": "预算决算一致性检查",
            "description": "检查预算与决算数据的一致性"
        }
    ]
    
    print("执行规则测试...")
    try:
        findings = await runner.run_rules(job_context, test_rules, config)
        print(f"规则执行结果数量: {len(findings)}")
        
        for finding in findings:
            print(f"\n发现项:")
            print(f"  ID: {finding.id}")
            print(f"  规则ID: {finding.rule_id}")
            print(f"  严重程度: {finding.severity}")
            print(f"  标题: {finding.title}")
            print(f"  消息: {finding.message}")
            print(f"  证据: {finding.evidence}")
            
    except Exception as e:
        print(f"规则执行失败: {e}")
        import traceback
        traceback.print_exc()


async def debug_v33_ruleset():
    """调试V3.3规则集"""
    print("\n=== V3.3规则集调试 ===")
    
    # 首先检查YAML文件格式
    print("检查YAML文件格式...")
    try:
        import yaml
        with open("rules/v3_3_all_in_one.yaml", "r", encoding="utf-8") as f:
            # 使用safe_load_all处理多文档YAML
            docs = list(yaml.safe_load_all(f))
            print(f"YAML文件包含 {len(docs)} 个文档")
            
            for i, doc in enumerate(docs):
                print(f"文档 {i+1} 类型: {type(doc)}")
                if isinstance(doc, dict):
                    print(f"  键: {list(doc.keys())}")
                    if 'meta' in doc:
                        print(f"  元数据版本: {doc['meta'].get('version', 'unknown')}")
                    elif 'tables_aliases' in doc:
                        print(f"  表格别名数量: {len(doc['tables_aliases'])}")
                    elif 'checks' in doc:
                        print(f"  检查规则数量: {len(doc['checks'])}")
    except Exception as e:
        print(f"YAML文件检查失败: {e}")
        return
    
    # 加载规则集
    loader = load_v33_ruleset("rules/v3_3_all_in_one.yaml")
    
    if loader:
        print("规则集加载成功")
        print(f"规则数量: {len(loader.rules)}")
        print(f"表格别名: {len(loader.table_aliases)}")
        
        # 显示规则详情
        for rule_id, rule in loader.rules.items():
            print(f"规则 {rule_id}: {rule.name}")
            print(f"  描述: {rule.desc}")
            print(f"  严重程度: {rule.severity}")
            print(f"  Profile: {rule.profile}")
    else:
        print("规则集加载失败")


async def main():
    """主调试函数"""
    print("开始规则引擎详细调试...")
    
    try:
        # 1. 调试表格匹配器
        await debug_table_matcher()
        
        # 2. 调试核心规则引擎
        await debug_core_rules()
        
        # 3. 调试所有规则
        await debug_all_rules()
        
        # 4. 调试引擎规则运行器
        await debug_engine_rule_runner()
        
        # 5. 调试V3.3规则集
        await debug_v33_ruleset()
        
    except Exception as e:
        print(f"调试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())