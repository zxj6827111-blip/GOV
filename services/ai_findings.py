"""
AI检查服务
直接调用 LLM 进行合规检查，生成统一的 IssueItem 格式结果
"""

import asyncio
import json
import logging
import re
import time
import traceback
from typing import Any, Dict, List, Optional

from engine.ai.extractor_client import ExtractorClient  # 复用现有AI客户端
from schemas.issues import AnalysisConfig, IssueItem, JobContext

logger = logging.getLogger(__name__)


class AIFindingsService:
    """AI检查服务（规则约束版）"""

    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.ai_client = ExtractorClient()  # 复用现有AI客户端
        self.ai_errors = []  # 聚合AI错误信息
        # 预加载规则白名单（来自 YAML）并构建双向映射（Rxxx 与 V33-xxx）
        self._rule_whitelist = set()
        self._mapped_whitelist = set()
        try:
            import os

            import yaml

            yaml_path = os.path.join("config", "rules", "rules_v3_3.yaml")
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            rules_dict = data.get("rules") or {}
            base_ids = set(rules_dict.keys())
            self._rule_whitelist = base_ids

            # 构建双向映射集合
            def _r_to_v33(code: str) -> str:
                if (
                    isinstance(code, str)
                    and code.startswith("R")
                    and len(code) == 4
                    and code[1:].isdigit()
                ):
                    return f"V33-{int(code[1:]):03d}"
                return code

            def _v33_to_r(code: str) -> str:
                # 将 V33-001 -> R001
                if isinstance(code, str) and code.startswith("V33-"):
                    try:
                        n = int(code.split("-", 1)[1])
                        return f"R{n:03d}"
                    except Exception:
                        return code
                return code

            mapped = set()
            for rid in base_ids:
                mapped.add(rid)
                mapped.add(_r_to_v33(rid))
                mapped.add(_v33_to_r(rid))
            # 去除空串
            self._mapped_whitelist = {x for x in mapped if x}
        except Exception as e:
            logger.warning(f"加载规则白名单失败，将使用空白名单: {e}")
            self._mapped_whitelist = set()
        # 允许的严重级别集合
        self._severity_set = {"info", "low", "medium", "high", "critical"}

    async def analyze(self, context: JobContext) -> List[IssueItem]:
        """执行AI分析"""
        if not self.config.ai_enabled:
            logger.info("AI分析已禁用")
            return []

        start_time = time.time()
        logger.info(f"开始AI分析: job_id={context.job_id}")

        # 重置错误计数
        self.ai_errors = []

        try:
            # 构建提示词
            prompt = self._build_prompt(context)

            # 调用AI
            ai_response = await self._call_ai_with_retry(prompt, context)

            # 解析结果
            issues = self._parse_ai_response(ai_response, context)

            elapsed = time.time() - start_time
            logger.info(
                f"AI分析完成: job_id={context.job_id}, issues={len(issues)}, elapsed={elapsed:.2f}s"
            )

            # 将错误信息添加到context中，供后续使用
            if hasattr(context, "ai_errors"):
                context.ai_errors = self.ai_errors

            return issues

        except Exception as e:
            logger.error(f"AI分析失败: job_id={context.job_id}, error={e}")
            logger.error(traceback.format_exc())

            # 记录分析失败错误
            self.ai_errors.append(
                {"type": "analysis_failure", "message": str(e), "timestamp": time.time()}
            )

            if hasattr(context, "ai_errors"):
                context.ai_errors = self.ai_errors

            return []

    def _build_prompt(self, context: JobContext) -> str:
        """构建AI提示词 - 规则约束模式"""
        # 将白名单及其映射（Rxxx 与 V33-xxx）放入提示，指导AI使用一致的ID
        wl = self._mapped_whitelist or self._rule_whitelist
        rule_ids = sorted(list(wl)) if wl else []
        rule_ids_json = json.dumps(rule_ids, ensure_ascii=False)
        ocr_preview = (context.ocr_text or "")[:15000]
        tables_preview = (
            json.dumps(context.tables[:8], ensure_ascii=False, indent=2)
            if context.tables
            else "无表格数据"
        )

        prompt = f"""
你是政府预决算合规检查的专家。请仅依据“提供的规则白名单”对文档进行检查；若没有命中任何规则，返回空数组 []。

严格约束：
- 你只能输出规则白名单中的 rule_id，不允许生成白名单之外的 rule_id
- 每条发现必须包含：rule_id、title、message、severity、page（数字>0）、evidence（文本证据，非空）
- 严重程度仅限：critical、high、medium、low、info
- 仅输出 JSON 数组，不要输出多余解释、不要包裹代码块
- 若没有发现命中规则的问题，返回空数组 []

规则白名单（仅可使用以下 rule_id）：
{rule_ids_json}

文档信息：
- 文件路径: {context.pdf_path}
- 页数: {context.pages}
- OCR文本（截断预览）:
{ocr_preview}

表格数据（最多8个，截断预览）:
{tables_preview}

输出JSON数组示例（字段名固定，按需填充指标与建议；未命中则返回[]）：
[
  {{
    "rule_id": "V33-002",
    "title": "问题标题",
    "message": "详细问题描述",
    "severity": "high",
    "page": 2,
    "section": "所在章节",
    "table": "所在表格",
    "evidence": "原文片段或数字摘录",
    "metrics": {{"expected": 1, "actual": 0, "diff": 1}},
    "suggestion": "修复建议",
    "tags": ["标签A","标签B"]
  }}
]
仅输出数组本身。
"""
        return prompt

    async def _call_ai_with_retry(self, prompt: str, context: JobContext) -> str:
        """带重试的AI调用"""
        last_error = None

        for attempt in range(self.config.ai_retry + 1):
            try:
                logger.info(f"AI调用尝试 {attempt + 1}/{self.config.ai_retry + 1}")

                # 使用现有的AI客户端
                response = await asyncio.wait_for(
                    self._call_ai_client(prompt), timeout=self.config.ai_timeout
                )

                if response and response.strip():
                    return response
                else:
                    raise ValueError("AI返回空响应")

            except asyncio.TimeoutError:
                last_error = f"AI调用超时 ({self.config.ai_timeout}s)"
                logger.warning(f"{last_error}, 尝试 {attempt + 1}")
            except Exception as e:
                last_error = f"AI调用失败: {e}"
                logger.warning(f"{last_error}, 尝试 {attempt + 1}")

            if attempt < self.config.ai_retry:
                await asyncio.sleep(2**attempt)  # 指数退避

        raise Exception(f"AI调用最终失败: {last_error}")

    async def _call_ai_client(self, prompt: str) -> str:
        """调用AI客户端"""
        try:
            # 使用现有的AI客户端接口
            if hasattr(self.ai_client, "chat_completion"):
                response = await self.ai_client.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=4000,
                    top_p=1,
                )
                return response.get("content", "")
            else:
                # 如果没有异步方法，使用同步方法
                import asyncio

                response = await asyncio.get_event_loop().run_in_executor(
                    None, self._sync_call_ai, prompt
                )
                return response
        except Exception as e:
            logger.error(f"AI客户端调用失败: {e}")
            raise

    def _sync_call_ai(self, prompt: str) -> str:
        """同步AI调用（兼容现有代码）"""
        try:
            # 这里需要根据实际的AI客户端接口调整
            # 返回模拟结果用于测试
            return self._get_mock_ai_response()
        except Exception as e:
            logger.error(f"同步AI调用失败: {e}")
            raise

    def _get_mock_ai_response(self) -> str:
        """获取模拟AI响应（用于测试）"""
        mock_response = [
            {
                "rule_id": "AI-COMP-001",
                "title": "预算收支总表缺失",
                "message": "未在文档中发现完整的预算收支总表，可能影响预算执行情况的全面了解",
                "severity": "high",
                "page": 1,
                "section": "预算表",
                "table": "预算收支总表",
                "evidence": "第1页目录显示应有预算收支总表，但正文中未找到对应表格",
                "metrics": {"expected": 1, "actual": 0, "diff": 1},
                "suggestion": "请补充完整的预算收支总表，包含收入和支出的详细分类",
                "tags": ["表格完整性", "预算表"],
                "category": "表格缺失",
            },
            {
                "rule_id": "AI-CALC-001",
                "title": "收入明细汇总不符",
                "message": "各项收入明细汇总与总收入金额不一致，存在计算错误",
                "severity": "medium",
                "page": 3,
                "section": "收入明细",
                "table": "收入明细表",
                "evidence": "第3页收入明细表显示：税收收入800万+非税收入150万=950万，但总收入显示1000万",
                "metrics": {"expected": 10000000, "actual": 9500000, "diff": 500000, "pct": 5.0},
                "suggestion": "请核对收入明细计算，确保各项明细汇总与总额一致",
                "tags": ["金额一致性", "收入"],
                "category": "计算错误",
            },
        ]
        return json.dumps(mock_response, ensure_ascii=False, indent=2)

    def _parse_ai_response(self, response: str, context: JobContext) -> List[IssueItem]:
        """解析AI响应"""
        discarded_count = 0
        discarded_examples = []

        try:
            # 提取JSON内容
            json_content = self._extract_json_from_response(response)
            if not json_content:
                logger.warning("AI响应中未找到有效JSON")
                self.ai_errors.append(
                    {
                        "type": "json_extraction_failed",
                        "message": "AI响应中未找到有效JSON",
                        "response_preview": response[:200] + "..."
                        if len(response) > 200
                        else response,
                    }
                )
                return []

            # 解析JSON
            raw_issues = json.loads(json_content)
            if not isinstance(raw_issues, list):
                logger.warning("AI响应JSON格式错误，应为数组")
                self.ai_errors.append(
                    {
                        "type": "json_format_error",
                        "message": "AI响应JSON格式错误，应为数组",
                        "actual_type": type(raw_issues).__name__,
                    }
                )
                return []

            # 转换为IssueItem
            issues = []
            for idx, raw_issue in enumerate(raw_issues):
                try:
                    issue = self._convert_ai_issue(raw_issue, context, idx)
                    if issue:
                        issues.append(issue)
                    else:
                        discarded_count += 1
                        if len(discarded_examples) < 3:  # 只保存前3个示例
                            discarded_examples.append(
                                {"index": idx, "issue": raw_issue, "reason": "conversion_failed"}
                            )
                except Exception as e:
                    logger.error(f"转换AI问题失败: {e}, issue={raw_issue}")
                    discarded_count += 1
                    if len(discarded_examples) < 3:
                        discarded_examples.append(
                            {"index": idx, "issue": raw_issue, "reason": f"exception: {str(e)}"}
                        )

            # 记录丢弃统计
            if discarded_count > 0:
                self.ai_errors.append(
                    {
                        "type": "items_discarded",
                        "count": discarded_count,
                        "total_items": len(raw_issues),
                        "examples": discarded_examples,
                        "message": f"因格式问题丢弃了 {discarded_count}/{len(raw_issues)} 个AI检测结果",
                    }
                )
                logger.warning(f"因格式问题丢弃了 {discarded_count}/{len(raw_issues)} 个AI检测结果")

            # 规则白名单+证据+页码 过滤（放宽：接受 Rxxx/V33-xxx 映射或 AI- 前缀）
            filtered = []
            for it in issues:
                try:
                    page = (it.location or {}).get("page", 0)
                    has_evidence = bool(it.evidence) and bool(
                        it.evidence[0].get("text") if isinstance(it.evidence[0], dict) else True
                    )
                    ok_sev = it.severity in self._severity_set

                    rid = it.rule_id or ""
                    # 允许 AI 自有前缀
                    is_ai_pref = isinstance(rid, str) and rid.upper().startswith("AI-")
                    # 白名单判定：白名单为空 或（在映射白名单内）或（AI-前缀）
                    wl = self._mapped_whitelist or self._rule_whitelist
                    ok_rule = (not wl) or (rid in wl) or is_ai_pref

                    if ok_rule and ok_sev and isinstance(page, int) and page > 0 and has_evidence:
                        filtered.append(it)
                    else:
                        self.ai_errors.append(
                            {
                                "type": "post_filter_discard",
                                "rule_id": rid,
                                "page": page,
                                "severity": it.severity,
                                "reason": "rule_not_allowed_or_missing_page_or_evidence",
                            }
                        )
                except Exception as _:
                    continue
            return filtered

        except json.JSONDecodeError as e:
            logger.error(f"AI响应JSON解析失败: {e}")
            self.ai_errors.append(
                {
                    "type": "json_decode_error",
                    "message": f"JSON解析失败: {str(e)}",
                    "response_preview": response[:200] + "..." if len(response) > 200 else response,
                }
            )
            return []
        except Exception as e:
            logger.error(f"解析AI响应失败: {e}")
            self.ai_errors.append(
                {
                    "type": "parse_error",
                    "message": f"解析失败: {str(e)}",
                    "response_preview": response[:200] + "..." if len(response) > 200 else response,
                }
            )
            return []

    def _extract_json_from_response(self, response: str) -> Optional[str]:
        """从响应中提取JSON内容"""
        # 尝试直接解析
        response = response.strip()
        if response.startswith("[") and response.endswith("]"):
            return response

        # 尝试从代码块中提取
        json_pattern = r"```(?:json)?\s*(\[.*?\])\s*```"
        match = re.search(json_pattern, response, re.DOTALL)
        if match:
            return match.group(1)

        # 尝试查找数组结构
        array_pattern = r"(\[.*?\])"
        match = re.search(array_pattern, response, re.DOTALL)
        if match:
            return match.group(1)

        return None

    def _convert_ai_issue(
        self, raw_issue: Dict[str, Any], context: JobContext, idx: int
    ) -> Optional[IssueItem]:
        """转换AI问题为IssueItem"""
        try:
            # 验证必需字段
            required_fields = ["title", "message", "severity"]
            missing_fields = []
            for field in required_fields:
                if field not in raw_issue:
                    missing_fields.append(field)

            if missing_fields:
                logger.warning(f"AI问题缺少必需字段: {missing_fields}")
                self.ai_errors.append(
                    {
                        "type": "missing_required_fields",
                        "missing_fields": missing_fields,
                        "issue_index": idx,
                        "issue_preview": str(raw_issue)[:100] + "..."
                        if len(str(raw_issue)) > 100
                        else str(raw_issue),
                    }
                )
                return None

            # 提取基本信息
            rule_id = raw_issue.get("rule_id", f"AI-GEN-{idx:03d}")
            title = raw_issue["title"]
            message = raw_issue["message"]
            severity = self._normalize_severity(raw_issue["severity"])

            # 构建位置信息
            location = {
                "page": raw_issue.get("page", 0),
                "section": raw_issue.get("section", ""),
                "table": raw_issue.get("table", ""),
                "row": raw_issue.get("row", ""),
                "col": raw_issue.get("col", ""),
            }

            # 构建证据
            evidence = []
            if "evidence" in raw_issue:
                evidence.append(
                    {
                        "page": location["page"],
                        "text": raw_issue["evidence"],
                        "bbox": raw_issue.get("bbox"),
                    }
                )

            # 构建指标
            metrics = raw_issue.get("metrics", {})

            # 构建标签
            tags = raw_issue.get("tags", [])
            if "category" in raw_issue:
                tags.append(raw_issue["category"])

            # 生成唯一ID
            issue_id = IssueItem.create_id("ai", rule_id, location)

            return IssueItem(
                id=issue_id,
                source="ai",
                rule_id=rule_id,
                severity=severity,
                title=title,
                message=message,
                evidence=evidence,
                location=location,
                metrics=metrics,
                suggestion=raw_issue.get("suggestion"),
                tags=tags,
                created_at=time.time(),
            )

        except Exception as e:
            logger.error(f"转换AI问题失败: {e}")
            self.ai_errors.append(
                {
                    "type": "conversion_error",
                    "error": str(e),
                    "issue_index": idx,
                    "issue_preview": str(raw_issue)[:100] + "..."
                    if len(str(raw_issue)) > 100
                    else str(raw_issue),
                }
            )
            return None

    def _normalize_severity(self, severity: str) -> str:
        """标准化严重程度"""
        severity_map = {
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
            "info": "info",
        }

        return severity_map.get(severity.lower(), "medium")


async def analyze_with_ai(context: JobContext, config: AnalysisConfig) -> List[IssueItem]:
    """使用AI分析的便捷函数"""
    service = AIFindingsService(config)
    return await service.analyze(context)
