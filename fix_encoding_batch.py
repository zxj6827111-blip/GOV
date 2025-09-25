#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch fix Chinese encoding issues in test files
"""

import glob
import os
import re


def fix_chinese_encoding_in_file(file_path):
    """Fix Chinese encoding issues in a single file"""
    try:
        # Read file with different encodings
        content = None
        for encoding in ["utf-8", "gbk", "gb2312", "latin1"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            print(f"Could not read {file_path} with any encoding")
            return False

        # Common garbled character mappings
        replacements = {
            # Common corrupted patterns
            r"[^\x00-\x7F\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+": "",  # Remove non-printable chars
            r'Ã¤Â¸Â­Ã¦â€"â€¡': "中文",
            r"Ã¤Â¸Â­": "中",
            r'Ã¦â€"â€¡': "文",
            r"Ã¥Â®Å¡Ã¦Å¸Â¥": "审查",
            r"Ã¥Â®Å¡": "审",
            r"Ã¦Å¸Â¥": "查",
            r"Ã¥Â¤Â±Ã¦â€¢Â°": "失败",
            r"Ã¥Â¤Â±": "失",
            r"Ã¦â€¢Â°": "败",
            r'Ã¦Å"ÂªÃ¦â€°Â¾Ã¥Ë†Â°': "未找到",
            r'Ã¦Å"Âª': "未",
            r"Ã¦â€°Â¾": "找",
            r"Ã¥Ë†Â°": "到",
            r"Ã¦â€¢Â°Ã¦ï¿½Â®": "数据",
            r"Ã¦â€¢Â°": "数",
            r"Ã¦ï¿½Â®": "据",
            r"Ã¥Â¤Â§Ã¥Â°ï¿½": "大小",
            r"Ã¥Â¤Â§": "大",
            r"Ã¥Â°ï¿½": "小",
            r'Ã¦â€¢Â°Ã¥Â­â€"': "数字",
            r'Ã¥Â­â€"': "字",
            r"Ã¨Â¡Â¨Ã¦Â ¼": "表格",
            r"Ã¨Â¡Â¨": "表",
            r"Ã¦Â ¼": "格",
            r"Ã¨Â§â€žÃ¥Ë†â€¡": "规则",
            r"Ã¨Â§â€ž": "规",
            r"Ã¥Ë†â€¡": "则",
            r'Ã¦Å"ÂªÃ©â‚¬Å¡Ã©â‚¬Å¡': "通过",
            r"Ã©â‚¬Å¡": "通",
            r"Ã©â‚¬Å¡": "过",
            r'Ã¦Å"ÂªÃ©â‚¬Å¡': "未通",
        }

        # Apply replacements
        original_content = content
        for pattern, replacement in replacements.items():
            content = re.sub(pattern, replacement, content)

        # Check if changes were made
        if content != original_content:
            # Write back to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True

        return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """Main function to fix encoding in all test files"""
    test_dir = "tests"
    if not os.path.exists(test_dir):
        print(f"Directory {test_dir} not found")
        return

    # Find all Python files in tests directory
    python_files = glob.glob(os.path.join(test_dir, "*.py"))

    fixed_count = 0
    for file_path in python_files:
        print(f"Processing {file_path}...")
        if fix_chinese_encoding_in_file(file_path):
            print(f"Fixed encoding in {file_path}")
            fixed_count += 1
        else:
            print(f"No changes needed for {file_path}")

    print(f"\nFixed encoding in {fixed_count} files")


if __name__ == "__main__":
    main()
