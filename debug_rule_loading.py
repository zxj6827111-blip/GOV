#!/usr/bin/env python3
"""
规则加载调试脚本 - 详细检查规则加载过程
"""
import os
import sys
import yaml
from pathlib import Path

# 将项目根目录添加到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from engine.rules_v33 import ALL_RULES_BASE, _resolve_active_rules, ALL_RULES

def debug_rule_loading():
    """详细调试规则加载过程"""
    print("=== 规则加载调试 ===")
    
    # 1. 检查环境变量
    print("\n1. 环境变量状态:")
    print(f"   ENABLE_RULES: {os.getenv('ENABLE_RULES', '未设置')}")
    print(f"   FOCUS_COMPARE_ONLY: {os.getenv('FOCUS_COMPARE_ONLY', '未设置')}")
    
    # 2. 检查基础规则
    print(f"\n2. 基础规则数量: {len(ALL_RULES_BASE)}")
    print("   基础规则代码:")
    for rule in ALL_RULES_BASE:
        print(f"     - {rule.code}: {rule.desc}")
    
    # 3. 检查活动规则
    print(f"\n3. 活动规则数量: {len(ALL_RULES)}")
    print("   活动规则代码:")
    for rule in ALL_RULES:
        print(f"     - {rule.code}: {rule.desc}")
    
    # 4. 手动测试解析函数
    print("\n4. 手动测试 _resolve_active_rules:")
    
    # 测试默认情况
    os.environ.pop('ENABLE_RULES', None)
    os.environ['FOCUS_COMPARE_ONLY'] = '1'
    rules_default = _resolve_active_rules()
    print(f"   FOCUS_COMPARE_ONLY=1 时规则数量: {len(rules_default)}")
    print(f"   规则代码: {[r.code for r in rules_default]}")
    
    # 测试启用所有规则
    os.environ['FOCUS_COMPARE_ONLY'] = '0'
    rules_all = _resolve_active_rules()
    print(f"   FOCUS_COMPARE_ONLY=0 时规则数量: {len(rules_all)}")
    print(f"   规则代码: {[r.code for r in rules_all]}")
    
    # 测试指定规则
    os.environ['ENABLE_RULES'] = 'V33-001,V33-002,V33-110'
    rules_specified = _resolve_active_rules()
    print(f"   ENABLE_RULES='V33-001,V33-002,V33-110' 时规则数量: {len(rules_specified)}")
    print(f"   规则代码: {[r.code for r in rules_specified]}")

if __name__ == "__main__":
    debug_rule_loading()