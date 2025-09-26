# engine/table_alias_matcher.py
"""九张表名称与别名库
支持标准名+常见别名，正则/模糊匹配，跨页表题识别。"""

import re
import logging
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


@dataclass
class TableAlias:
    """表格别名定义"""
    standard_name: str  # 标准名称
    aliases: List[str]  # 别名列表
    regex_patterns: List[str]  # 正则模式
    category: str  # 分类
    required: bool = True  # 是否必需


# 九张表官方标准名称与常见别名
NINE_TABLES_ALIASES = [
    TableAlias(
        standard_name="收入支出决算总表",
        aliases=[
            "收入支出决算总表", "收支决算总表", "收入支出总表", 
            "收支总表", "总表", "决算总表"
        ],
        regex_patterns=[
            r"收入.*支出.*决算.*总表",
            r"收支.*决算.*总表",
            r"收入.*支出.*总表"
        ],
        category="总表",
        required=True
    ),
    TableAlias(
        standard_name="收入决算表",
        aliases=[
            "收入决算表", "收入表", "决算收入表",
            "财政收入决算表", "收入决算明细表"
        ],
        regex_patterns=[
            r"收入.*决算表?",
            r"决算.*收入表?"
        ],
        category="收入",
        required=True
    ),
    TableAlias(
        standard_name="支出决算表",
        aliases=[
            "支出决算表", "支出表", "决算支出表",
            "财政支出决算表", "支出决算明细表"
        ],
        regex_patterns=[
            r"支出.*决算表?",
            r"决算.*支出表?"
        ],
        category="支出",
        required=True
    ),
    TableAlias(
        standard_name="财政拨款收入支出决算总表",
        aliases=[
            "财政拨款收入支出决算总表", "财政拨款收支决算总表",
            "财政拨款总表", "拨款收支总表", "拨款决算总表"
        ],
        regex_patterns=[
            r"财政拨款.*收入.*支出.*决算.*总表",
            r"财政拨款.*收支.*决算.*总表",
            r"拨款.*收支.*总表"
        ],
        category="拨款总表",
        required=True
    ),
    TableAlias(
        standard_name="一般公共预算财政拨款支出决算表",
        aliases=[
            "一般公共预算财政拨款支出决算表", "一般公共预算支出决算表",
            "公共预算拨款支出表", "一般预算支出表", "公共预算支出表"
        ],
        regex_patterns=[
            r"一般公共预算.*财政拨款.*支出.*决算表?",
            r"一般公共预算.*支出.*决算表?",
            r"公共预算.*拨款.*支出.*表?"
        ],
        category="一般预算",
        required=True
    ),
    TableAlias(
        standard_name="一般公共预算财政拨款基本支出决算表",
        aliases=[
            "一般公共预算财政拨款基本支出决算表", "基本支出决算表",
            "公共预算基本支出表", "一般预算基本支出表"
        ],
        regex_patterns=[
            r"一般公共预算.*财政拨款.*基本支出.*决算表?",
            r"基本支出.*决算表?",
            r"公共预算.*基本支出.*表?"
        ],
        category="基本支出",
        required=True
    ),
    TableAlias(
        standard_name='一般公共预算财政拨款"三公"经费支出决算表',
        aliases=[
            "一般公共预算财政拨款三公经费支出决算表", "三公经费支出决算表",
            "三公经费决算表", "三公经费表", "公务接待费等支出表"
        ],
        regex_patterns=[
            r"一般公共预算.*财政拨款.*三公.*经费.*支出.*决算表?",
            r"三公.*经费.*支出.*决算表?",
            r"三公.*经费.*表?",
            r"公务接待费.*支出.*表?"
        ],
        category="三公经费",
        required=True
    ),
    TableAlias(
        standard_name="政府性基金预算财政拨款收入支出决算表",
        aliases=[
            "政府性基金预算财政拨款收入支出决算表", "政府性基金收支决算表",
            "基金预算决算表", "政府基金表", "专项基金表"
        ],
        regex_patterns=[
            r"政府性基金预算.*财政拨款.*收入.*支出.*决算表?",
            r"政府性基金.*收支.*决算表?",
            r"基金预算.*决算表?",
            r"政府.*基金.*表?"
        ],
        category="政府基金",
        required=False  # 可选表格
    ),
    TableAlias(
        standard_name="国有资本经营预算财政拨款支出决算表",
        aliases=[
            "国有资本经营预算财政拨款支出决算表", "国有资本经营支出决算表",
            "国资预算决算表", "国有资本表", "经营预算表"
        ],
        regex_patterns=[
            r"国有资本经营预算.*财政拨款.*支出.*决算表?",
            r"国有资本经营.*支出.*决算表?",
            r"国资预算.*决算表?",
            r"国有资本.*表?"
        ],
        category="国有资本",
        required=False  # 可选表格
    )
]

# 关键口径项别名
CRITICAL_ITEMS_ALIASES = {
    "三公经费": [
        "三公经费", "因公出国(境)费", "公务用车购置及运行费",
        "公务接待费", "因公出国费", "出国境费", "车辆购置费",
        "车辆运行费", "接待费"
    ],
    "机关运行经费": [
        "机关运行经费", "行政运行", "机关事业单位基本支出",
        "日常运转经费", "基本运行费用"
    ],
    "政府采购": [
        "政府采购", "采购支出", "政府采购金额", "集中采购",
        "分散采购", "采购预算", "采购执行"
    ]
}


class TableAliasMatcher:
    """表格别名匹配器"""
    
    def __init__(self, fuzzy_threshold: float = 85.0):
        self.fuzzy_threshold = fuzzy_threshold
        self.compiled_patterns = self._compile_patterns()
        
    def _compile_patterns(self) -> Dict[str, List[re.Pattern]]:
        """编译正则表达式模式"""
        compiled = {}
        for table_alias in NINE_TABLES_ALIASES:
            compiled[table_alias.standard_name] = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in table_alias.regex_patterns
            ]
        return compiled
    
    def match_table_name(self, text: str) -> List[Tuple[str, float, str]]:
        """
        匹配表格名称
        
        Args:
            text: 待匹配的文本
            
        Returns:
            匹配结果列表: [(标准名称, 置信度, 匹配方式), ...]
        """
        matches = []
        text_clean = self._normalize_text(text)
        
        for table_alias in NINE_TABLES_ALIASES:
            # 1. 精确匹配
            exact_match = self._exact_match(text_clean, table_alias)
            if exact_match:
                matches.append((table_alias.standard_name, 100.0, "exact"))
                continue
            
            # 2. 正则匹配
            regex_match = self._regex_match(text, table_alias)
            if regex_match:
                matches.append((table_alias.standard_name, 95.0, "regex"))
                continue
            
            # 3. 模糊匹配
            fuzzy_match = self._fuzzy_match(text_clean, table_alias)
            if fuzzy_match:
                score = fuzzy_match[1]
                matches.append((table_alias.standard_name, score, "fuzzy"))
        
        # 按置信度排序
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    def _normalize_text(self, text: str) -> str:
        """标准化文本"""
        # 移除多余空格和标点
        text = re.sub(r'\s+', '', text)
        text = re.sub(r'[（）()【】\[\]""'']', '', text)
        # 统一引号
        text = text.replace('"', '').replace('"', '').replace('"', '')
        return text.strip()
    
    def _exact_match(self, text: str, table_alias: TableAlias) -> bool:
        """精确匹配"""
        for alias in table_alias.aliases:
            alias_clean = self._normalize_text(alias)
            if alias_clean in text or text in alias_clean:
                return True
        return False
    
    def _regex_match(self, text: str, table_alias: TableAlias) -> bool:
        """正则匹配"""
        patterns = self.compiled_patterns.get(table_alias.standard_name, [])
        for pattern in patterns:
            if pattern.search(text):
                return True
        return False
    
    def _fuzzy_match(self, text: str, table_alias: TableAlias) -> Optional[Tuple[str, float]]:
        """模糊匹配"""
        best_score = 0
        best_alias = None
        
        for alias in table_alias.aliases:
            alias_clean = self._normalize_text(alias)
            
            # 使用多种模糊匹配算法
            scores = [
                fuzz.ratio(text, alias_clean),
                fuzz.partial_ratio(text, alias_clean),
                fuzz.token_sort_ratio(text, alias_clean),
                fuzz.token_set_ratio(text, alias_clean)
            ]
            
            max_score = max(scores)
            if max_score > best_score and max_score >= self.fuzzy_threshold:
                best_score = max_score
                best_alias = alias
        
        return (best_alias, best_score) if best_alias else None
    
    def find_tables_in_document(self, pages_text: List[str]) -> Dict[str, List[Dict[str, any]]]:
        """
        在文档中查找所有表格
        
        Args:
            pages_text: 各页文本列表
            
        Returns:
            找到的表格信息: {标准名称: [{"page": 页码, "confidence": 置信度, "method": 方法}, ...]}
        """
        found_tables = {}
        
        for page_no, page_text in enumerate(pages_text, 1):
            # 跨页表题处理：合并当前页和下一页的部分文本
            search_text = page_text
            if page_no < len(pages_text):
                # 添加下一页前几行，处理跨页标题
                next_page_lines = pages_text[page_no].split('\n')[:3]
                search_text += '\n' + '\n'.join(next_page_lines)
            
            matches = self.match_table_name(search_text)
            
            for standard_name, confidence, method in matches:
                if standard_name not in found_tables:
                    found_tables[standard_name] = []
                
                found_tables[standard_name].append({
                    "page": page_no,
                    "confidence": confidence,
                    "method": method,
                    "text_snippet": page_text[:200] + "..." if len(page_text) > 200 else page_text
                })
        
        return found_tables
    
    def check_required_tables(self, found_tables: Dict[str, List[Dict]]) -> List[str]:
        """检查必需表格的缺失情况"""
        missing_tables = []
        
        for table_alias in NINE_TABLES_ALIASES:
            if table_alias.required and table_alias.standard_name not in found_tables:
                missing_tables.append(table_alias.standard_name)
        
        return missing_tables
    
    def get_table_category_summary(self, found_tables: Dict[str, List[Dict]]) -> Dict[str, int]:
        """获取表格分类汇总"""
        category_counts = {}
        
        for table_alias in NINE_TABLES_ALIASES:
            category = table_alias.category
            if category not in category_counts:
                category_counts[category] = 0
            
            if table_alias.standard_name in found_tables:
                category_counts[category] += 1
        
        return category_counts


def match_critical_items(text: str, item_type: str) -> List[Tuple[str, float]]:
    """匹配关键口径项"""
    if item_type not in CRITICAL_ITEMS_ALIASES:
        return []
    
    text_clean = re.sub(r'\s+', '', text)
    matches = []
    
    for alias in CRITICAL_ITEMS_ALIASES[item_type]:
        alias_clean = re.sub(r'\s+', '', alias)
        
        # 精确匹配
        if alias_clean in text_clean:
            matches.append((alias, 100.0))
            continue
        
        # 模糊匹配
        score = fuzz.partial_ratio(text_clean, alias_clean)
        if score >= 80:
            matches.append((alias, score))
    
    # 去重并排序
    unique_matches = {}
    for alias, score in matches:
        if alias not in unique_matches or score > unique_matches[alias]:
            unique_matches[alias] = score
    
    return sorted(unique_matches.items(), key=lambda x: x[1], reverse=True)


# 全局实例
_table_matcher: Optional[TableAliasMatcher] = None

def get_table_matcher() -> TableAliasMatcher:
    """获取全局表格匹配器实例"""
    global _table_matcher
    if _table_matcher is None:
        _table_matcher = TableAliasMatcher()
    return _table_matcher