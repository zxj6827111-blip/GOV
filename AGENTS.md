# AGENTS.md — 给 Codex 的工作说明（GovBudgetChecker）

## 目标
构建“政府预算/决算公开材料自动审校系统”：上传 PDF 或输入公开链接，按规则集（默认 v3_3）检查“九张表”/必备章节完整性、勾稽一致性、文字-数字自洽与典型口径项；输出可视化问题列表（含页码与红框截图），并支持导出 CSV/JSON 与标注版 PDF。

## 技术栈
- 前端：Next.js + Tailwind
- 后端：Python FastAPI
- PDF：PyMuPDF + pdfplumber（表格扩展 camelot/tabula）
- 测试：pytest（后端）、Playwright（前端）；类型：mypy；lint：ruff

## 目录结构（目标）
/app (Next.js)  
/api (FastAPI)  
/engine (解析与规则执行)  
/rules (YAML 规则；默认 v3_3.yaml)  
/tests (pytest)  
/e2e (Playwright)

## 基本命令（目标）
- 后端：`uv venv && uv pip install -r api/requirements.txt`；`uvicorn api.main:app --reload`
- 前端：`npm i`；`npm run dev`
- 一键：`make dev`（前后端并行）、`make test`（单测+E2E）

## 验收标准（必须全部满足）
1. 支持上传本地 PDF 与输入链接；解析封面/目录，定位“九张表”页码。
2. 执行 `rules/v3_3.yaml` 中的规则，产出问题列表（字段：规则编号/标题/证据页码/截图 bbox/命中片段/建议）。
3. 勾稽示例：`支出合计 = 结余分配 + 年末结转和结余 + 本年支出合计` 可校验并定位到证据。
4. 同比/口径差异有阈值与白名单，误报率 < 5%（以样例 PDF 为准）。
5. 导出 CSV/JSON 与标注版 PDF（红框标注问题位置）。
6. `make test` 全绿：至少 3 个后端单测 + 1 个前端 E2E。
7. 提交规范：Conventional Commits；pre-commit 含 black/ruff/mypy/pytest。

## 首任务（请 Codex 先完成）
- 按上文创建最小可运行脚手架（前后端 + 引擎占位 + 规则样例 + 测试与脚本）。
- 完成后在报告中附运行/测试日志与下一步建议。

