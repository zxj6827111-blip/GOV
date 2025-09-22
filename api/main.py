# api/main.py
import os
import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

import pdfplumber  # ✅ 新增：读取 PDF
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# 直接使用引擎暴露的构建与包装函数
from engine.pipeline import build_document, build_issues_payload

# ----------------------------- 基础配置 -----------------------------
APP_TITLE = "GovBudgetChecker API"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "30"))
UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=APP_TITLE)

# ----------------------------- CORS -----------------------------
# 本地 & Codespaces
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
codespace = os.getenv("CODESPACE_NAME")
gh_dom = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
if codespace and gh_dom:
    origins += [
        f"https://{codespace}-3000.{gh_dom}",
        f"https://{codespace}-8000.{gh_dom}",
    ]

extra = os.getenv("ALLOW_ORIGINS", "").strip()
if extra:
    origins += [o.strip() for o in extra.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------- 工具函数 -----------------------------
def _safe_write(job_dir: Path, payload: Dict[str, Any]) -> None:
    """将状态写入 status.json（带异常保护）"""
    try:
        (job_dir / "status.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        (job_dir / "status_error.log").write_text(str(e), encoding="utf-8")


def _find_first_pdf(job_dir: Path) -> Path:
    pdfs = sorted(job_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError("未在该 job 目录下找到 PDF 文件")
    return pdfs[0]


def _extract_tables_from_page(page) -> List[List[List[str]]]:
    """
    读取单页表格，返回：该页的多张表；每张表是 2D 数组（行→列）
    （和引擎里的逻辑一致，先用线策略，再退回默认）
    """
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


def _run_pipeline(job_dir: Path) -> None:
    """
    真正的解析管线：
    - 读取 job_dir 下的 PDF
    - 解析文本与表格，构建 Document
    - 调用 build_issues_payload 打包返回
    - 写入 status.json（result.summary / result.issues / result.meta）
    """
    try:
        # 标记 processing
        _safe_write(job_dir, {
            "job_id": job_dir.name,
            "status": "processing",
            "progress": 5,
            "ts": time.time(),
        })

        pdf_path = _find_first_pdf(job_dir)
        started = time.time()

        # 读取 PDF -> 文本/表格
        page_texts: List[str] = []
        page_tables: List[List[List[List[str]]]] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for p in pdf.pages:
                page_texts.append(p.extract_text() or "")
                page_tables.append(_extract_tables_from_page(p))
        filesize = pdf_path.stat().st_size

        # 构建 Document
        doc = build_document(
            path=str(pdf_path),
            page_texts=page_texts,
            page_tables=page_tables,
            filesize=filesize
        )

        # 运行规则并打包统一结构（issues: {error/warn/info/all}）
        payload_issues = build_issues_payload(doc)

        # 组装最终返回体（保持你之前的契约字段）
        result = {
            "summary": "",                       # 现在没有汇总，可后续填充
            "issues": payload_issues["issues"],  # 统一分桶结构
            "meta": {
                "pages": len(page_texts),
                "filesize": filesize,
                "job_id": job_dir.name,
                "started_at": started,
                "finished_at": time.time(),
            }
        }

        payload = {
            "job_id": job_dir.name,
            "status": "done",
            "progress": 100,
            "result": result,
            "ts": time.time(),
        }
        _safe_write(job_dir, payload)

    except Exception as e:
        _safe_write(job_dir, {
            "job_id": job_dir.name,
            "status": "error",
            "error": str(e),
            "ts": time.time(),
        })

# ----------------------------- 健康/根 -----------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": APP_TITLE}

@app.get("/")
def root():
    return {"service": APP_TITLE, "status": "ok"}

# ----------------------------- 上传 & 下载 -----------------------------
def _ensure_pdf(file: UploadFile):
    ct = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    return ct in ("application/pdf", "application/x-pdf") or name.endswith(".pdf")

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not _ensure_pdf(file):
        raise HTTPException(status_code=415, detail="仅支持 PDF 文件")

    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {MAX_UPLOAD_MB}MB 限制")

    job_id = os.urandom(16).hex()
    job_dir = UPLOAD_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "file.pdf").name
    dst = job_dir / safe_name
    with open(dst, "wb") as f:
        f.write(data)

    checksum = hashlib.sha256(data).hexdigest()
    return {
        "job_id": job_id,
        "filename": safe_name,
        "size": len(data),
        "saved_path": str(dst.relative_to(UPLOAD_ROOT)),
        "checksum": checksum,
    }

@app.get("/jobs/{job_id}")
def list_job_files(job_id: str):
    job_dir = (UPLOAD_ROOT / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    files = []
    for p in job_dir.iterdir():
        if p.is_file():
            st = p.stat()
            files.append({"name": p.name, "size": st.st_size, "mtime": int(st.st_mtime)})
    return {"job_id": job_id, "files": files}

@app.get("/jobs/{job_id}/download/{filename}")
def download(job_id: str, filename: str):
    job_dir = (UPLOAD_ROOT / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    safe_name = Path(filename).name
    path = (job_dir / safe_name).resolve()
    if job_dir not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, media_type="application/pdf", filename=safe_name)

# ----------------------------- 触发解析 & 轮询 -----------------------------
@app.post("/analyze2/{job_id}")
def analyze2(job_id: str):
    job_dir = (UPLOAD_ROOT / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    _safe_write(job_dir, {"job_id": job_id, "status": "queued", "ts": time.time()})
    threading.Thread(target=_run_pipeline, args=(job_dir,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}

# 轮询（保持接口名不变）
@app.get("/jobs_adv2/{job_id}/status")
def job_status_adv2(job_id: str):
    job_dir = (UPLOAD_ROOT / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    p = job_dir / "status.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"job_id": job_id, "status": "unknown"}

    # 如果刚触发但文件还没写出来，先返回 queued，避免“unknown”刷屏
    newest = max((f.stat().st_mtime for f in job_dir.glob("*") if f.is_file()), default=0)
    if newest and time.time() - newest < 60:
        return {"job_id": job_id, "status": "queued"}

    return {"job_id": job_id, "status": "unknown"}

# -----------------------------
# 启动示例：
# uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
# -----------------------------
