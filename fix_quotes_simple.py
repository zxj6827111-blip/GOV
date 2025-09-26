#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单有效的引号修复脚本
"""

import glob
import os


def fix_quotes_in_file(file_path):
    """修复单个文件中的引号问题"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # 1. 修复四个引号开头的docstring
        content = content.replace('""""', '"""')

        # 2. 修复装饰器后的多余引号
        content = content.replace(')"', ")")
        content = content.replace(")'", ")")

        # 3. 修复docstring结尾的多余引号
        content = content.replace('""""', '"""')

        # 4. 修复行尾的多余引号（但保留字符串内的引号）
        lines = content.split("\n")
        fixed_lines = []

        for line in lines:
            # 如果行以单独的引号结尾，移除它
            if (
                line.strip().endswith('"')
                and not line.strip().endswith('""')
                and line.count('"') % 2 == 1
            ):
                line = line.rstrip('"')
            if (
                line.strip().endswith("'")
                and not line.strip().endswith("''")
                and line.count("'") % 2 == 1
            ):
                line = line.rstrip("'")

            fixed_lines.append(line)

        content = "\n".join(fixed_lines)

        if content != original_content:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✓ 修复了 {file_path}")
            return True
        else:
            print(f"- 跳过 {file_path} (无需修复)")
            return False

    except Exception as e:
        print(f"✗ 处理 {file_path} 时出错: {e}")
        return False


def main():
    """主函数"""
    tests_dir = "tests"
    if not os.path.exists(tests_dir):
        print(f"错误: {tests_dir} 目录不存在")
        return

    # 查找所有Python测试文件
    test_files = glob.glob(os.path.join(tests_dir, "*.py"))

    print(f"找到 {len(test_files)} 个测试文件")

    fixed_count = 0
    for file_path in test_files:
        if fix_quotes_in_file(file_path):
            fixed_count += 1

    print(f"\n总结: 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()