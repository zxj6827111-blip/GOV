# engine/table_name_matcher.py
"""
九张表名称与别名匹配系统
支持标准名称、常见别名、模糊匹配和跨页表题识别
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


@dataclass
class TableNameConfig:
    """表格名称配置"""

    standard_name: str
    aliases: List[str]
    pattern_keywords: List[str]  # 关键词组合
    min_similarity: float = 80.0  # 最小相似度阈值
    category: str = "budget"  # 表格类别


class TableNameMatcher:
    """九张表名称匹配器"""

    def __init__(self):
        self.table_configs = self._load_table_configs()
        self.compiled_patterns = self._compile_patterns()

    def _load_table_configs(self) -> List[TableNameConfig]:
        """加载九张表配置"""
        return [
            TableNameConfig(
                standard_name="收入支出决算总表",
                aliases=[
                    "收入支出决算总表",
                    "收入支出决算表",
                    "收支决算总表",
                    "收支决算表",
                    "收入支出总表",
                    "总收支表",
                ],
                pattern_keywords=["收入", "支出", "决算", "总表"],
                category="comprehensive",
            ),
            TableNameConfig(
                standard_name="收入决算表",
                aliases=["收入决算表", "收入决算明细表", "决算收入表", "收入明细表", "收入情况表"],
                pattern_keywords=["收入", "决算"],
                category="income",
            ),
            TableNameConfig(
                standard_name="支出决算表",
                aliases=["支出决算表", "支出决算明细表", "决算支出表", "支出明细表", "支出情况表"],
                pattern_keywords=["支出", "决算"],
                category="expenditure",
            ),
            TableNameConfig(
                standard_name="财政拨款收入支出决算总表",
                aliases=[
                    "财政拨款收入支出决算总表",
                    "财政拨款收支决算总表",
                    "财政拨款收支表",
                    "拨款收支决算表",
                    "财政拨款总表",
                ],
                pattern_keywords=["财政", "拨款", "收入", "支出", "决算"],
                category="fiscal_allocation",
            ),
            TableNameConfig(
                standard_name="一般公共预算财政拨款支出决算表",
                aliases=[
                    "一般公共预算财政拨款支出决算表",
                    "一般公共预算支出决算表",
                    "公共预算支出决算表",
                    "一般预算支出表",
                    "公共预算拨款支出表",
                ],
                pattern_keywords=["一般", "公共", "预算", "财政", "拨款", "支出"],
                category="general_budget",
            ),
            TableNameConfig(
                standard_name="一般公共预算财政拨款基本支出决算表",
                aliases=[
                    "一般公共预算财政拨款基本支出决算表",
                    "基本支出决算表",
                    "一般预算基本支出表",
                    "公共预算基本支出表",
                    "财政拨款基本支出表",
                ],
                pattern_keywords=["一般", "公共", "预算", "基本", "支出"],
                category="basic_expenditure",
            ),
            TableNameConfig(
                standard_name="一般公共预算财政拨款三公经费支出决算表",
                aliases=[
                    "一般公共预算财政拨款三公经费支出决算表",
                    "三公经费支出决算表",
                    "三公经费决算表",
                    "三公经费表",
                    "公务支出决算表",
                ],
                pattern_keywords=["三公", "经费", "支出"],
                category="three_public",
            ),
            TableNameConfig(
                standard_name="政府性基金预算财政拨款收入支出决算表",
                aliases=[
                    "政府性基金预算财政拨款收入支出决算表",
                    "政府性基金收支决算表",
                    "基金预算决算表",
                    "政府基金收支表",
                    "基金拨款收支表",
                ],
                pattern_keywords=["政府", "基金", "预算", "收入", "支出"],
                category="government_fund",
            ),
            TableNameConfig(
                standard_name="国有资本经营预算财政拨款支出决算表",
                aliases=[
                    "国有资本经营预算财政拨款支出决算表",
                    "国有资本经营支出决算表",
                    "国资预算支出表",
                    "国有资本支出表",
                    "资本经营支出表",
                ],
                pattern_keywords=["国有", "资本", "经营", "预算", "支出"],
                category="state_capital",
            ),
        ]

    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """编译正则表达式模式"""
        patterns = {}

        # 通用表格标题模式
        patterns["table_title"] = re.compile(
            r"(?:附件|表\s*\d+|附表)?\s*[:：]?\s*([^。\n]{5,50}?表)\s*(?:单位|说明|注|：|$)",
            re.MULTILINE,
        )

        # 页眉页脚表名模式
        patterns["header_footer"] = re.compile(
            r"(?:^|\n)\s*([^。\n]{5,50}?表)\s*(?:第?\s*\d+\s*页|续表|\(续\)|$)", re.MULTILINE
        )

        # 跨页表题模式
        patterns["cross_page"] = re.compile(
            r"([^。\n]{5,50}?表)\s*(?:\(续\)|续表|第?\s*\d+\s*页)", re.MULTILINE
        )

        return patterns

    def extract_table_names(self, text: str, page_num: int = 1) -> List[Dict[str, Any]]:
        """从文本中提取表格名称"""
        found_names = []

        # 使用各种模式提取候选名称
        candidates = []

        for pattern_name, pattern in self.compiled_patterns.items():
            matches = pattern.finditer(text)
            for match in matches:
                table_name = match.group(1).strip()
                if len(table_name) >= 5:  # 过滤过短的名称
                    candidates.append(
                        {
                            "name": table_name,
                            "pattern": pattern_name,
                            "position": match.start(),
                            "match_text": match.group(0),
                        }
                    )

        # 对候选名称进行匹配
        for candidate in candidates:
            match_result = self.match_table_name(candidate["name"])
            if match_result:
                found_names.append(
                    {
                        "page": page_num,
                        "extracted_name": candidate["name"],
                        "standard_name": match_result["standard_name"],
                        "confidence": match_result["confidence"],
                        "category": match_result["category"],
                        "pattern": candidate["pattern"],
                        "position": candidate["position"],
                        "match_text": candidate["match_text"],
                    }
                )

        return found_names

    def match_table_name(self, input_name: str) -> Optional[Dict[str, Any]]:
        """匹配表格名称到标准名称"""
        input_name = input_name.strip()

        # 1. 精确匹配
        for config in self.table_configs:
            if input_name in config.aliases:
                return {
                    "standard_name": config.standard_name,
                    "confidence": 100.0,
                    "match_type": "exact",
                    "category": config.category,
                }

        # 2. 模糊匹配
        best_match = None
        best_score = 0

        for config in self.table_configs:
            for alias in config.aliases:
                # 使用rapidfuzz进行模糊匹配
                score = fuzz.ratio(input_name, alias)
                if score > best_score and score >= config.min_similarity:
                    best_score = score
                    best_match = {
                        "standard_name": config.standard_name,
                        "confidence": score,
                        "match_type": "fuzzy",
                        "category": config.category,
                        "matched_alias": alias,
                    }

        # 3. 关键词匹配
        if not best_match or best_score < 85:
            for config in self.table_configs:
                keyword_matches = sum(
                    1 for keyword in config.pattern_keywords if keyword in input_name
                )
                if keyword_matches >= len(config.pattern_keywords) * 0.6:  # 60%关键词匹配
                    keyword_score = (keyword_matches / len(config.pattern_keywords)) * 80
                    if keyword_score > best_score:
                        best_score = keyword_score
                        best_match = {
                            "standard_name": config.standard_name,
                            "confidence": keyword_score,
                            "match_type": "keyword",
                            "category": config.category,
                            "matched_keywords": keyword_matches,
                        }

        return best_match

    def find_missing_tables(self, found_tables: List[str]) -> List[str]:
        """找出缺失的表格"""
        standard_names = {config.standard_name for config in self.table_configs}
        found_standards = set(found_tables)
        return list(standard_names - found_standards)

    def validate_table_completeness(self, found_tables: List[Dict[str, Any]]) -> Dict[str, Any]:
        """验证表格完整性"""
        standard_names = {config.standard_name for config in self.table_configs}
        found_standards = {table["standard_name"] for table in found_tables}

        missing_tables = list(standard_names - found_standards)
        completion_rate = len(found_standards) / len(standard_names)

        # 按类别统计
        category_stats = {}
        for config in self.table_configs:
            category = config.category
            if category not in category_stats:
                category_stats[category] = {"total": 0, "found": 0}
            category_stats[category]["total"] += 1
            if config.standard_name in found_standards:
                category_stats[category]["found"] += 1

        return {
            "total_required": len(standard_names),
            "total_found": len(found_standards),
            "completion_rate": completion_rate,
            "missing_tables": missing_tables,
            "category_stats": category_stats,
            "is_complete": completion_rate >= 0.8,  # 80%完整度阈值
        }

    def cross_page_match(self, page_texts: List[str]) -> List[Dict[str, Any]]:
        """跨页表格名称匹配"""
        all_found = []

        for page_idx, text in enumerate(page_texts):
            page_tables = self.extract_table_names(text, page_idx + 1)
            all_found.extend(page_tables)

        # 去重和合并
        unique_tables = {}
        for table in all_found:
            key = table["standard_name"]
            if key not in unique_tables or table["confidence"] > unique_tables[key]["confidence"]:
                unique_tables[key] = table

        return list(unique_tables.values())


# 全局实例
_table_matcher: Optional[TableNameMatcher] = None


def get_table_matcher() -> TableNameMatcher:
    """获取全局表格匹配器实例"""
    global _table_matcher
    if _table_matcher is None:
        _table_matcher = TableNameMatcher()
    return _table_matcher


def match_nine_tables(page_texts: List[str]) -> Dict[str, Any]:
    """匹配九张表的便捷函数"""
    matcher = get_table_matcher()
    found_tables = matcher.cross_page_match(page_texts)
    completeness = matcher.validate_table_completeness(found_tables)

    return {
        "found_tables": found_tables,
        "completeness": completeness,
        "summary": {
            "total_found": len(found_tables),
            "completion_rate": completeness["completion_rate"],
            "missing_count": len(completeness["missing_tables"]),
        },
    }
