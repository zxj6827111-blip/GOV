# api/main.py
import os
import json
import time
import hashlib
import threading
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
# api/main.py
import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="GovBudgetChecker API")

# -------------------- CORS（跨域） --------------------
# 推荐精确白名单；如果你暂时不确定域名，可在开发时用 allow_origins=["*"]（不带凭据）
# 浏览器不能访问 0.0.0.0；用 localhost 或你的转发域名（codespaces）
default_origins = [
    "http://localhost:3000",
    "https://localhost:3000",
]

# Codespaces / GitHub 转发域名（如果你在云端跑前端）
codespace = os.getenv("CODESPACE_NAME")
gh_dom = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
if codespace and gh_dom:
    # 允许 3000 和 8000 两个端口的转发域名
    default_origins += [
        f"https://{codespace}-3000.{gh_dom}",
        f"https://{codespace}-8000.{gh_dom}",
    ]

# 允许通过环境变量追加自定义白名单，多个用逗号分隔
extra = os.getenv("ALLOW_ORIGINS", "").strip()
if extra:
    default_origins += [o.strip() for o in extra.split(",") if o.strip()]

# 开发期也可直接放开："*"
allow_all = os.getenv("CORS_ALLOW_ALL", "false").lower() in ("1", "true", "yes")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all else default_origins,
    allow_credentials=False,                 # 如果不需要 cookie，保持 False 更安全
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- 健康检查 --------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# 下面是你已有的上传/状态/分析路由……（保持不动）
# ...

# -----------------------------
# 基础配置
# -----------------------------
APP_TITLE = "GovBudgetChecker API"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "30"))
UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=APP_TITLE)

# 允许前端调试域名
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "https://jubilant-orbit-r4v9ww9pgq79fgwr-8000.app.github.dev",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\\.app\\.github\\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# 工具函数
# -----------------------------
def _safe_write(job_dir: Path, payload: Dict[str, Any]) -> None:
    """将状态写入 status.json（带异常保护）"""
    try:
        (job_dir / "status.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        (job_dir / "status_error.log").write_text(str(e), encoding="utf-8")


def _run_pipeline(job_dir: Path) -> None:
    """
    解析管线（示例）：
    - processing -> done
    - 这里你可以调用真正的规则引擎；目前是演示结果
    """
    try:
        _safe_write(job_dir, {
            "job_id": job_dir.name,
            "status": "processing",
            "progress": 10,
            "ts": time.time(),
        })
        time.sleep(0.8)

        # ====== 在此处接“规则引擎” ======
        # 你可以引入自己的模块： from rules_v33 import run_rules
        # result = run_rules(pdf_path= str(job_dir/'xxx.pdf'))
        # issues = result.issues
        # summary = result.summary
        # 这里仍然给一个演示 payload:
        issues = [
            {
                "rule": "MUST_HAVE_DIR",
                "severity": "info",
                "message": "前 3 页未检测到“目录”字样（示例规则）",
                "location": {"page": 1}
            },
            {
                "rule": "FILE_SIZE_INFO",
                "severity": "info",
                "message": "文件大小约 0.23 MB（信息）"
            }
        ]

        meta = {}
        # 如你有 OCR / 页面数等，可在 meta 里追加

        payload = {
            "job_id": job_dir.name,
            "status": "done",
            "progress": 100,
            "result": {
                "summary": f"规则共命中 {len(issues)} 条",
                "issues": issues,
                "meta": meta,
            },
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

# -----------------------------
# 健康/根
# -----------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": APP_TITLE}

@app.get("/")
def root():
    return {"service": APP_TITLE, "status": "ok"}

# -----------------------------
# 上传 & 下载
# -----------------------------
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

# -----------------------------
# 触发解析（新版 analyze2） & 轮询（新版 jobs_adv2）
# -----------------------------
@app.post("/analyze2/{job_id}")
def analyze2(job_id: str):
    job_dir = (UPLOAD_ROOT / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    _safe_write(job_dir, {"job_id": job_id, "status": "queued", "ts": time.time()})
    threading.Thread(target=_run_pipeline, args=(job_dir,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}

@app.get("/jobs_adv2/{job_id}/status")
def job_status_adv2(job_id: str):
    job_dir = (UPLOAD_ROOT / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    p = job_dir / "status.json"
    if not p.exists():
        return {"job_id": job_id, "status": "unknown"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"job_id": job_id, "status": "unknown"}

# -----------------------------
# 启动命令（供参考）
# uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
# -----------------------------
