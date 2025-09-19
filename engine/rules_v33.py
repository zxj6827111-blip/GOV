from typing import Any, Dict, Optional, List
from pathlib import Path
import logging
import yaml

_yaml_cache: Optional[Dict[str, Any]] = None

def _candidate_yaml_paths() -> List[Path]:
    # 依次尝试常见位置；按需可再加
    candidates = [
        Path("rules/v3_3.yaml"),
        Path("./rules/v3_3.yaml"),
        (Path(__file__).resolve().parent.parent / "rules" / "v3_3.yaml"),
    ]
    # 去重（保持顺序）
    uniq, seen = [], set()
    for p in candidates:
        rp = p.resolve()
        if rp not in seen:
            uniq.append(rp); seen.add(rp)
    return uniq

def load_rules_yaml() -> Optional[Dict[str, Any]]:
    """寻找 v3_3.yaml；兼容多文档 YAML（---），将多个文档合并为一个 dict。"""
    global _yaml_cache
    if _yaml_cache is not None:
        return _yaml_cache

    for p in _candidate_yaml_paths():
        try:
            if not p.exists():
                continue
            with p.open("r", encoding="utf-8") as f:
                docs = list(yaml.load_all(f, Loader=yaml.SafeLoader))
            merged: Dict[str, Any] = {}
            for d in docs:
                if isinstance(d, dict):
                    merged.update(d)   # 后文档覆盖前文档
            _yaml_cache = merged
            logging.info(f"[rules] loaded YAML from: {p} (docs={len(docs)})")
            return _yaml_cache
        except Exception as e:
            logging.warning(f"[rules] failed to load {p}: {e}")

    logging.warning("[rules] v3_3.yaml not found; fallback to builtin")
    return None
