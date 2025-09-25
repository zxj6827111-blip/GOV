# GLM模型配置更新说明

## 🔄 配置变更总结

根据您的要求，已完成以下GLM模型配置更新：

### 📋 变更内容

#### 1. 模型名称修正
- ❌ 旧配置：`GLM-4-Flash` → ✅ 新配置：`GLM-4.5-Flash`
- ❌ 旧配置：`GLM-4` → ✅ 新配置：`ZhipuAI/GLM-4.5`

#### 2. API接口地址分离
两个GLM模型现在使用不同的API接口：

**GLM-4.5-Flash (主AI)**
- API地址：`https://open.bigmodel.cn/api/paas/v4`
- 模型名称：`glm-4.5-flash`
- 环境变量：`ZHIPU_FLASH_API_KEY`

**GLM-4.5 (备用AI)**  
- API地址：`https://api-inference.modelscope.cn/v1`
- 模型名称：`ZhipuAI/GLM-4.5`
- 环境变量：`ZHIPU_GLM45_API_KEY`

### 🎯 4层AI容灾架构（更新后）

```
主AI: GLM-4.5-Flash (智谱AI - BigModel平台)
  ↓ 故障转移
备用AI: ZhipuAI/GLM-4.5 (智谱AI - ModelScope平台)
  ↓ 故障转移  
主灾备AI: DeepSeek-V3.1 (DeepSeek)
  ↓ 故障转移
备用灾备AI: DeepSeek-V3 (DeepSeek)
```

### 📄 更新的文件

1. **`.env`** - 环境变量配置文件
2. **`config/ai_models.py`** - AI模型管理器
3. **`config/providers.yaml`** - 提供商配置文件
4. **`setup_ai_env.ps1`** - 环境变量设置脚本
5. **`AI配置指南_GLM_DeepSeek.md`** - 配置指南文档

### 💻 新的环境变量配置

```bash
# GLM-4.5-Flash配置 (主AI)
ZHIPU_FLASH_API_KEY=your_actual_zhipu_flash_api_key_here
ZHIPU_FLASH_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_FLASH_MODEL=glm-4.5-flash

# GLM-4.5配置 (备用AI)
ZHIPU_GLM45_API_KEY=your_actual_zhipu_glm45_api_key_here
ZHIPU_GLM45_BASE_URL=https://api-inference.modelscope.cn/v1
ZHIPU_GLM45_MODEL=ZhipuAI/GLM-4.5

# DeepSeek配置 (灾备AI)
DEEPSEEK_API_KEY=your_actual_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_PRIMARY_MODEL=deepseek-ai/DeepSeek-V3.1
DEEPSEEK_BACKUP_MODEL=deepseek-ai/DeepSeek-V3
```

### 🔍 验证方法

#### 1. 配置验证
```bash
python -c "from config.ai_models import validate_ai_config; import json; validation = validate_ai_config(); print(json.dumps(validation, indent=2, ensure_ascii=False))"
```

#### 2. 查看故障转移序列
```bash
python config/ai_models.py
```

#### 3. 健康检查
```bash
curl http://localhost:9009/health
```

### 🚀 服务状态

当前AI抽取器服务v2.0已启动在端口9009：
- 状态：运行中（degraded模式，因为未配置API密钥）
- 支持：正则回退机制，即使无API密钥也能提供基础功能
- 版本：2.0.0

### 📝 下一步操作

1. **获取API密钥**：
   - GLM-4.5-Flash：访问 https://open.bigmodel.cn/
   - GLM-4.5：访问 https://www.modelscope.cn/
   - DeepSeek：访问 https://platform.deepseek.com/

2. **编辑.env文件**：
   - 将示例密钥替换为真实密钥
   - 保存文件后重启服务

3. **测试配置**：
   - 运行配置验证脚本
   - 使用 `.\start_services.ps1` 启动所有服务
   - 在前端测试AI辅助检测功能

### 🛠️ 技术特性

- ✅ 支持不同API接口的GLM模型
- ✅ 独立的API密钥管理
- ✅ 智能故障转移机制
- ✅ 正则回退保证可用性
- ✅ 详细的健康检查和监控
- ✅ 完整的配置验证

---

**总结**：GLM模型配置已按要求更新完成，支持GLM-4.5-Flash和GLM-4.5两个独立模型，使用不同的API接口。配置完API密钥后即可使用。