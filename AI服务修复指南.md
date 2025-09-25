# AI服务未启用 - 快速修复指南

## 问题描述
前端页面显示"AI服务未启用"，无法使用AI辅助检测功能。

## 解决方案

### 方案一：使用一键启动脚本（推荐）

```powershell
# 1. 运行启动脚本
.\start_services.ps1

# 2. 等待所有服务启动完成后访问
# http://localhost:3000
```

### 方案二：手动启动服务

```powershell
# 1. 确保环境变量已设置（已通过.env文件自动加载）
# 查看当前配置
python -c "import os; print('AI_ASSIST_ENABLED:', os.getenv('AI_ASSIST_ENABLED')); print('AI_EXTRACTOR_URL:', os.getenv('AI_EXTRACTOR_URL'))"

# 2. 启动后端API服务
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 启动AI抽取器服务（新终端）
python ai_extractor_service_v2.py

# 4. 启动前端服务（新终端）
cd app
npm run dev
```

### 方案三：使用Docker（生产环境）

```bash
# 使用AI版本的docker-compose
docker-compose -f docker-compose.ai.yml up -d

# 或者使用标准版本
docker-compose up -d
```

## 验证步骤

### 1. 检查后端配置
```powershell
# 应该返回 ai_enabled: true
Invoke-WebRequest -Uri "http://localhost:8000/api/config" -UseBasicParsing
```

### 2. 检查AI服务连通性
```powershell  
# 应该返回状态信息
Invoke-WebRequest -Uri "http://localhost:9009/health" -UseBasicParsing
```

### 3. 前端验证
- 访问 http://localhost:3000
- 上传PDF文件
- 检查"AI辅助检测"选项是否可用（不再显示"AI服务未启用"）

## 故障排除

### 如果仍显示"AI服务未启用"：

1. **检查环境变量**
   ```powershell
   # 确认.env文件存在且内容正确
   Get-Content .env
   ```

2. **检查后端配置**
   ```powershell
   # 应该显示 ai_enabled: true
   (Invoke-WebRequest -Uri "http://localhost:8000/api/config").Content | ConvertFrom-Json
   ```

3. **检查AI服务状态**
   ```powershell
   # 检查9009端口是否被监听
   netstat -an | findstr :9009
   ```

4. **查看服务日志**
   - 后端服务启动时应显示 "AI_ASSIST_ENABLED: true"
   - AI抽取器服务应成功启动在9009端口

### 常见错误及解决：

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| 端口被占用 | 8000/9009端口已被使用 | 结束占用进程或使用其他端口 |
| 模块导入错误 | Python路径问题 | 从项目根目录启动服务 |
| AI服务不可达 | AI抽取器未启动 | 启动 ai_extractor_service_v2.py |
| 环境变量未生效 | .env文件未加载 | 确认.env文件存在且语法正确 |

## 配置文件说明

### .env 文件内容
```bash
AI_ASSIST_ENABLED=true
AI_EXTRACTOR_URL=http://127.0.0.1:9009/ai/extract/v1
```

### 重要配置项
- `AI_ASSIST_ENABLED`: 控制是否启用AI辅助功能
- `AI_EXTRACTOR_URL`: AI抽取器服务地址
- 前端会同时检查后端配置和AI服务连通性

## 技术细节

前端AI状态判断逻辑：
```typescript
// 仅当后端开启且AI服务连通性为true时才认为AI可用
const enabled = !!config.ai_assist_enabled && config.ai_extractor_alive === true;
```

因此需要确保：
1. 后端 `ai_assist_enabled` 为 true
2. AI抽取器服务在指定URL可访问