# engine/rules_v33.py
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json

@dataclass
class Issue:
    rule_id: str
    severity: str   # low/medium/high
    title: str
    detail: str
    location: str | None = None

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def analyze(pdf_path: str, meta_hint: dict | None = None) -> dict:
    """
    返回结构:
    {
      "summary": "...",
      "issues": [ {rule_id, severity, title, detail, location}, ... ],
      "meta": { "path": "...", "size": 123, "pages": 25, "sha256": "..."}
    }
    """
    p = Path(pdf_path)
    size = p.stat().st_size
    sha = _sha256(p)

    # ---- 规则示例（你之后可以替换成真正的规则）----
    issues: list[Issue] = []

    # R-001: 文件大小过小（示例）
    if size < 1024:
        issues.append(Issue(
            "R-001", "low", "PDF 文件体积异常偏小",
            f"大小仅 {size} 字节，可能不是完整的 PDF。", location=None
        ))

    # R-002: 文件大小过大（示例阈值 50MB）
    if size > 50 * 1024 * 1024:
        issues.append(Issue(
            "R-002", "medium", "PDF 体积过大",
            f"大小 {size} 字节，超过 50MB，影响上传与解析效率。", location=None
        ))

    # R-003: 缺页/页数未知示例（若前置流程未识别出页数）
    pages = None
    if meta_hint and isinstance(meta_hint.get("pages"), int):
        pages = meta_hint["pages"]
    if pages is None:
        issues.append(Issue(
            "R-003", "low", "未能识别页数",
            "建议在解析环节识别页数，用于后续规则。", location=None
        ))

    summary = f"规则共命中 {len(issues)} 条"
    result = {
        "summary": summary,
        "issues": [asdict(x) for x in issues],
        "meta": {"path": str(p), "size": size, "pages": pages, "sha256": sha}
    }
    return result
