#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试双模式分析器的AI检测问题
"""

import asyncio
import sys
import json
import time
sys.path.append('.')

from services.analyze_dual import DualModeAnalyzer
from schemas.issues import AnalysisConfig, JobContext
from pathlib import Path

async def debug_dual_mode():
    print('🔍 调试双模式分析器')
    print('=' * 50)
    
    # 创建分析器和配置
    analyzer = DualModeAnalyzer()
    config = AnalysisConfig()
    
    print(f'配置信息:')
    print(f'  - AI启用: {config.ai_enabled}')
    print(f'  - 规则启用: {config.rule_enabled}')
    print(f'  - 双模式启用: {config.dual_mode}')
    print(f'  - AI分析启用: {config.enable_ai_analysis}')
    print()
    
    # 测试规则加载
    print('📋 测试规则加载...')
    rules = await analyzer._load_rules(config.rules_version)
    print(f'总规则数量: {len(rules)}')
    
    ai_rules, engine_rules = analyzer._separate_rules(rules)
    print(f'AI规则数量: {len(ai_rules)}')
    print(f'引擎规则数量: {len(engine_rules)}')
    
    if ai_rules:
        print('\nAI规则列表:')
        for rule in ai_rules[:3]:
            rule_id = rule.get('code', '未知ID')
            title = rule.get('desc', '未知标题')
            print(f'  - {rule_id}: {title}')
    print()
    
    # 创建测试上下文
    context = JobContext(
        job_id='debug-dual-001',
        pdf_path='samples/bad/中共上海市普陀区委社会工作部 2024 年度部门决算.pdf',
        pages=10,
        ocr_text='''
        2024年度部门决算说明
        
        一、一般公共预算收入执行情况
        预算数：1000万元，实际完成：800万元，完成率：80%
        
        二、一般公共预算支出执行情况  
        预算数：1200万元，实际支出：1300万元，超支：100万元
        
        三、三公经费支出情况
        预算数：50万元，实际支出：80万元，超支率：60%
        
        四、政府采购执行情况
        预算数：200万元，实际采购：180万元
        ''',
        tables=[],
        meta={'document_type': '部门决算', 'year': '2024'}
    )
    
    print('🧪 测试双模式分析...')
    start_time = time.time()
    
    try:
        # 调用双模式分析
        result = await analyzer.analyze(context, config)
        
        elapsed = time.time() - start_time
        print(f'✅ 双模式分析完成，耗时: {elapsed:.2f}s')
        print()
        
        # 显示结果统计
        print('📊 分析结果统计:')
        print(f'  - AI检测问题: {len(result.ai_findings)} 个')
        print(f'  - 规则检测问题: {len(result.rule_findings)} 个')
        merged_total = result.merged.totals.get("total", 0) if result.merged else 0
        print(f'  - 合并后问题: {merged_total} 个')
        print()
        
        # 显示性能统计
        if result.meta and 'performance' in result.meta:
            perf = result.meta['performance']
            print('⏱️ 性能统计:')
            print(f'  - AI检测耗时: {perf.get("ai_elapsed_ms", 0)}ms')
            print(f'  - 规则检测耗时: {perf.get("rule_elapsed_ms", 0)}ms')
            print(f'  - 总耗时: {perf.get("total_elapsed_ms", 0)}ms')
            print()
        
        # 显示AI检测结果
        if result.ai_findings:
            print('🤖 AI检测到的问题:')
            for i, issue in enumerate(result.ai_findings[:3], 1):
                print(f'  {i}. {issue.title} (严重程度: {issue.severity})')
                print(f'     描述: {issue.message[:100]}...' if len(issue.message) > 100 else f'     描述: {issue.message}')
        else:
            print('❌ AI检测没有发现问题')
        print()
        
        # 显示规则检测结果
        if result.rule_findings:
            print('📋 规则检测到的问题:')
            for i, issue in enumerate(result.rule_findings[:3], 1):
                print(f'  {i}. {issue.title} (严重程度: {issue.severity})')
        else:
            print('❌ 规则检测没有发现问题')
        print()
        
        # 检查AI分析是否被执行
        ai_elapsed = result.meta.get('performance', {}).get('ai_elapsed_ms', 0) if result.meta else 0
        if ai_elapsed == 0:
            print('⚠️  警告: AI检测耗时为0ms，AI分析可能没有被执行')
            
            # 检查AI服务状态
            print('🔍 检查AI服务状态...')
            if hasattr(analyzer, 'ai_service') and analyzer.ai_service:
                print('  - AI服务已初始化')
            else:
                print('  - AI服务未初始化')
                
            # 检查配置
            print('🔍 检查配置状态...')
            print(f'  - AI规则数量: {len(ai_rules)}')
            print(f'  - enable_ai_analysis: {config.enable_ai_analysis}')
            print(f'  - ai_enabled: {config.ai_enabled}')
        else:
            print('✅ AI检测正常执行')
            
    except Exception as e:
        print(f'❌ 双模式分析失败: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(debug_dual_mode())