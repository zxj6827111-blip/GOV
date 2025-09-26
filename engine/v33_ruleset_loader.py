"""
V3.3规则集加载器和验证器
支持多文档YAML规则加载、Profile筛选、规则验证
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from engine.robust_number_parser import RobustNumberParser
from engine.table_name_matcher import TableNameMatcher

logger = logging.getLogger(__name__)


@dataclass
class RuleDefinition:
    """规则定义数据类"""

    id: str
    name: str
    desc: str
    profile: List[str]
    severity: str
    inputs: Dict[str, Any]
    logic: str
    evidence: Dict[str, Any]

    def matches_profile(self, target_profile: str) -> bool:
        """检查规则是否匹配指定的Profile"""
        return target_profile in self.profile or not self.profile


@dataclass
class RulesetMetadata:
    """规则集元数据"""

    version: str
    generated_at: str
    description: str
    profiles: List[str]
    authors: List[str]
    changelog: List[str]


@dataclass
class TableAlias:
    """表格别名配置"""

    standard_name: str
    aliases: List[str]
    keywords: List[str]
    required: bool


class V33RulesetLoader:
    """V3.3规则集加载器"""

    def __init__(self, rules_file: str = "rules/v3_3_all_in_one.yaml"):
        """
        初始化规则集加载器

        Args:
            rules_file: 规则文件路径
        """
        self.rules_file = Path(rules_file)
        self.metadata: Optional[RulesetMetadata] = None
        self.table_aliases: Dict[str, TableAlias] = {}
        self.rules: Dict[str, RuleDefinition] = {}
        self.global_config: Dict[str, Any] = {}

        # 集成现有组件
        self.table_matcher = TableNameMatcher()
        self.number_parser = RobustNumberParser()

    def load_ruleset(self) -> bool:
        """
        加载规则集

        Returns:
            加载是否成功
        """
        try:
            if not self.rules_file.exists():
                logger.error(f"规则文件不存在: {self.rules_file}")
                return False

            with open(self.rules_file, "r", encoding="utf-8") as f:
                # 使用safe_load_all处理多文档YAML
                docs = list(yaml.safe_load_all(f))
                
            if not docs:
                logger.error("YAML文件为空")
                return False
                
            # 合并所有文档的数据
            merged_data = {}
            for doc in docs:
                if isinstance(doc, dict):
                    merged_data.update(doc)

            # 加载元数据
            self._load_metadata(merged_data.get("meta", {}))

            # 加载表格别名
            self._load_table_aliases(merged_data.get("tables_aliases", {}))

            # 加载检查规则
            self._load_rules(merged_data.get("checks", []))

            # 加载全局配置
            self._load_global_config(merged_data.get("global_config", {}))

            logger.info(f"规则集加载成功: {len(self.rules)} 条规则")
            return True

        except Exception as e:
            logger.error(f"规则集加载失败: {e}")
            return False

    def _load_metadata(self, meta_data: Dict[str, Any]):
        """加载元数据"""
        self.metadata = RulesetMetadata(
            version=meta_data.get("version", "unknown"),
            generated_at=meta_data.get("generated_at", ""),
            description=meta_data.get("description", ""),
            profiles=meta_data.get("profiles", []),
            authors=meta_data.get("authors", []),
            changelog=meta_data.get("changelog", []),
        )

    def _load_table_aliases(self, aliases_data: Dict[str, Any]):
        """加载表格别名配置"""
        for table_name, config in aliases_data.items():
            self.table_aliases[table_name] = TableAlias(
                standard_name=config.get("standard_name", table_name),
                aliases=config.get("aliases", []),
                keywords=config.get("keywords", []),
                required=config.get("required", True),
            )

        logger.info(f"加载了 {len(self.table_aliases)} 个表格别名配置")

    def _load_rules(self, rules_data: List[Dict[str, Any]]):
        """加载检查规则"""
        for rule_data in rules_data:
            rule = RuleDefinition(
                id=rule_data.get("id", ""),
                name=rule_data.get("name", ""),
                desc=rule_data.get("desc", ""),
                profile=rule_data.get("profile", []),
                severity=rule_data.get("severity", "info"),
                inputs=rule_data.get("inputs", {}),
                logic=rule_data.get("logic", ""),
                evidence=rule_data.get("evidence", {}),
            )

            self.rules[rule.id] = rule

        logger.info(f"加载了 {len(self.rules)} 条检查规则")

    def _load_global_config(self, config_data: Dict[str, Any]):
        """加载全局配置"""
        self.global_config = config_data
        logger.info("全局配置加载完成")

    def get_rules_by_profile(self, profile: str) -> List[RuleDefinition]:
        """
        根据Profile获取规则列表

        Args:
            profile: 目标Profile名称

        Returns:
            匹配的规则列表
        """
        matching_rules = []
        for rule in self.rules.values():
            if rule.matches_profile(profile):
                matching_rules.append(rule)

        logger.info(f"Profile '{profile}' 匹配到 {len(matching_rules)} 条规则")
        return matching_rules

    def get_required_tables(self) -> List[str]:
        """获取必需表格列表"""
        required_tables = []
        for alias_config in self.table_aliases.values():
            if alias_config.required:
                required_tables.append(alias_config.standard_name)

        return required_tables

    def find_table_by_alias(self, text: str) -> Optional[str]:
        """
        通过别名查找标准表格名称

        Args:
            text: 输入文本

        Returns:
            匹配的标准表格名称
        """
        # 优先精确匹配
        for standard_name, alias_config in self.table_aliases.items():
            if standard_name in text:
                return standard_name

            for alias in alias_config.aliases:
                if alias in text:
                    return standard_name

        # 关键词匹配
        for standard_name, alias_config in self.table_aliases.items():
            keyword_matches = 0
            for keyword in alias_config.keywords:
                if keyword in text:
                    keyword_matches += 1

            # 如果匹配了大部分关键词，认为匹配
            if keyword_matches >= len(alias_config.keywords) * 0.6:
                return standard_name

        return None

    def validate_ruleset(self) -> List[str]:
        """
        验证规则集的完整性和正确性

        Returns:
            验证错误列表
        """
        errors = []

        # 检查元数据
        if not self.metadata:
            errors.append("缺少元数据信息")
        elif not self.metadata.version:
            errors.append("元数据中缺少版本信息")

        # 检查表格别名
        if not self.table_aliases:
            errors.append("缺少表格别名配置")
        else:
            required_tables = ["一般公共预算收入表", "一般公共预算支出表", "一般公共预算本级支出表"]
            for required_table in required_tables:
                if required_table not in self.table_aliases:
                    errors.append(f"缺少必需表格配置: {required_table}")

        # 检查规则
        if not self.rules:
            errors.append("缺少检查规则")
        else:
            for rule_id, rule in self.rules.items():
                if not rule.id:
                    errors.append(f"规则缺少ID: {rule_id}")
                if not rule.name:
                    errors.append(f"规则缺少名称: {rule_id}")
                if rule.severity not in ["error", "warning", "info"]:
                    errors.append(f"规则严重性级别无效: {rule_id} - {rule.severity}")
                if not rule.logic:
                    errors.append(f"规则缺少逻辑定义: {rule_id}")

        # 检查全局配置
        if not self.global_config:
            errors.append("缺少全局配置")
        elif "tolerance" not in self.global_config:
            errors.append("全局配置中缺少容差设置")

        if errors:
            logger.warning(f"规则集验证发现 {len(errors)} 个问题")
        else:
            logger.info("规则集验证通过")

        return errors

    def get_tolerance_config(self) -> Dict[str, Any]:
        """获取容差配置"""
        return self.global_config.get(
            "tolerance",
            {
                "default_relative": 0.005,
                "default_absolute": 1,
                "currency_units": {"元": 1, "万元": 10000, "亿元": 100000000},
            },
        )

    def get_evidence_config(self) -> Dict[str, Any]:
        """获取证据配置"""
        return self.global_config.get(
            "evidence",
            {
                "max_snippet_length": 200,
                "screenshot_format": "png",
                "screenshot_quality": 85,
                "context_padding": 50,
            },
        )

    def export_rule_summary(self) -> Dict[str, Any]:
        """导出规则集摘要"""
        return {
            "metadata": {
                "version": self.metadata.version if self.metadata else "unknown",
                "profiles": self.metadata.profiles if self.metadata else [],
                "rule_count": len(self.rules),
                "table_count": len(self.table_aliases),
            },
            "rules_by_severity": {
                "error": len([r for r in self.rules.values() if r.severity == "error"]),
                "warning": len([r for r in self.rules.values() if r.severity == "warning"]),
                "info": len([r for r in self.rules.values() if r.severity == "info"]),
            },
            "profiles_available": list(
                set(profile for rule in self.rules.values() for profile in rule.profile)
            ),
            "required_tables": self.get_required_tables(),
        }


class V33RuleExecutor:
    """V3.3规则执行器"""

    def __init__(self, loader: V33RulesetLoader):
        """
        初始化规则执行器

        Args:
            loader: 规则集加载器
        """
        self.loader = loader
        self.tolerance_config = loader.get_tolerance_config()
        self.evidence_config = loader.get_evidence_config()

    def execute_rule(self, rule: RuleDefinition, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个规则

        Args:
            rule: 规则定义
            document_data: 文档数据

        Returns:
            执行结果
        """
        try:
            result = {
                "rule_id": rule.id,
                "rule_name": rule.name,
                "severity": rule.severity,
                "status": "success",
                "findings": [],
                "evidence": [],
                "execution_time": 0,
            }

            start_time = datetime.now()

            # 根据规则ID调用对应的执行方法
            if rule.id == "V33-001":
                findings = self._execute_toc_consistency(rule, document_data)
            elif rule.id == "V33-002":
                findings = self._execute_table_completeness(rule, document_data)
            elif rule.id == "V33-003":
                findings = self._execute_balance_equation(rule, document_data)
            elif rule.id in ["V33-004", "V33-005", "V33-006"]:
                findings = self._execute_amount_consistency(rule, document_data)
            elif rule.id == "V33-007":
                findings = self._execute_year_consistency(rule, document_data)
            elif rule.id == "V33-008":
                findings = self._execute_format_consistency(rule, document_data)
            elif rule.id == "V33-009":
                findings = self._execute_text_number_diff(rule, document_data)
            elif rule.id == "V33-010":
                findings = self._execute_missing_location(rule, document_data)
            else:
                findings = []
                logger.warning(f"未实现的规则: {rule.id}")

            result["findings"] = findings
            result["execution_time"] = (datetime.now() - start_time).total_seconds()

            logger.debug(f"规则 {rule.id} 执行完成，发现 {len(findings)} 个问题")
            return result

        except Exception as e:
            logger.error(f"规则 {rule.id} 执行失败: {e}")
            return {
                "rule_id": rule.id,
                "rule_name": rule.name,
                "severity": rule.severity,
                "status": "error",
                "error_message": str(e),
                "findings": [],
                "evidence": [],
                "execution_time": 0,
            }

    def _execute_toc_consistency(
        self, rule: RuleDefinition, document_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行目录一致性检查"""
        # 具体实现逻辑
        findings = []
        # TODO: 实现目录一致性检查逻辑
        return findings

    def _execute_table_completeness(
        self, rule: RuleDefinition, document_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行表格完整性检查"""
        findings = []

        pages_text = document_data.get("pages_text", [])
        required_tables = self.loader.get_required_tables()
        found_tables = set()

        # 检查每页文本
        for _page_no, page_text in enumerate(pages_text, 1):
            for _table_name in required_tables:
                matched_table = self.loader.find_table_by_alias(page_text)
                if matched_table:
                    found_tables.add(matched_table)

        # 找出缺失的表格
        missing_tables = set(required_tables) - found_tables
        for missing_table in missing_tables:
            findings.append(
                {
                    "type": "missing_table",
                    "message": f"缺失必要表格: {missing_table}",
                    "table_name": missing_table,
                    "severity": rule.severity,
                }
            )

        return findings

    def _execute_balance_equation(
        self, rule: RuleDefinition, document_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行总表恒等式检查"""
        # TODO: 实现恒等式检查逻辑
        return []

    def _execute_amount_consistency(
        self, rule: RuleDefinition, document_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行金额一致性检查"""
        # TODO: 实现金额一致性检查逻辑
        return []

    def _execute_year_consistency(
        self, rule: RuleDefinition, document_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行年份一致性检查"""
        # TODO: 实现年份一致性检查逻辑
        return []

    def _execute_format_consistency(
        self, rule: RuleDefinition, document_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行格式一致性检查"""
        # TODO: 实现格式一致性检查逻辑
        return []

    def _execute_text_number_diff(
        self, rule: RuleDefinition, document_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行文本数字差异检查"""
        # TODO: 实现文本数字差异检查逻辑
        return []

    def _execute_missing_location(
        self, rule: RuleDefinition, document_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """执行缺章缺表定位"""
        # TODO: 实现缺章缺表定位逻辑
        return []


# 便捷函数
def load_v33_ruleset(rules_file: str = "rules/v3_3_all_in_one.yaml") -> Optional[V33RulesetLoader]:
    """
    加载V3.3规则集

    Args:
        rules_file: 规则文件路径

    Returns:
        规则集加载器实例
    """
    loader = V33RulesetLoader(rules_file)
    if loader.load_ruleset():
        return loader
    return None


def validate_v33_ruleset(rules_file: str = "rules/v3_3_all_in_one.yaml") -> List[str]:
    """
    验证V3.3规则集

    Args:
        rules_file: 规则文件路径

    Returns:
        验证错误列表
    """
    loader = V33RulesetLoader(rules_file)
    if loader.load_ruleset():
        return loader.validate_ruleset()
    return ["无法加载规则文件"]
