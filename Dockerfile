# GovBudgetChecker 生产环境 Dockerfile
# 支持前端+后端一体化部署

# 多阶段构建：前端构建阶段
FROM node:18-alpine AS frontend-builder

WORKDIR /frontend

# 复制前端依赖文件
COPY app/package*.json ./
COPY app/yarn.lock* ./

# 安装前端依赖
RUN npm ci --only=production && npm cache clean --force

# 复制前端源码
COPY app/ ./

# 构建前端静态文件
RUN npm run build

# Python后端阶段
FROM python:3.11-slim AS backend

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# 复制Python依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端源码
COPY . .

# 从前端构建阶段复制静态文件
COPY --from=frontend-builder /frontend/out ./static/

# 创建必要的目录
RUN mkdir -p /app/logs /app/jobs /app/uploads /app/samples

# 复制demo规则和样例
COPY rules/ ./rules/
COPY samples/ ./samples/

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV HOST=0.0.0.0

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 暴露端口
EXPOSE 8000

# 创建非root用户
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# 启动命令
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]