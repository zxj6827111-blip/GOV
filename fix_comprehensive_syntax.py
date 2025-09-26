#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面修复所有测试文件中的语法错误
"""

import ast
import glob
import os
import re


def fix_syntax_errors_in_file(file_path):
    """修复单个文件中的语法错误"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # 1. 修复多余的引号问题
        content = re.sub(r'"""([^"]*?)""""', r'"""\1"""', content)
        content = re.sub(r'""""', '"""', content)

        # 2. 修复字典/列表中的尾随单引号
        content = re.sub(r"'([^']+)':\s*([^,}]+),'", r"'\1': \2,", content)
        content = re.sub(r"'([^']+)','", r"'\1',", content)

        # 3. 修复with语句后的多余引号
        content = re.sub(r"(with\s+[^:]+):\s*\'", r"\1:", content)

        # 4. 修复函数调用后的多余引号
        content = re.sub(r"(\w+\([^)]*\))\s*\'", r"\1", content)

        # 5. 修复字符串末尾的多余引号
        content = re.sub(r'"([^"]*)"\'', r'"\1"', content)
        content = re.sub(r"'([^']*)'\"", r"'\1'", content)

        # 6. 修复行尾的多余引号
        content = re.sub(r"\'$", "", content, flags=re.MULTILINE)
        content = re.sub(r"\"$", "", content, flags=re.MULTILINE)

        # 7. 修复return语句后的多余引号
        content = re.sub(r'return\s+"([^"]*)"\'', r'return "\1"', content)

        # 8. 修复变量赋值后的多余引号
        content = re.sub(r'=\s+"([^"]*)"\'', r'= "\1"', content)

        # 9. 修复patch装饰器中的多余引号
        content = re.sub(r"patch\('([^']+)'\)\s+as\s+(\w+):'", r"patch('\1') as \2:", content)

        # 10. 修复assert语句中的多余引号
        content = re.sub(r'assert\s+([^"\']+)"([^"]*)"\'', r'assert \1"\2"', content)

        # 11. 修复JSON字符串中的多余引号
        content = re.sub(r'"([^"]*)":\s*"([^"]*)"\'', r'"\1": "\2"', content)

        # 12. 修复列表/字典末尾的多余引号
        content = re.sub(r"([}\]])\s*\'", r"\1", content)

        # 13. 修复注释中的多余引号
        content = re.sub(r"#\s*([^\']*?)\'$", r"# \1", content, flags=re.MULTILINE)

        # 14. 修复特殊的编码问题导致的语法错误
        content = re.sub(r"(\w+)\s*\'([^\']*?)\'([^,}\]\n]*?)\'", r'\1 "\2"\3', content)

        if content != original_content:
            # 尝试解析修复后的代码，确保语法正确
            try:
                ast.parse(content)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"✓ 修复了 {file_path}")
                return True
            except SyntaxError as e:
                print(f"⚠ {file_path} 修复后仍有语法错误: {e}")
                # 如果修复后仍有错误，尝试更激进的修复
                return fix_aggressive_syntax(file_path, content)
        else:
            print(f"- 跳过 {file_path} (无需修复)")
            return False

    except Exception as e:
        print(f"✗ 处理 {file_path} 时出错: {e}")
        return False


def fix_aggressive_syntax(file_path, content):
    """更激进的语法修复"""
    try:
        lines = content.split("\n")
        fixed_lines = []

        for line in lines:
            # 移除行尾的多余引号
            line = re.sub(r"\'$", "", line)
            line = re.sub(r"\"$", "", line)

            # 修复常见的引号问题
            line = re.sub(r"([^\\])\'\'", r"\1\'", line)
            line = re.sub(r'([^\\])""', r'\1"', line)

            # 修复with语句
            if "with " in line and line.strip().endswith(":'"):
                line = line.rstrip("'") + ":"

            # 修复patch装饰器
            if "patch(" in line and line.strip().endswith(":'"):
                line = line.rstrip("'") + ":"

            fixed_lines.append(line)

        fixed_content = "\n".join(fixed_lines)

        # 再次尝试解析
        try:
            ast.parse(fixed_content)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fixed_content)
            print(f"✓ 激进修复成功 {file_path}")
            return True
        except SyntaxError as e:
            print(f"✗ 激进修复失败 {file_path}: {e}")
            return False

    except Exception as e:
        print(f"✗ 激进修复出错 {file_path}: {e}")
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
        if fix_syntax_errors_in_file(file_path):
            fixed_count += 1

    print(f"\n总结: 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()