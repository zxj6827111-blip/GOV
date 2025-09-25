"""
AI 提供商统一接口包
支持多提供商容灾回退：Zhipu → OpenAI 兼容等
注意：豆包相关内容已移除，使用新的AI客户端v2
"""
from .base import LLMProvider, LLMResponse, LLMError, LLMErrorType
from .zhipu import ZhipuProvider
from .openai_compat import OpenAICompatProvider

__all__ = [
    'LLMProvider',
    'LLMResponse', 
    'LLMError',
    'LLMErrorType',
    'ZhipuProvider',
    'OpenAICompatProvider'
]