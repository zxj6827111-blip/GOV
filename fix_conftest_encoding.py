#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix encoding issues in conftest.py specifically
"""

import re


def fix_conftest_encoding():
    """Fix encoding issues in conftest.py"""
    file_path = "tests/conftest.py"

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

        # Specific fixes for conftest.py
        fixes = [
            # Fix specific corrupted strings
            (r'"title": "[^"]*鐜囬棶棰?[^"]*"', '"title": "预算执行率问题"'),
            (r'"message": "[^"]*鐜囧簲涓嶄綆浜?[^"]*"', '"message": "预算执行率应不低于60%"'),
            (r'"text": "[^"]*鐜囬棶棰?[^"]*"', '"text": "预算执行率问题"'),
            (r'"table": "[^"]*琛?[^"]*"', '"table": "预算执行表"'),
            (
                r'"rule_description": "[^"]*鐜囧簲涓嶄綆浜?[^"]*"',
                '"rule_description": "预算执行率应不低于60%"',
            ),
            (r'"tags": \[[^\]]*瑙勫垯[^\]]*\]', '"tags": ["预算执行", "规则检测"]'),
            # Fix common corrupted characters
            ("鐜?", "率"),
            ("棶棰?", "问题"),
            ("簲涓嶄綆浜?", "应不低于"),
            ("瑙勫垯", "规则"),
            ("琛?", "表"),
            ("涓?", "不"),
            ("浜?", "于"),
            ("簲", "应"),
            ("浣?", "低"),
            ("綆", "低"),
            ("棰?", "题"),
            # Fix unterminated strings
            (r'"[^"]*琛\?,', '"预算执行表",'),
            (r'"[^"]*瑙勫垯检测\],', '"规则检测"],'),
        ]

        original_content = content
        for pattern, replacement in fixes:
            content = re.sub(pattern, replacement, content)

        # Check if changes were made
        if content != original_content:
            # Write back to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Fixed encoding in {file_path}")
            return True
        else:
            print(f"No changes needed for {file_path}")
            return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


if __name__ == "__main__":
    fix_conftest_encoding()
