#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复所有测试文件中的多余引号问题
"""

import glob
import os
import re


def fix_quotes_in_file(file_path):
    """修复单个文件中的多余引号"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # 修复多余的引号问题
        # 1. 修复四个引号开头的文件
        content = re.sub(r'^""""', '"""', content, flags=re.MULTILINE)

        # 2. 修复函数/类定义后的多余引号
        content = re.sub(r'(def\s+\w+\([^)]*\):)\s*""""', r'\1\n    """', content)
        content = re.sub(r'(class\s+\w+[^:]*:)\s*""""', r'\1\n    """', content)

        # 3. 修复docstring结尾的多余引号
        content = re.sub(r'"""([^"]*?)""""', r'"""\1"""', content)

        # 4. 修复行尾的多余引号
        content = re.sub(r'""""$', '"""', content, flags=re.MULTILINE)

        # 5. 修复fixture定义后的多余引号
        content = re.sub(r'(@pytest\.fixture[^)]*\))\s*"([^"]*)"', r"\1\ndef \2():", content)

        # 6. 修复return语句后的多余引号
        content = re.sub(r'return\s+""""', 'return """', content)

        # 7. 修复变量赋值后的多余引号
        content = re.sub(r'=\s+""""', '= """', content)

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
