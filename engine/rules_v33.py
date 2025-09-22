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
    按 (page, pos) 排序，并把 message 前面加上 “一、二、三…”
    说明：
    - 其它规则请尽量往 location 里塞 { "page": 页码, "pos": 页内位置 }，
      这样这里才能按文中顺序排。
    """
    def sort_key(it):
        p = it.location.get("page", 10**9)   # 没页码的排在最后
        s = it.location.get("pos", 0)        # 没 pos 的当 0 处理
        return (p, s)

    sorted_issues = sorted(issues, key=sort_key)
    for idx, it in enumerate(sorted_issues, start=1):
        cn = to_cn_num(idx)
        # 避免重复加序号（防止多次调用）
        if not it.message.startswith(("一、","二、","三、","四、","五、","六、","七、","八、","九、","十、")):
            it.message = f"{cn}、{it.message}"
    return sorted_issues
# engine/rules_v33.py  —— v3.3 规则（修正版）

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

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




def _guess_pos_in_page(doc: "Document", page: int, clip: str, fallback_text: str = "") -> int:
    """
    在该页内估一个'位置'（字符起始下标）。优先用 clip 里前 20~50 字。
    找不到时返回一个很大的数，保证排序时放在该页靠后。
    """
    try:
        if page is None or page < 1 or page > len(doc.page_texts):
            return 10**9
        hay = doc.page_texts[page-1]
        for k in (clip or "", fallback_text or ""):
            s = (k or "").strip().replace("\n", "")
            if len(s) >= 8:
                s = s[:50]
                i = hay.find(s)
                if i >= 0:
                    return i
        return 10**9
    except Exception:
        return 10**9
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
    pat = re.compile(rf"(?:{kw}).{{0,30}}?(-?\d{{1,3}}(?:,\d{{3}})*|\d+)(?:\.(\d+))?", flags=re.S | re.M)
    m = pat.search(text)
    if not m:
        return None
    n = re.findall(r"-?\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?", m.group(0))
    if not n:
        return None
    try:
        return float(n[0].replace(",", ""))
    except Exception:
        return None

def find_percent(text: str, keywords: List[str]) -> Optional[float]:
    if not text:
        return None
    kw = "|".join(map(re.escape, keywords))
    m = re.search(rf"(?:{kw}).{{0,30}}?(-?\d+(?:\.\d+)?)\s*%", text, flags=re.S | re.M)
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
        issues: List[Issue] = []

        # 1) 找“收入支出决算总表”的第一页
        p = _get_first_anchor_page(doc, "收入支出决算总表")
        if not p:
            return issues

        # 2) 取该页最大的一张表
        table = _largest_table_on_page(doc.page_tables[p - 1])
        if not table:
            return issues

        # 3) 表中“支出合计/支出总计/合计/收支总计”的值
        total = _row_value(table, ("支出合计", "支出总计", "合计", "收支总计"))
        if total is None:
            return issues

        # 4) 在全文“收入支出决算总体情况说明 / 年度收入支出总计 / 总计 / 合计”附近拿一个数字
        txt = "\n".join(doc.page_texts)
        t_total = near_number(
            txt,
            ["收入支出决算总体情况说明", "年度收入支出总计", "总计", "合计"]
        )

        # 5) 不一致则报问题
        if (t_total is not None) and not tolerant_equal(total, t_total):
            issues.append(self._issue(
                f"总表支出合计：表{total} ≠ 文本{t_total}",
                {"page": p},
                "warn"
            ))
        return issues

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
        issues: List[Issue] = []
        name = "一般公共预算财政拨款支出决算表"
        p = _get_first_anchor_page(doc, name)
        if not p:
            return issues
        table = _largest_table_on_page(doc.page_tables[p - 1])
        if not table:
            return issues

        total = _row_value(table, ("合计", "本年支出合计", "支出合计"),
                           prefer_cols=("合计", "本年支出合计", "支出合计"))
        if total is None:
            return issues

        txt = "\n".join(doc.page_texts)
        t_total = near_number(txt, ["一般公共预算财政拨款支出决算总体情况", "支出决算总体情况", "合计", "总计"])
        if t_total and not tolerant_equal(total, t_total):
            issues.append(self._issue(f"一般公共预算财拨支出合计：表{total} ≠ 文本{t_total}", {"page": p}, "warn"))

        by_cls = _sum_by_func_class(table, 3)
        if total and by_cls:
            for cls, val in list(by_cls.items())[:10]:
                pct_c = round(val / total * 100, 2)
                pct_t = find_percent(txt, [cls, "占比", "比重"])
                if pct_t is not None and abs(pct_c - pct_t) > 1.5:
                    issues.append(self._issue(f"功能分类{cls}占比：表算{pct_c}% ≠ 文本{pct_t}%（容忍±1.5pct）", {"page": p}, "warn"))
        return issues


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


# ---------- V33-110：预算/决算与“大于/小于/持平”文句一致性 ----------
class R33110_BudgetVsFinal_TextConsistency(Rule):
    code, severity = "V33-110", "error"
    desc = "（三）具体情况：文句“大于/小于/持平”与预算/决算数字一致性"

    _SEC_START = re.compile(r"(（三）|三、)\s*一般公共预算财政拨款支出决算具体情况")
    _NEXT_SEC  = re.compile(r"(（四）|四、|（六）|六、|一般公共预算财政拨款基本支出决算情况说明)")

    # 语句匹配：… 年初预算 为/是 X ，支出决算 为/是 Y …（并出现“大于/小于/等于/持平/基本持平”）
    _PAIR = re.compile(
        r"年初预算[为是]?\s*(\d+(?:\.\d+)?)\s*万?元?.{0,40}?支出决算[为是]?\s*(\d+(?:\.\d+)?)\s*万?元?.{0,60}?"
        r"(决算数(?:大于|小于|等于|持平|基本持平)预算数)",
        re.S
    )

    def _slice_section_span(self, full: str):
        """
        返回：该小节文本 + 在全文中的起止下标（start, end）。
        便于用 m.start() 做“绝对位置”，从而映射到“第几页/页内位置”。
        """
        m1 = self._SEC_START.search(full)
        if not m1:
            return None, -1, -1
        start = m1.start()
        m2 = self._NEXT_SEC.search(full[m1.end():])
        end = m1.end() + (m2.start() if m2 else len(full[m1.end():]))
        return full[start:end], start, end

    def apply(self, doc: Document) -> List[Issue]:
        issues: List[Issue] = []
        full = "\n".join(doc.page_texts)

        # 取该节文本 + 在全文中的起点
        sec, sec_start, _ = self._slice_section_span(full)
        if not sec:
            return issues

        # 把每页在全文中的起始下标算出来：offsets[i] = 第 i 页在全文中的起点
        offsets = [0]
        acc = 0
        for t in doc.page_texts:
            acc += len(t)
            offsets.append(acc)

        for m in self._PAIR.finditer(sec):
            b, a = float(m.group(1)), float(m.group(2))  # budget, actual
            phrase = m.group(3)

            # —— 判定大于/小于/持平（容差）
            tol = max(0.5, max(abs(a), abs(b)) * 0.003)
            if a > b + tol:
                calc = "大于"
            elif a < b - tol:
                calc = "小于"
            else:
                calc = "持平"

            stated = "持平" if "持平" in phrase else ("大于" if "大于" in phrase else ("小于" if "小于" in phrase else "等于"))

            # “基本持平”提示
            if "基本持平" in phrase:
                issues.append(self._issue("用语“基本持平”不规范，建议写“持平”并说明原因。", severity="warn"))

            # —— 计算这条命中的“绝对位置 & 第几页 & 页内位置”
            abs_pos = sec_start + m.start()  # sec 在全文中的起点 + 片段在 sec 中的起点
            page = 1
            pos_in_page = 0
            for i in range(len(offsets) - 1):
                if offsets[i] <= abs_pos < offsets[i + 1]:
                    page = i + 1
                    pos_in_page = abs_pos - offsets[i]
                    break

            if calc != stated and not ("等于" == stated and calc == "持平"):
                issues.append(self._issue(
                    f"“{phrase}”与数字不一致：年初预算={b}，决算={a}（判定为“{calc}”）",
                    {"page": page, "pos": pos_in_page, "clip": m.group(0)},   # ★ 写入 pos + 片段
                    severity="error"
                ))
        return issues




# ---------- 注册 ----------
ALL_RULES: List[Rule] = [
    R33001_CoverYearUnit(),
    R33002_NineTablesCheck(),
    R33003_PageFileThreshold(),
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
