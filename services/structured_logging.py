"""
结构化日志系统
支持job_id、阶段、耗时、页数、OCR触发率等关键指标的结构化记录
"""

import json
import logging
import sys
import time
import traceback
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

# 上下文变量
current_job_id: ContextVar[Optional[str]] = ContextVar('current_job_id', default=None)
current_stage: ContextVar[Optional[str]] = ContextVar('current_stage', default=None)


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ProcessingStage(Enum):
    """处理阶段"""
    UPLOAD = "upload"
    PARSING = "parsing"
    TEXT_EXTRACTION = "text_extraction"
    OCR_PROCESSING = "ocr_processing"
    RULE_ANALYSIS = "rule_analysis"
    AI_ANALYSIS = "ai_analysis"
    EVIDENCE_GENERATION = "evidence_generation"
    RESULT_MERGING = "result_merging"
    EXPORT = "export"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class StructuredLogEntry:
    """结构化日志条目"""
    timestamp: str
    level: str
    message: str
    job_id: Optional[str] = None
    stage: Optional[str] = None
    
    # 性能指标
    duration_ms: Optional[float] = None
    memory_mb: Optional[float] = None
    
    # 文档处理指标
    total_pages: Optional[int] = None
    current_page: Optional[int] = None
    ocr_triggered_pages: Optional[int] = None
    ocr_trigger_rate: Optional[float] = None
    
    # 业务指标
    rules_triggered: Optional[int] = None
    ai_findings: Optional[int] = None
    total_findings: Optional[int] = None
    
    # 错误信息
    error_type: Optional[str] = None
    error_details: Optional[str] = None
    stack_trace: Optional[str] = None
    
    # 额外数据
    extra_data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        # 移除None值
        return {k: v for k, v in data.items() if v is not None}
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(',', ':'))


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 基础信息
        log_entry = StructuredLogEntry(
            timestamp=datetime.fromtimestamp(record.created).isoformat(),
            level=record.levelname,
            message=record.getMessage(),
            job_id=current_job_id.get(),
            stage=current_stage.get()
        )
        
        # 从record中提取额外信息
        if hasattr(record, 'duration_ms'):
            log_entry.duration_ms = record.duration_ms
        if hasattr(record, 'memory_mb'):
            log_entry.memory_mb = record.memory_mb
        if hasattr(record, 'total_pages'):
            log_entry.total_pages = record.total_pages
        if hasattr(record, 'current_page'):
            log_entry.current_page = record.current_page
        if hasattr(record, 'ocr_triggered_pages'):
            log_entry.ocr_triggered_pages = record.ocr_triggered_pages
        if hasattr(record, 'ocr_trigger_rate'):
            log_entry.ocr_trigger_rate = record.ocr_trigger_rate
        if hasattr(record, 'rules_triggered'):
            log_entry.rules_triggered = record.rules_triggered
        if hasattr(record, 'ai_findings'):
            log_entry.ai_findings = record.ai_findings
        if hasattr(record, 'total_findings'):
            log_entry.total_findings = record.total_findings
        if hasattr(record, 'extra_data'):
            log_entry.extra_data = record.extra_data
        
        # 错误信息
        if record.exc_info:
            log_entry.error_type = record.exc_info[0].__name__ if record.exc_info[0] else None
            log_entry.error_details = str(record.exc_info[1]) if record.exc_info[1] else None
            log_entry.stack_trace = ''.join(traceback.format_exception(*record.exc_info))
        
        return log_entry.to_json()


class BusinessLoggerAdapter(logging.LoggerAdapter):
    """业务日志适配器"""
    
    def __init__(self, logger: logging.Logger):
        super().__init__(logger, {})
    
    def log_stage_start(self, stage: ProcessingStage, **kwargs):
        """记录阶段开始"""
        current_stage.set(stage.value)
        self.info(f"开始 {stage.value} 阶段", extra=kwargs)
    
    def log_stage_end(self, stage: ProcessingStage, duration_ms: float, **kwargs):
        """记录阶段结束"""
        self.info(f"完成 {stage.value} 阶段", extra={
            'duration_ms': duration_ms,
            **kwargs
        })
    
    def log_page_processed(self, page_no: int, total_pages: int, ocr_used: bool = False, **kwargs):
        """记录页面处理"""
        self.debug(f"处理页面 {page_no}/{total_pages}", extra={
            'current_page': page_no,
            'total_pages': total_pages,
            'ocr_used': ocr_used,
            **kwargs
        })
    
    def log_ocr_summary(self, total_pages: int, ocr_triggered_pages: int, **kwargs):
        """记录OCR处理总结"""
        ocr_rate = ocr_triggered_pages / total_pages if total_pages > 0 else 0
        self.info(f"OCR处理总结: {ocr_triggered_pages}/{total_pages} ({ocr_rate:.1%})", extra={
            'total_pages': total_pages,
            'ocr_triggered_pages': ocr_triggered_pages,
            'ocr_trigger_rate': ocr_rate,
            **kwargs
        })
    
    def log_analysis_result(self, rules_triggered: int, ai_findings: int, total_findings: int, **kwargs):
        """记录分析结果"""
        self.info(f"分析完成: 规则 {rules_triggered} 项, AI {ai_findings} 项, 总计 {total_findings} 项", extra={
            'rules_triggered': rules_triggered,
            'ai_findings': ai_findings,
            'total_findings': total_findings,
            **kwargs
        })
    
    def log_performance(self, operation: str, duration_ms: float, memory_mb: float, **kwargs):
        """记录性能指标"""
        self.info(f"性能: {operation} 耗时 {duration_ms:.1f}ms, 内存 {memory_mb:.1f}MB", extra={
            'duration_ms': duration_ms,
            'memory_mb': memory_mb,
            **kwargs
        })
    
    def log_error_with_context(self, message: str, error: Exception, **kwargs):
        """记录带上下文的错误"""
        self.error(message, exc_info=(type(error), error, error.__traceback__), extra=kwargs)


class LoggingContextManager:
    """日志上下文管理器"""
    
    def __init__(self, job_id: str, stage: Optional[ProcessingStage] = None):
        self.job_id = job_id
        self.stage = stage.value if stage else None
        self.start_time = time.time()
        self._job_token = None
        self._stage_token = None
    
    def __enter__(self):
        """进入上下文"""
        self._job_token = current_job_id.set(self.job_id)
        if self.stage:
            self._stage_token = current_stage.set(self.stage)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        if self._job_token:
            current_job_id.reset(self._job_token)
        if self._stage_token:
            current_stage.reset(self._stage_token)
    
    @property
    def duration_ms(self) -> float:
        """获取耗时（毫秒）"""
        return (time.time() - self.start_time) * 1000


def setup_structured_logging(log_file: Optional[str] = None, 
                            log_level: str = "INFO",
                            enable_console: bool = True) -> BusinessLoggerAdapter:
    """
    设置结构化日志
    
    Args:
        log_file: 日志文件路径
        log_level: 日志级别
        enable_console: 是否启用控制台输出
        
    Returns:
        业务日志适配器
    """
    # 创建根日志器
    root_logger = logging.getLogger("govbudget")
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # 清除现有处理器
    root_logger.handlers.clear()
    
    # 结构化格式化器
    structured_formatter = StructuredFormatter()
    
    # 控制台处理器（带颜色的人类可读格式）
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # 控制台使用简化格式
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)8s] [%(name)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # 文件处理器（结构化JSON格式）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(getattr(logging, log_level.upper()))
        file_handler.setFormatter(structured_formatter)
        root_logger.addHandler(file_handler)
    
    # 创建业务日志适配器
    return BusinessLoggerAdapter(root_logger)


class LogAnalyzer:
    """日志分析器"""
    
    def __init__(self, log_file: str):
        """
        初始化日志分析器
        
        Args:
            log_file: 日志文件路径
        """
        self.log_file = Path(log_file)
    
    def analyze_job_performance(self, job_id: str) -> Dict[str, Any]:
        """
        分析任务性能
        
        Args:
            job_id: 任务ID
            
        Returns:
            性能分析结果
        """
        if not self.log_file.exists():
            return {"error": "日志文件不存在"}
        
        job_logs = []
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    log_entry = json.loads(line)
                    if log_entry.get('job_id') == job_id:
                        job_logs.append(log_entry)
                except json.JSONDecodeError:
                    continue
        
        if not job_logs:
            return {"error": f"未找到任务 {job_id} 的日志"}
        
        # 分析性能指标
        stages = {}
        total_duration = 0
        max_memory = 0
        error_count = 0
        ocr_stats = {"total_pages": 0, "ocr_pages": 0}
        
        for log in job_logs:
            # 阶段分析
            stage = log.get('stage')
            if stage and log.get('duration_ms'):
                if stage not in stages:
                    stages[stage] = {"count": 0, "total_duration": 0, "avg_duration": 0}
                stages[stage]["count"] += 1
                stages[stage]["total_duration"] += log['duration_ms']
                stages[stage]["avg_duration"] = stages[stage]["total_duration"] / stages[stage]["count"]
                total_duration += log['duration_ms']
            
            # 内存分析
            if log.get('memory_mb'):
                max_memory = max(max_memory, log['memory_mb'])
            
            # 错误统计
            if log.get('level') == 'ERROR':
                error_count += 1
            
            # OCR统计
            if log.get('total_pages'):
                ocr_stats["total_pages"] = max(ocr_stats["total_pages"], log['total_pages'])
            if log.get('ocr_triggered_pages'):
                ocr_stats["ocr_pages"] = max(ocr_stats["ocr_pages"], log['ocr_triggered_pages'])
        
        return {
            "job_id": job_id,
            "total_duration_ms": total_duration,
            "max_memory_mb": max_memory,
            "error_count": error_count,
            "stages": stages,
            "ocr_trigger_rate": ocr_stats["ocr_pages"] / ocr_stats["total_pages"] if ocr_stats["total_pages"] > 0 else 0,
            "log_entries_count": len(job_logs)
        }
    
    def get_system_overview(self, hours: int = 24) -> Dict[str, Any]:
        """
        获取系统概览
        
        Args:
            hours: 分析最近多少小时的日志
            
        Returns:
            系统概览数据
        """
        if not self.log_file.exists():
            return {"error": "日志文件不存在"}
        
        cutoff_time = datetime.now().timestamp() - (hours * 3600)
        
        job_stats = {}
        error_count = 0
        total_jobs = set()
        
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    log_entry = json.loads(line)
                    
                    # 时间过滤
                    log_time = datetime.fromisoformat(log_entry['timestamp']).timestamp()
                    if log_time < cutoff_time:
                        continue
                    
                    job_id = log_entry.get('job_id')
                    if job_id:
                        total_jobs.add(job_id)
                        
                        if job_id not in job_stats:
                            job_stats[job_id] = {
                                "stages": set(),
                                "errors": 0,
                                "max_memory": 0,
                                "total_duration": 0
                            }
                        
                        # 统计信息
                        if log_entry.get('stage'):
                            job_stats[job_id]["stages"].add(log_entry['stage'])
                        
                        if log_entry.get('level') == 'ERROR':
                            job_stats[job_id]["errors"] += 1
                            error_count += 1
                        
                        if log_entry.get('memory_mb'):
                            job_stats[job_id]["max_memory"] = max(
                                job_stats[job_id]["max_memory"],
                                log_entry['memory_mb']
                            )
                        
                        if log_entry.get('duration_ms'):
                            job_stats[job_id]["total_duration"] += log_entry['duration_ms']
                
                except (json.JSONDecodeError, KeyError):
                    continue
        
        # 计算统计指标
        completed_jobs = len([j for j in job_stats.values() if "completed" in j["stages"]])
        failed_jobs = len([j for j in job_stats.values() if j["errors"] > 0])
        avg_memory = sum(j["max_memory"] for j in job_stats.values()) / len(job_stats) if job_stats else 0
        avg_duration = sum(j["total_duration"] for j in job_stats.values()) / len(job_stats) if job_stats else 0
        
        return {
            "time_range_hours": hours,
            "total_jobs": len(total_jobs),
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "success_rate": completed_jobs / len(total_jobs) if total_jobs else 0,
            "total_errors": error_count,
            "avg_memory_mb": avg_memory,
            "avg_duration_ms": avg_duration,
            "job_details": {k: {**v, "stages": list(v["stages"])} for k, v in job_stats.items()}
        }


# 便捷函数
def with_job_context(job_id: str, stage: Optional[ProcessingStage] = None):
    """日志上下文装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with LoggingContextManager(job_id, stage):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# 全局日志器实例
business_logger = None

def get_business_logger() -> BusinessLoggerAdapter:
    """获取全局业务日志器"""
    global business_logger
    if business_logger is None:
        business_logger = setup_structured_logging(
            log_file="logs/govbudget.jsonl",
            log_level="INFO",
            enable_console=True
        )
    return business_logger