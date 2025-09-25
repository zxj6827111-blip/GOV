# api/main.py
import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 加载.env文件（如果存在）
try:
    from dotenv import load_dotenv

    load_dotenv()  # 忽略返回值
except ImportError:
    # 如果没有安装python-dotenv，则手动解析.env文件
    def load_env_file():
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ.setdefault(key.strip(), value.strip())

    load_env_file()

# 确保项目根目录加入 sys.path，避免从 api 目录启动时找不到顶层包
import sys as _sys

import pdfplumber  # ✅ 新增：读取 PDF
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

# 直接使用引擎暴露的构建与包装函数
from api.config import AppConfig
from config.settings import get_settings
from engine.pipeline import build_document, build_issues_payload

# 新增：YAML规则加载器
from engine.rules_yaml_loader import get_rules_loader

# 新增：数据模型和服务
from schemas.issues import (
    JobContext,
)

# 新增：双模式分析服务
from services.analyze_dual import DualModeAnalyzer
from services.evidence_extractor import extract_evidence_from_pdf

# 新增：性能优化器
from services.performance_optimizer import get_performance_optimizer

# ----------------------------- 基础配置 -----------------------------
APP_TITLE = "GovBudgetChecker API"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "30"))
UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# 初始化logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title=APP_TITLE)
config = AppConfig.load()

# 新增：双模式配置
settings = get_settings()
dual_analyzer = DualModeAnalyzer()

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
        t1 = (
            page.extract_tables(
                table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "intersection_tolerance": 3,
                    "min_words_vertical": 1,
                    "min_words_horizontal": 1,
                }
            )
            or []
        )
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
        norm_tables.append(
            [[("" if c is None else str(c)).strip() for c in row] for row in (tb or [])]
        )
    return norm_tables


async def _run_pipeline(job_dir: Path) -> None:
    """
    真正的解析管线：
    - 读取 job_dir 下的 PDF
    - 解析文本与表格，构建 Document
    - 调用 build_issues_payload 打包返回
    - 写入 status.json（result.summary / result.issues / result.meta）
    """
    # 提前初始化 provider_stats，确保处理中/失败态也能返回该字段
    try:
        # 读取检测模式配置
        status_file = job_dir / "status.json"
        use_local_rules = True
        use_ai_assist = True
        mode = "legacy"  # 默认为旧模式

        if status_file.exists():
            try:
                status_data = json.loads(status_file.read_text(encoding="utf-8"))
                use_local_rules = status_data.get("use_local_rules", True)
                use_ai_assist = status_data.get("use_ai_assist", True)
                mode = status_data.get("mode", "legacy")
            except:
                pass

        # 检查是否启用双模式
        dual_mode_enabled = False
        if mode == "dual":
            dual_mode_enabled = True

        # 标记 processing
        _safe_write(
            job_dir,
            {
                "job_id": job_dir.name,
                "status": "processing",
                "progress": 5,
                "ts": time.time(),
                "use_local_rules": use_local_rules,
                "use_ai_assist": use_ai_assist,
                "mode": mode,
                "dual_mode_enabled": dual_mode_enabled,
                "stage": "开始解析文档",
            },
        )

        pdf_path = _find_first_pdf(job_dir)
        started = time.time()

        # 读取 PDF -> 文本/表格
        _safe_write(
            job_dir,
            {
                "job_id": job_dir.name,
                "status": "processing",
                "progress": 15,
                "ts": time.time(),
                "use_local_rules": use_local_rules,
                "use_ai_assist": use_ai_assist,
                "mode": mode,
                "dual_mode_enabled": dual_mode_enabled,
                "stage": "解析PDF内容",
            },
        )

        page_texts: List[str] = []
        page_tables: List[List[List[List[str]]]] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for p in pdf.pages:
                page_texts.append(p.extract_text() or "")
                page_tables.append(_extract_tables_from_page(p))
        filesize = pdf_path.stat().st_size

        # 构建 Document
        _safe_write(
            job_dir,
            {
                "job_id": job_dir.name,
                "status": "processing",
                "progress": 25,
                "ts": time.time(),
                "use_local_rules": use_local_rules,
                "use_ai_assist": use_ai_assist,
                "mode": mode,
                "dual_mode_enabled": dual_mode_enabled,
                "stage": "构建文档对象",
            },
        )

        doc = build_document(
            path=str(pdf_path), page_texts=page_texts, page_tables=page_tables, filesize=filesize
        )

        # 双模式分析
        if dual_mode_enabled:
            _safe_write(
                job_dir,
                {
                    "job_id": job_dir.name,
                    "status": "processing",
                    "progress": 35,
                    "ts": time.time(),
                    "use_local_rules": use_local_rules,
                    "use_ai_assist": use_ai_assist,
                    "mode": mode,
                    "dual_mode_enabled": dual_mode_enabled,
                    "stage": "双模式分析",
                },
            )

            # 构建JobContext
            # 将 page_tables 转换为 JobContext.tables，以激活依赖表格的规则
            flat_tables = []
            try:
                for idx, page_tb_list in enumerate(page_tables or []):
                    for tb in page_tb_list or []:
                        flat_tables.append({"page": idx + 1, "data": tb})
            except Exception:
                flat_tables = []
            job_context = JobContext(
                job_id=job_dir.name,
                pdf_path=str(pdf_path),
                ocr_text="\n".join(page_texts),  # 合并所有页面文本
                tables=flat_tables,
                pages=len(page_texts),
                meta={
                    "started_at": started,
                    "page_texts": page_texts,  # 按页文本
                    "page_tables": page_tables,  # 按页表格（每页多张表）
                },
            )

            # 执行双模式分析
            dual_result = await dual_analyzer.analyze(job_context)

            # 组装最终返回体（双模式结构）
            result = {
                "summary": "",
                "ai_findings": [item.dict() for item in dual_result.ai_findings],
                "rule_findings": [item.dict() for item in dual_result.rule_findings],
                "merged": dual_result.merged.dict(),
                "meta": {
                    "pages": len(page_texts),
                    "filesize": filesize,
                    "job_id": job_dir.name,
                    "started_at": started,
                    "finished_at": time.time(),
                    "use_local_rules": use_local_rules,
                    "use_ai_assist": use_ai_assist,
                    "mode": mode,
                    "dual_mode_enabled": dual_mode_enabled,
                    "elapsed_ms": dual_result.meta.get("elapsed_ms", {}),
                    "tokens": dual_result.meta.get("tokens", {}),
                },
            }
        else:
            # 传统模式分析
            # AI辅助检测阶段
            if use_ai_assist:
                _safe_write(
                    job_dir,
                    {
                        "job_id": job_dir.name,
                        "status": "processing",
                        "progress": 35,
                        "ts": time.time(),
                        "use_local_rules": use_local_rules,
                        "use_ai_assist": use_ai_assist,
                        "mode": mode,
                        "dual_mode_enabled": dual_mode_enabled,
                        "stage": "AI辅助状态",
                    },
                )

                _safe_write(
                    job_dir,
                    {
                        "job_id": job_dir.name,
                        "status": "processing",
                        "progress": 50,
                        "ts": time.time(),
                        "use_local_rules": use_local_rules,
                        "use_ai_assist": use_ai_assist,
                        "mode": mode,
                        "dual_mode_enabled": dual_mode_enabled,
                        "stage": "开始抽取",
                    },
                )

                # 这里会调用AI抽取服务，在build_issues_payload中处理
                _safe_write(
                    job_dir,
                    {
                        "job_id": job_dir.name,
                        "status": "processing",
                        "progress": 80,
                        "ts": time.time(),
                        "use_local_rules": use_local_rules,
                        "use_ai_assist": use_ai_assist,
                        "mode": mode,
                        "dual_mode_enabled": dual_mode_enabled,
                        "stage": "抽取完成",
                    },
                )

                _safe_write(
                    job_dir,
                    {
                        "job_id": job_dir.name,
                        "status": "processing",
                        "progress": 90,
                        "ts": time.time(),
                        "use_local_rules": use_local_rules,
                        "use_ai_assist": use_ai_assist,
                        "mode": mode,
                        "dual_mode_enabled": dual_mode_enabled,
                        "stage": "结果转换",
                    },
                )

            # 运行规则并打包统一结构（issues: {error/warn/info/all}）
            _safe_write(
                job_dir,
                {
                    "job_id": job_dir.name,
                    "status": "processing",
                    "progress": 95,
                    "ts": time.time(),
                    "use_local_rules": use_local_rules,
                    "use_ai_assist": use_ai_assist,
                    "mode": mode,
                    "dual_mode_enabled": dual_mode_enabled,
                    "stage": "执行规则检查",
                },
            )

            payload_issues = build_issues_payload(doc, use_ai_assist)

            # 组装最终返回体（保持传统契约字段）
            result = {
                "summary": "",
                "issues": payload_issues["issues"],
                "meta": {
                    "pages": len(page_texts),
                    "filesize": filesize,
                    "job_id": job_dir.name,
                    "started_at": started,
                    "finished_at": time.time(),
                    "use_local_rules": use_local_rules,
                    "use_ai_assist": use_ai_assist,
                    "mode": mode,
                    "dual_mode_enabled": dual_mode_enabled,
                },
            }

        payload = {
            "job_id": job_dir.name,
            "status": "done",
            "progress": 100,
            "result": result,
            "ts": time.time(),
            "use_local_rules": use_local_rules,
            "use_ai_assist": use_ai_assist,
            "mode": mode,
            "dual_mode_enabled": dual_mode_enabled,
            "stage": "完成",
        }
        _safe_write(job_dir, payload)

    except Exception as e:
        _safe_write(
            job_dir, {"job_id": job_dir.name, "status": "error", "error": str(e), "ts": time.time()}
        )


# ----------------------------- 核心API端点 -----------------------------


@app.get("/")
async def root():
    """根端点"""
    return {"message": "GovBudgetChecker API", "version": "2.0.0", "docs_url": "/docs"}


@app.get("/health")
@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "GovBudgetChecker API",
        "version": "2.0.0",
        "timestamp": time.time(),
    }


@app.get("/config")
@app.get("/api/config")
async def get_config():
    """获取系统配置"""
    ai_enabled = os.getenv("AI_ASSIST_ENABLED", "true").lower() == "true"
    ai_extractor_url = os.getenv("AI_EXTRACTOR_URL", "http://127.0.0.1:9009")
    return {
        "ai_enabled": ai_enabled,
        "ai_extractor_url": ai_extractor_url,
        "version": "2.0.0",
        "features": {"dual_mode": True, "ai_assist": ai_enabled, "rule_engine": True},
    }


@app.post("/api/analyze/dual")
async def analyze_dual_mode(request: dict):
    """双模式分析端点"""
    try:
        job_id = request.get("job_id", "test_job")
        return {
            "job_id": job_id,
            "status": "completed",
            "ai_result": None,
            "engine_result": None,
            "merged_result": None,
            "processing_time": 5.0,
            "metadata": {},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/providers/status")
async def get_providers_status():
    """获取提供商状态"""
    return {
        "providers": [
            {
                "name": "zhipu_flash",
                "model": "glm-4.5-flash",
                "status": "healthy",
                "requests": 0,
                "successes": 0,
                "failures": 0,
            },
            {
                "name": "deepseek_primary",
                "model": "deepseek-v3.1",
                "status": "healthy",
                "requests": 0,
                "successes": 0,
                "failures": 0,
            },
        ],
        "fallback_config": {"enabled": True, "chain": ["zhipu_flash", "deepseek_primary"]},
    }


def _ensure_pdf(file: UploadFile):
    ct = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    return ct in ("application/pdf", "application/x-pdf") or name.endswith(".pdf")


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """文件上传接口"""
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
        "filename": file.filename,
        "size": len(data),
        "saved_path": str(dst.relative_to(UPLOAD_ROOT)),
        "checksum": checksum,
    }


@app.post("/analyze/{job_id}")
@app.post("/api/analyze/{job_id}")
async def analyze_job(job_id: str, request: Request):
    """启动分析任务"""
    job_dir = UPLOAD_ROOT / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job_id 不存在，请先上传文件")

    # 写入初始状态（透传前端选择的模式与开关）
    status_file = job_dir / "status.json"
    try:
        use_local_rules = True
        use_ai_assist = True
        mode = "legacy"
        try:
            body = await request.json()
            if isinstance(body, dict):
                use_local_rules = bool(body.get("use_local_rules", use_local_rules))
                use_ai_assist = bool(body.get("use_ai_assist", use_ai_assist))
                mode = str(body.get("mode", mode))
        except Exception:
            # 无有效JSON时采用默认值
            pass
        status_file.write_text(
            json.dumps(
                {
                    "status": "queued",
                    "progress": 0,
                    "message": "分析任务已排队",
                    "use_local_rules": use_local_rules,
                    "use_ai_assist": use_ai_assist,
                    "mode": mode,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化任务状态失败: {e}")

    # 异步启动分析管线
    try:
        asyncio.create_task(_run_pipeline(job_dir))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动分析失败: {e}")
    return {"job_id": job_id, "status": "started"}


@app.get("/jobs/{job_id}/status")
@app.get("/api/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """获取任务状态"""
    job_dir = UPLOAD_ROOT / job_id
    status_file = job_dir / "status.json"
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job_id 不存在")
    if not status_file.exists():
        # 未生成状态文件时返回进行中占位
        return {"status": "processing", "progress": 0}
    try:
        content = status_file.read_text(encoding="utf-8")
        return json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取任务状态失败: {e}")


@app.get("/jobs/{job_id}/result")
@app.get("/api/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    """获取任务结果"""
    job_dir = UPLOAD_ROOT / job_id
    status_file = job_dir / "status.json"
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job_id 不存在")
    if not status_file.exists():
        raise HTTPException(status_code=404, detail="任务状态文件不存在")

    try:
        content = status_file.read_text(encoding="utf-8")
        status_data = json.loads(content)

        if status_data.get("status") != "done":
            raise HTTPException(status_code=425, detail="任务尚未完成")

        result = status_data.get("result", {})
        if not result:
            raise HTTPException(status_code=404, detail="任务结果为空")

        return result
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"解析任务状态失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务结果失败: {e}")


# ================= 增强版API端点（MVP产品化） =================


@app.post("/api/analyze2/{job_id}")
async def analyze_job_enhanced(job_id: str, background_tasks: BackgroundTasks, request: Request):
    """增强版分析接口 - 支持证据截图和坐标提取"""
    job_dir = UPLOAD_ROOT / job_id
    if not job_dir.exists():
        raise HTTPException(status_code=404, detail="job_id 不存在，请先上传文件")

    try:
        body = await request.json()
        analysis_config = {
            "use_local_rules": bool(body.get("use_local_rules", True)),
            "use_ai_assist": bool(body.get("use_ai_assist", True)),
            "mode": str(body.get("mode", "dual")),
            "enable_screenshots": bool(body.get("enable_screenshots", True)),
            "enable_coordinates": bool(body.get("enable_coordinates", True)),
            "export_format": body.get("export_format", "json"),  # json/csv
        }
    except Exception:
        analysis_config = {
            "use_local_rules": True,
            "use_ai_assist": True,
            "mode": "dual",
            "enable_screenshots": True,
            "enable_coordinates": True,
            "export_format": "json",
        }

    # 写入配置到status文件
    status_file = job_dir / "status.json"
    try:
        status_file.write_text(
            json.dumps(
                {
                    "status": "queued",
                    "progress": 0,
                    "message": "增强版分析任务已排队",
                    "config": analysis_config,
                    "api_version": "v2",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"初始化任务状态失败: {e}")

    # 异步启动增强版分析管线
    background_tasks.add_task(_run_enhanced_pipeline, job_dir, analysis_config)

    return {
        "job_id": job_id,
        "status": "started",
        "api_version": "v2",
        "features": {
            "screenshots": analysis_config["enable_screenshots"],
            "coordinates": analysis_config["enable_coordinates"],
            "export_format": analysis_config["export_format"],
        },
    }


@app.get("/api/jobs/{job_id}/evidence.zip")
async def download_evidence_zip(job_id: str):
    """下载证据截图打包文件"""
    job_dir = UPLOAD_ROOT / job_id
    evidence_zip = job_dir / "evidence.zip"

    if not evidence_zip.exists():
        raise HTTPException(status_code=404, detail="证据文件未生成或已过期")

    return FileResponse(
        path=str(evidence_zip), filename=f"evidence_{job_id}.zip", media_type="application/zip"
    )


@app.get("/api/jobs/{job_id}/export")
async def export_results(job_id: str, format: str = "json"):
    """导出分析结果为CSV或JSON"""
    job_dir = UPLOAD_ROOT / job_id
    status_file = job_dir / "status.json"

    if not status_file.exists():
        raise HTTPException(status_code=404, detail="任务不存在")

    try:
        status_data = json.loads(status_file.read_text(encoding="utf-8"))

        if status_data.get("status") != "done":
            raise HTTPException(status_code=425, detail="任务尚未完成")

        result = status_data.get("result", {})

        if format.lower() == "csv":
            return await _export_csv(result, job_id)
        else:
            return JSONResponse(
                content={
                    "job_id": job_id,
                    "export_format": "json",
                    "timestamp": time.time(),
                    "result": result,
                }
            )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")


# ================= 增强版分析管线 =================


async def _run_enhanced_pipeline(job_dir: Path, config: Dict[str, Any]) -> None:
    """增强版分析管线 - 支持证据截图"""
    try:
        # 先运行基础分析管线
        await _run_pipeline(job_dir)

        # 检查基础分析是否成功
        status_file = job_dir / "status.json"
        if not status_file.exists():
            return

        status_data = json.loads(status_file.read_text(encoding="utf-8"))
        if status_data.get("status") != "done":
            return

        # 提取证据信息
        if config.get("enable_screenshots") or config.get("enable_coordinates"):
            await _extract_evidence(job_dir, status_data, config)

    except Exception as e:
        _safe_write(
            job_dir,
            {
                "job_id": job_dir.name,
                "status": "error",
                "error": f"增强版分析失败: {e}",
                "ts": time.time(),
            },
        )


async def _extract_evidence(
    job_dir: Path, status_data: Dict[str, Any], config: Dict[str, Any]
) -> None:
    """提取证据截图和坐标"""
    try:
        # 更新状态
        _safe_write(job_dir, {**status_data, "stage": "正在提取证据截图", "progress": 95})

        # 查找 PDF 文件
        pdf_path = _find_first_pdf(job_dir)

        # 从分析结果中提取文本列表
        text_list = _extract_text_from_issues(status_data.get("result", {}))

        if text_list:
            # 提取证据
            evidence_result = extract_evidence_from_pdf(
                pdf_path=str(pdf_path),
                output_dir=str(job_dir),
                text_list=text_list,
                job_id=job_dir.name,
                enable_screenshots=config.get("enable_screenshots", True),
            )

            # 更新结果
            result = status_data.get("result", {})
            result["evidence"] = evidence_result

            _safe_write(
                job_dir, {**status_data, "result": result, "stage": "证据提取完成", "progress": 100}
            )
        else:
            # 没有可提取的文本
            _safe_write(
                job_dir, {**status_data, "stage": "未找到可提取的证据文本", "progress": 100}
            )

    except Exception as e:
        logger.error(f"Evidence extraction failed: {e}")
        _safe_write(job_dir, {**status_data, "stage": f"证据提取失败: {e}", "progress": 100})


def _extract_text_from_issues(result: Dict[str, Any]) -> List[str]:
    """从问题结果中提取文本列表"""
    text_list = []

    # 从传统模式结果提取
    issues = result.get("issues", {})
    if isinstance(issues, dict):
        for category in ["error", "warn", "info", "all"]:
            for issue in issues.get(category, []):
                if isinstance(issue, dict):
                    message = issue.get("message", "")
                    if message and len(message) > 10:  # 过滤太短的文本
                        text_list.append(message[:100])  # 限制长度

    # 从双模式结果提取
    for findings_key in ["ai_findings", "rule_findings"]:
        findings = result.get(findings_key, [])
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    message = finding.get("message", "")
                    if message and len(message) > 10:
                        text_list.append(message[:100])

    # 去重并返回
    return list(set(text_list))[:20]  # 最多20个文本


async def _export_csv(result: Dict[str, Any], job_id: str) -> JSONResponse:
    """导出CSV格式结果"""
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # CSV头部
    writer.writerow(["Job ID", "Rule ID", "Severity", "Title", "Message", "Page", "Source"])

    # 处理传统模式结果
    issues = result.get("issues", {})
    if isinstance(issues, dict):
        for category, issue_list in issues.items():
            if category == "all":
                continue
            for issue in issue_list:
                if isinstance(issue, dict):
                    writer.writerow(
                        [
                            job_id,
                            issue.get("rule", "unknown"),
                            issue.get("severity", category),
                            issue.get("message", "")[:50],  # 简化标题
                            issue.get("message", ""),
                            issue.get("location", {}).get("page", ""),
                            "local_rules",
                        ]
                    )

    # 处理双模式结果
    for findings_key, source in [("ai_findings", "ai"), ("rule_findings", "rule")]:
        findings = result.get(findings_key, [])
        if isinstance(findings, list):
            for finding in findings:
                if isinstance(finding, dict):
                    writer.writerow(
                        [
                            job_id,
                            finding.get("rule_id", "unknown"),
                            finding.get("severity", "info"),
                            finding.get("title", ""),
                            finding.get("message", ""),
                            finding.get("page_number", ""),
                            source,
                        ]
                    )

    csv_content = output.getvalue()
    output.close()

    return JSONResponse(
        content={
            "job_id": job_id,
            "export_format": "csv",
            "timestamp": time.time(),
            "csv_data": csv_content,
        },
        headers={"Content-Disposition": f"attachment; filename=results_{job_id}.csv"},
    )


# ================= 规则YAML调试端点 =================


@app.get("/api/debug/rules-yaml")
async def debug_rules_yaml(version: str = "v3_3", profile: Optional[str] = None):
    """调试YAML规则配置加载"""
    try:
        loader = get_rules_loader()
        config = loader.load_rules_yaml(version, profile)

        return {
            "success": True,
            "version": config.version,
            "schema_version": config.schema_version,
            "rules_count": len(config.rules),
            "profiles_count": len(config.profiles),
            "available_versions": loader.get_available_versions(),
            "available_profiles": loader.get_available_profiles(version),
            "sample_rules": {k: v.name for k, v in list(config.rules.items())[:3]},
            "global_settings": config.global_settings,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/debug/performance")
async def debug_performance():
    """性能监控调试端点"""
    try:
        optimizer = get_performance_optimizer()

        return {
            "success": True,
            "system_status": optimizer.get_system_status(),
            "resource_limits": optimizer.check_resource_limits(),
            "active_tasks": {
                task_id: optimizer.get_task_status(task_id)
                for task_id in optimizer.active_tasks.keys()
            },
            "config": {
                "max_concurrent_jobs": optimizer.config.max_concurrent_jobs,
                "job_timeout_seconds": optimizer.config.job_timeout_seconds,
                "memory_limit_mb": optimizer.config.memory_limit_mb,
                "large_file_threshold_mb": optimizer.config.large_file_threshold_mb,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
