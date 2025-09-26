#!/usr/bin/env python3
"""
简化调试脚本 - 直接测试规则执行
"""
import os
import sys
from pathlib import Path

# 将项目根目录添加到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 关键：在导入任何模块之前设置环境变量
os.environ["FOCUS_COMPARE_ONLY"] = "0"  # 禁用聚焦模式
os.environ["ENABLE_RULES"] = "ALL"       # 启用所有规则

from engine.rules_v33 import ALL_RULES, build_document

def test_rules_directly():
    """直接测试规则执行"""
    print("=== 直接规则测试 ===")
    
    print(f"\n1. 环境变量设置:")
    print(f"   FOCUS_COMPARE_ONLY: {os.environ.get('FOCUS_COMPARE_ONLY')}")
    print(f"   ENABLE_RULES: {os.environ.get('ENABLE_RULES')}")
    
    print(f"\n2. 加载的规则数量: {len(ALL_RULES)}")
    print("   可用规则:")
    for rule in ALL_RULES:
        print(f"     - {rule.code}: {rule.desc}")
    
    # 创建测试文档
    print(f"\n3. 创建测试文档:")
    page_texts = [
        "2024年度上海市财政局部门决算\n单位：万元\n目录\n一、收入支出决算总表\n二、收入决算表\n三、支出决算表",
        "收入支出决算总表\n项目\n年初预算数\n调整预算数\n决算数\n支出总计\n1000.00\n1200.00\n1300.00",
        "三公经费支出表\n因公出国(境)费\n0.00\n公务用车购置及运行维护费\n50.00\n公务接待费\n20.00",
    ]
    
    page_tables = [
        [],  # 第1页没有表格
        [   # 第2页表格
            [["项目"], ["年初预算数"], ["调整预算数"], ["决算数"]],
            [["支出总计"], ["1000.00"], ["1200.00"], ["1300.00"]],
        ],
        [   # 第3页表格
            [["三公经费项目"], ["决算数"]],
            [["因公出国(境)费"], ["0.00"]],
            [["公务用车购置及运行维护费"], ["50.00"]],
            [["公务接待费"], ["20.00"]],
        ],
    ]
    
    # 确保page_tables与page_texts长度一致
    while len(page_tables) < len(page_texts):
        page_tables.append([])
    
    document = build_document(
        path="test_document.pdf",
        page_texts=page_texts,
        page_tables=page_tables,
        filesize=1024000
    )
    
    print(f"   文档路径: {document.path}")
    print(f"   页数: {document.pages}")
    print(f"   主要年份: {document.dominant_year}")
    print(f"   主要单位: {document.dominant_unit}")
    print(f"   表格锚点: {document.anchors}")
    
    # 测试具体规则
    print(f"\n4. 测试具体规则:")
    
    # 测试 R33001 - 封面年份单位检查
    print(f"\n   测试 R33001 (V33-001) - 封面年份单位检查:")
    rule_33001 = next((r for r in ALL_RULES if r.code == "V33-001"), None)
    if rule_33001:
        issues_33001 = rule_33001.apply(document)
        print(f"     找到规则: {rule_33001.code} - {rule_33001.desc}")
        print(f"     发现问题数量: {len(issues_33001)}")
        for issue in issues_33001:
            print(f"     问题: {issue.description}")
    else:
        print(f"     错误: 未找到 V33-001 规则")
    
    # 测试 R33002 - 九张表完整性检查
    print(f"\n   测试 R33002 (V33-002) - 九张表完整性检查:")
    rule_33002 = next((r for r in ALL_RULES if r.code == "V33-002"), None)
    if rule_33002:
        issues_33002 = rule_33002.apply(document)
        print(f"     找到规则: {rule_33002.code} - {rule_33002.desc}")
        print(f"     发现问题数量: {len(issues_33002)}")
        for issue in issues_33002:
            print(f"     问题: {issue.description}")
    else:
        print(f"     错误: 未找到 V33-002 规则")
    
    # 测试 R33110 - 预算决算一致性检查
    print(f"\n   测试 R33110 (V33-110) - 预算决算一致性检查:")
    rule_33110 = next((r for r in ALL_RULES if r.code == "V33-110"), None)
    if rule_33110:
        issues_33110 = rule_33110.apply(document)
        print(f"     找到规则: {rule_33110.code} - {rule_33110.desc}")
        print(f"     发现问题数量: {len(issues_33110)}")
        for issue in issues_33110:
            print(f"     问题: {issue.description}")
    else:
        print(f"     错误: 未找到 V33-110 规则")

def test_rule_mapping():
    """测试规则代码映射"""
    print("\n=== 规则代码映射测试 ===")
    
    # 模拟 EngineRuleRunner 的代码规范化
    def normalize_rule_code(code: str) -> str:
        """模拟规则代码规范化"""
        if code.startswith("R") and len(code) == 6 and code[1:].isdigit():
            return f"V33-{int(code[1:]):03d}"
        return code
    
    test_codes = ["R33001", "R33002", "R33110", "V33-001", "V33-002", "V33-110"]
    
    print("\n规则代码映射:")
    for code in test_codes:
        normalized = normalize_rule_code(code)
        found = any(r.code == normalized for r in ALL_RULES)
        print(f"   {code} -> {normalized} -> 找到: {found}")

if __name__ == "__main__":
    test_rules_directly()
    test_rule_mapping()