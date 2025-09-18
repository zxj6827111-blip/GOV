from fastapi import FastAPI, UploadFile, File, HTTPException
from starlette.responses import JSONResponse

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"service": "GovBudgetChecker API", "status": "ok"}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not (file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")):
        raise HTTPException(status_code=415, detail="仅支持 PDF 文件")
    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 30MB 限制")
    return JSONResponse({"job_id": "demo", "filename": file.filename, "size": len(data)})
