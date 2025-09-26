#!/usr/bin/env python3
"""
规则检测问题诊断脚本
用于分析为什么规则检测在正常文件上发现过多问题
"""

import asyncio
import os
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from engine.rules_v33 import Document, R33003_PageFileThreshold, R33002_NineTablesCheck, R33001_CoverYearUnit
import pdfplumber


async def analyze_pdf_rules(pdf_path: str):
    """分析PDF文件的规则检测情况"""
    print(f"\n📊 分析文件: {os.path.basename(pdf_path)}")
    print("=" * 60)
    
    # 解析PDF
    try:
        # 使用pdfplumber解析PDF
        page_texts = []
        page_tables = []
        units_per_page = []
        years_per_page = []
        
        with pdfplumber.open(pdf_path) as pdf:
            pages = len(pdf.pages)
            filesize = os.path.getsize(pdf_path)
            
            for page in pdf.pages:
                # 提取文本
                text = page.extract_text() or ""
                page_texts.append(text)
                
                # 提取表格
                tables = page.extract_tables() or []
                page_tables.append(tables)
                
                # 提取单位和年份（简单的正则匹配）
                import re
                unit_match = re.search(r'单位[:：]\s*(万元|元|亿元)', text)
                units_per_page.append(unit_match.group(1) if unit_match else None)
                
                year_matches = re.findall(r'(?<!\d)(20\d{2})(?:(?:\s*年(?:度)?)|(?=\D))', text)
                years_per_page.append([int(y) for y in year_matches])
        
        print(f"📄 页数: {pages}")
        print(f"📦 文件大小: {filesize / 1024 / 1024:.2f} MB")
        print(f"📋 表格数量: {sum(len(tables) for tables in page_tables)}")
        
        # 创建文档对象
        doc = Document(
            path=pdf_path,
            pages=pages,
            filesize=filesize,
            page_texts=page_texts,
            page_tables=page_tables,
            units_per_page=units_per_page,
            years_per_page=years_per_page
        )
        
        # 测试各个规则
        rules = [
            ("V33-001", "封面年份单位检查", R33001_CoverYearUnit()),
            ("V33-002", "九张表定位缺失重复", R33002_NineTablesCheck()),
            ("V33-003", "页数文件大小阈值", R33003_PageFileThreshold()),
        ]
        
        all_issues = []
        
        for rule_code, rule_name, rule in rules:
            print(f"\n🔍 测试规则: {rule_code} - {rule_name}")
            try:
                issues = rule.apply(doc)
                print(f"   发现问题: {len(issues)}")
                
                for i, issue in enumerate(issues, 1):
                    print(f"   {i}. {issue.message} (严重程度: {issue.severity})")
                    if issue.location:
                        print(f"      位置: {issue.location}")
                    
                    all_issues.append({
                        'rule': rule_code,
                        'rule_name': rule_name,
                        'message': issue.message,
                        'severity': issue.severity,
                        'location': issue.location
                    })
                    
            except Exception as e:
                print(f"   ❌ 规则执行失败: {e}")
        
        # 总结
        print(f"\n📈 总结分析")
        print("=" * 40)
        print(f"总问题数: {len(all_issues)}")
        
        # 按规则统计
        rule_stats = {}
        for issue in all_issues:
            rule = issue['rule']
            if rule not in rule_stats:
                rule_stats[rule] = 0
            rule_stats[rule] += 1
        
        print("\n按规则统计:")
        for rule, count in rule_stats.items():
            print(f"  {rule}: {count} 个问题")
        
        # 按严重程度统计
        severity_stats = {}
        for issue in all_issues:
            severity = issue['severity']
            if severity not in severity_stats:
                severity_stats[severity] = 0
            severity_stats[severity] += 1
        
        print("\n按严重程度统计:")
        for severity, count in severity_stats.items():
            print(f"  {severity}: {count} 个问题")
        
        return all_issues
        
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        return []


async def main():
    """主函数"""
    print("🔧 规则检测问题诊断工具")
    print("=" * 60)
    
    # 测试文件列表
    test_files = [
        "samples/bad/中共上海市普陀区委社会工作部 2024 年度部门决算.pdf",
        "samples/good/上海市普陀区财政局2024年度部门决算.pdf",
    ]
    
    results = {}
    
    for pdf_file in test_files:
        pdf_path = os.path.join(os.path.dirname(__file__), pdf_file)
        if os.path.exists(pdf_path):
            issues = await analyze_pdf_rules(pdf_path)
            results[pdf_file] = issues
        else:
            print(f"❌ 文件不存在: {pdf_path}")
    
    # 对比分析
    print(f"\n\n📊 对比分析")
    print("=" * 60)
    
    for filename, issues in results.items():
        print(f"\n文件: {os.path.basename(filename)}")
        print(f"总问题数: {len(issues)}")
        
        # 关键问题识别
        error_count = sum(1 for issue in issues if issue['severity'] == 'error')
        warn_count = sum(1 for issue in issues if issue['severity'] == 'warn')
        info_count = sum(1 for issue in issues if issue['severity'] == 'info')
        
        print(f"错误: {error_count}, 警告: {warn_count}, 信息: {info_count}")
        
        # 显示关键问题
        if error_count > 0:
            print("关键错误:")
            for issue in issues:
                if issue['severity'] == 'error':
                    print(f"  - {issue['rule']}: {issue['message']}")


if __name__ == "__main__":
    asyncio.run(main())