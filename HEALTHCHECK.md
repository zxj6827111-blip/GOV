# HEALTHCHECK

> 所有命令在容器内的 Linux (Python 3.12 / Node 18) 环境执行，用于模拟 Windows 步骤。由于离线环境无法安装依赖，Windows 原生验证被阻塞。

## Backend (FastAPI)
- 结论：❌ 无法启动。pip 无法从代理下载依赖，导致 `uvicorn api.main:app` 在导入 `psutil` 时失败。
- 关键端点：`/api/status` 与 `/api/debug/rules-yaml` 未验证（服务未启动）。

<details>
<summary><code>pip install -r requirements.txt</code></summary>

```text
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'ProxyError('\nCannot connect to proxy.', OSError('Tunnel connection failed: 403 Forbidden'))': /simple/fastapi/
ERROR: Could not find a version that satisfies the requirement fastapi==0.116.2 (from versions: none)
ERROR: No matching distribution found for fastapi==0.116.2
```
</details>

<details>
<summary><code>uvicorn api.main:app --host 127.0.0.1 --port 8000</code></summary>

```text
Traceback (most recent call last):
  File "/workspace/GOV/services/performance_optimizer.py", line 10, in <module>
    import psutil
ModuleNotFoundError: No module named 'psutil'
```
</details>

## Frontend (Next.js)
- 结论：✅ `npm run dev` 成功启动 Next.js 14.1 开发服务器（localhost:3000）。

<details>
<summary><code>npm install --prefix app</code></summary>

```text
up to date in 886ms
214 packages are looking for funding
```
</details>

<details>
<summary><code>npm run --prefix app dev</code></summary>

```text
▲ Next.js 14.1.0
- Local:        http://localhost:3000
✓ Ready in 1816ms
```
</details>

## AI Microservice (Port 9009)
- 结论：⚠️ `python ai_extractor_service_v2.py` 缺少 `python-dotenv`，同样受限于代理无法安装依赖。

<details>
<summary><code>python ai_extractor_service_v2.py</code></summary>

```text
ModuleNotFoundError: No module named 'dotenv'
```
</details>

## Quality

### Python - Ruff
- `ruff check . --fix` 自动修复 149 条，但仍剩余 237 个问题（长行、异常处理规范等）。

<details>
<summary>命令输出节选</summary>

```text
Found 386 errors (149 fixed, 237 remaining).
```
</details>

### Python - Mypy
- `mypy api engine` 在 `engine/table_alias_matcher.py` 触发语法错误，类型检查中断。

<details>
<summary>命令输出节选</summary>

```text
engine/table_alias_matcher.py:111: error: Invalid syntax. Perhaps you forgot a comma?
Found 1 error in 1 file (errors prevented further checking)
```
</details>

### npm audit
- 结论：⚠️ 由于 npm registry 403 Forbidden 无法获取审计数据。

<details>
<summary>命令输出节选</summary>

```text
npm warn audit 403 Forbidden - POST https://registry.npmjs.org/-/npm/v1/security/advisories/bulk
npm error audit endpoint returned an error
```
</details>

### 前端依赖使用情况
- `npx depcheck --json` 因 403 Forbidden 无法下载依赖（离线环境）。

<details>
<summary>命令输出节选</summary>

```text
npm error 403 403 Forbidden - GET https://registry.npmjs.org/depcheck
```
</details>

## 后续建议
- 在有网络的 Windows 环境重试 pip/npx/npm audit，以完成依赖安装后重新验证 API/AI 服务端口与质量工具。
- 依据 `scripts/find_orphans.py` 的报告，评估未被引用的核心引擎/服务模块，确认是否可以下线或迁移。
