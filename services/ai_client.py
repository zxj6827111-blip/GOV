"""
AI 客户端灾备核心
实现多提供商容灾回退、熔断器、可观测性
"""
import asyncio
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, AsyncIterator, Union
from pathlib import Path

import yaml

from providers import LLMProvider, LLMError, LLMErrorType, LLMResponse
from providers.zhipu import ZhipuProvider
from providers.doubao import DoubaoProvider
from providers.openai_compat import OpenAICompatProvider


logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态
    OPEN = "open"          # 熔断状态
    HALF_OPEN = "half_open"  # 半开状态


@dataclass
class CircuitBreaker:
    """熔断器"""
    failure_threshold: int = 3  # 失败阈值
    open_seconds: int = 60      # 熔断持续时间
    
    # 内部状态
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    failure_count: int = field(default=0, init=False)
    last_failure_time: float = field(default=0, init=False)
    last_success_time: float = field(default=0, init=False)
    
    def can_execute(self) -> bool:
        """是否可以执行请求"""
        now = time.time()
        
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.open_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.last_success_time = time.time()
        self.state = CircuitState.CLOSED
    
    def record_failure(self):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


@dataclass
class ProviderStats:
    """提供商统计信息"""
    name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: int = 0
    total_tokens: int = 0
    last_used: Optional[float] = None
    circuit_state: CircuitState = CircuitState.CLOSED
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    @property
    def avg_latency_ms(self) -> float:
        """平均延迟"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency_ms / self.successful_requests
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "total_tokens": self.total_tokens,
            "last_used": self.last_used,
            "circuit_state": self.circuit_state.value
        }


@dataclass
class AIClientConfig:
    """AI 客户端配置"""
    region: str = "cn"
    fallback_chain: List[str] = field(default_factory=list)
    providers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=dict)
    circuit_breaker: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_yaml(cls, config_path: str) -> 'AIClientConfig':
        """从 YAML 文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            return cls(
                region=data.get('region', 'cn'),
                fallback_chain=data.get('fallback_chain', []),
                providers=data.get('providers', {}),
                thresholds=data.get('thresholds', {}),
                circuit_breaker=data.get('circuit_breaker', {})
            )
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            return cls()


class AIClient:
    """AI 客户端 - 容灾回退核心"""
    
    def __init__(self, config_path: Optional[str] = None):
        # 加载配置
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'providers.yaml')
        
        self.config = AIClientConfig.from_yaml(config_path)
        
        # 初始化提供商
        self.providers: Dict[str, LLMProvider] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.stats: Dict[str, ProviderStats] = {}
        
        self._init_providers()
        self._init_circuit_breakers()
        
        # 记录初始化时加载的提供商列表
        self.loaded_providers = list(self.providers.keys())
        logger.info(f"Loaded providers: {self.loaded_providers}")
    
    def _init_providers(self):
        """初始化提供商"""
        for name, config in self.config.providers.items():
            if not config.get('enabled', True):
                continue
            
            try:
                provider = self._create_provider(name, config)
                if provider:
                    self.providers[name] = provider
                    self.stats[name] = ProviderStats(name=name)
                    logger.info(f"Initialized provider: {name}")
            except Exception as e:
                logger.error(f"Failed to initialize provider {name}: {e}")
    
    def _create_provider(self, name: str, config: Dict[str, Any]) -> Optional[LLMProvider]:
        """创建提供商实例"""
        api_key_env = config.get('api_key_env')
        if not api_key_env:
            logger.error(f"No api_key_env specified for provider {name}")
            return None
        
        api_key = os.getenv(api_key_env)
        if not api_key:
            logger.warning(f"API key not found in environment variable {api_key_env} for provider {name}")
            return None
        
        base_url = config.get('base', config.get('base_url', ''))
        model = config.get('model', '')
        timeout = config.get('timeout_s', config.get('timeout', 60))
        max_retries = config.get('retries', 1)
        
        # 根据名称或配置创建对应的提供商
        if 'zhipu' in name.lower():
            return ZhipuProvider(
                api_key=api_key,
                base_url=base_url,
                default_model=model,
                timeout=timeout,
                max_retries=max_retries
            )
        elif 'doubao' in name.lower() or 'ark' in base_url.lower():
            return DoubaoProvider(
                api_key=api_key,
                base_url=base_url,
                default_model=model,
                timeout=timeout,
                max_retries=max_retries
            )
        elif 'openai' in name.lower() or 'openai.com' in base_url:
            return OpenAICompatProvider(
                api_key=api_key,
                base_url=base_url,
                default_model=model,
                timeout=timeout,
                max_retries=max_retries
            )
        else:
            # 默认使用 OpenAI 兼容接口
            return OpenAICompatProvider(
                api_key=api_key,
                base_url=base_url,
                default_model=model,
                timeout=timeout,
                max_retries=max_retries
            )
    
    def _init_circuit_breakers(self):
        """初始化熔断器"""
        cb_config = self.config.circuit_breaker
        failure_threshold = cb_config.get('failure_threshold', 3)
        open_seconds = cb_config.get('open_seconds', 60)
        
        for name in self.providers.keys():
            self.circuit_breakers[name] = CircuitBreaker(
                failure_threshold=failure_threshold,
                open_seconds=open_seconds
            )
    
    def get_available_providers(self) -> List[str]:
        """获取可用的提供商列表（按回退链顺序）"""
        available = []
        
        # 按照回退链顺序
        for name in self.config.fallback_chain:
            if name in self.providers and self.circuit_breakers[name].can_execute():
                available.append(name)
        
        # 添加其他可用的提供商
        for name in self.providers.keys():
            if name not in available and self.circuit_breakers[name].can_execute():
                available.append(name)
        
        return available
    
    async def chat(self, 
                   messages: List[Dict[str, str]], 
                   model: Optional[str] = None,
                   temperature: float = 0.2,
                   max_tokens: Optional[int] = None,
                   timeout: int = 60,
                   **kwargs) -> Dict[str, Any]:
        """
        聊天接口 - 带容灾回退
        
        Returns:
            {
                "content": str,
                "model": str,
                "provider_used": str,
                "retries": int,
                "fell_back": bool,
                "circuit_state": str,
                "latency_ms": int,
                "tokens": dict,
                "request_id": str
            }
        """
        available_providers = self.get_available_providers()
        
        if not available_providers:
            raise LLMError(
                error_type=LLMErrorType.NO_PROVIDERS_AVAILABLE,
                message="No providers available (all circuit breakers open)",
                provider="none"
            )
        
        last_error = None
        retries = 0
        fell_back = False
        
        for i, provider_name in enumerate(available_providers):
            if i > 0:
                fell_back = True
            
            provider = self.providers[provider_name]
            circuit_breaker = self.circuit_breakers[provider_name]
            stats = self.stats[provider_name]
            
            # 检查熔断器
            if not circuit_breaker.can_execute():
                logger.warning(f"Circuit breaker open for provider {provider_name}")
                continue
            
            try:
                # 执行请求
                response = await self._execute_with_retry(
                    provider, messages, model, temperature, max_tokens, timeout, **kwargs
                )
                
                # 记录成功
                circuit_breaker.record_success()
                stats.successful_requests += 1
                stats.total_requests += 1
                stats.last_used = time.time()
                stats.total_latency_ms += response.latency_ms
                if response.usage:
                    stats.total_tokens += response.usage.get('total_tokens', 0)
                
                # 更新熔断器状态
                stats.circuit_state = circuit_breaker.state
                
                return {
                    "content": response.content,
                    "model": response.model,
                    "provider_used": provider_name,
                    "retries": retries,
                    "fell_back": fell_back,
                    "circuit_state": circuit_breaker.state.value,
                    "latency_ms": response.latency_ms,
                    "tokens": response.usage or {},
                    "request_id": response.request_id,
                    "finish_reason": response.finish_reason
                }
                
            except LLMError as e:
                last_error = e
                retries += 1
                
                # 记录失败
                stats.failed_requests += 1
                stats.total_requests += 1
                stats.last_used = time.time()
                
                # 根据错误类型决定是否切换提供商
                if self._should_fallback(e):
                    logger.warning(f"Provider {provider_name} failed with {e.error_type.value}: {e.message}")
                    circuit_breaker.record_failure()
                    stats.circuit_state = circuit_breaker.state
                    continue
                else:
                    # 不应该回退的错误（如无效请求），直接抛出
                    raise e
        
        # 所有提供商都失败了
        if last_error:
            raise last_error
        else:
            raise LLMError(
                error_type=LLMErrorType.NO_PROVIDERS_AVAILABLE,
                message="All providers failed or unavailable",
                provider="all"
            )
    
    async def _execute_with_retry(self, 
                                  provider: LLMProvider, 
                                  messages: List[Dict[str, str]], 
                                  model: Optional[str],
                                  temperature: float,
                                  max_tokens: Optional[int],
                                  timeout: int,
                                  **kwargs) -> LLMResponse:
        """带重试的执行"""
        max_retries = getattr(provider, 'max_retries', 1)
        
        for attempt in range(max_retries + 1):
            try:
                return await provider.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    **kwargs
                )
            except LLMError as e:
                if attempt == max_retries or not self._should_retry(e):
                    raise e
                
                # 指数回退 + 抖动
                delay = min(2 ** attempt + random.uniform(0, 1), 10)
                logger.info(f"Retrying {provider.name} after {delay:.1f}s (attempt {attempt + 1}/{max_retries + 1})")
                await asyncio.sleep(delay)
        
        # 不应该到达这里
        raise LLMError(
            error_type=LLMErrorType.UNKNOWN,
            message="Unexpected retry loop exit",
            provider=provider.name
        )
    
    def _should_retry(self, error: LLMError) -> bool:
        """判断是否应该重试"""
        # 不重试的错误类型
        no_retry_types = {
            LLMErrorType.AUTHENTICATION,
            LLMErrorType.MODEL_NOT_FOUND,
            LLMErrorType.INVALID_REQUEST,
            LLMErrorType.QUOTA_EXCEEDED
        }
        
        return error.error_type not in no_retry_types
    
    def _should_fallback(self, error: LLMError) -> bool:
        """判断是否应该回退到下一个提供商"""
        # 总是回退的错误类型
        always_fallback = {
            LLMErrorType.AUTHENTICATION,
            LLMErrorType.MODEL_NOT_FOUND,
            LLMErrorType.QUOTA_EXCEEDED,
            LLMErrorType.SERVER_ERROR,
            LLMErrorType.TIMEOUT,
            LLMErrorType.NETWORK_ERROR,
            LLMErrorType.RATE_LIMIT
        }
        
        return error.error_type in always_fallback
    
    async def chat_stream(self, 
                         messages: List[Dict[str, str]], 
                         model: Optional[str] = None,
                         temperature: float = 0.2,
                         max_tokens: Optional[int] = None,
                         timeout: int = 60,
                         **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """流式聊天接口"""
        available_providers = self.get_available_providers()
        
        if not available_providers:
            raise LLMError(
                error_type=LLMErrorType.NO_PROVIDERS_AVAILABLE,
                message="No providers available for streaming",
                provider="none"
            )
        
        # 流式接口只使用第一个可用的提供商，不做回退
        provider_name = available_providers[0]
        provider = self.providers[provider_name]
        circuit_breaker = self.circuit_breakers[provider_name]
        
        if not circuit_breaker.can_execute():
            raise LLMError(
                error_type=LLMErrorType.CIRCUIT_BREAKER_OPEN,
                message=f"Circuit breaker open for provider {provider_name}",
                provider=provider_name
            )
        
        try:
            async for chunk in provider.chat_stream(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                **kwargs
            ):
                yield chunk
            
            # 记录成功
            circuit_breaker.record_success()
            stats = self.stats[provider_name]
            stats.successful_requests += 1
            stats.total_requests += 1
            stats.last_used = time.time()
            
        except LLMError as e:
            # 记录失败
            circuit_breaker.record_failure()
            stats = self.stats[provider_name]
            stats.failed_requests += 1
            stats.total_requests += 1
            stats.last_used = time.time()
            raise e
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        provider_status = {}
        
        for name, provider in self.providers.items():
            circuit_breaker = self.circuit_breakers[name]
            stats = self.stats[name]
            
            provider_status[name] = {
                "available": circuit_breaker.can_execute(),
                "circuit_state": circuit_breaker.state.value,
                "stats": stats.to_dict()
            }
        
        return {
            "total_providers": len(self.providers),
            "available_providers": len(self.get_available_providers()),
            "fallback_chain": self.config.fallback_chain,
            "providers": provider_status
        }
    
    def get_provider_stats(self) -> List[Dict[str, Any]]:
        """获取提供商统计信息"""
        stats_list = []
        
        # 添加已加载的提供商信息
        for name in self.loaded_providers:
            if name in self.stats:
                stats_dict = self.stats[name].to_dict()
                # 添加模型信息
                if name in self.providers:
                    provider = self.providers[name]
                    stats_dict["model_used"] = getattr(provider, 'default_model', 'unknown')
                stats_list.append(stats_dict)
            else:
                # 即使没有统计信息，也要返回基础信息
                stats_list.append({
                    "name": name,
                    "model_used": "unknown",
                    "total_requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "success_rate": 0.0,
                    "avg_latency_ms": 0.0,
                    "total_tokens": 0,
                    "last_used": None,
                    "circuit_state": "closed"
                })
        
        return stats_list
    
    def reset_circuit_breaker(self, provider_name: str) -> bool:
        """重置熔断器"""
        if provider_name in self.circuit_breakers:
            cb = self.circuit_breakers[provider_name]
            cb.state = CircuitState.CLOSED
            cb.failure_count = 0
            logger.info(f"Reset circuit breaker for provider {provider_name}")
            return True
        return False
    
    def disable_provider(self, provider_name: str) -> bool:
        """禁用提供商"""
        if provider_name in self.circuit_breakers:
            cb = self.circuit_breakers[provider_name]
            cb.state = CircuitState.OPEN
            cb.last_failure_time = time.time()
            logger.info(f"Disabled provider {provider_name}")
            return True
        return False


# 全局实例
_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """获取全局 AI 客户端实例"""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client


async def chat(messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
    """便捷的聊天接口"""
    client = get_ai_client()
    return await client.chat(messages, **kwargs)


async def chat_stream(messages: List[Dict[str, str]], **kwargs) -> AsyncIterator[Dict[str, Any]]:
    """便捷的流式聊天接口"""
    client = get_ai_client()
    async for chunk in client.chat_stream(messages, **kwargs):
        yield chunk