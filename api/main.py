import os, hashlib
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
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
