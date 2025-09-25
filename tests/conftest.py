"""
pytest配置文件，提供共享的测试fixtures和配置
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环用于异步测试"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """模拟配置对象"""
    return {
        "ai.enabled": True,
        "ai.provider": "test",
        "ai.model": "test-model",
        "ai.api_key": "test-key",
        "ai.base_url": "http://test.com",
        "dual_mode.enabled": True,
        "dual_mode.ai_weight": 0.7,
        "dual_mode.rules_weight": 0.3,
        "dual_mode.confidence_threshold": 0.8,
        "dual_mode.merge_strategy": "weighted",
        "logging.level": "INFO",
        "logging.format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        "performance.enable_monitoring": True,
        "performance.log_slow_queries": True,
        "performance.slow_query_threshold": 1.0,
    }


@pytest.fixture
def mock_ai_client():
    """模拟AI客户端"""
    client = AsyncMock()
    client.extract_issues.return_value = {"issues": [], "confidence": 0.9, "processing_time": 0.5}
    return client


@pytest.fixture
def mock_rules_engine():
    """模拟规则引擎"""
    engine = Mock()
    engine.validate.return_value = []
    return engine


@pytest.fixture
def sample_pdf_content():
    """提供测试用的PDF内容"""
    return b"Sample PDF content for testing"


@pytest.fixture
def temp_pdf_file():
    """创建临时PDF文件用于测试"""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"Sample PDF content for testing")
        temp_path = f.name

    yield temp_path

    # 清理临时文件
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def mock_text_extractor():
    """模拟文本提取器"""
    extractor = Mock()
    extractor.extract_text.return_value = "Sample extracted text"
    return extractor


@pytest.fixture
def sample_budget_data():
    """提供测试用的预算数据"""
    return {
        "department": "测试部门",
        "year": 2024,
        "budget_items": [
            {"name": "人员经费", "amount": 1000000},
            {"name": "公用经费", "amount": 500000},
            {"name": "项目支出", "amount": 2000000},
        ],
        "total_budget": 3500000,
    }


@pytest.fixture
def mock_database():
    """模拟数据库连接"""
    db = Mock()
    db.execute.return_value = []
    db.fetch_all.return_value = []
    db.fetch_one.return_value = None
    return db
