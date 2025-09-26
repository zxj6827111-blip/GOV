#!/usr/bin/env python3
"""调试表格匹配器的页码输出"""

from engine.table_alias_matcher import TableAliasMatcher


def main():
    matcher = TableAliasMatcher()
    pages_text = [
        "第一页：收入支出决算总表\n总表数据...",
        "第二页：收入决算表\n收入明细数据...",
        "第三页：支出决算表\n支出明细数据...",
    ]

    found_tables = matcher.find_tables_in_document(pages_text)

    print("找到的表格及其页码：")
    for table_name, matches in found_tables.items():
        for match in matches:
            print(f"{table_name}: page {match['page']}")


if __name__ == "__main__":
    main()