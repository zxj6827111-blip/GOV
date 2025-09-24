# coding: utf-8
# ---------- “九张表” ----------
NINE_TABLES = [
    {"name": "收入支出决算总表",
     "aliases": ["部门收支决算总表", "收入支出决算总表", "收支决算总表"]},
    {"name": "收入决算表",
     "aliases": ["部门收入决算表", "收入决算表"]},
    {"name": "支出决算表",
     "aliases": ["部门支出决算表", "支出决算表"]},
    {"name": "财政拨款收入支出决算总表",
     "aliases": ["财政拨款收支决算总表", "财政拨款收入支出决算总表"]},
    {"name": "一般公共预算财政拨款支出决算表",
     "aliases": ["一般公共预算财政拨款支出决算表", "一般公共预算支出决算表"]},
    {"name": "一般公共预算财政拨款基本支出决算表",
     "aliases": ["一般公共预算财政拨款基本支出决算表", "基本支出决算表"]},
    {"name": "一般公共预算财政拨款“三公”经费支出决算表",
     "aliases": ["财政拨款“三公”经费支出决算表", "三公经费支出决算表", "“三公”经费支出决算表"]},
    {"name": "政府性基金预算财政拨款收入支出决算表",
     "aliases": ["政府性基金预算财政拨款收入支出决算表", "政府性基金决算表"]},
    {"name": "国有资本经营预算财政拨款收入支出决算表",
     "aliases": [
         "国有资本经营预算财政拨款收入支出决算表",
         "国有资本经营预算财政拨款支出决算表",
         "国有资本经营支出决算表"
     ]}
]

# ========= 工具：中文序号 & 排序+编号 =========
_CN_NUM = "零一二三四五六七八九十"
def to_cn_num(n: int) -> str:
    """把 1,2,3... 变成 一、二、三……（<= 99 的中文数字）"""
    if n <= 10:
        return _CN_NUM[n]
    t, o = divmod(n, 10)
    if n < 20:
        return "十" + (_CN_NUM[o] if o else "")
    return _CN_NUM[t] + "十" + (_CN_NUM[o] if o else "")

def order_and_number_issues(doc, issues):
    """
    按 (page, pos) 排序，并把 message 前面加上 "一、二、三…"
    说明：
    - 其它规则请尽量往 location 里塞 { "page": 页码, "pos": 页内位置 }，
      这样这里才能按文中顺序排。
    - 噪声过滤增强：剔除含"表出现多次"的问题，提升检测结果质量
    """
    # 增强噪声过滤逻辑
    filtered_issues = []
    for issue in issues:
        # 检查多种噪声模式
        is_noise = False
        
        # 1. 表重复噪声
        if "表出现多次" in issue.message:
            is_noise = True
            
        # 2. 检查desc字段（如果存在）
        if hasattr(issue, 'desc') and issue.desc and "表出现多次" in issue.desc:
            is_noise = True
            
        # 3. 其他潜在噪声模式（可扩展）
        noise_patterns = [
            "页码异常",
            "格式错误",
            "解析失败"
        ]
        for pattern in noise_patterns:
            if pattern in issue.message:
                is_noise = True
                break
                
        if not is_noise:
            filtered_issues.append(issue)
    
    def sort_key(it):
        p = it.location.get("page", 10**9)   # 没页码的排在最后
        s = it.location.get("pos", 0)        # 没 pos 的当 0 处理
        return (p, s)

    sorted_issues = sorted(filtered_issues, key=sort_key)
    for idx, it in enumerate(sorted_issues, start=1):
        cn = to_cn_num(idx)
        # 避免重复加序号（防止多次调用）
        if not it.message.startswith(("一、","二、","三、","四、","五、","六、","七、","八、","九、","十、")):
            it.message = f"{cn}、{it.message}"
    return sorted_issues
# engine/rules_v33.py  —— v3.3 规则（修正版）

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

import os
import re
from collections import Counter, defaultdict
import numpy as np
from rapidfuzz import fuzz

# ---------- 数据结构 ----------
@dataclass
class Issue:
    rule: str
    severity: str
    message: str
    location: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Document:
    path: str
    pages: int
    filesize: int
    page_texts: List[str]
    # 维度：页 -> 表 -> 行 -> 列
    page_tables: List[List[List[List[str]]]]
    units_per_page: List[Optional[str]]
    years_per_page: List[List[int]]
    anchors: Dict[str, List[int]] = field(default_factory=dict)
    dominant_year: Optional[int] = None
    dominant_unit: Optional[str] = None


# ---------- 工具 ----------
def zh_pat(pat: str) -> re.Pattern:
    """中文文本常用正则：统一多行/点任意匹配 & 忽略大小写"""
    return re.compile(pat, flags=re.S | re.M | re.I)

_ZH_PUNCS = r"[ \t\r\n　，,。.:：；;、/（）()【】《》〈〉—\-━﻿·•●\[\]\{\}_~“”\"'‘’＋+]"
def normalize_text(s: str) -> str:
    s = s or ""
    return re.sub(_ZH_PUNCS, "", s)

# 避免把“2013901”等编码识别成年份
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?:(?:\s*年(?:度)?)|(?=\D))")
def extract_years(s: str) -> List[int]:
    return [int(y) for y in _YEAR_RE.findall(s or "")]

_UNIT_RE = re.compile(r"单位[:：]\s*(万元|元|亿元)")
def extract_money_unit(s: str) -> Optional[str]:
    m = _UNIT_RE.search(s or "")
    return m.group(1) if m else None

_NUM_RE  = re.compile(r"^-?\s*(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?$")
_PCT_RE  = re.compile(r"^-?\s*(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?\s*%$")
_DASHES  = {"-", "—", "–", "— —", "— — —", "— — — —", ""}

def parse_number(cell: Any) -> Optional[float]:
    if cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    s = str(cell).strip()
    if s in _DASHES:
        return None
    if _PCT_RE.match(s):
        s = s.replace("%", "").replace(",", "").strip()
        try:
            return float(s)
        except Exception:
            return None
    s2 = s.replace(",", "")
    if _NUM_RE.match(s):
        try:
            return float(s2)
        except Exception:
            return None
    return None

def looks_like_percent(cell: Any) -> bool:
    try:
        return "%" in str(cell)
    except Exception:
        return False

def has_negative_sign(cell: Any) -> bool:
    try:
        return str(cell).strip().startswith("-")
    except Exception:
        return False

def majority(items: List[Any]) -> Optional[Any]:
    if not items:
        return None
    c = Counter(items).most_common(1)
    return c[0][0] if c else None

# 数值容差比较（±1 或 相对 0.1% 取较大）
def tolerant_equal(a: Optional[float], b: Optional[float],
                   atol: float = 1.0, rtol: float = 0.001) -> bool:
    if a is None or b is None:
        return False
    tol = max(atol, abs(a) * rtol, abs(b) * rtol)
    return abs(a - b) <= tol

def calculate_dynamic_tolerance(a: float, b: float, base_tol: float = 1.0) -> float:
    """统一的动态容差计算：根据金额级别调整容差"""
    max_val = max(abs(a), abs(b))
    if max_val < 100:  # 小额：固定容差1.0
        return base_tol
    elif max_val < 10000:  # 中等金额：0.5%
        return max(base_tol, max_val * 0.005)
    else:  # 大额：0.3%
        return max(base_tol, max_val * 0.003)

def normalize_number_text(text: str) -> str:
    """标准化数字文本格式：移除千分位逗号、统一空格"""
    return text.replace(",", "").replace(" ", "").strip()




def _guess_pos_in_page(doc: "Document", page: int, clip: str, fallback_text: str = "") -> int:
    """
    增强的文本定位精度：改进位置检测算法，增强片段提取完整性
    """
    try:
        if page is None or page < 1 or page > len(doc.page_texts):
            return 10**9
        
        hay = doc.page_texts[page-1]
        
        # 1. 首先尝试精确匹配
        for k in (clip or "", fallback_text or ""):
            s = (k or "").strip().replace("\n", "")
            if len(s) >= 8:
                s = s[:50]
                i = hay.find(s)
                if i >= 0:
                    return i
        
        # 2. 标准化后匹配（处理空格、标点差异）
        if clip and len(clip) >= 8:
            normalized_hay = normalize_text(hay)
            normalized_clip = normalize_text(clip[:50])
            pos = normalized_hay.find(normalized_clip)
            if pos >= 0:
                # 映射回原始位置（简化版）
                return _map_normalized_pos_to_original(hay, normalized_hay, pos)
        
        # 3. 分段匹配：将clip分成多个片段，找到最佳匹配位置
        if clip and len(clip) > 50:
            segments = _split_text_segments(clip, 3)  # 分成3段
            best_pos = 10**9
            best_score = 0
            
            for segment in segments:
                if len(segment) >= 8:
                    seg_pos = hay.find(segment[:30])
                    if seg_pos >= 0:
                        # 计算匹配得分
                        score = len(segment) / len(clip)
                        if score > best_score:
                            best_score = score
                            best_pos = seg_pos
            
            if best_score > 0.3:  # 至少30%匹配
                return best_pos
        
        return 10**9
    except Exception:
        return 10**9

def _map_normalized_pos_to_original(original: str, normalized: str, norm_pos: int) -> int:
    """将标准化文本中的位置映射回原始文本位置（简化版）"""
    try:
        # 简化映射：按比例估算
        if len(normalized) == 0:
            return 0
        ratio = norm_pos / len(normalized)
        return int(ratio * len(original))
    except:
        return 0

def _split_text_segments(text: str, num_segments: int) -> List[str]:
    """将文本分割成指定数量的片段"""
    if num_segments <= 1:
        return [text]
    
    segment_length = len(text) // num_segments
    segments = []
    
    for i in range(num_segments):
        start = i * segment_length
        end = start + segment_length if i < num_segments - 1 else len(text)
        segment = text[start:end].strip()
        if segment:
            segments.append(segment)
    
    return segments
NINE_ALIAS_NORMAL = [{"name": it["name"], "aliases_norm": [normalize_text(x) for x in it["aliases"]]}
                     for it in NINE_TABLES]

def _is_non_table_page(raw: str) -> bool:
    r = raw or ""
    return ("目录" in r) or ("名词解释" in r) or ("情况说明" in r)

def find_table_anchors(doc: Document) -> Dict[str, List[int]]:
    anchors: Dict[str, List[int]] = {it["name"]: [] for it in NINE_TABLES}
    for pidx, raw in enumerate(doc.page_texts):
        if _is_non_table_page(raw):
            continue
        ntxt = normalize_text(raw)
        if not ntxt:
            continue
        is_table_page = ("单位：" in raw) or ("本表反映" in raw)
        if not is_table_page:
            continue
        for it in NINE_ALIAS_NORMAL:
            for alias_norm in it["aliases_norm"]:
                if alias_norm and (alias_norm in ntxt or fuzz.partial_ratio(alias_norm, ntxt) >= 95):
                    anchors[it["name"]].append(pidx + 1)
                    break
    return anchors


# ---------- 规则基类 ----------
class Rule:
    code: str
    severity: str
    desc: str

    def apply(self, doc: Document) -> List[Issue]:
        raise NotImplementedError

    def apply_with_ai(self, doc: Document, use_ai_assist: bool) -> List[Issue]:
        """支持AI辅助的apply方法，默认实现直接调用标准apply方法"""
        return self.apply(doc)

    def _issue(self, message: str,
               location: Optional[Dict[str, Any]] = None,
               severity: Optional[str] = None) -> Issue:
        return Issue(
            rule=self.code,
            severity=severity or self.severity,
            message=message,
            location=location or {}
        )


# ---------- 规则实现 ----------
class R33001_CoverYearUnit(Rule):
    code, severity = "V33-001", "error"
    desc = "封面/目录年份、单位抽取与一致性"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        # 年份：前 3 页 + 首个表页（若存在）
        front_idxs = list(range(min(3, doc.pages)))
        years, units = [], []
        for i in front_idxs:
            years += doc.years_per_page[i]
            if doc.units_per_page[i]:
                units.append(doc.units_per_page[i])

        first_table_page = None
        if doc.anchors:
            ps = [min(v) for v in doc.anchors.values() if v]
            if ps:
                first_table_page = min(ps)
        scan_upto = max(front_idxs[-1] + 1 if front_idxs else 1, (first_table_page or 1))
        for i in range(scan_upto):
            if doc.units_per_page[i]:
                units.append(doc.units_per_page[i])

        doc.dominant_year = majority(years)
        doc.dominant_unit = majority(units)

        if doc.dominant_year is None:
            issues.append(self._issue("未能在封面/目录或首个表页附近识别年度。", {"page": 1}, severity="warn"))
        all_units = [u for u in doc.units_per_page if u]
        if not all_units:
            issues.append(self._issue("未识别到金额单位（单位：万元/元/亿元）。", {"page": 1}, severity="warn"))
        elif len(set(all_units)) > 1:
            issues.append(self._issue(f"金额单位混用：{sorted(set(all_units))}。", {"page": 1}, severity="warn"))
        return issues

class R33002_NineTablesCheck(Rule):
    code, severity = "V33-002", "error"
    desc = "九张表定位、缺失、重复与顺序"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        anchors = doc.anchors or find_table_anchors(doc)
        doc.anchors = anchors

        missing, duplicates, order_pages = [], [], []
        # 逐张检查
        for spec in NINE_TABLES:
            nm = spec["name"]
            pages = anchors.get(nm, [])
            if not pages:
                missing.append(nm)
            else:
                order_pages.append((nm, min(pages)))
                if len(pages) > 1:
                    duplicates.append((nm, pages))

        # 缺失
        for nm in missing:
            issues.append(self._issue(f"缺失表：{nm}", {"table": nm}, severity="error"))

        # 重复
        for nm, pgs in duplicates:
            issues.append(self._issue(f"表出现多次：{nm}（页码 {pgs}）", {"table": nm, "pages": pgs}, severity="warn"))

        # 顺序（按首次出现页）——至少识别出 3 张表才判断
        if len(order_pages) >= 3:
            expected_index = {spec["name"]: idx for idx, spec in enumerate(NINE_TABLES)}
            actual = sorted(order_pages, key=lambda x: x[1])       # 按页码升序
            indices = [expected_index[nm] for nm, _ in actual]
            if indices != sorted(indices):
                msg = "九张表出现顺序可能异常（按首次出现页）。实际：" + " > ".join(f"{nm}@{pg}" for nm, pg in actual)
                issues.append(self._issue(msg, {}, severity="warn"))
        return issues

class R33003_PageFileThreshold(Rule):
    code, severity = "V33-003", "warn"
    desc = "页数/文件大小阈值"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        if doc.pages < 8:
            issues.append(self._issue(f"页数过少：{doc.pages} 页，疑似不完整。", {"pages": doc.pages}, severity="error"))
        if doc.pages > 300:
            issues.append(self._issue(f"页数较多：{doc.pages} 页，建议分卷检查。", {"pages": doc.pages}))
        if doc.filesize > 50 * 1024 * 1024:
            mb = round(doc.filesize / (1024 * 1024), 1)
            issues.append(self._issue(f"文件体积较大：{mb} MB，可能影响解析速度。", {"filesize": doc.filesize}))
        return issues


class R33004_CellNumberValidity(Rule):
    code, severity = "V33-004", "error"
    desc = "表内数字合法性（百分比>100、负数提示）"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        for pidx, tables in enumerate(doc.page_tables):
            for tindex, table in enumerate(tables):
                if not table or not any(row for row in table):
                    continue
                for r, row in enumerate(table):
                    for c, cell in enumerate(row):
                        s = "" if cell is None else str(cell)
                        if looks_like_percent(s):
                            v = parse_number(s)
                            if v is not None and (v < 0 or v > 100):
                                issues.append(self._issue(
                                    f"百分比越界：{s}",
                                    {"page": pidx + 1, "table_index": tindex, "row": r + 1, "col": c + 1},
                                    severity="error"
                                ))
                        else:
                            if has_negative_sign(s) and parse_number(s) is not None:
                                issues.append(self._issue(
                                    f"出现负数：{s}（请确认是否合理）",
                                    {"page": pidx + 1, "table_index": tindex, "row": r + 1, "col": c + 1},
                                    severity="warn"
                                ))
        return issues


class R33005_TableTotalConsistency(Rule):
    code, severity = "V33-005", "error"
    desc = "表内合计与分项和一致（±1 或 0.1% 容忍）"
    _TOTAL_RE = re.compile(r"^(合计|总计)$")
    _EXCLUDE_HEAD = ("其中", "小计", "分项", "人员经费合计", "公用经费合计")

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        money_col_hint = ("金额", "合计", "本年收入", "本年支出", "决算数", "预算数")

        for pidx, tables in enumerate(doc.page_tables):
            for tindex, table in enumerate(tables):
                if not table or len(table) < 3:
                    continue

                header = [str(x or "") for x in (table[0] if table else [])]
                header_join = "".join(header)

                # 左右两栏（收入+支出）总表：跳过
                if ("收入" in header_join) and ("支出" in header_join):
                    continue

                # 找“合计/总计”行（第一列严格等于）
                total_row_idx = None
                for r, row in enumerate(table):
                    head = str((row[0] if row else "") or "").strip()
                    if head in self._EXCLUDE_HEAD:
                        continue
                    if self._TOTAL_RE.match(head):
                        total_row_idx = r
                        break
                if total_row_idx is None or total_row_idx < 2:
                    continue

                # 选择金额相关的列（优先表头关键词）
                ncols = max(len(row) for row in table)
                cand_cols: List[int] = []
                for c in range(1, ncols):
                    headc = header[c] if c < len(header) else ""
                    if any(h in headc for h in money_col_hint):
                        cand_cols.append(c)
                if not cand_cols:
                    for c in range(1, ncols):
                        cnt = 0
                        for r in range(0, total_row_idx):
                            cell = table[r][c] if c < len(table[r]) else None
                            v = parse_number(cell)
                            if v is not None and not looks_like_percent(cell):
                                cnt += 1
                        if cnt >= 3:
                            cand_cols.append(c)
                if not cand_cols:
                    continue

                # 功能分类层级：只累计叶子行
                code_rows: List[Tuple[int, str]] = []
                for r in range(1, total_row_idx):
                    row = table[r]
                    name0 = str((row[0] if row else "") or "")
                    m = re.match(r"^\s*(\d{3,7})", name0)
                    if m:
                        code_rows.append((r, m.group(1)))
                leaf_len = max((len(c) for _, c in code_rows), default=None)

                for c in cand_cols:
                    total_cell = table[total_row_idx][c] if c < len(table[total_row_idx]) else None
                    total_val = parse_number(total_cell)
                    if total_val is None or looks_like_percent(total_cell):
                        continue

                    parts: List[float] = []
                    for r in range(1, total_row_idx):
                        headr = str((table[r][0] if 0 < len(table[r]) else "") or "")
                        if headr in self._EXCLUDE_HEAD or self._TOTAL_RE.match(headr.strip()):
                            continue
                        if leaf_len is not None:
                            m = re.match(r"^\s*(\d{3,7})", headr)
                            if not (m and len(m.group(1)) == leaf_len):
                                continue
                        cell = table[r][c] if c < len(table[r]) else None
                        v = parse_number(cell)
                        if v is not None and not looks_like_percent(cell):
                            parts.append(float(v))
                    if len(parts) < 1:
                        continue

                    sum_val = float(np.nansum(parts))
                    tol = max(1.0, abs(sum_val) * 0.001)
                    diff = abs(sum_val - (total_val or 0.0))
                    if diff > tol and (total_val == 0 or diff / max(abs(total_val), 1e-6) > 0.5):
                        issues.append(self._issue(
                            f"“合计”与分项和不一致：合计={total_val}，分项和={sum_val}（容忍±{round(tol, 2)}）",
                            {"page": pidx + 1, "table_index": tindex, "col": c + 1, "total_row": total_row_idx + 1},
                            severity="error"
                        ))
        return issues


# ---------- 辅助（跨表/文数一致） ----------
def _largest_table_on_page(tables: List[List[List[str]]]) -> Optional[List[List[str]]]:
    if not tables:
        return None
    return sorted(tables, key=lambda t: sum(len(r) for r in t), reverse=True)[0]

def _get_first_anchor_page(doc: Document, table_name: str) -> Optional[int]:
    pages = (doc.anchors or {}).get(table_name) or []
    return min(pages) if pages else None

def _row_value(table: List[List[str]],
               name_keys: Tuple[str, ...],
               prefer_cols: Tuple[str, ...] = ()) -> Optional[float]:
    if not table:
        return None
    header = [str(x or "") for x in (table[0] if table else [])]
    target_row = None
    for r, row in enumerate(table):
        head = str((row[0] if row else "") or "")
        if any(k in head for k in name_keys):
            target_row = r
            break
    if target_row is None:
        return None

    if prefer_cols:
        prefer_idx: List[int] = []
        for i, col_name in enumerate(header):
            if any(k in col_name for k in prefer_cols):
                prefer_idx.append(i)
        for c in prefer_idx:
            if c < len(table[target_row]):
                cell = table[target_row][c]
                if looks_like_percent(cell):
                    continue
                v = parse_number(cell)
                if v is not None:
                    return float(v)

    ncols = max(len(r) for r in table)
    for c in range(ncols - 1, -1, -1):
        cell = table[target_row][c] if c < len(table[target_row]) else None
        if looks_like_percent(cell):
            continue
        v = parse_number(cell)
        if v is not None:
            return float(v)
    return None

def _sum_by_func_class(table: List[List[str]], digits: int = 3) -> Dict[str, float]:
    agg: Dict[str, float] = defaultdict(float)
    if not table:
        return agg
    ncols = max(len(r) for r in table)
    for r, row in enumerate(table[1:], start=1):
        name = str((row[0] if row else "") or "")
        m = re.match(r"(\d{3,7})", name.strip())
        if not m:
            continue
        code = m.group(1)[:digits]
        val: Optional[float] = None
        for c in range(ncols - 1, 0, -1):
            v = parse_number(row[c] if c < len(row) else None)
            if v is not None and not looks_like_percent(row[c]):
                val = v
                break
        if val is not None:
            agg[code] += float(val)
    return dict(agg)

def near_number(text: str, keywords: List[str]) -> Optional[float]:
    if not text:
        return None
    kw = "|".join(map(re.escape, keywords))
    # 简化正则表达式，避免复杂的嵌套量词导致回溯
    pat = re.compile(rf"(?:{kw})[^0-9]*?(-?\d+(?:,\d{{3}})*(?:\.\d+)?)", flags=re.S | re.M)
    m = pat.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except Exception:
        return None

def find_percent(text: str, keywords: List[str]) -> Optional[float]:
    if not text:
        return None
    kw = "|".join(map(re.escape, keywords))
    # 简化正则表达式，避免复杂的嵌套量词导致回溯
    m = re.search(rf"(?:{kw})[^0-9]*?(-?\d+(?:\.\d+)?)\s*%", text, flags=re.S | re.M)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def _snippet(s: str, start: int, end: int, max_len: int = 32) -> str:
    seg = s[max(0, start - max_len): min(len(s), end + max_len)]
    seg = re.sub(r"\s+", " ", seg).strip()
    if len(seg) > max_len * 2:
        seg = seg[:max_len] + " … " + seg[-max_len:]
    return seg


# ---------- 跨表勾稽（V33-101~105） ----------
class R33101_TotalSheet_Identity(Rule):
    code, severity = "V33-101", "error"
    desc = "收入支出决算总表：支出列恒等式"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        p = _get_first_anchor_page(doc, "收入支出决算总表")
        if not p:
            return issues
        table = _largest_table_on_page(doc.page_tables[p - 1])
        if not table:
            return issues
        total = _row_value(table, ("支出合计", "支出总计", "合计"))
        bn = _row_value(table, ("本年支出合计", "本年支出", "本年合计"))
        jy = _row_value(table, ("结余分配", "结余分配支出"))
        jz = _row_value(table, ("年末结转和结余", "年末结转", "结转结余"))

        if (total is not None) and (bn is not None) and (jy is not None) and (jz is not None):
            try:
                bn_f, jy_f, jz_f, total_f = float(bn), float(jy), float(jz), float(total)
                sum_val = bn_f + jy_f + jz_f
                if not tolerant_equal(total_f, sum_val):
                    issues.append(self._issue(
                        f"总表支出恒等式不成立：支出合计={total_f} vs 本年支出{bn_f}+结余分配{jy_f}+年末结转{jz_f}={sum_val}",
                        {"page": p}, "error"
                    ))
            except Exception:
                pass
        return issues

class R33102_TotalSheet_vs_Text(Rule):
    code, severity = "V33-102", "warn"
    desc = "收入支出决算总表 ↔ 总体情况说明"

    def apply(self, doc: Document) -> List[Issue]:
        try:
            issues: List[Issue] = []

            # 1) 找"收入支出决算总表"的第一页
            p = _get_first_anchor_page(doc, "收入支出决算总表")
            if not p:
                return issues

            # 2) 取该页最大的一张表
            table = _largest_table_on_page(doc.page_tables[p - 1])
            if not table:
                return issues

            # 3) 从表中提取"支出合计"
            total_expense = _row_value(table, ("支出合计", "支出总计", "合计"))
            if total_expense is None:
                return issues

            # 4) 简化搜索，直接在关键词附近查找数字，避免复杂正则表达式
            # 只搜索前5页的文本，进一步限制搜索范围
            search_text = "\n".join(doc.page_texts[:min(5, len(doc.page_texts))])
            
            # 使用简单的字符串搜索而不是复杂的正则表达式
            found_num = None
            for keyword in ["总体情况说明", "总体情况"]:
                pos = search_text.find(keyword)
                if pos != -1:
                    # 在关键词后面100个字符内查找数字
                    snippet = search_text[pos:pos+100]
                    import re
                    numbers = re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', snippet)
                    if numbers:
                        try:
                            found_num = float(numbers[0].replace(",", ""))
                            break
                        except:
                            continue
            
            if found_num is None:
                return issues

            # 5) 比较
            if not tolerant_equal(total_expense, found_num):
                issues.append(self._issue(
                    f"收入支出决算总表支出合计({total_expense:.2f})与总体情况说明数字({found_num:.2f})不一致",
                    {"page": p, "pos": 0}
                ))

            return issues
        except RecursionError:
            return [self._issue("规则执行异常：maximum recursion depth exceeded", {"page": 1, "pos": 0}, "info")]
        except Exception as e:
            return [self._issue(f"规则执行异常：{str(e)}", {"page": 1, "pos": 0}, "info")]

class R33103_Income_vs_Text(Rule):
    code, severity = "V33-103", "warn"
    desc = "收入决算表 ↔ 收入决算情况说明（含占比）"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        p = _get_first_anchor_page(doc, "收入决算表")
        if not p:
            return issues
        t = _largest_table_on_page(doc.page_tables[p - 1])
        if not t:
            return issues
        total = _row_value(t, ("本年收入合计", "本年合计", "合计"))
        fp = _row_value(t, ("财政拨款收入", "一般公共预算财政拨款收入", "财政拨款"))
        if total is None or fp is None:
            return issues
        txt = "\n".join(doc.page_texts)
        tt = near_number(txt, ["收入决算情况说明", "本年收入合计", "合计"])
        tf = near_number(txt, ["财政拨款收入"])
        if tt and not tolerant_equal(total, tt):
            issues.append(self._issue(f"收入合计：表{total} ≠ 文本{tt}", {"page": p}, "warn"))
        if tf and not tolerant_equal(fp, tf):
            issues.append(self._issue(f"财政拨款收入：表{fp} ≠ 文本{tf}", {"page": p}, "warn"))
        p_txt = find_percent(txt, ["财政拨款收入", "占比", "比重"])
        if p_txt is not None and total:
            p_calc = round(fp / total * 100, 2)
            if abs(p_calc - p_txt) > 1.0:
                issues.append(self._issue(f"财政拨款收入占比：表算{p_calc}% ≠ 文本{p_txt}%（容忍±1pct）", {"page": p}, "warn"))
        return issues


class R33104_Expense_vs_Text(Rule):
    code, severity = "V33-104", "warn"
    desc = "支出决算表 ↔ 支出决算情况说明（含占比）"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        p = _get_first_anchor_page(doc, "支出决算表")
        if not p:
            return issues
        t = _largest_table_on_page(doc.page_tables[p - 1])
        if not t:
            return issues
        total = _row_value(t, ("本年支出合计", "本年合计", "合计"))
        basic = _row_value(t, ("基本支出",))
        proj = _row_value(t, ("项目支出",))
        if total is None or basic is None or proj is None:
            return issues
        txt = "\n".join(doc.page_texts)
        for (nm, a, b) in [("本年支出合计", total, near_number(txt, ["支出决算情况说明", "本年支出合计", "合计"])),
                           ("基本支出", basic, near_number(txt, ["基本支出"])),
                           ("项目支出", proj, near_number(txt, ["项目支出"]))]:
            if b and not tolerant_equal(a, b):
                issues.append(self._issue(f"{nm}：表{a} ≠ 文本{b}", {"page": p}, "warn"))
        for (nm, a) in [("基本支出", basic), ("项目支出", proj)]:
            pct_t = find_percent(txt, [nm, "占比", "比重"])
            if pct_t is not None and total:
                pct_c = round(a / total * 100, 2)
                if abs(pct_c - pct_t) > 1.0:
                    issues.append(self._issue(f"{nm}占比：表算{pct_c}% ≠ 文本{pct_t}%（容忍±1pct）", {"page": p}, "warn"))
        return issues


class R33105_FinGrantTotal_vs_Text(Rule):
    code, severity = "V33-105", "warn"
    desc = "财政拨款收入支出决算总表 ↔ 总体情况说明"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        p = _get_first_anchor_page(doc, "财政拨款收入支出决算总表")
        if not p:
            return issues
        t = _largest_table_on_page(doc.page_tables[p - 1])
        if not t:
            return issues
        total = _row_value(t, ("支出合计", "支出总计", "合计"))
        if total is None:
            return issues
        txt = "\n".join(doc.page_texts)
        t_total = near_number(txt, ["财政拨款收入支出决算总体情况说明", "总计", "合计"])
        if t_total and not tolerant_equal(total, t_total):
            issues.append(self._issue(f"财政拨款支出合计：表{total} ≠ 文本{t_total}", {"page": p}, "warn"))
        return issues


# ---------- 文数一致（V33-106、V33-107、V33-108、V33-109、V33-110） ----------
class R33106_GeneralBudgetStruct(Rule):
    code, severity = "V33-106", "warn"
    desc = "一般公共预算财拨支出：合计↔总体；结构（类3位）占比 ↔ 结构情况"

    def apply(self, doc: Document) -> List[Issue]:
        try:
            issues: List[Issue] = []

            # 1) 找"一般公共预算财政拨款支出决算表"的第一页
            p = _get_first_anchor_page(doc, "一般公共预算财政拨款支出决算表")
            if not p:
                return issues

            table = _largest_table_on_page(doc.page_tables[p - 1])
            if not table:
                return issues

            # 2) 提取"合计"
            total_val = _row_value(table, ("合计", "支出合计"))
            if total_val is None:
                return issues

            # 3) 在"总体情况说明"中查找相近数字
            full_text = "\n".join(doc.page_texts)
            found_num = near_number(full_text, ["总体情况说明", "总体情况"])
            if found_num is not None:
                if not tolerant_equal(total_val, found_num):
                    issues.append(self._issue(
                        f"一般公共预算财拨支出合计({total_val:.2f})与总体情况说明数字({found_num:.2f})不一致",
                        {"page": p, "pos": 0}
                    ))

            # 4) 结构占比检查
            func_sums = _sum_by_func_class(table)
            for func_name, func_val in func_sums.items():
                if func_val > 0:
                    pct = func_val / total_val * 100
                    found_pct = find_percent(full_text, [func_name, "结构情况"])
                    if found_pct is not None:
                        if abs(pct - found_pct) > 2.0:
                            issues.append(self._issue(
                                f"{func_name}占比：表格计算{pct:.1f}%，文本{found_pct:.1f}%，差异超过2%",
                                {"page": p, "pos": 0}
                            ))

            return issues
        except RecursionError:
            return [self._issue("规则执行异常：maximum recursion depth exceeded", {"page": 1, "pos": 0}, "info")]
        except Exception as e:
            return [self._issue(f"规则执行异常：{str(e)}", {"page": 1, "pos": 0}, "info")]


class R33107_BasicExpense_Check(Rule):
    code, severity = "V33-107", "warn"
    desc = "基本支出：人员经费合计 + 公用经费合计 ↔ 文本说明"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        p = _get_first_anchor_page(doc, "一般公共预算财政拨款基本支出决算表")
        if not p:
            return issues
        t = _largest_table_on_page(doc.page_tables[p - 1])
        if not t:
            return issues
        ren = _row_value(t, ("人员经费合计", "人员经费"))
        gong = _row_value(t, ("公用经费合计", "公用经费"))
        if ren is None or gong is None:
            return issues
        total = ren + gong
        txt = "\n".join(doc.page_texts)
        t_total = near_number(txt, ["一般公共预算财政拨款基本支出决算情况说明", "基本支出", "合计"])
        if t_total and not tolerant_equal(total, t_total):
            issues.append(self._issue(f"基本支出合计：表算{total} ≠ 文本{t_total}", {"page": p}, "warn"))
        return issues


class R33108_ThreePublic_vs_Text(Rule):
    code, severity = "V33-108", "warn"
    desc = "三公经费：表 ↔ “总体情况说明”"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        p = _get_first_anchor_page(doc, "一般公共预算财政拨款“三公”经费支出决算表")
        if not p:
            return issues
        t = _largest_table_on_page(doc.page_tables[p - 1])
        if not t:
            return issues
        bud = _row_value(t, ("合计预算数", "预算合计", "预算数"))
        act = _row_value(t, ("合计决算数", "决算合计", "决算数"))
        if bud is None and act is None:
            return issues
        txt = "\n".join(doc.page_texts)
        tb = near_number(txt, ["三公", "年初预算", "预算"])
        ta = near_number(txt, ["三公", "支出决算", "决算"])
        if tb and bud and not tolerant_equal(bud, tb):
            issues.append(self._issue(f"三公经费预算：表{bud} ≠ 文本{tb}", {"page": p}, "warn"))
        if ta and act and not tolerant_equal(act, ta):
            issues.append(self._issue(f"三公经费决算：表{act} ≠ 文本{ta}", {"page": p}, "warn"))
        return issues


class R33109_EmptyTables_Statement(Rule):
    code, severity = "V33-109", "warn"
    desc = "政府性基金/国有资本经营：如为空表，必须有空表说明"

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        txt_all = "\n".join(doc.page_texts)
        for nm in ["政府性基金预算财政拨款收入支出决算表", "国有资本经营预算财政拨款收入支出决算表"]:
            p = _get_first_anchor_page(doc, nm)
            if not p:
                continue
            table = _largest_table_on_page(doc.page_tables[p - 1])
            if not table:
                continue
            vals = []
            for row in table:
                for cell in row[1:]:
                    v = parse_number(cell)
                    if v is not None:
                        vals.append(v)
            is_empty = (not vals) or all(abs(v) < 1e-9 for v in vals)
            if is_empty:
                if not re.search(r"(空表|无相关收支|不存在|无此项|本表无数据|故本表无数据|无数据)", txt_all, flags=re.S | re.M):
                    issues.append(self._issue(f"【{nm}】为空表，但未见“空表说明/无相关收支/无数据”等说明。", {"page": p}, "warn"))
        return issues


class R33110_BudgetVsFinal_TextConsistency(Rule):
    code, severity = "V33-110", "error"
    desc = "（三）一般公共预算财政拨款支出决算（具体）情况:数字与大于/小于/持平一致性，并校验是否说明原因"

    # 1) 小节起止（行首匹配 + 变体）
    _SEC_START = re.compile(r"(?m)^\s*(（三）|三、)\s*一般公共预算财政拨款支出决算(?:具体)?情况")
    _NEXT_SEC  = re.compile(r"(?m)^\s*(（四）|四、|（六）|六、|一般公共预算财政拨款基本支出决算情况说明)")

    # 2) 优化后的主配对模式：缩小匹配窗口，增加上下文约束
    _PAIR = re.compile(
        r"(?:年初?\s*预算|预算|年初预算数|预算数)(?:数)?[为是]?\s*"
        r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:亿元|万元|元)?"
        r"(?:[^决]{0,50}?)?"  # 使用非贪婪量词避免回溯
        r"(?:支出\s*决算|决算|决算支出)(?:数)?[为是]?\s*"
        r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:亿元|万元|元)?"
        r"(?:[^。]{0,50}?)?"  # 使用非贪婪量词避免回溯
        r"(决算(?:数)?(?:大于|小于|等于|持平|基本持平)预算(?:数)?)",
        re.S
    )
    
    # 3) 备用配对模式：适度放宽但仍比原来严格
    _PAIR_FALLBACK = re.compile(
        r"(?:年初?\s*预算|预算|年初预算数|预算数)(?:数)?[为是]?\s*"
        r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:亿元|万元|元)?"
        r"(?:[^决]{0,80}?)?"  # 使用非贪婪量词避免回溯
        r"(?:支出\s*决算|决算|决算支出)(?:数)?[为是]?\s*"
        r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:亿元|万元|元)?"
        r"(?:[^。]{0,80}?)?"  # 使用非贪婪量词避免回溯
        r"(决算(?:数)?(?:大于|小于|等于|持平|基本持平)预算(?:数)?)",
        re.S
    )

    # 4) 反序配对：同样缩小窗口
    _PAIR_REV = re.compile(
        r"(?:支出\s*决算|决算|决算支出)(?:数)?[为是]?\s*"
        r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:亿元|万元|元)?"
        r"(?:[^预]{0,50}?)?"  # 使用非贪婪量词避免回溯
        r"(?:年初?\s*预算|预算|年初预算数|预算数)(?:数)?[为是]?\s*"
        r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:亿元|万元|元)?"
        r"(?:[^。]{0,50}?)?"  # 使用非贪婪量词避免回溯
        r"(决算(?:数)?(?:大于|小于|等于|持平|基本持平)预算(?:数)?)",
        re.S
    )

    # 5) 增强的负样本过滤：添加更多干扰词
    _NEGATIVE_FILTER = re.compile(r"同比|比上年|比上年度|比上期|增长|减少|较去年|与去年|上年同期")

    # 6) 原因检查（"其中："之后的分项）
    _REASON_CHECK = re.compile(r"(主要原因|增减原因|变动原因)\s*[:：]")

    # 7) 本项边界（用于"缺少原因"的定位：到下一条"^\s*\d+、"或段落终点）
    _NEXT_ITEM = re.compile(r"(?m)^\s*\d+、")

    def _slice_section_span(self, full: str):
        import os
        import logging
        logger = logging.getLogger(__name__)
        
        m1 = self._SEC_START.search(full)
        if not m1:
            return None, -1, -1
        start = m1.start()
        m2 = self._NEXT_SEC.search(full[m1.end():])
        end = m1.end() + (m2.start() if m2 else len(full) - m1.end())
        
        sec = full[start:end]
        
        # 在 DEBUG 模式下打印小节截取信息
        debug_enabled = os.getenv("DEBUG_R33110", "0") == "1"
        if debug_enabled:
            logger.info(f"[R33110] 小节截取: len(sec)={len(sec)}, 首120字: {sec[:120]!r}")
            logger.info(f"[R33110] 小节截取: 尾120字: {sec[-120:]!r}")
        
        return sec, start, end

    def apply(self, doc: Document) -> List[Issue]:
        """标准apply方法，不使用AI辅助"""
        return self._apply_internal(doc, use_ai_assist=False)
    
    def apply_with_ai(self, doc: Document, use_ai_assist: bool) -> List[Issue]:
        """支持AI辅助的apply方法"""
        return self._apply_internal(doc, use_ai_assist=use_ai_assist)
    
    def _apply_internal(self, doc: Document, use_ai_assist: bool = False) -> List[Issue]:
        issues: List[Issue] = []
        full = "\n".join(doc.page_texts)

        # 计算每页 offset → page/pos 映射
        offsets, acc = [0], 0
        for t in doc.page_texts:
            acc += len(t); offsets.append(acc)

        # 抽取该小节全文
        sec, sec_start, _ = self._slice_section_span(full)
        if not sec:
            return issues

        # 两轮合并：规则 + AI辅助 + fallback
        all_pairs = []
        
        # 第一轮：现有确定性规则
        rule_pairs = self._extract_by_rules(sec, sec_start, offsets)
        all_pairs.extend(rule_pairs)
        
        # 导入必要模块（在方法开始处导入，确保作用域正确）
        import logging
        logger = logging.getLogger(__name__)
        
        # 第二轮：AI辅助（如果启用且参数为True）
        if use_ai_assist:
            try:
                from engine.ai.extractor_client import ai_extract_pairs, generate_doc_hash
                import asyncio
                
                ai_enabled = os.getenv("AI_ASSIST_ENABLED", "true").lower() == "true"
                logger.info(f"[R33110] AI辅助状态: {ai_enabled}, 用户选择: {use_ai_assist}")
                
                if ai_enabled:
                    try:
                        # 使用同步方式调用AI抽取，避免事件循环冲突
                        doc_hash = generate_doc_hash(sec)
                        logger.info(f"[R33110] 开始AI抽取，文档哈希: {doc_hash[:8]}...")
                        
                        # 直接使用同步HTTP请求，避免异步事件循环问题
                        import requests
                        import json
                        
                        ai_extractor_url = os.getenv("AI_EXTRACTOR_URL", "http://127.0.0.1:9009/ai/extract/v1")
                        
                        payload = {
                            "task": "R33110_pairs_v1",
                            "section_text": sec,
                            "doc_hash": doc_hash,
                            "max_windows": 3
                        }
                        
                        response = requests.post(
                            ai_extractor_url,
                            json=payload,
                            timeout=120,
                            headers={"Content-Type": "application/json"}
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            ai_pairs = result.get("hits", [])
                            logger.info(f"[R33110] AI抽取完成，获得 {len(ai_pairs)} 个结果")
                            
                            # 转换AI结果为内部格式
                            converted_ai_pairs = self._convert_ai_pairs(ai_pairs, sec_start, offsets)
                            all_pairs.extend(converted_ai_pairs)
                            logger.info(f"[R33110] AI结果转换完成，添加 {len(converted_ai_pairs)} 个有效结果")
                        else:
                            logger.warning(f"[R33110] AI抽取服务返回错误: {response.status_code}")
                        
                    except Exception as e:
                        # AI失败不影响主流程
                        logger.warning(f"[R33110] AI辅助抽取失败: {e}")
                else:
                    logger.info(f"[R33110] AI辅助未启用，跳过AI处理")
                        
            except ImportError as e:
                # AI模块不可用，继续使用纯规则模式
                logger.info(f"[R33110] AI模块不可用，使用纯规则模式: {e}")
        else:
            logger.info(f"[R33110] 用户未选择AI辅助，跳过AI处理")

        # 第一次去重合并
        unique_pairs = self._deduplicate_pairs(all_pairs)
        
        # 调试打印：显示regex_hits和ai_hits数量
        debug_enabled = os.getenv("DEBUG_R33110", "").lower() in ("1", "true", "yes")
        if debug_enabled:
            regex_hits = len([p for p in all_pairs if p.get("source") in ("regex", "fallback", "reverse")])
            ai_hits = len([p for p in all_pairs if p.get("source") == "ai"])
            logger.info(f"[R33110] regex_hits={regex_hits}, ai_hits={ai_hits}")
        
        # 第二次去重合并
        unique_pairs = self._deduplicate_pairs(all_pairs)
        
        # 生成问题
        for pair_info in unique_pairs:
            issues.extend(self._generate_issues_for_pair(pair_info, sec))

        return issues
    
    def _extract_by_rules(self, sec: str, sec_start: int, offsets: List[int]) -> List[Dict[str, Any]]:
        """使用确定性规则抽取"""
        pairs = []
        
        # "其中"锚点：之后视为分项段，需检查"原因"
        idx_qizhong = sec.find("其中")
        qizhong_pos = idx_qizhong if idx_qizhong >= 0 else None

        # 第一轮：主配对规则
        for m in self._PAIR.finditer(sec):
            raw_bud, raw_act, phrase = m.group(1), m.group(2), m.group(3)
            
            # 负样本过滤：检查结论短语附近±40字内是否有排除词
            phrase_start = m.start(3)
            phrase_end = m.end(3)
            check_start = max(0, phrase_start - 40)
            check_end = min(len(sec), phrase_end + 40)
            check_window = sec[check_start:check_end]
            
            if self._NEGATIVE_FILTER.search(check_window):
                continue  # 跳过包含同比、增长等词的句子

            # 数字解析（支持千分位）
            try:
                b = float(raw_bud.replace(",", ""))
                a = float(raw_act.replace(",", ""))
            except Exception:
                continue

            pair_info = self._create_pair_info(raw_bud, raw_act, phrase, m, sec, sec_start, offsets, qizhong_pos, "regex")
            if pair_info:
                pairs.append(pair_info)

        # 第二轮：备用配对规则（更宽松）
        for m in self._PAIR_FALLBACK.finditer(sec):
            raw_bud, raw_act, phrase = m.group(1), m.group(2), m.group(3)
            
            # 检查是否与已有匹配重叠（按start位置去重）
            if any(abs(p["match_start"] - m.start()) < 50 for p in pairs):
                continue
                
            # 负样本过滤
            phrase_start = m.start(3)
            phrase_end = m.end(3)
            check_start = max(0, phrase_start - 40)
            check_end = min(len(sec), phrase_end + 40)
            check_window = sec[check_start:check_end]
            
            if self._NEGATIVE_FILTER.search(check_window):
                continue

            # 数字解析
            try:
                b = float(raw_bud.replace(",", ""))
                a = float(raw_act.replace(",", ""))
            except Exception:
                continue

            pair_info = self._create_pair_info(raw_bud, raw_act, phrase, m, sec, sec_start, offsets, qizhong_pos, "fallback")
            if pair_info:
                pairs.append(pair_info)

        # 第三轮：反序配对规则（决算→预算）
        for m in self._PAIR_REV.finditer(sec):
            raw_act, raw_bud, phrase = m.group(1), m.group(2), m.group(3)  # 注意顺序调换
            
            # 检查是否与已有匹配重叠
            if any(abs(p["match_start"] - m.start()) < 50 for p in pairs):
                continue
                
            # 负样本过滤
            phrase_start = m.start(3)
            phrase_end = m.end(3)
            check_start = max(0, phrase_start - 40)
            check_end = min(len(sec), phrase_end + 40)
            check_window = sec[check_start:check_end]
            
            if self._NEGATIVE_FILTER.search(check_window):
                continue

            # 数字解析
            try:
                b = float(raw_bud.replace(",", ""))
                a = float(raw_act.replace(",", ""))
            except Exception:
                continue

            pair_info = self._create_pair_info(raw_bud, raw_act, phrase, m, sec, sec_start, offsets, qizhong_pos, "reverse")
            if pair_info:
                pairs.append(pair_info)

        return pairs

    def _create_pair_info(self, raw_bud: str, raw_act: str, phrase: str, match, sec: str, 
                         sec_start: int, offsets: List[int], qizhong_pos, source: str) -> Dict[str, Any]:
        """创建配对信息的辅助方法"""
        # 绝对位置 → page/pos
        abs_pos = sec_start + match.start()
        page, pos_in_page = 1, 0
        for i in range(len(offsets) - 1):
            if offsets[i] <= abs_pos < offsets[i + 1]:
                page = i + 1
                pos_in_page = abs_pos - offsets[i]
                break

        clip = (match.group(0)[:80] if match.group(0) else "")
        
        # 检查是否有原因说明
        in_items = (qizhong_pos is not None) and (match.start() > qizhong_pos)
        reason_text = None
        if in_items:
            # 从当前匹配尾部到"下一项"或 320 字节内寻找"原因"
            tail = sec[match.end():]
            next_item = self._NEXT_ITEM.search(tail)
            end_idx = next_item.start() if next_item else min(len(tail), 320)
            window = tail[:end_idx]
            reason_match = self._REASON_CHECK.search(window)
            if reason_match:
                # 提取原因内容（到句号或窗口结束）
                reason_start = reason_match.end()
                reason_content = window[reason_start:]
                period_pos = reason_content.find("。")
                if period_pos >= 0:
                    reason_text = reason_content[:period_pos].strip()
                else:
                    reason_text = reason_content.strip()

        return {
            "budget_text": raw_bud,
            "final_text": raw_act,
            "stmt_text": phrase,
            "reason_text": reason_text,
            "page": page,
            "pos": pos_in_page,
            "clip": clip,
            "source": source,  # 标记抽取来源
            "match_start": match.start(),
            "match_end": match.end()
        }
    
    def _extract_by_fallback(self, sec: str, sec_start: int, offsets: List[int]) -> List[Dict[str, Any]]:
        """使用fallback模式抽取（更宽松的匹配）"""
        pairs = []
        
        # "其中"锚点：之后视为分项段，需检查"原因"
        idx_qizhong = sec.find("其中")
        qizhong_pos = idx_qizhong if idx_qizhong >= 0 else None

        for m in self._PAIR_FALLBACK.finditer(sec):
            raw_bud, raw_act, phrase = m.group(1), m.group(2), m.group(3)

            # 数字解析（支持千分位）
            try:
                b = float(raw_bud.replace(",", ""))
                a = float(raw_act.replace(",", ""))
            except Exception:
                continue

            # 绝对位置 → page/pos
            abs_pos = sec_start + m.start()
            page, pos_in_page = 1, 0
            for i in range(len(offsets) - 1):
                if offsets[i] <= abs_pos < offsets[i + 1]:
                    page = i + 1
                    pos_in_page = abs_pos - offsets[i]
                    break

            clip = (m.group(0)[:80] if m.group(0) else "")
            
            # 检查是否有原因说明
            in_items = (qizhong_pos is not None) and (m.start() > qizhong_pos)
            reason_text = None
            if in_items:
                # 从当前匹配尾部到"下一项"或 220 字节内寻找"原因"
                tail = sec[m.end():]
                next_item = self._NEXT_ITEM.search(tail)
                end_idx = next_item.start() if next_item else min(len(tail), 220)
                window = tail[:end_idx]
                reason_match = re.search(r"(主要原因|增减原因|变动原因)\s*[:：]([^。]*)", window)
                if reason_match:
                    reason_text = reason_match.group(2).strip()

            pairs.append({
                "budget_text": raw_bud,
                "final_text": raw_act,
                "stmt_text": phrase,
                "reason_text": reason_text,
                "page": page,
                "pos": pos_in_page,
                "clip": clip,
                "source": "fallback"  # 标记来源
            })

        return pairs
    
    def _convert_ai_pairs(self, ai_pairs: List[Dict[str, Any]], sec_start: int, offsets: List[int]) -> List[Dict[str, Any]]:
        """转换AI抽取结果为内部格式，完善location信息"""
        converted = []
        
        for ai_pair in ai_pairs:
            try:
                # 获取stmt_span的中点作为位置参考
                stmt_span = ai_pair.get("stmt_span", [0, 0])
                match_start = stmt_span[0]
                match_end = stmt_span[1]
                
                # 绝对位置 → page/pos
                abs_pos = sec_start + match_start
                page, pos_in_page = 1, 0
                for i in range(len(offsets) - 1):
                    if offsets[i] <= abs_pos < offsets[i + 1]:
                        page = i + 1
                        pos_in_page = abs_pos - offsets[i]
                        break

                # 确保clip信息完整
                clip = ai_pair.get("clip", "")
                if not clip and ai_pair.get("stmt_text"):
                    # 如果没有clip，使用stmt_text作为fallback
                    clip = ai_pair["stmt_text"][:50] + ("..." if len(ai_pair["stmt_text"]) > 50 else "")

                converted.append({
                    "budget_text": ai_pair.get("budget_text", ""),
                    "final_text": ai_pair.get("final_text", ""),
                    "stmt_text": ai_pair.get("stmt_text", ""),
                    "reason_text": ai_pair.get("reason_text"),
                    "page": page,
                    "pos": pos_in_page,
                    "clip": clip,
                    "source": "ai",
                    "match_start": match_start,
                    "match_end": match_end
                })
                
            except Exception as e:
                import logging
                logging.warning(f"转换AI pair失败: {e}")
                continue
                
        return converted
    
    def _deduplicate_pairs(self, all_pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        改进的去重逻辑：扩大位置容差，增加数字格式标准化，考虑语义相似度
        """
        if not all_pairs:
            return []
            
        unique_pairs = []
        
        for pair in all_pairs:
            is_duplicate = False
            
            for i, existing in enumerate(unique_pairs):
                # 扩大位置容差：30→60字符
                if (pair["page"] == existing["page"] and
                    abs(pair["pos"] - existing["pos"]) <= 60):
                    
                    try:
                        # 标准化数字格式后比较
                        existing_bud = normalize_number_text(existing["budget_text"])
                        existing_act = normalize_number_text(existing["final_text"])
                        pair_bud = normalize_number_text(pair["budget_text"])
                        pair_act = normalize_number_text(pair["final_text"])
                        
                        # 使用动态容差比较数字
                        bud_tol = calculate_dynamic_tolerance(float(existing_bud), float(pair_bud))
                        act_tol = calculate_dynamic_tolerance(float(existing_act), float(pair_act))
                        
                        if (abs(float(existing_bud) - float(pair_bud)) <= bud_tol and
                            abs(float(existing_act) - float(pair_act)) <= act_tol):
                            
                            is_duplicate = True
                            # 优先保留有reason的
                            if pair.get("reason_text") and not existing.get("reason_text"):
                                unique_pairs[i] = pair
                            break
                    except (ValueError, TypeError):
                        # 如果数字解析失败，回退到字符串比较
                        if (pair["budget_text"] == existing["budget_text"] and
                            pair["final_text"] == existing["final_text"]):
                            is_duplicate = True
                            if pair.get("reason_text") and not existing.get("reason_text"):
                                unique_pairs[i] = pair
                            break
                    
            if not is_duplicate:
                unique_pairs.append(pair)
                
        return unique_pairs
    
    def _generate_issues_for_pair(self, pair_info: Dict[str, Any], sec: str) -> List[Issue]:
        """为单个pair生成问题，完善location信息"""
        issues = []
        
        raw_bud = pair_info["budget_text"]
        raw_act = pair_info["final_text"]
        phrase = pair_info["stmt_text"]
        reason_text = pair_info.get("reason_text")
        page = pair_info["page"]
        pos_in_page = pair_info["pos"]
        clip = pair_info["clip"]

        # 数字解析（支持千分位）
        try:
            # 使用标准化函数处理数字格式
            b = float(normalize_number_text(raw_bud))
            a = float(normalize_number_text(raw_act))
        except Exception:
            return issues

        # 使用动态容差计算
        tol = calculate_dynamic_tolerance(a, b)
        calc = "大于" if a > b + tol else ("小于" if a < b - tol else "持平")
        stated = ("持平" if "持平" in phrase
                  else ("大于" if "大于" in phrase
                        else ("小于" if "小于" in phrase else "等于")))

        # 确保clip信息格式（确保统一格式和内容完整性）
        if not clip or clip.strip() == "":
            # 如果clip为空，使用phrase作为fallback
            clip = phrase[:50] + "..." if len(phrase) > 50 else phrase
        
        # 确保clip格式统一
        final_clip = f"片段：「{clip}」" if not clip.startswith("片段：") else clip
        
        # 构建完整的location信息
        location_info = {
            "page": page,
            "pos": pos_in_page,
            "clip": clip
        }

        # 1. "基本持平"提示（不影响一致性判断）
        if "基本持平" in phrase:
            issues.append(self._issue(
                f"用语基本持平不规范，建议写持平并说明原因。{final_clip}",
                location_info,
                severity="warn"
            ))

        # 2. 数字 vs 文句：不一致则报错（"等于"视为"持平"同等）
        if calc != stated and not ("等于" == stated and calc == "持平"):
            issues.append(self._issue(
                f"年初预算={raw_bud}，决算={raw_act}（判定为{calc}，文本表述{stated}）{final_clip}",
                location_info,
                severity="error"
            ))

        # 3. "缺少原因"：仅当 stated 是"大于/小于"且在"其中："之后
        if stated in {"大于", "小于"} and not reason_text:
            # 检查是否在"其中："之后
            idx_qizhong = sec.find("其中")
            if idx_qizhong >= 0 and pair_info["match_start"] > idx_qizhong:
                issues.append(self._issue(
                    f"本项表述决算数{stated}预算数后未见主要原因...，请补充原因说明。{final_clip}",
                    location_info,
                    severity="error"
                ))

        return issues


# ---------- 注册 ----------
ALL_RULES: List[Rule] = [
    R33001_CoverYearUnit(),
    R33002_NineTablesCheck(),
    R33003_PageFileThreshold(),
    R33004_CellNumberValidity(),
    R33005_TableTotalConsistency(),

    # —— 跨表 & 文数一致 —— #
    R33101_TotalSheet_Identity(),
    R33102_TotalSheet_vs_Text(),
    R33103_Income_vs_Text(),
    R33104_Expense_vs_Text(),
    R33105_FinGrantTotal_vs_Text(),
    R33106_GeneralBudgetStruct(),
    R33107_BasicExpense_Check(),
    R33108_ThreePublic_vs_Text(),
    R33109_EmptyTables_Statement(),
    R33110_BudgetVsFinal_TextConsistency(),
]


# ---------- 构建 Document ----------
def build_document(path: str,
                   page_texts: List[str],
                   page_tables: List[List[List[List[str]]]],
                   filesize: int) -> Document:
    pages = len(page_texts)
    units: List[Optional[str]] = []
    years: List[List[int]] = []
    for i in range(pages):
        units.append(extract_money_unit(page_texts[i]))
        years.append(extract_years(page_texts[i]))
    doc = Document(
        path=path, pages=pages, filesize=filesize,
        page_texts=page_texts, page_tables=page_tables,
        units_per_page=units, years_per_page=years,
    )
    doc.anchors = find_table_anchors(doc)

    # 主年度：前 3 页 + 首个表页之前
    front_years: List[int] = []
    for i in range(min(3, pages)):
        front_years += years[i]
    doc.dominant_year = majority(front_years)

    # 主单位：直到首张表页
    first_table_page = None
    if doc.anchors:
        ps = [min(v) for v in doc.anchors.values() if v]
        if ps:
            first_table_page = min(ps)
    scan_upto = min(pages, max(3, (first_table_page or 3)))
    doc.dominant_unit = majority([u for u in units[:scan_upto] if u])

    return doc
