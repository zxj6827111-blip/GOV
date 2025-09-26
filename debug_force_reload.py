#!/usr/bin/env python3
"""
强制重新加载规则 - 直接修改ALL_RULES
"""
import os
import sys
from pathlib import Path

# 将项目根目录添加到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 关键：在导入任何模块之前设置环境变量
os.environ["FOCUS_COMPARE_ONLY"] = "0"  # 禁用聚焦模式
os.environ["ENABLE_RULES"] = "ALL"    # 启用所有规则

def force_reload_rules():
    """强制重新加载规则"""
    print("=== 强制重新加载规则 ===")
    
    # 导入规则模块
    import engine.rules_v33 as rules_module
    
    # 重新计算 ALL_RULES
    rules_module.ALL_RULES = rules_module._resolve_active_rules()
    
    print(f"\n环境变量状态:")
    print(f"   FOCUS_COMPARE_ONLY: {os.environ.get('FOCUS_COMPARE_ONLY')}")
    print(f"   ENABLE_RULES: {os.environ.get('ENABLE_RULES')}")
    
    print(f"\n基础规则数量: {len(rules_module.ALL_RULES_BASE)}")
    print(f"活动规则数量: {len(rules_module.ALL_RULES)}")
    
    if len(rules_module.ALL_RULES) > 0:
        print("\n可用规则:")
        for rule in rules_module.ALL_RULES:
            print(f"   - {rule.code}: {rule.desc}")
        return rules_module.ALL_RULES
    else:
        print("\n⚠️  警告：活动规则仍然为空")
        print("\n手动检查 _resolve_active_rules() 逻辑:")
        
        # 手动调用解析函数
        active_rules = rules_module._resolve_active_rules()
        print(f"手动解析规则数量: {len(active_rules)}")
        
        # 检查基础规则
        print(f"\n基础规则列表:")
        for rule in rules_module.ALL_RULES_BASE:
            print(f"   - {rule.code}: {rule.desc}")
        
        # 检查环境变量影响
        enable_env = os.getenv("ENABLE_RULES", "")
        focus_compare = os.getenv("FOCUS_COMPARE_ONLY", "1").lower() in ("1", "true", "yes")
        
        print(f"\n解析逻辑检查:")
        print(f"   ENABLE_RULES: '{enable_env}'")
        print(f"   FOCUS_COMPARE_ONLY: {focus_compare}")
        
        if enable_env.strip():
            code_set = {x.strip() for x in enable_env.split(",") if x.strip()}
            print(f"   代码集合: {code_set}")
            matching_rules = [r for r in rules_module.ALL_RULES_BASE if r.code in code_set]
            print(f"   匹配规则数量: {len(matching_rules)}")
        
        return active_rules

def test_rule_execution(rules):
    """测试规则执行"""
    print("\n=== 测试规则执行 ===")
    
    from engine.rules_v33 import build_document
    
    # 创建测试文档
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
    
    print(f"\n测试文档信息:")
    print(f"   页数: {document.pages}")
    print(f"   主要年份: {document.dominant_year}")
    print(f"   主要单位: {document.dominant_unit}")
    
    # 测试具体规则
    test_rules = [
        ("V33-001", "封面年份单位检查"),
        ("V33-002", "九张表完整性检查"),
        ("V33-110", "预算决算一致性检查"),
    ]
    
    for rule_code, rule_desc in test_rules:
        print(f"\n测试 {rule_code} - {rule_desc}:")
        rule = next((r for r in rules if r.code == rule_code), None)
        
        if rule:
            try:
                issues = rule.apply(document)
                print(f"   ✓ 找到规则: {rule.code}")
                print(f"   ✓ 发现问题数量: {len(issues)}")
                
                if issues:
                    for i, issue in enumerate(issues[:3]):  # 只显示前3个问题
                        print(f"   问题 {i+1}: {issue.description}")
                    if len(issues) > 3:
                        print(f"   ... 还有 {len(issues) - 3} 个问题")
            except Exception as e:
                print(f"   ✗ 执行失败: {e}")
        else:
            print(f"   ✗ 未找到规则: {rule_code}")

def test_rule_mapping(rules):
    """测试规则代码映射"""
    print("\n=== 规则代码映射测试 ===")
    
    def normalize_rule_code(code: str) -> str:
        """模拟规则代码规范化"""
        if code.startswith("R") and len(code) == 6 and code[1:].isdigit():
            return f"V33-{int(code[1:]):03d}"
        return code
    
    test_codes = ["R33001", "R33002", "R33110", "V33-001", "V33-002", "V33-110"]
    
    print("\n规则代码映射:")
    for code in test_codes:
        normalized = normalize_rule_code(code)
        found = any(r.code == normalized for r in rules)
        print(f"   {code} -> {normalized} -> 找到: {found}")

if __name__ == "__main__":
    # 强制重新加载规则
    rules = force_reload_rules()
    
    if rules:
        # 测试规则执行
        test_rule_execution(rules)
        
        # 测试规则映射
        test_rule_mapping(rules)
    else:
        print("\n❌ 错误：无法加载任何规则！")