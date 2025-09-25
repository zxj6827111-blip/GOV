# GovBudgetChecker 部署指南

## 🎯 快速开始

### 一键部署（推荐）

**Linux/macOS:**
```bash
chmod +x deploy.sh
./deploy.sh
```

**Windows:**
```cmd
deploy.bat
```

### 手动部署

1. **克隆项目**
```bash
git clone <repository-url>
cd GovBudgetChecker
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑.env文件，配置API密钥等
```

3. **启动服务**
```bash
# 基础版（仅主服务+AI微服务）
docker-compose up -d

# 完整版（包含数据库、缓存、代理）
docker-compose --profile with-db --profile with-cache --profile with-nginx up -d

# 监控版（额外包含监控服务）
docker-compose --profile with-db --profile with-cache --profile with-nginx --profile with-monitoring up -d
```

## 📋 系统要求

### 最低配置
- **CPU:** 2核心
- **内存:** 4GB RAM
- **磁盘:** 10GB 可用空间
- **操作系统:** Linux/Windows/macOS

### 推荐配置
- **CPU:** 4核心或以上
- **内存:** 8GB RAM或以上
- **磁盘:** 20GB 可用空间
- **网络:** 互联网连接（用于AI服务）

### 软件依赖
- Docker 20.10+
- Docker Compose 2.0+
- curl（用于健康检查）

## 🏗️ 架构说明

### 服务组件

| 服务 | 端口 | 说明 | 必需 |
|------|------|------|------|
| govbudget-main | 8000 | 主应用（前端+后端） | ✅ |
| govbudget-ai | 9009 | AI微服务 | ✅ |
| redis | 6379 | 缓存服务 | ⚪ |
| postgres | 5432 | 数据库 | ⚪ |
| nginx | 80/443 | 反向代理 | ⚪ |
| prometheus | 9090 | 监控服务 | ⚪ |
| grafana | 3000 | 监控仪表板 | ⚪ |

### 部署模式

#### 1. 基础版
- 仅包含主应用和AI微服务
- 适合快速测试和演示
- 资源占用最少

#### 2. 完整版
- 包含数据库、缓存和反向代理
- 支持持久化存储和负载均衡
- 适合生产环境

#### 3. 监控版
- 在完整版基础上增加监控服务
- 提供详细的性能指标和仪表板
- 适合生产运维

## ⚙️ 配置说明

### 环境变量配置（.env文件）

```bash
# AI服务配置
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
ZHIPU_API_KEY=your_zhipu_api_key_here
DOUBAO_API_KEY=your_doubao_api_key_here

# 数据库配置
POSTGRES_PASSWORD=your_secure_password

# 监控配置
GRAFANA_PASSWORD=your_grafana_password

# 应用配置
LOG_LEVEL=INFO
MAX_UPLOAD_SIZE=100MB
MEMORY_LIMIT_MB=2048
OCR_ENABLED=true
AI_ASSIST_ENABLED=true
```

### 关键配置项说明

- **OPENAI_API_KEY**: OpenAI API密钥，用于AI分析功能
- **ZHIPU_API_KEY**: 智谱AI API密钥（可选，多重保障）
- **DOUBAO_API_KEY**: 豆包AI API密钥（可选，多重保障）
- **LOG_LEVEL**: 日志级别（DEBUG/INFO/WARNING/ERROR）
- **MAX_UPLOAD_SIZE**: 最大文件上传大小
- **MEMORY_LIMIT_MB**: 内存使用限制
- **OCR_ENABLED**: 是否启用OCR功能
- **AI_ASSIST_ENABLED**: 是否启用AI辅助分析

## 🔍 健康检查

### 服务状态检查

```bash
# 检查所有服务状态
docker-compose ps

# 检查主服务健康状态
curl http://localhost:8000/health

# 检查AI服务健康状态
curl http://localhost:9009/health
```

### 预期响应
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "version": "1.0.0",
  "services": {
    "database": "connected",
    "ai_service": "available",
    "cache": "connected"
  }
}
```

## 📊 监控和日志

### 日志查看

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f govbudget-main
docker-compose logs -f govbudget-ai

# 查看最近100行日志
docker-compose logs --tail=100 govbudget-main
```

### 结构化日志格式

系统采用JSON格式的结构化日志，包含以下关键字段：

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "message": "处理文档完成",
  "job_id": "job_123456",
  "stage": "text_extraction",
  "duration_ms": 1500.0,
  "memory_mb": 256.5,
  "total_pages": 45,
  "ocr_trigger_rate": 0.15
}
```

### 监控指标

访问Grafana仪表板（http://localhost:3000）查看：

- **系统资源**: CPU、内存、磁盘使用率
- **服务性能**: 响应时间、吞吐量、错误率
- **业务指标**: 处理文档数、OCR使用率、规则触发数
- **AI服务**: 调用次数、成功率、平均响应时间

## 🔧 故障排除

### 常见问题

#### 1. 服务启动失败

**现象**: 服务无法启动或健康检查失败

**排查步骤**:
```bash
# 查看服务状态
docker-compose ps

# 查看错误日志
docker-compose logs govbudget-main
docker-compose logs govbudget-ai

# 检查端口占用
netstat -tulpn | grep :8000
netstat -tulpn | grep :9009
```

**解决方案**:
- 确保端口未被占用
- 检查Docker和Docker Compose版本
- 验证配置文件格式正确

#### 2. AI服务不可用

**现象**: AI分析功能异常，返回错误

**排查步骤**:
```bash
# 检查AI服务状态
curl http://localhost:9009/health

# 查看AI服务日志
docker-compose logs govbudget-ai

# 检查API密钥配置
cat .env | grep API_KEY
```

**解决方案**:
- 验证API密钥正确性
- 检查网络连接
- 查看API额度和限制

#### 3. 文件上传失败

**现象**: PDF文件无法上传或处理失败

**排查步骤**:
```bash
# 检查磁盘空间
df -h

# 查看上传相关日志
docker-compose logs govbudget-main | grep -i upload

# 检查文件权限
ls -la uploads/
```

**解决方案**:
- 清理磁盘空间
- 检查文件大小限制
- 验证文件格式

#### 4. 内存不足

**现象**: 处理大文件时服务崩溃或响应缓慢

**排查步骤**:
```bash
# 检查容器资源使用
docker stats

# 查看系统内存
free -h

# 检查内存相关日志
docker-compose logs | grep -i "memory\|oom"
```

**解决方案**:
- 增加系统内存
- 调整MEMORY_LIMIT_MB配置
- 启用大文件分段处理

### 性能优化

#### 1. 资源限制配置

在docker-compose.yml中调整资源限制：

```yaml
services:
  govbudget-main:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
        reservations:
          memory: 2G
          cpus: '1.0'
```

#### 2. 缓存优化

启用Redis缓存以提升性能：

```bash
# 启动包含缓存的完整版
docker-compose --profile with-cache up -d
```

#### 3. 并发调优

调整配置文件中的并发参数：

```yaml
environment:
  - MAX_CONCURRENT_PAGES=3
  - MAX_WORKERS=4
  - OCR_TIMEOUT=60
```

## 🚀 生产部署建议

### 安全配置

1. **修改默认密码**
```bash
# 数据库密码
POSTGRES_PASSWORD=your_strong_password

# Grafana管理员密码
GRAFANA_PASSWORD=your_admin_password
```

2. **启用HTTPS**
```bash
# 配置SSL证书
mkdir -p nginx/ssl
# 将证书文件放入nginx/ssl目录
# 修改nginx/nginx.conf启用HTTPS
```

3. **API密钥安全**
```bash
# 使用环境变量或密钥管理服务
# 避免在配置文件中明文存储
```

### 备份策略

1. **数据备份**
```bash
# 备份数据库
docker-compose exec postgres pg_dump -U govbudget govbudget > backup.sql

# 备份文件数据
tar -czf backup_files.tar.gz jobs/ uploads/ logs/
```

2. **配置备份**
```bash
# 备份配置文件
tar -czf backup_config.tar.gz .env docker-compose.yml nginx/ monitoring/
```

### 更新升级

1. **滚动更新**
```bash
# 拉取最新代码
git pull

# 重新构建镜像
docker-compose build --no-cache

# 滚动重启服务
docker-compose up -d --force-recreate
```

2. **零停机更新**
```bash
# 使用蓝绿部署或金丝雀部署策略
# 详见高级部署文档
```

## 📞 技术支持

### 获取帮助

- **文档**: 查看项目README和相关文档
- **日志**: 优先查看结构化日志定位问题
- **社区**: 提交Issue或PR到项目仓库

### 联系方式

- **项目仓库**: [GitHub链接]
- **技术文档**: [文档链接]
- **反馈邮箱**: [邮箱地址]

---

*最后更新: 2024年1月*