# AI辅助抽取功能使用指南

## 概述

本项目已集成豆包（Doubao）AI抽取器微服务，用于辅助规则 V33-110：`R33110_BudgetVsFinal_TextConsistency` 找齐"年初预算 vs 支出决算 + 文本判断短语 +（原因说明）"的三元组及其 span。

## 功能特性

- ✅ 支持OpenAI兼容网关和直连火山方舟豆包API两种调用方式
- ✅ 滑窗处理超长文本（每窗1600-1800字，重叠200字）
- ✅ 二次校验确保抽取结果与原文完全一致
- ✅ 智能去重合并规则抽取和AI抽取结果
- ✅ 自动生成问题片段（clip）
- ✅ 过滤"表出现多次"类噪声提示
- ✅ 网络失败时自动降级到纯规则模式

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动AI抽取器微服务

#### 方式一：使用.env.doubao配置文件（推荐）

```bash
# 编辑配置文件
cp .env.doubao .env.doubao.local
# 填入您的真实API密钥
nano .env.doubao.local

# 加载配置并启动
source .env.doubao.local
uvicorn ai_extractor_service:app --host 0.0.0.0 --port 9009
```

#### 方式二：直连火山方舟豆包API

```bash
export ARK_API_KEY=your_ark_api_key
uvicorn ai_extractor_service:app --host 0.0.0.0 --port 9009
```

#### 方式三：通过OpenAI兼容网关

```bash
export OPENAI_BASE=http://127.0.0.1:9008/v1
export OPENAI_API_KEY=dummy
export OPENAI_MODEL=doubao-main
uvicorn ai_extractor_service:app --host 0.0.0.0 --port 9009
```

### 3. 配置后端服务

```bash
export AI_ASSIST_ENABLED=true
export AI_EXTRACTOR_URL=http://127.0.0.1:9009/ai/extract/v1
```

### 4. 使用Docker Compose（可选）

```bash
docker-compose -f docker-compose.ai.yml up -d
```

## API接口

### AI抽取器接口

**POST** `/ai/extract/v1`

**请求参数：**
```json
{
  "task": "R33110_pairs_v1",
  "section_text": "<（三）小节全文>",
  "language": "zh",
  "doc_hash": "sha1(section_text)",
  "max_windows": 3
}
```

**响应格式：**
```json
{
  "hits": [
    {
      "budget_text": "232.02",
      "budget_span": [58, 64],
      "final_text": "219.24",
      "final_span": [86, 92],
      "stmt_text": "决算数大于预算数",
      "stmt_span": [100, 109],
      "reason_text": null,
      "reason_span": null,
      "item_title": "公安(可选)",
      "clip": "…原文截取…"
    }
  ],
  "meta": {"model":"doubao-main","cached":false}
}
```

### 健康检查接口

**GET** `/health`

## 测试

### 运行单元测试

```bash
# 运行所有AI辅助相关测试
pytest -q tests/test_v33110_ai_assist.py

# 运行特定测试
pytest -q tests/test_v33110_ai_assist.py::TestR33110AIAssist::test_pure_rules_mode

# 跳过真实AI集成测试（需要真实API密钥）
pytest -q tests/test_v33110_ai_assist.py -k "not real_ai"
```

### 测试覆盖范围

- ✅ 纯规则模式测试
- ✅ AI辅助模式测试（Mock）
- ✅ AI失败降级测试
- ✅ 去重功能测试
- ✅ 问题生成测试
- ✅ 基本持平警告测试
- ✅ 噪声过滤测试
- ✅ 真实AI集成测试（可选）

## 验收标准

使用金标样本文本验证，应满足以下要求：

1. **六段全部命中**：在"（三）一般公共预算财政拨款支出决算（具体）情况"小节中
2. **错误检测**：
   - 第1段与第3~6段：数值实际"小于"，文本写"大于" ⇒ 均报 error
   - 第2段：数值与文本一致（小于），但缺少"主要原因：……" ⇒ 报 error（缺少原因）
3. **数字一致性**：每条问题 message 中的数字必须与 PDF 原文逐字一致
4. **片段附加**：每条问题 message 末尾附片段：「…」
5. **位置信息**：每条问题 location 必含 {page, pos, clip}
6. **基本持平**：只给 warn 提示
7. **噪声过滤**：不再出现"表出现多次：××表（页码 […]）"类噪声

## 配置选项

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `AI_ASSIST_ENABLED` | `false` | 是否启用AI辅助功能 |
| `AI_EXTRACTOR_URL` | `http://127.0.0.1:9009/ai/extract/v1` | AI抽取器服务地址 |
| `OPENAI_BASE` | - | OpenAI兼容网关地址 |
| `OPENAI_API_KEY` | - | API密钥 |
| `OPENAI_MODEL` | `doubao-main` | 模型名称 |
| `ARK_API_KEY` | - | 火山方舟豆包API密钥（推荐） |
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | 火山方舟豆包API地址 |
| `ARK_MODEL` | `doubao-1-5-pro-32k-250115` | 火山方舟豆包模型名称 |

### 模型切换

系统支持灵活的模型切换，只需修改环境变量即可：

```bash
# 切换主模型
export OPENAI_MODEL=doubao-pro-32k

# 设置备选模型（可选）
export OPENAI_BACKUP_MODEL=doubao-lite-4k
```

**注意**：
- 后端与规则无需感知模型变化
- 支持主模型失败时自动切换到备选模型
- 模型名称需与网关或API提供商保持一致

### 滑窗参数

```python
SLIDING_WINDOW_CONFIG = {
    "window_size": 1700,      # 每个窗口大小（字符）
    "overlap_size": 200,      # 窗口重叠大小（字符）
    "max_windows": 5,         # 最大窗口数量
    "min_window_size": 500    # 最小窗口大小（字符）
}
```

## 故障排除

### 常见问题

1. **AI服务连接失败**
   - 检查 `AI_EXTRACTOR_URL` 配置
   - 确认AI抽取器服务正常运行
   - 查看网络连接和防火墙设置

2. **豆包API调用失败**
   - 验证API密钥和端点配置
   - 检查网络连接和API配额
   - 查看服务日志获取详细错误信息

3. **抽取结果不准确**
   - 检查输入文本格式和编码
   - 调整滑窗参数
   - 查看二次校验日志

4. **性能问题**
   - 调整 `max_windows` 参数
   - 优化文本预处理
   - 考虑使用缓存

### 日志查看

```bash
# 查看AI抽取器日志
tail -f logs/ai_extractor.log

# 查看后端服务日志
tail -f logs/backend.log
```

### 回滚到纯规则模式

如需临时禁用AI辅助功能：

```bash
export AI_ASSIST_ENABLED=false
```

或在代码中设置：

```python
from api.config import AppConfig
config = AppConfig.load()
config.ai_assist_enabled = False
```

## 开发指南

### 添加新的抽取任务

1. 在 `ai_extractor_service_v2.py` 中添加新的任务类型
2. 更新 `ExtractRequest` 模型
3. 实现对应的抽取逻辑
4. 添加单元测试

### 自定义抽取规则

1. 继承 `Rule` 基类
2. 实现 `apply` 方法
3. 集成AI辅助抽取逻辑
4. 注册到 `ALL_RULES` 列表

### 性能优化

1. 使用异步处理
2. 实现结果缓存
3. 优化正则表达式
4. 批量处理请求

## 更新日志

### v1.0.0 (2024-01-XX)
- ✅ 初始版本发布
- ✅ 支持豆包AI抽取器集成
- ✅ 实现规则V33-110的AI辅助功能
- ✅ 添加滑窗处理和去重功能
- ✅ 完整的单元测试覆盖

## 技术支持

如遇到问题，请：

1. 查看本文档的故障排除部分
2. 检查项目日志文件
3. 运行单元测试验证功能
4. 提交Issue并附上详细的错误信息和环境配置

## 许可证

本项目遵循原项目许可证。