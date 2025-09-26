#!/usr/bin/env python3
"""调试配置加载"""

import os
import sys
import tempfile
import yaml

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def debug_config():
    """调试配置加载"""
    
    # 创建临时配置文件
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
    
    print(f"临时配置文件路径: {temp_config_path}")
    print(f"临时配置文件内容: {temp_config_content}")
    
    try:
        # 临时修改环境变量
        original_config = os.environ.get('APP_CONFIG_PATH')
        os.environ['APP_CONFIG_PATH'] = temp_config_path
        
        print(f"环境变量APP_CONFIG_PATH: {os.environ.get('APP_CONFIG_PATH')}")
        
        # 直接测试Settings类
        from config.settings import Settings
        settings_obj = Settings(temp_config_path)
        
        print(f"配置路径: {settings_obj.config_path}")
        print(f"完整配置: {settings_obj._config}")
        print(f"AI配置段: {settings_obj.get_section('ai')}")
        print(f"预算排除设置: {settings_obj.is_budget_content_excluded()}")
        
    finally:
        # 恢复原始配置
        if original_config:
            os.environ['APP_CONFIG_PATH'] = original_config
        else:
            os.environ.pop('APP_CONFIG_PATH', None)
        
        # 清理临时文件
        os.unlink(temp_config_path)

if __name__ == "__main__":
    debug_config()