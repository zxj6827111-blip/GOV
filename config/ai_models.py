"""
AI模型配置管理器
实现GLM和DeepSeek的4层容灾架构
"""

import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """模型层级"""
    PRIMARY = "primary"           # 主AI
    BACKUP = "backup"            # 备用AI  
    DISASTER_PRIMARY = "disaster_primary"   # 主灾备AI
    DISASTER_BACKUP = "disaster_backup"     # 备用灾备AI


class ModelProvider(Enum):
    """模型提供商"""
    ZHIPU = "zhipu"              # 智谱AI
    DEEPSEEK = "deepseek"        # DeepSeek


@dataclass
class ModelConfig:
    """单个模型配置"""
    provider: ModelProvider
    model_name: str
    api_key: str
    base_url: str
    tier: ModelTier
    timeout: int = 60
    max_retries: int = 3
    
    @property
    def is_available(self) -> bool:
        """检查模型是否可用"""
        return bool(self.api_key and not self.api_key.startswith("your_"))


class AIModelManager:
    """AI模型管理器"""
    
    def __init__(self):
        self.models: Dict[ModelTier, ModelConfig] = {}
        self._load_models()
    
    def _load_models(self):
        """从环境变量加载模型配置"""
        
        # GLM-4.5-Flash配置 (主AI)
        zhipu_flash_api_key = os.getenv("ZHIPU_FLASH_API_KEY", "")
        zhipu_flash_base_url = os.getenv("ZHIPU_FLASH_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
        zhipu_flash_model = os.getenv("ZHIPU_FLASH_MODEL", "glm-4.5-flash")
        
        # GLM-4.5配置 (备用AI)
        zhipu_glm45_api_key = os.getenv("ZHIPU_GLM45_API_KEY", "")
        zhipu_glm45_base_url = os.getenv("ZHIPU_GLM45_BASE_URL", "https://api-inference.modelscope.cn/v1")
        zhipu_glm45_model = os.getenv("ZHIPU_GLM45_MODEL", "ZhipuAI/GLM-4.5")
        
        # DeepSeek配置
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")
        deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        deepseek_primary_model = os.getenv("DEEPSEEK_PRIMARY_MODEL", "deepseek-ai/DeepSeek-V3.1")
        deepseek_backup_model = os.getenv("DEEPSEEK_BACKUP_MODEL", "deepseek-ai/DeepSeek-V3")
        
        # 全局配置
        timeout = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
        max_retries = int(os.getenv("AI_MAX_RETRIES", "3"))
        
        # 1. 主AI - GLM-4.5-Flash
        if zhipu_flash_api_key and not zhipu_flash_api_key.startswith("your_"):
            self.models[ModelTier.PRIMARY] = ModelConfig(
                provider=ModelProvider.ZHIPU,
                model_name=zhipu_flash_model,
                api_key=zhipu_flash_api_key,
                base_url=zhipu_flash_base_url,
                tier=ModelTier.PRIMARY,
                timeout=timeout,
                max_retries=max_retries
            )
        
        # 2. 备用AI - GLM-4.5  
        if zhipu_glm45_api_key and not zhipu_glm45_api_key.startswith("your_"):
            self.models[ModelTier.BACKUP] = ModelConfig(
                provider=ModelProvider.ZHIPU,
                model_name=zhipu_glm45_model,
                api_key=zhipu_glm45_api_key,
                base_url=zhipu_glm45_base_url,
                tier=ModelTier.BACKUP,
                timeout=timeout,
                max_retries=max_retries
            )
        
        # 3. 主灾备AI - DeepSeek-V3.1
        if deepseek_api_key and not deepseek_api_key.startswith("your_"):
            self.models[ModelTier.DISASTER_PRIMARY] = ModelConfig(
                provider=ModelProvider.DEEPSEEK,
                model_name=deepseek_primary_model,
                api_key=deepseek_api_key,
                base_url=deepseek_base_url,
                tier=ModelTier.DISASTER_PRIMARY,
                timeout=timeout,
                max_retries=max_retries
            )
        
        # 4. 备用灾备AI - DeepSeek-V3
        if deepseek_api_key and not deepseek_api_key.startswith("your_"):
            self.models[ModelTier.DISASTER_BACKUP] = ModelConfig(
                provider=ModelProvider.DEEPSEEK,
                model_name=deepseek_backup_model,
                api_key=deepseek_api_key,
                base_url=deepseek_base_url,
                tier=ModelTier.DISASTER_BACKUP,
                timeout=timeout,
                max_retries=max_retries
            )
    
    def get_failover_sequence(self) -> List[ModelConfig]:
        """获取故障转移序列"""
        sequence = []
        
        # 按优先级排序：主AI -> 备用AI -> 主灾备AI -> 备用灾备AI
        tier_order = [
            ModelTier.PRIMARY,
            ModelTier.BACKUP, 
            ModelTier.DISASTER_PRIMARY,
            ModelTier.DISASTER_BACKUP
        ]
        
        for tier in tier_order:
            if tier in self.models and self.models[tier].is_available:
                sequence.append(self.models[tier])
        
        if not sequence:
            logger.warning("没有可用的AI模型配置")
        else:
            logger.info(f"AI模型故障转移序列: {[f'{m.provider.value}:{m.model_name}' for m in sequence]}")
        
        return sequence
    
    def get_model(self, tier: ModelTier) -> Optional[ModelConfig]:
        """获取指定层级的模型"""
        return self.models.get(tier)
    
    def get_available_models(self) -> List[ModelConfig]:
        """获取所有可用模型"""
        return [model for model in self.models.values() if model.is_available]
    
    def validate_configuration(self) -> Dict[str, Any]:
        """验证配置完整性"""
        result = {
            "valid": True,
            "available_models": 0,
            "missing_keys": [],
            "warnings": [],
            "providers": {}
        }
        
        # 检查环境变量
        required_env_vars = [
            "ZHIPU_FLASH_API_KEY",
            "ZHIPU_GLM45_API_KEY", 
            "DEEPSEEK_API_KEY",
            "ZHIPU_FLASH_MODEL", 
            "ZHIPU_GLM45_MODEL",
            "DEEPSEEK_PRIMARY_MODEL",
            "DEEPSEEK_BACKUP_MODEL"
        ]
        
        for var in required_env_vars:
            value = os.getenv(var)
            if not value or value.startswith("your_"):
                result["missing_keys"].append(var)
        
        # 统计可用模型
        available_models = self.get_available_models()
        result["available_models"] = len(available_models)
        
        # 按提供商分组
        for model in available_models:
            provider = model.provider.value
            if provider not in result["providers"]:
                result["providers"][provider] = []
            result["providers"][provider].append({
                "model": model.model_name,
                "tier": model.tier.value
            })
        
        # 验证结果
        if result["available_models"] == 0:
            result["valid"] = False
            result["warnings"].append("没有可用的AI模型")
        elif result["available_models"] < 2:
            result["warnings"].append("建议配置至少2个可用模型以提供容灾能力")
        
        if result["missing_keys"]:
            result["valid"] = False
        
        return result


# 全局实例
ai_model_manager = AIModelManager()


# 便捷函数
def get_failover_models() -> List[ModelConfig]:
    """获取故障转移模型序列"""
    return ai_model_manager.get_failover_sequence()


def validate_ai_config() -> Dict[str, Any]:
    """验证AI配置"""
    return ai_model_manager.validate_configuration()


if __name__ == "__main__":
    # 测试配置
    import json
    
    print(f"AI模型配置验证:")  
    validation = validate_ai_config()
    print(json.dumps(validation, indent=2, ensure_ascii=False))
    
    print(f"\n故障转移序列:")
    models = get_failover_models()
    for i, model in enumerate(models, 1):
        print(f"{i}. {model.provider.value}:{model.model_name} ({model.tier.value}) - {model.base_url}")