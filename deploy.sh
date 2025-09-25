#!/bin/bash

# GovBudgetChecker 一键部署脚本
# 支持不同的部署模式：基础版、完整版、开发版

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的信息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查系统要求
check_requirements() {
    print_info "检查系统要求..."
    
    # 检查Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装，请先安装Docker"
        exit 1
    fi
    
    # 检查Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose 未安装，请先安装Docker Compose"
        exit 1
    fi
    
    # 检查可用内存
    AVAILABLE_MEM=$(free -m | awk 'NR==2{printf "%d", $7}')
    if [ "$AVAILABLE_MEM" -lt 2048 ]; then
        print_warning "可用内存少于2GB，可能影响性能"
    fi
    
    # 检查磁盘空间
    AVAILABLE_DISK=$(df . | awk 'NR==2{printf "%d", $4/1024}')
    if [ "$AVAILABLE_DISK" -lt 5120 ]; then
        print_warning "可用磁盘空间少于5GB，可能影响运行"
    fi
    
    print_success "系统要求检查完成"
}

# 创建必要的目录
create_directories() {
    print_info "创建必要的目录..."
    
    mkdir -p logs
    mkdir -p jobs
    mkdir -p uploads
    mkdir -p monitoring
    mkdir -p nginx
    mkdir -p scripts
    
    print_success "目录创建完成"
}

# 生成配置文件
generate_configs() {
    print_info "生成配置文件..."
    
    # 生成.env文件
    if [ ! -f .env ]; then
        cat > .env << EOF
# AI服务配置
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
ZHIPU_API_KEY=your_zhipu_api_key_here
DOUBAO_API_KEY=your_doubao_api_key_here

# 数据库配置
POSTGRES_PASSWORD=govbudget123

# 监控配置
GRAFANA_PASSWORD=admin123

# 其他配置
LOG_LEVEL=INFO
DEBUG=false
EOF
        print_warning "已生成.env文件，请根据需要修改API密钥等配置"
    fi
    
    # 生成Nginx配置
    if [ ! -f nginx/nginx.conf ]; then
        cat > nginx/nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    upstream govbudget {
        server govbudget-main:8000;
    }
    
    server {
        listen 80;
        server_name localhost;
        
        client_max_body_size 100M;
        
        location / {
            proxy_pass http://govbudget;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # 超时设置
            proxy_connect_timeout 60s;
            proxy_send_timeout 300s;
            proxy_read_timeout 300s;
        }
        
        # 静态文件缓存
        location /static/ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
EOF
    fi
    
    # 生成Prometheus配置
    if [ ! -f monitoring/prometheus.yml ]; then
        cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'govbudget'
    static_configs:
      - targets: ['govbudget-main:8000']
  
  - job_name: 'govbudget-ai'
    static_configs:
      - targets: ['govbudget-ai:9009']
EOF
    fi
    
    # 生成数据库初始化脚本
    if [ ! -f scripts/init.sql ]; then
        cat > scripts/init.sql << 'EOF'
-- GovBudgetChecker 数据库初始化脚本
CREATE DATABASE IF NOT EXISTS govbudget;

-- 创建任务表
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    file_name VARCHAR(255),
    file_size BIGINT,
    result_data JSONB
);

-- 创建日志表
CREATE TABLE IF NOT EXISTS logs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255),
    level VARCHAR(20),
    message TEXT,
    stage VARCHAR(50),
    duration_ms FLOAT,
    memory_mb FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extra_data JSONB
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_logs_job_id ON logs(job_id);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at);
EOF
    fi
    
    print_success "配置文件生成完成"
}

# 显示部署选项
show_deployment_options() {
    echo ""
    echo "请选择部署模式："
    echo "1) 基础版 - 仅主服务和AI微服务"
    echo "2) 完整版 - 包含数据库、缓存和反向代理"
    echo "3) 监控版 - 额外包含监控和仪表板"
    echo "4) 开发版 - 所有服务，用于开发调试"
    echo ""
    read -p "请输入选项 (1-4): " choice
    
    case $choice in
        1)
            COMPOSE_PROFILES=""
            ;;
        2)
            COMPOSE_PROFILES="--profile with-db --profile with-cache --profile with-nginx"
            ;;
        3)
            COMPOSE_PROFILES="--profile with-db --profile with-cache --profile with-nginx --profile with-monitoring"
            ;;
        4)
            COMPOSE_PROFILES="--profile with-db --profile with-cache --profile with-nginx --profile with-monitoring"
            export DEBUG=true
            ;;
        *)
            print_error "无效选项"
            exit 1
            ;;
    esac
}

# 构建和启动服务
deploy_services() {
    print_info "开始构建和部署服务..."
    
    # 停止现有服务
    print_info "停止现有服务..."
    docker-compose down --remove-orphans 2>/dev/null || docker compose down --remove-orphans 2>/dev/null || true
    
    # 构建镜像
    print_info "构建Docker镜像..."
    if command -v docker-compose &> /dev/null; then
        docker-compose build --no-cache
    else
        docker compose build --no-cache
    fi
    
    # 启动服务
    print_info "启动服务..."
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d $COMPOSE_PROFILES
    else
        docker compose up -d $COMPOSE_PROFILES
    fi
    
    print_success "服务启动完成"
}

# 等待服务就绪
wait_for_services() {
    print_info "等待服务就绪..."
    
    # 等待主服务
    print_info "等待主服务启动..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health >/dev/null 2>&1; then
            print_success "主服务已就绪"
            break
        fi
        sleep 2
        if [ $i -eq 30 ]; then
            print_error "主服务启动超时"
            exit 1
        fi
    done
    
    # 等待AI服务
    print_info "等待AI服务启动..."
    for i in {1..30}; do
        if curl -s http://localhost:9009/health >/dev/null 2>&1; then
            print_success "AI服务已就绪"
            break
        fi
        sleep 2
        if [ $i -eq 30 ]; then
            print_error "AI服务启动超时"
            exit 1
        fi
    done
}

# 显示部署结果
show_deployment_result() {
    echo ""
    print_success "🎉 GovBudgetChecker 部署完成！"
    echo ""
    echo "服务访问地址："
    echo "  📱 主应用: http://localhost:8000"
    echo "  🤖 AI微服务: http://localhost:9009"
    
    if [[ $COMPOSE_PROFILES == *"with-nginx"* ]]; then
        echo "  🌐 Nginx代理: http://localhost"
    fi
    
    if [[ $COMPOSE_PROFILES == *"with-monitoring"* ]]; then
        echo "  📊 Prometheus: http://localhost:9090"
        echo "  📈 Grafana: http://localhost:3000 (admin/admin123)"
    fi
    
    echo ""
    echo "常用命令："
    echo "  查看日志: docker-compose logs -f"
    echo "  停止服务: docker-compose down"
    echo "  重启服务: docker-compose restart"
    echo "  查看状态: docker-compose ps"
    echo ""
    
    # 显示样例文档信息
    if [ -d "samples" ] && [ "$(ls -A samples 2>/dev/null)" ]; then
        echo "📁 样例文档位置: ./samples/"
        echo "   可以使用这些文档测试系统功能"
        echo ""
    fi
    
    print_info "部署日志已保存到 deployment.log"
}

# 主函数
main() {
    echo "===========================================" 
    echo "  GovBudgetChecker 一键部署脚本"
    echo "  政府预决算检查系统"
    echo "==========================================="
    echo ""
    
    check_requirements
    create_directories
    generate_configs
    show_deployment_options
    deploy_services
    wait_for_services
    show_deployment_result
}

# 如果直接运行此脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@" 2>&1 | tee deployment.log
fi