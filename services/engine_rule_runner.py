"""
引擎规则运行器
封装现有的 engine/rules_v33，统一输出格式为 IssueItem
"""
import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from schemas.issues import JobContext, AnalysisConfig, IssueItem
from engine.rules_v33 import (
    ALL_RULES, build_document, Issue, Document
)

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
        }
    
    async def run_rules(self, 
                       job_context: JobContext,
                       rules: List[Dict[str, Any]],
                       config: AnalysisConfig) -> List[IssueItem]:
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
        
        for rule in rules:
            rule_id = rule.get('id', 'unknown')
            
            try:
                start_time = time.time()
                
                # 执行规则
                result = await self._execute_rule(
                    rule=rule,
                    document=document,
                    job_context=job_context,
                    config=config
                )
                
                result.elapsed_ms = int((time.time() - start_time) * 1000)
                
                if result.success:
                    self._stats["successful_rules"] += 1
                    all_findings.extend(result.findings)
                    self._stats["total_findings"] += len(result.findings)
                    
                    logger.debug(f"Rule {rule_id} found {len(result.findings)} issues")
                else:
                    self._stats["failed_rules"] += 1
                    logger.debug(f"Rule {rule_id} failed: {result.why_not}")
                
            except Exception as e:
                self._stats["failed_rules"] += 1
                logger.error(f"Rule {rule_id} execution failed: {e}")
                
                # 创建失败记录
                if config.record_rule_failures:
                    failure_item = IssueItem(
                        rule_id=rule_id,
                        title=f"规则执行失败: {rule.get('title', rule_id)}",
                        description=f"规则执行过程中发生错误: {str(e)}",
                        severity="low",
                        page_number=1,
                        evidence={"text_snippet": f"执行错误: {str(e)}"},
                        source="rule",
                        job_id=job_context.job_id,
                        why_not=f"EXECUTION_ERROR: {str(e)}"
                    )
                    all_findings.append(failure_item)
        
        logger.info(f"Engine rules completed: {len(all_findings)} findings from {len(rules)} rules "
                   f"(success: {self._stats['successful_rules']}, failed: {self._stats['failed_rules']})")
        
        return all_findings
    
    async def _prepare_document(self, job_context: JobContext) -> Document:
        """准备文档对象"""
        
        # 加载表格数据
        tables = {}
        if job_context.tables:
            for table in job_context.tables:
                table_id = table.get('table_id', f"table_{table.get('page', 1)}")
                tables[table_id] = table.get('data', [])
        else:
            # 如果没有表格数据，尝试从 PDF 加载
            try:
                tables = load_tables(job_context.pdf_path)
            except Exception as e:
                logger.warning(f"Failed to load tables from PDF: {e}")
                tables = {}
        
        # 创建文档对象
        document = Document(
            pdf_path=job_context.pdf_path,
            tables=tables,
            ocr_text=job_context.ocr_text or "",
            pages=job_context.pages or 1
        )
        
        return document
    
    async def _execute_rule(self, 
                           rule: Dict[str, Any],
                           document: Document,
                           job_context: JobContext,
                           config: AnalysisConfig) -> EngineRuleResult:
        """执行单个规则"""
        
        start_time = time.time()
        rule_id = rule.get('id', 'unknown')
        
        try:
            # 查找对应的规则对象
            rule_obj = None
            for r in ALL_RULES:
                if r.code == rule_id or rule_id in r.code:
                    rule_obj = r
                    break
            
            if rule_obj is None:
                return EngineRuleResult(
                    rule_id=rule_id,
                    success=False,
                    findings=[],
                    why_not=f"NO_RULE: Rule object not found for {rule_id}",
                    elapsed_ms=int((time.time() - start_time) * 1000)
                )
            
            # 执行规则
            issues = rule_obj.apply(document)
            
            # 转换为 IssueItem 格式
            findings = []
            
            if issues:
                for issue in issues:
                    if isinstance(issue, Issue):
                        finding = self._convert_issue_to_item(
                            issue=issue,
                            rule=rule,
                            job_context=job_context
                        )
                        findings.append(finding)
                    else:
                        logger.warning(f"Rule {rule_id} returned non-Issue object: {type(issue)}")
            
            # 应用容差设置
            if rule.get('tolerance') and findings:
                findings = self._apply_tolerance(findings, rule['tolerance'])
            
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            return EngineRuleResult(
                rule_id=rule_id,
                success=True,
                findings=findings,
                why_not=None if findings else "NO_ISSUES_FOUND",
                elapsed_ms=elapsed_ms
            )
            
        except Exception as e:
            # 分析失败原因
            why_not = self._analyze_failure_reason(e, rule_id)
            elapsed_ms = int((time.time() - start_time) * 1000)
            
            return EngineRuleResult(
                rule_id=rule_id,
                success=False,
                findings=[],
                why_not=why_not,
                elapsed_ms=elapsed_ms
            )
    
    def _convert_issue_to_item(self, 
                              issue: Issue,
                              rule: Dict[str, Any],
                              job_context: JobContext) -> IssueItem:
        """将 Issue 对象转换为 IssueItem"""
        
        # 提取证据信息
        evidence = {
            "text_snippet": getattr(issue, 'evidence_text', '') or getattr(issue, 'description', ''),
        }
        
        # 如果有坐标信息，添加 bbox
        if hasattr(issue, 'bbox') and issue.bbox:
            evidence["bbox"] = issue.bbox
        
        # 确定严重程度
        severity = getattr(issue, 'severity', 'medium')
        if severity not in ['high', 'medium', 'low']:
            severity = 'medium'
        
        # 提取金额和比例
        amount = getattr(issue, 'amount', None)
        percentage = getattr(issue, 'percentage', None)
        
        # 提取页码
        page_number = getattr(issue, 'page_number', 1)
        if not isinstance(page_number, int) or page_number < 1:
            page_number = 1
        
        # 提取标签
        tags = getattr(issue, 'tags', []) or []
        if isinstance(tags, str):
            tags = [tags]
        
        return IssueItem(
            rule_id=rule.get('id', 'unknown'),
            title=getattr(issue, 'title', '') or rule.get('title', '未知问题'),
            description=getattr(issue, 'description', '') or rule.get('description', ''),
            severity=severity,
            page_number=page_number,
            evidence=evidence,
            amount=amount,
            percentage=percentage,
            tags=tags,
            source="rule",
            job_id=job_context.job_id,
            why_not=None
        )
    
    def _apply_tolerance(self, 
                        findings: List[IssueItem], 
                        tolerance: Dict[str, Any]) -> List[IssueItem]:
        """应用容差设置过滤结果"""
        
        filtered_findings = []
        
        money_rel = tolerance.get('money_rel', 0.005)  # 默认 0.5%
        pct_abs = tolerance.get('pct_abs', 0.002)      # 默认 0.2pp
        
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
            "total_findings": 0
        }


# 便捷函数
async def run_engine_rules(job_context: JobContext,
                          rules: List[Dict[str, Any]],
                          config: Optional[AnalysisConfig] = None) -> List[IssueItem]:
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