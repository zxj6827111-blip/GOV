# GovBudgetChecker AI配置指南 v2.0

## 🔄 升级说明

本版本已完全替换豆包AI，采用GLM和DeepSeek的4层容灾架构：

1. **主AI**: GLM-4.5-Flash (智谱AI - BigModel平台)
2. **备用AI**: GLM-4.5 (智谱AI - ModelScope平台) 
3. **主灾备AI**: DeepSeek-V3.1 (DeepSeek)
4. **备用灾备AI**: DeepSeek-V3 (DeepSeek)

## 📋 配置步骤

### 1. 获取API密钥

#### 智谱AI（推荐）
1. **GLM-4.5-Flash（主AI）**
   - 访问 [智谱AI开放平台](https://open.bigmodel.cn/)
   - 注册账号并完成实名认证
   - 创建API密钥，复制保存
   - 模型：`glm-4.5-flash`
   - API地址：`https://open.bigmodel.cn/api/paas/v4`

2. **GLM-4.5（备用AI）**
   - 访问 [ModelScope平台](https://www.modelscope.cn/)
   - 注册账号并获取API密钥
   - 模型：`ZhipuAI/GLM-4.5`
   - API地址：`https://api-inference.modelscope.cn/v1`

#### DeepSeek AI（灾备）
1. 访问 [DeepSeek AI平台](https://platform.deepseek.com/)
2. 注册账号并完成认证
3. 创建API密钥，复制保存
4. 模型：`deepseek-ai/DeepSeek-V3.1` (主) + `deepseek-ai/DeepSeek-V3` (备用)

### 2. 配置环境变量

编辑项目根目录下的 `.env` 文件：

```bash
# ==== AI服务启用开关 ====
AI_ASSIST_ENABLED=true
AI_EXTRACTOR_URL=http://127.0.0.1:9009/ai/extract/v1

# ==== GLM-4.5-Flash配置 (主AI) ====
ZHIPU_FLASH_API_KEY=your_actual_zhipu_flash_api_key_here
ZHIPU_FLASH_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_FLASH_MODEL=glm-4.5-flash

# ==== GLM-4.5配置 (备用AI) ====
ZHIPU_GLM45_API_KEY=your_actual_zhipu_glm45_api_key_here
ZHIPU_GLM45_BASE_URL=https://api-inference.modelscope.cn/v1
ZHIPU_GLM45_MODEL=ZhipuAI/GLM-4.5

# ==== DeepSeek配置 (灾备AI) ====
DEEPSEEK_API_KEY=your_actual_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_PRIMARY_MODEL=deepseek-ai/DeepSeek-V3.1
DEEPSEEK_BACKUP_MODEL=deepseek-ai/DeepSeek-V3

# ==== AI模型容灾配置 ====
AI_FAILOVER_STRATEGY=smart_failover
AI_MAX_RETRIES=3
AI_TIMEOUT_SECONDS=60
```

**重要提示**：
- 将 `your_actual_zhipu_flash_api_key_here` 替换为真实的GLM-4.5-Flash密钥
- 将 `your_actual_zhipu_glm45_api_key_here` 替换为真实的GLM-4.5密钥  
- 将 `your_actual_deepseek_api_key_here` 替换为真实的DeepSeek密钥
- 至少配置一个提供商的密钥，系统才能正常工作

### 3. 安装依赖

确保安装了必要的Python包：

```bash
pip install python-dotenv httpx fastapi uvicorn pydantic
```

### 4. 验证配置

运行配置验证脚本：

```bash
python -c "from config.ai_models import validate_ai_config; import json; print(json.dumps(validate_ai_config(), indent=2, ensure_ascii=False))"
```

预期输出示例：
```json
{
  "valid": true,
  "available_models": 4,
  "missing_keys": [],
  "warnings": [],
  "providers": {
    "zhipu": [
      {"model": "glm-4.5-flash", "tier": "primary", "base_url": "https://open.bigmodel.cn/api/paas/v4"},
      {"model": "ZhipuAI/GLM-4.5", "tier": "backup", "base_url": "https://api-inference.modelscope.cn/v1"}
    ],
    "deepseek": [
      {"model": "deepseek-ai/DeepSeek-V3.1", "tier": "disaster_primary"},
      {"model": "deepseek-ai/DeepSeek-V3", "tier": "disaster_backup"}
    ]
  }
}
```

## 🚀 启动服务

### 方法1：一键启动（推荐）
```powershell
# Windows PowerShell
.\start_services.ps1
```

### 方法2：手动启动
```bash
# 1. 启动后端API服务
cd api
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 2. 启动AI抽取器服务v2.0 (新终端)
python ai_extractor_service_v2.py

# 3. 启动前端服务 (新终端)
cd app
npm run dev
```

## 📊 测试AI功能

### 1. 健康检查
```bash
curl http://localhost:9009/health
```

### 2. 测试抽取功能
```bash
curl -X POST "http://localhost:9009/ai/extract/v1" \
     -H "Content-Type: application/json" \
     -d '{
       "task": "R33110_pairs_v1",
       "section_text": "年初预算为100万元，决算支出为95万元，决算数小于预算数。",
       "doc_hash": "test123",
       "max_windows": 1
     }'
```

### 3. 前端验证
1. 访问 http://localhost:3000
2. 上传PDF文件
3. 选择"AI辅助检测"或"双模式分析"
4. 查看是否显示"AI服务已启用"

## 🔧 故障排除

### 问题1：显示"AI服务未启用"
**解决方案**：
1. 检查.env文件中的API密钥是否正确
2. 运行健康检查：`curl http://localhost:9009/health`
3. 查看AI抽取器服务日志

### 问题2：模型调用失败
**解决方案**：
1. 验证API密钥有效性
2. 检查网络连接
3. 查看容灾日志，确认是否有可用模型

### 问题3：端口占用
**解决方案**：
```bash
# Windows 查看端口占用
netstat -ano | findstr :9009
netstat -ano | findstr :8000

# 终止占用进程
taskkill /PID <进程ID> /F
```

### 问题4：依赖包缺失
**解决方案**：
```bash
pip install -r requirements.txt
pip install python-dotenv httpx
```

## 💡 高级配置

### 自定义容灾策略
在 `.env` 中配置：
```bash
# 调整超时时间（秒）
AI_TIMEOUT_SECONDS=90

# 调整重试次数
AI_MAX_RETRIES=5

# 启用详细日志
LOG_LEVEL=DEBUG
```

### 性能优化
```bash
# AI抽取器服务端口（如有冲突可修改）
AI_EXTRACTOR_PORT=9009

# API服务端口（如有冲突可修改）
API_PORT=8000
```

## 📋 配置清单

- [ ] 获取GLM-4.5-Flash API密钥 (BigModel平台)
- [ ] 获取GLM-4.5 API密钥 (ModelScope平台)
- [ ] 获取DeepSeek API密钥（可选，用于灾备）
- [ ] 编辑 `.env` 文件，填入真实密钥
- [ ] 运行配置验证脚本
- [ ] 启动所有服务
- [ ] 测试AI抽取功能
- [ ] 前端验证AI服务状态

## 🆘 技术支持

如遇到配置问题：

1. 查看服务日志：`python ai_extractor_service_v2.py`
2. 运行健康检查：`curl http://localhost:9009/health`  
3. 验证配置：运行配置验证脚本
4. 检查网络连接和API密钥有效性

---

**注意**：旧版豆包相关配置已全部移除，请使用新的GLM+DeepSeek配置。