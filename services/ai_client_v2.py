"""
AI客户端 v2.0
支持GLM和DeepSeek的多模型容灾架构
替换豆包，实现智能故障转移
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from config.ai_models import (
    AIModelManager,
    ModelConfig,
    ModelProvider,
    get_failover_models,
    validate_ai_config,
)

logger = logging.getLogger(__name__)


@dataclass
class AIResponse:
    """AI响应结果"""
    content: str
    model: str
    provider: str
    tier: str
    usage: Dict[str, Any]
    latency_ms: int
    success: bool = True
    error_message: Optional[str] = None


class AIError(Exception):
    """AI调用错误"""
    
    def __init__(self, message: str, provider: str = "", model: str = "", tier: str = ""):
        super().__init__(message)
        self.provider = provider
        self.model = model  
        self.tier = tier


class AIClientV2:
    """AI客户端 v2.0 - 支持多模型容灾"""
    
    def __init__(self):
        self.model_manager = AIModelManager()
        self.session_cache = {}  # HTTP会话缓存
        
        # 验证配置
        validation = validate_ai_config()
        if not validation["valid"]:
            logger.warning(f"AI配置验证失败: {validation}")
        else:
            logger.info(f"AI配置验证成功，可用模型数: {validation['available_models']}")
    
    async def chat_completion(self, 
                             messages: List[Dict[str, str]],
                             temperature: float = 0.2,
                             max_tokens: Optional[int] = None,
                             timeout: int = 60,
                             **kwargs) -> AIResponse:
        """
        聊天补全接口，支持多模型容灾
        
        Args:
            messages: 对话消息列表
            temperature: 随机性参数
            max_tokens: 最大token数
            timeout: 超时时间（秒）
            **kwargs: 其他参数
            
        Returns:
            AIResponse: AI响应结果
            
        Raises:
            AIError: 所有模型都失败时抛出异常
        """
        failover_models = get_failover_models()
        
        if not failover_models:
            raise AIError("没有可用的AI模型配置")
        
        last_error = None
        
        # 按优先级尝试每个模型
        for model_config in failover_models:
            try:
                logger.info(f"尝试使用模型: {model_config.provider.value}:{model_config.model_name}")
                
                start_time = time.time()
                
                if model_config.provider == ModelProvider.ZHIPU:
                    response = await self._call_zhipu(model_config, messages, temperature, max_tokens, timeout, **kwargs)
                elif model_config.provider == ModelProvider.DEEPSEEK:
                    response = await self._call_deepseek(model_config, messages, temperature, max_tokens, timeout, **kwargs)
                else:
                    raise AIError(f"不支持的模型提供商: {model_config.provider}")
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                logger.info(f"模型调用成功: {model_config.provider.value}:{model_config.model_name}, 耗时: {latency_ms}ms")
                
                return AIResponse(
                    content=response["content"],
                    model=model_config.model_name,
                    provider=model_config.provider.value,
                    tier=model_config.tier.value,
                    usage=response.get("usage", {}),
                    latency_ms=latency_ms,
                    success=True
                )
                
            except Exception as e:
                last_error = e
                logger.warning(f"模型 {model_config.provider.value}:{model_config.model_name} 调用失败: {str(e)}")
                continue
        
        # 所有模型都失败
        error_msg = f"所有AI模型都调用失败，最后错误: {str(last_error)}"
        logger.error(error_msg)
        raise AIError(error_msg)
    
    async def _call_zhipu(self, 
                         model_config: ModelConfig,
                         messages: List[Dict[str, str]], 
                         temperature: float,
                         max_tokens: Optional[int],
                         timeout: int,
                         **kwargs) -> Dict[str, Any]:
        """调用智谱AI模型"""
        
        headers = {
            "Authorization": f"Bearer {model_config.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_config.model_name,
            "messages": messages,
            "temperature": min(max(temperature, 0.0), 1.0),
            "stream": False
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        # 添加其他参数
        if "top_p" in kwargs:
            payload["top_p"] = kwargs["top_p"]
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{model_config.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise AIError(f"智谱AI调用失败 (HTTP {response.status_code}): {error_text}")
            
            response_data = response.json()
            
            # 解析响应
            if "choices" not in response_data or not response_data["choices"]:
                raise AIError("智谱AI响应格式错误：缺少choices")
            
            choice = response_data["choices"][0]
            content = choice["message"]["content"]
            usage = response_data.get("usage", {})
            
            return {
                "content": content,
                "usage": usage
            }
    
    async def _call_deepseek(self,
                           model_config: ModelConfig,
                           messages: List[Dict[str, str]],
                           temperature: float, 
                           max_tokens: Optional[int],
                           timeout: int,
                           **kwargs) -> Dict[str, Any]:
        """调用DeepSeek模型"""
        
        headers = {
            "Authorization": f"Bearer {model_config.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_config.model_name, 
            "messages": messages,
            "temperature": min(max(temperature, 0.0), 1.0),
            "stream": False
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        # 添加其他参数
        if "top_p" in kwargs:
            payload["top_p"] = kwargs["top_p"]
        if "frequency_penalty" in kwargs:
            payload["frequency_penalty"] = kwargs["frequency_penalty"]
        if "presence_penalty" in kwargs:
            payload["presence_penalty"] = kwargs["presence_penalty"]
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{model_config.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            
            if response.status_code != 200:
                error_text = response.text
                raise AIError(f"DeepSeek调用失败 (HTTP {response.status_code}): {error_text}")
            
            response_data = response.json()
            
            # 解析响应
            if "choices" not in response_data or not response_data["choices"]:
                raise AIError("DeepSeek响应格式错误：缺少choices")
            
            choice = response_data["choices"][0]
            content = choice["message"]["content"]
            usage = response_data.get("usage", {})
            
            return {
                "content": content,
                "usage": usage
            }
    
    async def stream_chat(self,
                         messages: List[Dict[str, str]],
                         temperature: float = 0.2,
                         max_tokens: Optional[int] = None,
                         timeout: int = 60,
                         **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """
        流式聊天接口
        
        Args:
            messages: 对话消息列表
            temperature: 随机性参数  
            max_tokens: 最大token数
            timeout: 超时时间（秒）
            **kwargs: 其他参数
            
        Yields:
            Dict[str, Any]: 流式响应数据块
        """
        failover_models = get_failover_models()
        
        if not failover_models:
            raise AIError("没有可用的AI模型配置")
        
        # 尝试第一个可用模型进行流式调用
        model_config = failover_models[0]
        
        try:
            if model_config.provider == ModelProvider.ZHIPU:
                async for chunk in self._stream_zhipu(model_config, messages, temperature, max_tokens, timeout, **kwargs):
                    yield chunk
            elif model_config.provider == ModelProvider.DEEPSEEK:
                async for chunk in self._stream_deepseek(model_config, messages, temperature, max_tokens, timeout, **kwargs):
                    yield chunk
            else:
                raise AIError(f"不支持的流式模型提供商: {model_config.provider}")
                
        except Exception as e:
            logger.error(f"流式调用失败: {str(e)}")
            raise AIError(f"流式调用失败: {str(e)}")
    
    async def _stream_zhipu(self, 
                           model_config: ModelConfig,
                           messages: List[Dict[str, str]],
                           temperature: float,
                           max_tokens: Optional[int], 
                           timeout: int,
                           **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """智谱AI流式调用"""
        
        headers = {
            "Authorization": f"Bearer {model_config.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_config.model_name,
            "messages": messages,
            "temperature": min(max(temperature, 0.0), 1.0),
            "stream": True
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{model_config.base_url}/chat/completions", 
                headers=headers,
                json=payload
            ) as response:
                
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise AIError(f"智谱AI流式调用失败 (HTTP {response.status_code}): {error_text}")
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            yield {
                                "provider": model_config.provider.value,
                                "model": model_config.model_name,
                                "data": data
                            }
                        except json.JSONDecodeError:
                            continue
    
    async def _stream_deepseek(self,
                              model_config: ModelConfig,
                              messages: List[Dict[str, str]],
                              temperature: float,
                              max_tokens: Optional[int],
                              timeout: int, 
                              **kwargs) -> AsyncIterator[Dict[str, Any]]:
        """DeepSeek流式调用"""
        
        headers = {
            "Authorization": f"Bearer {model_config.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_config.model_name,
            "messages": messages,
            "temperature": min(max(temperature, 0.0), 1.0),
            "stream": True
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{model_config.base_url}/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise AIError(f"DeepSeek流式调用失败 (HTTP {response.status_code}): {error_text}")
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            yield {
                                "provider": model_config.provider.value,
                                "model": model_config.model_name,
                                "data": data
                            }
                        except json.JSONDecodeError:
                            continue
    
    def get_model_status(self) -> Dict[str, Any]:
        """获取模型状态信息"""
        return validate_ai_config()
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        result = {
            "healthy": False,
            "available_models": 0,
            "tested_models": {},
            "timestamp": time.time()
        }
        
        models = get_failover_models()
        result["available_models"] = len(models)
        
        # 测试每个模型
        for model_config in models[:2]:  # 只测试前2个模型
            model_key = f"{model_config.provider.value}:{model_config.model_name}"
            
            try:
                # 发送简单测试消息
                test_messages = [{"role": "user", "content": "Hello"}]
                response = await self.chat_completion(test_messages, timeout=10)
                
                result["tested_models"][model_key] = {
                    "status": "healthy",
                    "latency_ms": response.latency_ms
                }
                result["healthy"] = True  # 至少一个模型可用就算健康
                break  # 第一个成功就够了
                
            except Exception as e:
                result["tested_models"][model_key] = {
                    "status": "unhealthy", 
                    "error": str(e)
                }
        
        return result


# 全局实例
ai_client_v2 = AIClientV2()


# 便捷函数
async def chat_completion(**kwargs) -> AIResponse:
    """便捷的聊天补全函数"""
    return await ai_client_v2.chat_completion(**kwargs)


async def stream_chat(**kwargs) -> AsyncIterator[Dict[str, Any]]:
    """便捷的流式聊天函数"""
    async for chunk in ai_client_v2.stream_chat(**kwargs):
        yield chunk


if __name__ == "__main__":
    # 测试代码
    import asyncio
    
    async def test_ai_client():
        """测试AI客户端"""
        print("=== AI客户端测试 ===")
        
        # 健康检查
        health = await ai_client_v2.health_check()
        print(f"健康检查: {health}")
        
        # 如果有可用模型，测试聊天
        if health["healthy"]:
            try:
                response = await ai_client_v2.chat_completion(
                    messages=[{"role": "user", "content": "你好，请简单介绍一下你自己"}],
                    temperature=0.2,
                    max_tokens=100
                )
                print("聊天测试成功:")
                print(f"  模型: {response.provider}:{response.model}")
                print(f"  层级: {response.tier}")
                print(f"  耗时: {response.latency_ms}ms")
                print(f"  回复: {response.content[:100]}...")
                
            except Exception as e:
                print(f"聊天测试失败: {e}")
    
    # 运行测试
    asyncio.run(test_ai_client())