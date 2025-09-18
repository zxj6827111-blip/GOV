import os, hashlib, json, time
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"service": "GovBudgetChecker API", "status": "ok"}

def _config():
    max_mb = int(os.getenv("MAX_UPLOAD_MB", "30"))
    upload_root = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    return max_mb, upload_root

def _is_pdf(up: UploadFile) -> bool:
    ct = (up.content_type or "").lower()
    name = (up.filename or "").lower()
    return ct in ("application/pdf", "application/x-pdf") or name.endswith(".pdf")

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not _is_pdf(file):
        raise HTTPException(status_code=415, detail="仅支持 PDF 文件")
    data = await file.read()

    max_mb, upload_root = _config()
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {max_mb}MB 限制")

    job_id = os.urandom(16).hex()
    job_dir = (upload_root / job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "file.pdf").name  # 去除路径片段
    dst = (job_dir / safe_name)

    with open(dst, "wb") as f:
        f.write(data)

    checksum = hashlib.sha256(data).hexdigest()
    return {
        "job_id": job_id,
        "filename": safe_name,
        "size": len(data),
        "saved_path": str(dst.relative_to(upload_root)),
        "checksum": checksum,
    }

@app.get("/jobs/{job_id}")
def list_job_files(job_id: str):
    _, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
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
    _, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")

    safe_name = Path(filename).name
    path = (job_dir / safe_name).resolve()
    # 路径穿越保护：必须位于该 job 目录下
    if job_dir not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")

    return FileResponse(path, media_type="application/pdf", filename=safe_name)

@app.post("/analyze/{job_id}")
def analyze(job_id: str):
    max_mb, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    payload = {"job_id": job_id, "status": "queued"}
    (job_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload

def _write_status(job_dir: Path, payload: dict):
    (job_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

def _run_analysis(job_dir: Path):
    # processing
    _write_status(job_dir, {"job_id": job_dir.name, "status": "processing", "progress": 10})
    time.sleep(1)
    _write_status(job_dir, {"job_id": job_dir.name, "status": "processing", "progress": 60})
    time.sleep(1)
    # done（这里先写一个占位结果）
    _write_status(job_dir, {
        "job_id": job_dir.name, "status": "done", "progress": 100,
        "result": {"issues": [], "summary": "解析完成（占位）"}
    })

@app.post("/analyze/{job_id}")
def analyze(job_id: str, bg: BackgroundTasks):
    _, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    # 置为 queued，并在后台异步推进状态
    _write_status(job_dir, {"job_id": job_id, "status": "queued"})
    bg.add_task(_run_analysis, job_dir)
    return {"job_id": job_id, "status": "queued"}

# 补一个查询状态的接口，便于前端轮询
@app.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    _, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    p = job_dir / "status.json"
    if not p.exists():
        return {"job_id": job_id, "status": "unknown"}
    return json.loads(p.read_text(encoding="utf-8"))

def _write_status(job_dir: Path, payload: dict):
    (job_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

def _run_analysis(job_dir: Path):
    # processing -> done 的简单演示
    _write_status(job_dir, {"job_id": job_dir.name, "status": "processing", "progress": 10})
    time.sleep(1)
    _write_status(job_dir, {"job_id": job_dir.name, "status": "processing", "progress": 60})
    time.sleep(1)
    _write_status(job_dir, {
        "job_id": job_dir.name, "status": "done", "progress": 100,
        "result": {"issues": [], "summary": "解析完成（占位）"}
    })

@app.post("/analyze/{job_id}")
def analyze(job_id: str):
    _, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    _write_status(job_dir, {"job_id": job_id, "status": "queued"})
    # 用守护线程推进状态，避免 dev 热载时 BackgroundTasks 偶发不跑
    threading.Thread(target=_run_analysis, args=(job_dir,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}

def _safe_write(job_dir: Path, payload: dict):
    try:
        (job_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        (job_dir / "status_error.log").write_text(str(e), encoding="utf-8")

def _run_analysis_v2(job_dir: Path):
    try:
        _safe_write(job_dir, {"job_id": job_dir.name, "status": "processing", "progress": 10})
        time.sleep(1)
        _safe_write(job_dir, {"job_id": job_dir.name, "status": "processing", "progress": 60})
        time.sleep(1)
        _safe_write(job_dir, {
            "job_id": job_dir.name, "status": "done", "progress": 100,
            "result": {"issues": [], "summary": "解析完成（占位）"}
        })
    except Exception as e:
        _safe_write(job_dir, {"job_id": job_dir.name, "status": "error", "error": str(e)})

# 覆盖同一路由，使用守护线程推进状态
@app.post("/analyze/{job_id}")
def analyze(job_id: str):
    _, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")
    _safe_write(job_dir, {"job_id": job_id, "status": "queued"})
    threading.Thread(target=_run_analysis_v2, args=(job_dir,), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}

# 覆盖 /jobs/{job_id}/status：读取并按时间推进 queued->processing->done
@app.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    _, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")

    p = job_dir / "status.json"
    now = time.time()
    state = {"job_id": job_id, "status": "unknown", "ts": now}

    if p.exists():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 推进状态：第一次查询把 queued -> processing；第二次（>1s）把 processing -> done
    if state.get("status") == "queued":
        state = {"job_id": job_id, "status": "processing", "progress": 50, "ts": now}
        p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    elif state.get("status") == "processing" and (now - state.get("ts", 0)) > 1.0:
        state = {
            "job_id": job_id,
            "status": "done",
            "progress": 100,
            "result": {"issues": [], "summary": "解析完成（占位）"},
            "ts": now,
        }
        p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    return state

# 自推进状态：第一次查询把 queued->processing，下一次(>1s)把 processing->done
@app.get("/jobs_adv/{job_id}/status")
def job_status_adv(job_id: str):
    _, upload_root = _config()
    job_dir = (upload_root / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="job not found")

    p = job_dir / "status.json"
    now = time.time()
    state = {"job_id": job_id, "status": "unknown", "ts": now}

    if p.exists():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass

    if state.get("status") == "queued":
        state = {"job_id": job_id, "status": "processing", "progress": 50, "ts": now}
        p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    elif state.get("status") == "processing" and (now - state.get("ts", 0)) > 1.0:
        state = {
            "job_id": job_id,
            "status": "done",
            "progress": 100,
            "result": {"issues": [], "summary": "解析完成（占位）"},
            "ts": now,
        }
        p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    return state
