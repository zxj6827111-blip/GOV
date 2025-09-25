@echo off
REM GovBudgetChecker Windows一键部署脚本

setlocal enabledelayedexpansion

echo ==========================================
echo   GovBudgetChecker 一键部署脚本 (Windows)
echo   政府预决算检查系统
echo ===========================================
echo.

REM 检查Docker是否安装
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Docker 未安装，请先安装Docker Desktop
    pause
    exit /b 1
)

REM 检查Docker Compose是否可用
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    docker compose version >nul 2>&1
    if !errorlevel! neq 0 (
        echo [错误] Docker Compose 未安装或不可用
        pause
        exit /b 1
    )
    set USE_COMPOSE_V2=1
) else (
    set USE_COMPOSE_V2=0
)

echo [信息] Docker环境检查通过

REM 创建必要目录
echo [信息] 创建必要目录...
if not exist logs mkdir logs
if not exist jobs mkdir jobs
if not exist uploads mkdir uploads
if not exist monitoring mkdir monitoring
if not exist nginx mkdir nginx
if not exist scripts mkdir scripts

REM 生成.env文件（如果不存在）
if not exist .env (
    echo [信息] 生成.env配置文件...
    (
        echo # AI服务配置
        echo OPENAI_API_KEY=your_openai_api_key_here
        echo OPENAI_BASE_URL=https://api.openai.com/v1
        echo ZHIPU_API_KEY=your_zhipu_api_key_here
        echo DOUBAO_API_KEY=your_doubao_api_key_here
        echo.
        echo # 数据库配置
        echo POSTGRES_PASSWORD=govbudget123
        echo.
        echo # 监控配置
        echo GRAFANA_PASSWORD=admin123
        echo.
        echo # 其他配置
        echo LOG_LEVEL=INFO
        echo DEBUG=false
    ) > .env
    echo [警告] 已生成.env文件，请根据需要修改API密钥等配置
)

REM 选择部署模式
echo.
echo 请选择部署模式：
echo 1) 基础版 - 仅主服务和AI微服务
echo 2) 完整版 - 包含数据库、缓存和反向代理
echo 3) 监控版 - 额外包含监控和仪表板
echo.
set /p choice="请输入选项 (1-3): "

set COMPOSE_PROFILES=
if "%choice%"=="1" (
    set COMPOSE_PROFILES=
    echo [信息] 选择基础版部署
) else if "%choice%"=="2" (
    set COMPOSE_PROFILES=--profile with-db --profile with-cache --profile with-nginx
    echo [信息] 选择完整版部署
) else if "%choice%"=="3" (
    set COMPOSE_PROFILES=--profile with-db --profile with-cache --profile with-nginx --profile with-monitoring
    echo [信息] 选择监控版部署
) else (
    echo [错误] 无效选项
    pause
    exit /b 1
)

REM 停止现有服务
echo [信息] 停止现有服务...
if %USE_COMPOSE_V2%==1 (
    docker compose down --remove-orphans >nul 2>&1
) else (
    docker-compose down --remove-orphans >nul 2>&1
)

REM 构建镜像
echo [信息] 构建Docker镜像，这可能需要几分钟时间...
if %USE_COMPOSE_V2%==1 (
    docker compose build --no-cache
) else (
    docker-compose build --no-cache
)

if %errorlevel% neq 0 (
    echo [错误] 镜像构建失败
    pause
    exit /b 1
)

REM 启动服务
echo [信息] 启动服务...
if %USE_COMPOSE_V2%==1 (
    docker compose up -d %COMPOSE_PROFILES%
) else (
    docker-compose up -d %COMPOSE_PROFILES%
)

if %errorlevel% neq 0 (
    echo [错误] 服务启动失败
    pause
    exit /b 1
)

REM 等待服务就绪
echo [信息] 等待服务就绪...

REM 等待主服务（最多60秒）
set /a count=0
:wait_main
set /a count+=1
timeout /t 2 /nobreak >nul
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel%==0 (
    echo [成功] 主服务已就绪
    goto wait_ai
)
if %count% geq 30 (
    echo [错误] 主服务启动超时
    goto show_logs
)
goto wait_main

:wait_ai
REM 等待AI服务
set /a count=0
:wait_ai_loop
set /a count+=1
timeout /t 2 /nobreak >nul
curl -s http://localhost:9009/health >nul 2>&1
if %errorlevel%==0 (
    echo [成功] AI服务已就绪
    goto deployment_success
)
if %count% geq 30 (
    echo [错误] AI服务启动超时
    goto show_logs
)
goto wait_ai_loop

:deployment_success
echo.
echo ===========================================
echo 🎉 GovBudgetChecker 部署完成！
echo ===========================================
echo.
echo 服务访问地址：
echo   📱 主应用: http://localhost:8000
echo   🤖 AI微服务: http://localhost:9009

if not "%COMPOSE_PROFILES%"=="" (
    if not "%COMPOSE_PROFILES:with-nginx=%"=="%COMPOSE_PROFILES%" (
        echo   🌐 Nginx代理: http://localhost
    )
    if not "%COMPOSE_PROFILES:with-monitoring=%"=="%COMPOSE_PROFILES%" (
        echo   📊 Prometheus: http://localhost:9090
        echo   📈 Grafana: http://localhost:3000 ^(admin/admin123^)
    )
)

echo.
echo 常用命令：
if %USE_COMPOSE_V2%==1 (
    echo   查看日志: docker compose logs -f
    echo   停止服务: docker compose down
    echo   重启服务: docker compose restart
    echo   查看状态: docker compose ps
) else (
    echo   查看日志: docker-compose logs -f
    echo   停止服务: docker-compose down
    echo   重启服务: docker-compose restart
    echo   查看状态: docker-compose ps
)

echo.
if exist samples (
    echo 📁 样例文档位置: .\samples\
    echo    可以使用这些文档测试系统功能
    echo.
)

echo [信息] 部署完成，按任意键退出...
goto end

:show_logs
echo.
echo [信息] 服务启动可能存在问题，显示最近的日志：
echo ==========================================
if %USE_COMPOSE_V2%==1 (
    docker compose logs --tail=20
) else (
    docker-compose logs --tail=20
)
echo ==========================================
echo.
echo 请检查上述日志信息，或运行以下命令查看详细日志：
if %USE_COMPOSE_V2%==1 (
    echo   docker compose logs -f
) else (
    echo   docker-compose logs -f
)

:end
pause