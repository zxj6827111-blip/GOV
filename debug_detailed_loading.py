#!/usr/bin/env python3
"""详细调试配置加载过程"""

import os
import sys
import tempfile
import yaml

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def debug_detailed_loading():
    """详细调试配置加载过程"""
    
    # 创建临时配置文件（exclude_budget_content: False）
    temp_config_content = {
        'dual_mode': {'enabled': True},
        'ai': {
            'provider': 'zhipu',
            'model': 'glm-4.5-flash',
            'exclude_budget_content': False  # 关键：设置为False
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_config:
        yaml.dump(temp_config_content, temp_config, allow_unicode=True)
        temp_config_path = temp_config.name
    
    try:
        # 临时修改环境变量
        original_config = os.environ.get('APP_CONFIG_PATH')
        os.environ['APP_CONFIG_PATH'] = temp_config_path
        
        print("=== 详细调试配置加载过程 ===")
        
        # 手动逐步调试Settings加载过程
        from config.settings import Settings
        
        print(f"1. 临时配置文件路径: {temp_config_path}")
        
        # 检查YAML文件内容
        with open(temp_config_path, 'r', encoding='utf-8') as f:
            yaml_content = yaml.safe_load(f)
        print(f"2. YAML文件内容: {yaml_content}")
        
        # 创建Settings实例，但手动调试每个步骤
        settings = Settings.__new__(Settings)  # 不调用__init__
        settings.config_path = temp_config_path
        settings._config = {}
        
        print(f"3. 初始化后_config: {settings._config}")
        
        # 手动执行加载步骤
        print("\n--- 步骤1: 加载YAML配置 ---")
        if os.path.exists(settings.config_path):
            with open(settings.config_path, "r", encoding="utf-8") as f:
                settings._config = yaml.safe_load(f) or {}
        print(f"YAML加载后_config: {settings._config}")
        
        print("\n--- 步骤2: 环境变量覆盖 ---")
        settings._load_env_overrides()
        print(f"环境变量覆盖后_config: {settings._config}")
        print(f"此时exclude_budget_content值: {settings.get('ai', 'exclude_budget_content')}")
        
        print("\n--- 步骤3: 设置默认值 ---")
        if 'ai' not in settings._config:
            settings._config['ai'] = {}
        print(f"确保ai段存在后_config: {settings._config}")
        
        current_value = settings.get("ai", "exclude_budget_content")
        print(f"当前exclude_budget_content值: {current_value} (类型: {type(current_value)})")
        print(f"current_value is None: {current_value is None}")
        
        if current_value is None:
            settings._config['ai']['exclude_budget_content'] = True
            print("设置为默认值: True")
        else:
            print("保持当前值，不设置默认值")
        
        print(f"最终_config: {settings._config}")
        print(f"最终is_budget_content_excluded(): {settings.is_budget_content_excluded()}")
        
        return True
        
    finally:
        # 恢复原始配置
        if original_config:
            os.environ['APP_CONFIG_PATH'] = original_config
        else:
            os.environ.pop('APP_CONFIG_PATH', None)
        
        # 清理临时文件
        os.unlink(temp_config_path)

if __name__ == "__main__":
    debug_detailed_loading()