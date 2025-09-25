"""
性能与稳定性增强
实现大文件分段处理、页级并发控制、内存监控、超时控制、进度上报
"""

import asyncio
import logging
import psutil
import time
import weakref
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, AsyncIterator
from threading import Lock
import gc

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标"""
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    memory_peak_mb: float = 0.0
    pages_processed: int = 0
    ocr_triggered_count: int = 0
    errors_count: int = 0
    processing_stages: Dict[str, float] = field(default_factory=dict)
    
    @property
    def total_time(self) -> float:
        """总耗时（秒）"""
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    @property
    def ocr_trigger_rate(self) -> float:
        """OCR触发率"""
        if self.pages_processed == 0:
            return 0.0
        return self.ocr_triggered_count / self.pages_processed
    
    def record_stage(self, stage_name: str, duration: float):
        """记录处理阶段耗时"""
        self.processing_stages[stage_name] = duration
    
    def finish(self):
        """标记处理完成"""
        self.end_time = time.time()


@dataclass
class ProgressInfo:
    """进度信息"""
    job_id: str
    current_stage: str
    current_page: int
    total_pages: int
    progress_percent: float
    stage_detail: str = ""
    estimated_remaining: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "job_id": self.job_id,
            "current_stage": self.current_stage,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "progress_percent": self.progress_percent,
            "stage_detail": self.stage_detail,
            "estimated_remaining": self.estimated_remaining
        }


class ResourceMonitor:
    """资源监控器"""
    
    def __init__(self, memory_limit_mb: int = 2048):
        """
        初始化资源监控器
        
        Args:
            memory_limit_mb: 内存限制（MB）
        """
        self.memory_limit_mb = memory_limit_mb
        self.memory_limit_bytes = memory_limit_mb * 1024 * 1024
        self.process = psutil.Process()
        self._monitoring = False
        self._peak_memory = 0
    
    def get_memory_usage(self) -> float:
        """获取当前内存使用量（MB）"""
        try:
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            self._peak_memory = max(self._peak_memory, memory_mb)
            return memory_mb
        except Exception as e:
            logger.warning(f"获取内存使用量失败: {e}")
            return 0.0
    
    def check_memory_limit(self) -> bool:
        """检查是否超过内存限制"""
        current_memory = self.get_memory_usage()
        return current_memory > self.memory_limit_mb
    
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        try:
            return {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_available_mb": psutil.virtual_memory().available / 1024 / 1024,
                "process_memory_mb": self.get_memory_usage(),
                "process_memory_peak_mb": self._peak_memory,
                "disk_usage_percent": psutil.disk_usage('/').percent if hasattr(psutil, 'disk_usage') else 0
            }
        except Exception as e:
            logger.warning(f"获取系统信息失败: {e}")
            return {}
    
    def force_gc(self):
        """强制垃圾回收"""
        gc.collect()
        logger.debug(f"强制垃圾回收完成，当前内存: {self.get_memory_usage():.1f}MB")


class ConcurrencyController:
    """并发控制器"""
    
    def __init__(self, max_concurrent_pages: int = 3, max_workers: int = 4):
        """
        初始化并发控制器
        
        Args:
            max_concurrent_pages: 最大并发页面数
            max_workers: 最大工作线程数
        """
        self.max_concurrent_pages = max_concurrent_pages
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_concurrent_pages)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._active_tasks = weakref.WeakSet()
        self._lock = Lock()
    
    @asynccontextmanager
    async def acquire_page_slot(self):
        """获取页面处理槽位"""
        async with self.semaphore:
            yield
    
    async def submit_page_task(self, coro_func: Callable, *args, **kwargs):
        """提交页面处理任务"""
        async with self.acquire_page_slot():
            return await coro_func(*args, **kwargs)
    
    def submit_blocking_task(self, func: Callable, *args, **kwargs):
        """提交阻塞任务到线程池"""
        future = self.executor.submit(func, *args, **kwargs)
        with self._lock:
            self._active_tasks.add(future)
        return future
    
    def get_active_tasks_count(self) -> int:
        """获取活动任务数量"""
        with self._lock:
            return len(self._active_tasks)
    
    def shutdown(self, wait: bool = True):
        """关闭执行器"""
        self.executor.shutdown(wait=wait)


class ProgressReporter:
    """进度上报器"""
    
    def __init__(self):
        """初始化进度上报器"""
        self._progress_store: Dict[str, ProgressInfo] = {}
        self._callbacks: List[Callable[[ProgressInfo], None]] = []
        self._lock = Lock()
    
    def register_callback(self, callback: Callable[[ProgressInfo], None]):
        """注册进度回调函数"""
        with self._lock:
            self._callbacks.append(callback)
    
    def update_progress(self, progress: ProgressInfo):
        """更新进度"""
        with self._lock:
            self._progress_store[progress.job_id] = progress
            
            # 调用所有回调函数
            for callback in self._callbacks:
                try:
                    callback(progress)
                except Exception as e:
                    logger.warning(f"进度回调函数执行失败: {e}")
    
    def get_progress(self, job_id: str) -> Optional[ProgressInfo]:
        """获取任务进度"""
        with self._lock:
            return self._progress_store.get(job_id)
    
    def get_all_progress(self) -> Dict[str, ProgressInfo]:
        """获取所有任务进度"""
        with self._lock:
            return self._progress_store.copy()
    
    def remove_progress(self, job_id: str):
        """移除任务进度"""
        with self._lock:
            self._progress_store.pop(job_id, None)


class TimeoutController:
    """超时控制器"""
    
    def __init__(self, default_timeout: float = 300):
        """
        初始化超时控制器
        
        Args:
            default_timeout: 默认超时时间（秒）
        """
        self.default_timeout = default_timeout
    
    @asynccontextmanager
    async def timeout_context(self, timeout: Optional[float] = None):
        """超时上下文管理器"""
        timeout = timeout or self.default_timeout
        try:
            async with asyncio.timeout(timeout):
                yield
        except asyncio.TimeoutError:
            logger.error(f"操作超时，限制时间: {timeout}秒")
            raise


class DocumentSegmentProcessor:
    """文档分段处理器"""
    
    def __init__(self, 
                 max_pages_per_segment: int = 50,
                 max_memory_mb: int = 2048,
                 max_concurrent_pages: int = 3,
                 timeout_seconds: float = 300):
        """
        初始化文档分段处理器
        
        Args:
            max_pages_per_segment: 每段最大页数
            max_memory_mb: 内存限制（MB）
            max_concurrent_pages: 最大并发页面数
            timeout_seconds: 超时时间（秒）
        """
        self.max_pages_per_segment = max_pages_per_segment
        self.resource_monitor = ResourceMonitor(max_memory_mb)
        self.concurrency_controller = ConcurrencyController(max_concurrent_pages)
        self.progress_reporter = ProgressReporter()
        self.timeout_controller = TimeoutController(timeout_seconds)
        self.metrics = PerformanceMetrics()
    
    async def process_document_with_monitoring(self, 
                                             document_path: str,
                                             job_id: str,
                                             processor_func: Callable,
                                             **kwargs) -> Dict[str, Any]:
        """
        带监控的文档处理
        
        Args:
            document_path: 文档路径
            job_id: 任务ID
            processor_func: 处理函数
            **kwargs: 处理函数参数
            
        Returns:
            处理结果
        """
        self.metrics = PerformanceMetrics()
        
        try:
            async with self.timeout_controller.timeout_context():
                # 检查文件是否存在
                if not Path(document_path).exists():
                    raise FileNotFoundError(f"文档文件不存在: {document_path}")
                
                # 获取文档信息
                doc_info = await self._get_document_info(document_path)
                total_pages = doc_info.get("total_pages", 0)
                file_size_mb = doc_info.get("file_size_mb", 0)
                
                logger.info(f"开始处理文档: {document_path}, 总页数: {total_pages}, 文件大小: {file_size_mb:.1f}MB")
                
                # 初始化进度
                progress = ProgressInfo(
                    job_id=job_id,
                    current_stage="preparing",
                    current_page=0,
                    total_pages=total_pages,
                    progress_percent=0.0,
                    stage_detail="准备处理文档"
                )
                self.progress_reporter.update_progress(progress)
                
                # 根据页数和内存情况决定处理策略
                if total_pages <= self.max_pages_per_segment and file_size_mb < 100:
                    # 小文档，直接处理
                    result = await self._process_small_document(
                        document_path, job_id, processor_func, **kwargs
                    )
                else:
                    # 大文档，分段处理
                    result = await self._process_large_document(
                        document_path, job_id, processor_func, **kwargs
                    )
                
                # 完成处理
                self.metrics.finish()
                progress.current_stage = "completed"
                progress.progress_percent = 100.0
                progress.stage_detail = f"处理完成，耗时: {self.metrics.total_time:.1f}秒"
                self.progress_reporter.update_progress(progress)
                
                # 添加性能指标到结果
                result["performance_metrics"] = {
                    "total_time": self.metrics.total_time,
                    "memory_peak_mb": self.metrics.memory_peak_mb,
                    "pages_processed": self.metrics.pages_processed,
                    "ocr_trigger_rate": self.metrics.ocr_trigger_rate,
                    "processing_stages": self.metrics.processing_stages
                }
                
                logger.info(f"文档处理完成: {job_id}, 耗时: {self.metrics.total_time:.1f}秒")
                return result
                
        except Exception as e:
            logger.error(f"文档处理失败: {job_id}, 错误: {e}")
            self.metrics.errors_count += 1
            
            # 更新错误状态
            progress = ProgressInfo(
                job_id=job_id,
                current_stage="error",
                current_page=0,
                total_pages=0,
                progress_percent=0.0,
                stage_detail=f"处理失败: {str(e)}"
            )
            self.progress_reporter.update_progress(progress)
            
            raise
        finally:
            # 清理资源
            self.concurrency_controller.shutdown(wait=False)
            self.resource_monitor.force_gc()
    
    async def _get_document_info(self, document_path: str) -> Dict[str, Any]:
        """获取文档基本信息"""
        try:
            import fitz
            
            file_path = Path(document_path)
            file_size_mb = file_path.stat().st_size / 1024 / 1024
            
            # 快速获取页数
            doc = fitz.open(document_path)
            total_pages = len(doc)
            doc.close()
            
            return {
                "total_pages": total_pages,
                "file_size_mb": file_size_mb,
                "file_name": file_path.name
            }
        except Exception as e:
            logger.warning(f"获取文档信息失败: {e}")
            return {"total_pages": 0, "file_size_mb": 0, "file_name": "unknown"}
    
    async def _process_small_document(self, 
                                    document_path: str,
                                    job_id: str,
                                    processor_func: Callable,
                                    **kwargs) -> Dict[str, Any]:
        """处理小文档"""
        stage_start = time.time()
        
        progress = ProgressInfo(
            job_id=job_id,
            current_stage="processing",
            current_page=0,
            total_pages=0,
            progress_percent=10.0,
            stage_detail="处理中..."
        )
        self.progress_reporter.update_progress(progress)
        
        # 调用处理函数
        result = await self._execute_processor(processor_func, document_path, **kwargs)
        
        self.metrics.record_stage("processing", time.time() - stage_start)
        return result
    
    async def _process_large_document(self,
                                    document_path: str,
                                    job_id: str,
                                    processor_func: Callable,
                                    **kwargs) -> Dict[str, Any]:
        """分段处理大文档"""
        # 这里可以实现更复杂的分段逻辑
        # 目前简化为单段处理，可以根据需要扩展
        return await self._process_small_document(document_path, job_id, processor_func, **kwargs)
    
    async def _execute_processor(self, processor_func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """执行处理函数"""
        if asyncio.iscoroutinefunction(processor_func):
            return await processor_func(*args, **kwargs)
        else:
            # 在线程池中执行同步函数
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.concurrency_controller.executor,
                processor_func,
                *args,
                **kwargs
            )


# 全局实例
_document_processor = None

def get_document_processor() -> DocumentSegmentProcessor:
    """获取全局文档处理器实例"""
    global _document_processor
    if _document_processor is None:
        _document_processor = DocumentSegmentProcessor()
    return _document_processor