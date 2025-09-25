#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终的编码修复脚本 - 专门处理中文编码和缩进问题
"""

import glob
import re

import chardet


def detect_encoding(file_path):
    """检测文件编码"""
    with open(file_path, "rb") as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result["encoding"]


def fix_file_encoding_and_syntax(file_path):
    """修复文件编码和语法问题"""
    try:
        # 检测编码
        encoding = detect_encoding(file_path)
        print(f"检测到 {file_path} 的编码: {encoding}")

        # 读取文件
        with open(file_path, "r", encoding=encoding, errors="ignore") as f:
            content = f.read()

        # 记录原始内容长度
        original_length = len(content)

        # 1. 移除或替换中文乱码字符
        # 常见的乱码模式
        corrupted_patterns = [
            r"[^\x00-\x7F\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+",  # 非ASCII、非中文、非标点的字符
            r"[\x80-\xff]{2,}",  # 连续的高位字节
            r"â€™|â€œ|â€\x9d|â€¦",  # 常见UTF-8乱码
            r"ï¿½",  # 替换字符
        ]

        for pattern in corrupted_patterns:
            content = re.sub(pattern, "", content)

        # 2. 修复缩进问题
        lines = content.split("\n")
        fixed_lines = []

        for i, line in enumerate(lines):
            # 移除行尾的乱码字符
            line = re.sub(r"[^\x00-\x7F\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\s]+$", "", line)

            # 修复缩进 - 确保使用4个空格
            if line.strip():  # 非空行
                # 计算应有的缩进级别
                stripped = line.lstrip()
                if stripped:
                    # 根据前一行的缩进和语法结构确定缩进
                    indent_level = 0

                    # 查找前面的非空行来确定缩进
                    for j in range(i - 1, -1, -1):
                        prev_line = lines[j].strip()
                        if prev_line:
                            prev_indent = len(lines[j]) - len(lines[j].lstrip())

                            # 如果前一行以冒号结尾，增加缩进
                            if prev_line.endswith(":"):
                                indent_level = prev_indent + 4
                            # 如果当前行是def/class/if/for等，保持或减少缩进
                            elif any(
                                stripped.startswith(kw)
                                for kw in [
                                    "def ",
                                    "class ",
                                    "if ",
                                    "for ",
                                    "while ",
                                    "try:",
                                    "except",
                                    "finally:",
                                    "with ",
                                    "elif ",
                                    "else:",
                                ]
                            ):
                                # 找到合适的缩进级别
                                if stripped.startswith("def ") or stripped.startswith("class "):
                                    indent_level = 0  # 顶级定义
                                else:
                                    indent_level = prev_indent
                            else:
                                indent_level = prev_indent
                            break

                    # 应用缩进
                    line = " " * indent_level + stripped

            fixed_lines.append(line)

        content = "\n".join(fixed_lines)

        # 3. 修复常见的语法问题
        # 修复多余的引号
        content = re.sub(r'"""([^"]*?)""""', r'"""\1"""', content)  # 四引号变三引号
        content = re.sub(r"'''([^']*?)''''", r"'''\1'''", content)  # 四单引号变三单引号

        # 修复字符串末尾的多余引号
        content = re.sub(r"'([^']*?)''", r"'\1'", content)
        content = re.sub(r'"([^"]*?)""', r'"\1"', content)

        # 修复装饰器后的多余引号
        content = re.sub(r'(@[^\n]+)"', r"\1", content)

        # 4. 确保文件以UTF-8编码保存
        with open(file_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

        new_length = len(content)
        print(f"✓ 修复了 {file_path} (长度: {original_length} -> {new_length})")
        return True

    except Exception as e:
        print(f"✗ 修复 {file_path} 时出错: {e}")
        return False


def main():
    """主函数"""
    test_files = glob.glob("tests/*.py")
    print(f"找到 {len(test_files)} 个测试文件")

    fixed_count = 0
    for file_path in test_files:
        if fix_file_encoding_and_syntax(file_path):
            fixed_count += 1

    print(f"\n总结: 修复了 {fixed_count} 个文件")


if __name__ == "__main__":
    main()
