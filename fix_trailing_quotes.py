#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复所有测试文件中的尾随单引号问题
"""

import glob
import os
import re


def fix_trailing_quotes_in_file(file_path):
    """修复单个文件中的尾随单引号"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # 修复字典/列表中的尾随单引号问题
        # 1. 修复 'key': value,' 格式
        content = re.sub(r"'([^']+)':\s*([^,}]+),'", r"'\1': \2,", content)

        # 2. 修复列表中的尾随单引号 'item','
        content = re.sub(r"'([^']+)','", r"'\1',", content)

        # 3. 修复行尾的尾随单引号
        content = re.sub(r",'$", ",", content, flags=re.MULTILINE)

        # 4. 修复特殊情况：注释中的尾随单引号
        content = re.sub(r"#\s*([^']*)'$", r"# \1", content, flags=re.MULTILINE)

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
        if fix_trailing_quotes_in_file(file_path):
            fixed_count += 1

    print(f"\n总结: 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
