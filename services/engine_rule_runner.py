"""
引擎规则运行器
封装现有的 engine/rules_v33，统一输出格式为 IssueItem
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from engine.rules_v33 import ALL_RULES, Document, Issue, build_document
from schemas.issues import AnalysisConfig, IssueItem, JobContext

logger = logging.getLogger(__name__)


@dataclass
class EngineRuleResult:
    """引擎规则执行结果"""

    rule_id: str
    success: bool
    findings: List[IssueItem]
    why_not: Optional[str] = None
    elapsed_ms: int = 0


class EngineRuleRunner:
    """引擎规则运行器"""

    def __init__(self):
        self._stats = {
            "total_rules": 0,
            "successful_rules": 0,
            "failed_rules": 0,
            "total_findings": 0,
        }

    async def run_rules(
        self, job_context: JobContext, rules: List[Dict[str, Any]], config: AnalysisConfig
    ) -> List[IssueItem]:
        """
        运行引擎规则检查

        Args:
            job_context: 作业上下文
            rules: 引擎规则列表
            config: 分析配置

        Returns:
            List[IssueItem]: 检查结果列表
        """
        if not rules:
            logger.info("No engine rules to execute")
            return []

        logger.info(f"Running {len(rules)} engine rules for job {job_context.job_id}")

        # 准备文档对象
        document = await self._prepare_document(job_context)

        all_findings = []
        self._stats["total_rules"] = len(rules)
        per_rule_details = []

        for rule in rules:
            rule_id = rule.get("id") or rule.get("code") or "unknown"

            try:
                start_time = time.time()

                # 执行规则
                result = await self._execute_rule(
                    rule=rule, document=document, job_context=job_context, config=config
                )

                result.elapsed_ms = int((time.time() - start_time) * 1000)

                if result.success:
                    self._stats["successful_rules"] += 1
                    all_findings.extend(result.findings)
                    self._stats["total_findings"] = self._stats.get("total_findings", 0) + len(
                        result.findings
                    )
                    per_rule_details.append(
                        {
                            "rule_id": rule_id,
                            "success": True,
                            "findings": len(result.findings),
                            "elapsed_ms": result.elapsed_ms,
                        }
                    )
                    logger.debug(f"Rule {rule_id} found {len(result.findings)} issues")
                else:
                    self._stats["failed_rules"] += 1
                    per_rule_details.append(
                        {
                            "rule_id": rule_id,
                            "success": False,
                            "why_not": result.why_not,
                            "elapsed_ms": result.elapsed_ms,
                        }
                    )
                    logger.debug(f"Rule {rule_id} failed: {result.why_not}")

            except Exception as e:
                self._stats["failed_rules"] += 1
                logger.error(f"Rule {rule_id} execution failed: {e}")

                # 创建失败记录（按新 IssueItem 模型）
                if config.record_rule_failures:
                    page_number = 1
                    location = {"page": page_number}
                    failure_item = IssueItem(
                        id=IssueItem.create_id("rule", rule_id, location),
                        source="rule",
                        rule_id=rule_id,
                        severity="low",
                        title=f"规则执行失败: {rule.get('title', rule_id)}",
                        message=f"规则执行过程中发生错误: {str(e)}",
                        evidence=[{"text_snippet": f"执行错误: {str(e)}"}],
                        location=location,
                        page_number=page_number,
                        why_not=f"EXECUTION_ERROR: {str(e)}",
                    )
                    all_findings.append(failure_item)

        # 若本轮全部未命中，则回退执行 ALL_RULES，避免命名不一致造成全空
        fallback_all = False
        if self._stats.get("successful_rules", 0) == 0:
            fallback_all = True
            logger.warning("No engine rules matched; falling back to execute ALL_RULES")
            for r in ALL_RULES:
                try:
                    issues = r.apply(document)
                    if issues:
                        for issue in issues:
                            if isinstance(issue, Issue):
                                pseudo_rule = {
                                    "code": r.code,
                                    "title": getattr(issue, "title", r.code),
                                    "description": getattr(issue, "description", ""),
                                }
                                finding = self._convert_issue_to_item(
                                    issue=issue, rule=pseudo_rule, job_context=job_context
                                )
                                all_findings.append(finding)
                        self._stats["successful_rules"] += 1
                        self._stats["total_findings"] = self._stats.get("total_findings", 0) + len(
                            issues
                        )
                        per_rule_details.append(
                            {
                                "rule_id": r.code,
                                "success": True,
                                "findings": len(issues),
                                "elapsed_ms": 0,
                                "fallback": True,
                            }
                        )
                    else:
                        per_rule_details.append(
                            {
                                "rule_id": r.code,
                                "success": True,
                                "findings": 0,
                                "elapsed_ms": 0,
                                "fallback": True,
                                "why_not": "NO_ISSUES_FOUND",
                            }
                        )
                except Exception as fe:
                    self._stats["failed_rules"] += 1
                    per_rule_details.append(
                        {
                            "rule_id": r.code,
                            "success": False,
                            "fallback": True,
                            "why_not": f"FALLBACK_EXECUTION_ERROR: {str(fe)}",
                        }
                    )

        logger.info(
            f"Engine rules completed: {len(all_findings)} findings from {len(rules)} rules "
            f"(success: {self._stats['successful_rules']}, failed: {self._stats['failed_rules']})"
        )

        # 写入诊断信息到 uploads/<job_id>/diag.json（包含 per_rule 和回退标记）
        try:
            import json
            import os
            from pathlib import Path

            upload_root = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
            job_dir = upload_root / job_context.job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            diag = {
                "job_id": job_context.job_id,
                "received_rules": [r.get("id") or r.get("code") or "unknown" for r in rules],
                "stats": self._stats,
                "findings_count": len(all_findings),
                "document_hint": {
                    "pages": job_context.pages,
                    "ocr_text_len": len(job_context.ocr_text or ""),
                    "tables_count": len(job_context.tables or []),
                },
                "per_rule": per_rule_details,
                "fallback_all_rules": fallback_all,
                "timestamp": time.time(),
            }
            (job_dir / "diag.json").write_text(
                json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as diag_err:
            logger.debug(f"Write diag.json failed: {diag_err}")

        return all_findings

    async def _prepare_document(self, job_context: JobContext) -> Document:
        """准备文档对象"""

        # 加载表格数据
        tables = {}
        if job_context.tables:
            for table in job_context.tables:
                table_id = table.get("table_id", f"table_{table.get('page', 1)}")
                tables[table_id] = table.get("data", [])
        else:
            # 如果没有表格数据，使用空字典
            logger.warning("No table data available, using empty tables")
            tables = {}

        # 使用 build_document 函数创建文档对象
        try:
            # 优先使用 meta 中的按页文本与表格
            meta = job_context.meta or {}
            meta_page_texts = meta.get("page_texts")
            meta_page_tables = meta.get("page_tables")

            # 准备页面文本
            if isinstance(meta_page_texts, list) and len(meta_page_texts) > 0:
                page_texts = meta_page_texts
            else:
                # 回退：将整份文本简单按页复制（不理想，但保证不崩）
                page_texts = [job_context.ocr_text or ""] * (job_context.pages or 1)

            # 准备页面表格
            if isinstance(meta_page_tables, list) and len(meta_page_tables) > 0:
                page_tables = meta_page_tables
            else:
                # 从 JobContext.tables 聚合到每页
                total_pages = len(page_texts) if page_texts else (job_context.pages or 1)
                page_tables = [[] for _ in range(total_pages)]
                if job_context.tables:
                    for tb in job_context.tables:
                        try:
                            p = int(tb.get("page", 1)) - 1
                            if 0 <= p < total_pages:
                                data = tb.get("data", [])
                                if data:
                                    page_tables[p].append(data)
                        except Exception:
                            continue

            # 使用 build_document 函数
            document = build_document(
                path=job_context.pdf_path,
                page_texts=page_texts,
                page_tables=page_tables,
                filesize=getattr(job_context, "filesize", 0) or 0,
            )
        except Exception as e:
            logger.error(f"Failed to build document: {e}")
            # 创建一个最小的文档对象，使用正确的参数
            document = Document(path=job_context.pdf_path)

        return document

    def _normalize_rule_code(self, code: str) -> str:
        """
        将外部规则代码规范化到引擎代码：
        - R001 -> V33-001
        - R014 -> V33-014
        其他不匹配形态保持原样
        """
        try:
            if (
                isinstance(code, str)
                and code.startswith("R")
                and len(code) == 4
                and code[1:].isdigit()
            ):
                return f"V33-{int(code[1:]):03d}"
        except Exception:
            pass
        return code

    async def _execute_rule(
        self,
        rule: Dict[str, Any],
        document: Document,
        job_context: JobContext,
        config: AnalysisConfig,
    ) -> EngineRuleResult:
        """执行单个规则"""

        start_time = time.time()
        rule_id = rule.get("id") or rule.get("code") or "unknown"

        try:
            # 查找对应的规则对象（先做代码规范化映射）
            rule_obj = None
            raw_code = rule.get("code") or rule_id
            code_to_match = self._normalize_rule_code(raw_code)
            for r in ALL_RULES:
                if r.code == code_to_match or code_to_match in r.code:
                    rule_obj = r
                    break

            if rule_obj is None:
                return EngineRuleResult(
                    rule_id=rule_id,
                    success=False,
                    findings=[],
                    why_not=f"NO_RULE: Rule object not found for {rule_id}",
                    elapsed_ms=int((time.time() - start_time) * 1000),
                )

            # 执行规则
            issues = rule_obj.apply(document)

            # 转换为 IssueItem 格式
            findings = []

            if issues:
                for issue in issues:
                    if isinstance(issue, Issue):
                        finding = self._convert_issue_to_item(
                            issue=issue, rule=rule, job_context=job_context
                        )
                        findings.append(finding)
                    else:
                        logger.warning(f"Rule {rule_id} returned non-Issue object: {type(issue)}")

            # 应用容差设置
            if rule.get("tolerance") and findings:
                findings = self._apply_tolerance(findings, rule["tolerance"])

            elapsed_ms = int((time.time() - start_time) * 1000)

            return EngineRuleResult(
                rule_id=rule_id,
                success=True,
                findings=findings,
                why_not=None if findings else "NO_ISSUES_FOUND",
                elapsed_ms=elapsed_ms,
            )

        except Exception as e:
            # 分析失败原因
            why_not = self._analyze_failure_reason(e, rule_id)
            elapsed_ms = int((time.time() - start_time) * 1000)

            return EngineRuleResult(
                rule_id=rule_id, success=False, findings=[], why_not=why_not, elapsed_ms=elapsed_ms
            )

    def _convert_issue_to_item(
        self, issue: Issue, rule: Dict[str, Any], job_context: JobContext
    ) -> IssueItem:
        """将 Issue 对象转换为 IssueItem（符合 schemas.IssueItem）"""
        rule_id = rule.get("id") or rule.get("code", "unknown")
        # 页码
        page_number = getattr(issue, "page_number", 1)
        if not isinstance(page_number, int) or page_number < 1:
            page_number = 1
        # 文本与证据
        text_snippet = (
            getattr(issue, "evidence_text", "")
            or getattr(issue, "description", "")
            or getattr(issue, "title", "")
        )
        # 若证据为空，尝试从对应页文本回填一段摘要
        if not text_snippet:
            try:
                meta = getattr(job_context, "meta", {}) or {}
                pts = meta.get("page_texts")
                if (
                    isinstance(pts, list)
                    and isinstance(page_number, int)
                    and 1 <= page_number <= len(pts)
                ):
                    candidate = (pts[page_number - 1] or "").strip()
                    if candidate:
                        text_snippet = candidate[:200]
            except Exception:
                pass
        bbox = getattr(issue, "bbox", None)
        evidence_item = {"text_snippet": text_snippet}
        if bbox:
            evidence_item["bbox"] = bbox
        evidence_list = [evidence_item] if evidence_item else []
        location = {"page": page_number}
        # 严重程度映射
        severity = getattr(issue, "severity", "medium")
        if severity not in ["info", "low", "medium", "high", "critical"]:
            severity = "medium"
        # 数值与标签
        amount = getattr(issue, "amount", None)
        percentage = getattr(issue, "percentage", None)
        tags = getattr(issue, "tags", []) or []
        if isinstance(tags, str):
            tags = [tags]
        # 标题与消息
        title = getattr(issue, "title", "") or rule.get("title", "未知问题")
        message = (
            getattr(issue, "description", "")
            or rule.get("description", "")
            or text_snippet
            or title
        )
        # 唯一ID
        issue_id = IssueItem.create_id("rule", rule_id, location)
        return IssueItem(
            id=issue_id,
            source="rule",
            rule_id=rule_id,
            severity=severity,
            title=title,
            message=message,
            evidence=evidence_list,
            location=location,
            page_number=page_number,
            bbox=bbox,
            amount=amount,
            percentage=percentage,
            tags=tags,
        )

    def _apply_tolerance(
        self, findings: List[IssueItem], tolerance: Dict[str, Any]
    ) -> List[IssueItem]:
        """应用容差设置过滤结果"""

        filtered_findings = []

        money_rel = tolerance.get("money_rel", 0.005)  # 默认 0.5%
        pct_abs = tolerance.get("pct_abs", 0.002)  # 默认 0.2pp

        for finding in findings:
            should_include = True

            # 金额容差检查
            if finding.amount is not None and money_rel > 0:
                # 这里需要根据具体的业务逻辑实现容差检查
                # 暂时保留所有金额相关的问题
                pass

            # 比例容差检查
            if finding.percentage is not None and pct_abs > 0:
                # 这里需要根据具体的业务逻辑实现容差检查
                # 暂时保留所有比例相关的问题
                pass

            if should_include:
                filtered_findings.append(finding)
            else:
                # 更新 why_not 说明被容差过滤
                finding.why_not = f"TOLERANCE_FILTERED: money_rel={money_rel}, pct_abs={pct_abs}"

        return filtered_findings

    def _analyze_failure_reason(self, error: Exception, rule_id: str) -> str:
        """分析失败原因"""

        error_str = str(error).lower()

        if "anchor" in error_str or "找不到" in error_str:
            return f"NO_ANCHOR: {str(error)}"
        elif "table" in error_str or "表格" in error_str:
            return f"TABLE_PARSE_FAIL: {str(error)}"
        elif "unit" in error_str or "单位" in error_str:
            return f"UNIT_MISMATCH: {str(error)}"
        elif "tolerance" in error_str or "容差" in error_str:
            return f"TOLERANCE_FAIL: {str(error)}"
        elif "keyerror" in error_str or "key" in error_str:
            return f"MISSING_DATA: {str(error)}"
        elif "valueerror" in error_str or "value" in error_str:
            return f"DATA_FORMAT_ERROR: {str(error)}"
        else:
            return f"UNKNOWN_ERROR: {str(error)}"

    def get_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        return self._stats.copy()

    def clear_stats(self):
        """清除统计信息"""
        self._stats = {
            "total_rules": 0,
            "successful_rules": 0,
            "failed_rules": 0,
            "total_findings": 0,
        }


# 便捷函数
async def run_engine_rules(
    job_context: JobContext, rules: List[Dict[str, Any]], config: Optional[AnalysisConfig] = None
) -> List[IssueItem]:
    """便捷的引擎规则运行函数"""
    if config is None:
        from schemas.issues import AnalysisConfig

        config = AnalysisConfig()

    runner = EngineRuleRunner()
    return await runner.run_rules(job_context, rules, config)


def get_available_rules() -> List[str]:
    """获取可用的规则列表"""
    return [rule.code for rule in ALL_RULES]


def validate_rule_id(rule_id: str) -> bool:
    """验证规则ID是否有效"""
    return any(rule.code == rule_id or rule_id in rule.code for rule in ALL_RULES)
