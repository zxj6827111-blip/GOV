#!/usr/bin/env python3
"""调试配置加载过程"""

import os
import sys
import tempfile
import yaml

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def debug_config_loading():
    """调试配置加载过程"""
    
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
        
        print("=== 调试配置加载过程 ===")
        
        # 手动创建Settings实例来调试
        from config.settings import Settings
        
        print(f"1. 临时配置文件路径: {temp_config_path}")
        print(f"2. 环境变量 APP_CONFIG_PATH: {os.environ.get('APP_CONFIG_PATH')}")
        
        # 检查YAML文件内容
        with open(temp_config_path, 'r', encoding='utf-8') as f:
            yaml_content = yaml.safe_load(f)
        print(f"3. YAML文件内容: {yaml_content}")
        
        # 创建Settings实例
        settings = Settings()
        
        print(f"4. 加载后配置: {settings._config}")
        print(f"5. AI配置段: {settings.get_section('ai')}")
        print(f"6. exclude_budget_content值: {settings.get('ai', 'exclude_budget_content')}")
        print(f"7. is_budget_content_excluded(): {settings.is_budget_content_excluded()}")
        
        # 检查环境变量映射
        print(f"8. AI_EXCLUDE_BUDGET环境变量: {os.environ.get('AI_EXCLUDE_BUDGET')}")
        
        # 检查所有环境变量
        print("9. 所有相关环境变量:")
        env_vars = ["AI_EXCLUDE_BUDGET", "APP_CONFIG_PATH"]
        for var in env_vars:
            value = os.environ.get(var)
            if value:
                print(f"   {var}: {value}")
        
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
    debug_config_loading()