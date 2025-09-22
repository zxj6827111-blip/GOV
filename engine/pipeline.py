# engine/pipeline.py
from __future__ import annotations
import os, time
from typing import Dict, Any, List, Optional  # ✅ 增加 Optional
import pdfplumber

from .rules_v33 import ALL_RULES, build_document, order_and_number_issues, Issue

def _extract_tables_from_page(page) -> List[List[List[str]]]:
    # 返回：该页的多张表；每张表是 2D 数组（行→列）
    tables: List[List[List[str]]] = []
    try:
        t1 = page.extract_tables(table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_tolerance": 3,
            "min_words_vertical": 1,
            "min_words_horizontal": 1,
        }) or []
        tables += t1
    except Exception:
        pass
    try:
        if not tables:
            t2 = page.extract_tables() or []
            tables += t2
    except Exception:
        pass
    norm_tables: List[List[List[str]]] = []
    for tb in tables:
        norm_tables.append([[("" if c is None else str(c)).strip() for c in row] for row in (tb or [])])
    return norm_tables

def run_rules(doc):
    issues = []
    for rule in ALL_RULES:
        try:
            issues.extend(rule.apply(doc))
        except Exception as e:
            issues.append(Issue(
                rule=rule.code, severity="hint",
                message=f"规则执行异常：{e}",
                location={"page": 1, "pos": 0}
            ))
    # ★ 统一排序 + 编号
    issues = order_and_number_issues(doc, issues)
    return issues

# ===== 在此行下面粘贴 =====

def _issue_to_dict(x) -> dict:
    if isinstance(x, dict):
        return {
            "rule": x.get("rule", ""),
            "severity": (x.get("severity") or "info"),
            "message": x.get("message", ""),
            "location": (x.get("location") or {}),
        }
    return {
        "rule": getattr(x, "rule", "") or "",
        "severity": getattr(x, "severity", None) or "info",
        "message": getattr(x, "message", "") or "",
        "location": getattr(x, "location", None) or {},
    }

def _norm_sev(s: Optional[str]) -> str:  # ✅ 参数改为 Optional[str]
    s = (s or "").lower()
    if s in ("error", "err", "fatal", "critical"):
        return "error"
    if s in ("warn", "warning"):
        return "warn"
    return "info"


def build_issues_payload(doc) -> dict:
    """
    把规则结果打包成前端需要的结构：
    {
      "issues": {
        "error": [...],
        "warn":  [...],
        "info":  [...],
        "all":   [...]
      }
    }
    """
    raw_list = run_rules(doc)  # List[Issue]
    items = [_issue_to_dict(x) for x in raw_list]
    for it in items:
        it["severity"] = _norm_sev(it.get("severity"))

    buckets = {"error": [], "warn": [], "info": []}
    for d in items:
        buckets[d["severity"]].append(d)
    buckets["all"] = items

    # 关键：返回必须带 "issues" 这个键
    return {"issues": buckets}
