#!/usr/bin/env python3
"""
V33-002规则修复方案
解决"表出现多次"误报问题
"""

import os
import sys
from pathlib import Path

# 备份原始文件
original_file = "engine/rules_v33.py"
backup_file = "engine/rules_v33.py.backup"

print("🔧 V33-002规则修复工具")
print("=" * 50)

# 检查文件是否存在
if not os.path.exists(original_file):
    print(f"❌ 文件不存在: {original_file}")
    sys.exit(1)

# 创建备份
import shutil
shutil.copy(original_file, backup_file)
print(f"✅ 已创建备份: {backup_file}")

# 读取原始文件
with open(original_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 修复V33-002规则
old_logic = """        # 重复
        for nm, pgs in duplicates:
            issues.append(
                self._issue(
                    f"表出现多次：{nm}（页码 {pgs}）", {"table": nm, "pages": pgs}, severity="warn"
                )
            )"""

new_logic = """        # 重复（修复：降低误报，只有真正异常才报告）
        for nm, pgs in duplicates:
            # 智能判断：只有在同一页面重复，或者页面间隔过小（<2页）才认为是异常
            if len(pgs) > 2:  # 出现3次及以上才报告
                # 检查页面间隔
                sorted_pages = sorted(pgs)
                min_gap = min(sorted_pages[i+1] - sorted_pages[i] for i in range(len(sorted_pages)-1))
                if min_gap <= 2:  # 页面间隔过小，可能是异常
                    issues.append(
                        self._issue(
                            f"表出现多次且页面间隔过小：{nm}（页码 {pgs}）", 
                            {"table": nm, "pages": pgs}, 
                            severity="info"  # 降低为信息级别
                        )
                    )
            elif max(pgs) - min(pgs) <= 3:  # 集中在少数几页内
                issues.append(
                    self._issue(
                        f"表在相邻页面重复出现：{nm}（页码 {pgs}）", 
                        {"table": nm, "pages": pgs}, 
                        severity="info"  # 降低为信息级别
                    )
                )"""

# 应用修复
if old_logic in content:
    content = content.replace(old_logic, new_logic)
    print("✅ 已修复V33-002规则的重复检测逻辑")
else:
    print("⚠️  未找到原始逻辑，可能需要手动修复")

# 保存修复后的文件
with open(original_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ 修复完成！")
print("\n修复内容：")
print("1. 增加智能判断逻辑，区分正常多页展示 vs 异常重复")
print("2. 将警告级别从'warn'降低为'info'，减少用户困扰")
print("3. 只在真正异常的情况下才报告问题")

print(f"\n📋 验证修复效果：")
print(f"运行: python diagnose_rule_issues.py")
print(f"对比修复前后的检测结果差异")