# services/performance_optimizer.py
"""
性能优化服务
负责任务队列管理、性能监控和资源优化
"""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


@dataclass
class TaskMetrics:
    """任务性能指标"""
    task_id: str
    start_time: float
    end_time: Optional[float] = None
    progress: float = 0.0
    status: str = "pending"
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    stage: str = "初始化"
    estimated_remaining_seconds: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class PerformanceConfig:
    """性能配置"""
    max_concurrent_jobs: int = 3
    job_timeout_seconds: int = 300  # 5分钟默认超时
    memory_limit_mb: int = 2048
    cpu_limit_percent: int = 80
    enable_progress_estimation: bool = True
    enable_resource_monitoring: bool = True
    large_file_threshold_mb: int = 20  # 大文件阈值
    large_file_timeout_seconds: int = 600  # 大文件超时时间


class PerformanceOptimizer:
    """性能优化器"""
    
    def __init__(self, config: Optional[PerformanceConfig] = None):
        self.config = config or PerformanceConfig()
        self.active_tasks: Dict[str, TaskMetrics] = {}
        self.task_history: List[TaskMetrics] = []
        self.executor = ThreadPoolExecutor(max_workers=self.config.max_concurrent_jobs)
        self._shutdown = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # 启动资源监控
        if self.config.enable_resource_monitoring:
            self._start_monitoring()
        
        logger.info(f"性能优化器已启动，最大并发任务: {self.config.max_concurrent_jobs}")
    
    def _start_monitoring(self):
        """启动资源监控线程"""
        def monitor_loop():
            while not self._shutdown:
                try:
                    self._update_resource_metrics()
                    time.sleep(5)  # 每5秒更新一次
                except Exception as e:
                    logger.warning(f"资源监控出错: {e}")
                    time.sleep(10)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.debug("资源监控线程已启动")
    
    def _update_resource_metrics(self):
        """更新系统资源指标"""
        try:
            # 获取系统资源使用情况
            memory_info = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 更新活跃任务的资源使用情况
            for task_id, metrics in self.active_tasks.items():
                metrics.memory_usage_mb = memory_info.used / (1024 * 1024)
                metrics.cpu_usage_percent = cpu_percent
                
                # 检查资源限制
                if metrics.memory_usage_mb > self.config.memory_limit_mb:
                    logger.warning(f"任务 {task_id} 内存使用超限: {metrics.memory_usage_mb}MB")
                
                if metrics.cpu_usage_percent > self.config.cpu_limit_percent:
                    logger.warning(f"任务 {task_id} CPU使用超限: {metrics.cpu_usage_percent}%")
        
        except Exception as e:
            logger.warning(f"更新资源指标失败: {e}")
    
    def estimate_task_duration(self, file_size_mb: float, page_count: int) -> float:
        """估算任务完成时间（秒）"""
        # 基于历史数据的简单估算模型
        base_time = 30  # 基础处理时间30秒
        
        # 文件大小影响因子
        size_factor = max(1.0, file_size_mb / 10.0)  # 每10MB增加1倍时间
        
        # 页数影响因子
        page_factor = max(1.0, page_count / 50.0)  # 每50页增加1倍时间
        
        # 大文件额外惩罚
        if file_size_mb > self.config.large_file_threshold_mb:
            size_factor *= 1.5
        
        estimated = base_time * size_factor * page_factor
        
        # 根据历史数据调整
        if self.task_history:
            avg_duration = sum(
                (t.end_time - t.start_time) for t in self.task_history[-10:] 
                if t.end_time is not None
            ) / min(len(self.task_history), 10)
            estimated = estimated * 0.7 + avg_duration * 0.3  # 加权平均
        
        return min(estimated, self.config.job_timeout_seconds)
    
    def start_task(self, task_id: str, file_info: Dict[str, Any]) -> TaskMetrics:
        """开始一个新任务"""
        # 检查并发限制
        if len(self.active_tasks) >= self.config.max_concurrent_jobs:
            raise RuntimeError(f"达到最大并发任务数限制: {self.config.max_concurrent_jobs}")
        
        # 创建任务指标
        file_size_mb = file_info.get("size", 0) / (1024 * 1024)
        page_count = file_info.get("pages", 0)
        
        metrics = TaskMetrics(
            task_id=task_id,
            start_time=time.time(),
            status="running"
        )
        
        # 估算完成时间
        if self.config.enable_progress_estimation:
            estimated_duration = self.estimate_task_duration(file_size_mb, page_count)
            metrics.estimated_remaining_seconds = estimated_duration
        
        self.active_tasks[task_id] = metrics
        
        # 调整超时时间
        timeout = self.config.job_timeout_seconds
        if file_size_mb > self.config.large_file_threshold_mb:
            timeout = self.config.large_file_timeout_seconds
        
        logger.info(f"任务 {task_id} 已启动，预估完成时间: {metrics.estimated_remaining_seconds:.1f}秒")
        return metrics
    
    def update_task_progress(self, task_id: str, progress: float, stage: Optional[str] = None):
        """更新任务进度"""
        if task_id not in self.active_tasks:
            logger.warning(f"尝试更新不存在的任务: {task_id}")
            return
        
        metrics = self.active_tasks[task_id]
        metrics.progress = max(0.0, min(100.0, progress))
        
        if stage:
            metrics.stage = stage
        
        # 更新预估剩余时间
        if self.config.enable_progress_estimation and progress > 0:
            elapsed = time.time() - metrics.start_time
            if progress > 5:  # 避免早期进度导致的不准确估算
                estimated_total = elapsed * (100.0 / progress)
                metrics.estimated_remaining_seconds = max(0, estimated_total - elapsed)
        
        logger.debug(f"任务 {task_id} 进度更新: {progress:.1f}% - {stage}")
    
    def complete_task(self, task_id: str, success: bool = True, error: Optional[str] = None):
        """完成任务"""
        if task_id not in self.active_tasks:
            logger.warning(f"尝试完成不存在的任务: {task_id}")
            return
        
        metrics = self.active_tasks[task_id]
        metrics.end_time = time.time()
        metrics.status = "completed" if success else "failed"
        metrics.progress = 100.0 if success else metrics.progress
        metrics.estimated_remaining_seconds = 0
        
        if error:
            metrics.error_message = error
        
        duration = metrics.end_time - metrics.start_time
        
        # 移动到历史记录
        self.task_history.append(metrics)
        del self.active_tasks[task_id]
        
        # 保持历史记录在合理范围内
        if len(self.task_history) > 100:
            self.task_history = self.task_history[-50:]
        
        status_msg = "成功" if success else f"失败: {error}"
        logger.info(f"任务 {task_id} 已完成 ({duration:.1f}秒) - {status_msg}")
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        if task_id in self.active_tasks:
            metrics = self.active_tasks[task_id]
            return {
                "task_id": task_id,
                "status": metrics.status,
                "progress": metrics.progress,
                "stage": metrics.stage,
                "start_time": metrics.start_time,
                "estimated_remaining_seconds": metrics.estimated_remaining_seconds,
                "memory_usage_mb": metrics.memory_usage_mb,
                "cpu_usage_percent": metrics.cpu_usage_percent
            }
        
        # 检查历史记录
        for metrics in reversed(self.task_history):
            if metrics.task_id == task_id:
                return {
                    "task_id": task_id,
                    "status": metrics.status,
                    "progress": metrics.progress,
                    "stage": metrics.stage,
                    "start_time": metrics.start_time,
                    "end_time": metrics.end_time,
                    "duration": metrics.end_time - metrics.start_time if metrics.end_time else None,
                    "error_message": metrics.error_message
                }
        
        return None
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态概览"""
        try:
            memory_info = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent()
            
            return {
                "active_tasks": len(self.active_tasks),
                "max_concurrent_jobs": self.config.max_concurrent_jobs,
                "memory_usage": {
                    "used_mb": memory_info.used / (1024 * 1024),
                    "available_mb": memory_info.available / (1024 * 1024),
                    "percent": memory_info.percent
                },
                "cpu_usage_percent": cpu_percent,
                "task_queue_available": self.config.max_concurrent_jobs - len(self.active_tasks),
                "recent_completions": len([t for t in self.task_history if 
                                         time.time() - t.start_time < 3600])  # 最近1小时完成的任务
            }
        except Exception as e:
            logger.warning(f"获取系统状态失败: {e}")
            return {"error": str(e)}
    
    def optimize_for_large_file(self, file_size_mb: float) -> Dict[str, Any]:
        """为大文件处理进行优化"""
        optimizations = {}
        
        if file_size_mb > self.config.large_file_threshold_mb:
            # 大文件优化策略
            optimizations["use_streaming"] = True
            optimizations["chunk_size"] = min(5, file_size_mb / 10)  # 动态chunk大小
            optimizations["enable_gc"] = True  # 启用垃圾回收
            optimizations["memory_optimization"] = True
            
            # 调整超时时间
            optimizations["timeout_seconds"] = self.config.large_file_timeout_seconds
            
            logger.info(f"大文件优化已启用 ({file_size_mb:.1f}MB): {optimizations}")
        
        return optimizations
    
    def check_resource_limits(self) -> Dict[str, Any]:
        """检查资源限制"""
        try:
            memory_info = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent()
            
            warnings = []
            
            # 内存检查
            memory_used_mb = memory_info.used / (1024 * 1024)
            if memory_used_mb > self.config.memory_limit_mb * 0.9:
                warnings.append(f"内存使用接近限制: {memory_used_mb:.1f}MB / {self.config.memory_limit_mb}MB")
            
            # CPU检查
            if cpu_percent > self.config.cpu_limit_percent * 0.9:
                warnings.append(f"CPU使用率过高: {cpu_percent:.1f}%")
            
            # 任务队列检查
            if len(self.active_tasks) >= self.config.max_concurrent_jobs:
                warnings.append("任务队列已满")
            
            return {
                "status": "warning" if warnings else "ok",
                "warnings": warnings,
                "can_accept_new_tasks": len(self.active_tasks) < self.config.max_concurrent_jobs
            }
        
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def cleanup_expired_tasks(self):
        """清理过期任务"""
        current_time = time.time()
        expired_tasks = []
        
        for task_id, metrics in self.active_tasks.items():
            elapsed = current_time - metrics.start_time
            timeout = self.config.large_file_timeout_seconds if metrics.memory_usage_mb > self.config.large_file_threshold_mb else self.config.job_timeout_seconds
            
            if elapsed > timeout:
                expired_tasks.append(task_id)
        
        for task_id in expired_tasks:
            logger.warning(f"任务 {task_id} 已超时，正在清理")
            self.complete_task(task_id, success=False, error="任务超时")
        
        return len(expired_tasks)
    
    def shutdown(self):
        """关闭性能优化器"""
        logger.info("正在关闭性能优化器...")
        self._shutdown = True
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        self.executor.shutdown(wait=True)
        logger.info("性能优化器已关闭")


# 全局实例
_performance_optimizer: Optional[PerformanceOptimizer] = None

def get_performance_optimizer() -> PerformanceOptimizer:
    """获取全局性能优化器实例"""
    global _performance_optimizer
    if _performance_optimizer is None:
        # 从配置文件加载性能设置
        config = PerformanceConfig()
        
        # 从环境变量覆盖配置
        config.max_concurrent_jobs = int(os.getenv("MAX_CONCURRENT_JOBS", config.max_concurrent_jobs))
        config.job_timeout_seconds = int(os.getenv("JOB_TIMEOUT_SECONDS", config.job_timeout_seconds))
        config.memory_limit_mb = int(os.getenv("MEMORY_LIMIT_MB", config.memory_limit_mb))
        
        _performance_optimizer = PerformanceOptimizer(config)
    
    return _performance_optimizer


def optimize_analysis_pipeline(file_info: Dict[str, Any]) -> Dict[str, Any]:
    """为分析管线进行性能优化"""
    optimizer = get_performance_optimizer()
    
    file_size_mb = file_info.get("size", 0) / (1024 * 1024)
    
    # 获取优化建议
    optimizations = optimizer.optimize_for_large_file(file_size_mb)
    
    # 检查资源状态
    resource_status = optimizer.check_resource_limits()
    
    return {
        "optimizations": optimizations,
        "resource_status": resource_status,
        "estimated_duration": optimizer.estimate_task_duration(
            file_size_mb, 
            file_info.get("pages", 0)
        )
    }