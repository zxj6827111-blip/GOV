# CLEANUP PLAN

> 依据 `scripts/find_orphans.py`（扫描 `api/`, `engine/`, `services/`, `rules/`）与 `git grep` 结果整理。`ReferencedBy` 统计指静态引用次数，`0` 表示未被其他模块 import。

| Path | Why | ReferencedBy | Action | Risk |
| --- | --- | --- | --- | --- |
| `quick_test.py` | 手工联调脚本，未在包内引用，功能已由正式 API 覆盖。 | 0（self-call only） | move → `scripts/legacy/quick_test.py` | Low |
| `debug_dual_mode.py` | 早期调试 Dual 模式的脚本，未被服务引用。 | 0（self-call only） | move → `scripts/legacy/debug_dual_mode.py` | Low |
| `debug_job_status.py` | 手工轮询 job 状态脚本，未被服务引用。 | 0（self-call only） | move → `scripts/legacy/debug_job_status.py` | Low |
| `monitor_analysis.py` | CLI 监控脚本，依赖旧日志格式，未被其他模块 import。 | 0（self-call only） | move → `scripts/legacy/monitor_analysis.py` | Low |
| `show_expected_result.py` | 演示脚本，打印静态样例结果，未被生产代码使用。 | 0（self-call only） | move → `scripts/legacy/show_expected_result.py` | Low |
| `check_ai_detection.py` | 一次性检测脚本，功能已由 `/api/debug` 系列接口覆盖。 | 0（self-call only） | move → `scripts/legacy/check_ai_detection.py` | Low |
| `reports/alignment_*.md` | 自动生成的比对报告样例，未被程序读取，可按需再生成。 | 0（未被引用） | delete | Low |
| `engine/hybrid_pipeline.py` | find_orphans 标记为未引用，可能为下一版混合引擎预研代码。 | 0 | keep（待产品确认是否下线） | Medium |
| `engine/core_rules_engine.py` | 老版规则引擎实现，未被现有服务 import。 | 0 | keep（待确认是否可替换） | Medium |
| `engine/v33_ruleset_loader.py` | 历史版本规则加载器，未被现有入口调用。 | 0 | keep（需确认是否仍需兼容 v3.3） | Medium |
| `engine/table_alias_matcher.py` | mypy 检测语法错误（第 111 行），且无引用，疑似废弃。 | 0 | keep（建议后续修复或下线） | Medium |
| `services/ai_rule_runner.py` | 旧版 AI 规则执行器，新 orchestrator 未 import。 | 0 | keep（待业务确认） | Medium |
| `services/performance_monitor.py` | 性能监控工具模块未被引用，可能由外部脚本调用。 | 0 | keep（调查监控链路） | Medium |
| `services/rule_findings.py` | find_orphans 显示无引用，功能被 `services/analyze_dual.py` 内联。 | 0 | keep（建议确认后再下线） | Medium |
| `services/structured_logging.py` | 结构化日志模块未被引用，但可能供外部脚本使用。 | 0 | keep（确认日志需求） | Medium |
| `services/text_extractor.py` | 文本抽取工具未被 import，可能用于手动诊断。 | 0 | keep（建议迁移到 utils 或 legacy） | Medium |

> 处理顺序建议：先将 6 个一次性脚本迁移到 `scripts/legacy/`；确认无依赖后删除 `reports/alignment_*.md`；其余核心模块待产品/研发确认后再定去留。
