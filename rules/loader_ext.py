"""
规则加载器扩展
在原 YAML 加载基础上兼容新字段，保持向后兼容性
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ToleranceConfig:
    """容差配置"""
    money_rel: float = 0.005  # 金额相对误差 0.5%
    pct_abs: float = 0.002    # 百分比绝对差 0.2pp
    page_tol: int = 1         # 页码容差


@dataclass
class EvidenceRequirement:
    """证据要求配置"""
    page_number: bool = True      # 需要页码
    text_snippet: bool = True     # 需要文本摘录
    bbox: bool = False           # 需要边界框（可选）
    amount: bool = False         # 需要金额信息
    percentage: bool = False     # 需要百分比信息


@dataclass
class ExtendedRule:
    """扩展规则定义"""
    # 原有字段
    code: str
    severity: str
    desc: str
    
    # 新增字段
    executor: str = "engine"  # ai | engine | both
    ai_prompt: Optional[str] = None
    evidence_requirements: EvidenceRequirement = field(default_factory=EvidenceRequirement)
    tolerance: ToleranceConfig = field(default_factory=ToleranceConfig)
    engine_hook: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    
    # 元数据
    enabled: bool = True
    priority: int = 100
    tags: List[str] = field(default_factory=list)
    category: str = "general"  # 规则分类
    
    # AI 相关配置
    ai_model: Optional[str] = None  # 指定AI模型
    ai_temperature: float = 0.1     # AI温度参数
    ai_max_tokens: int = 1000       # 最大token数
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'code': self.code,
            'severity': self.severity,
            'desc': self.desc,
            'executor': self.executor,
            'ai_prompt': self.ai_prompt,
            'evidence_requirements': {
                'page_number': self.evidence_requirements.page_number,
                'text_snippet': self.evidence_requirements.text_snippet,
                'bbox': self.evidence_requirements.bbox,
                'amount': self.evidence_requirements.amount,
                'percentage': self.evidence_requirements.percentage
            },
            'tolerance': {
                'money_rel': self.tolerance.money_rel,
                'pct_abs': self.tolerance.pct_abs,
                'page_tol': self.tolerance.page_tol
            },
            'engine_hook': self.engine_hook,
            'aliases': self.aliases,
            'enabled': self.enabled,
            'priority': self.priority,
            'tags': self.tags,
            'category': self.category,
            'ai_model': self.ai_model,
            'ai_temperature': self.ai_temperature,
            'ai_max_tokens': self.ai_max_tokens
        }


class RuleLoaderExt:
    """扩展规则加载器"""
    
    def __init__(self, rules_dir: str = None):
        self.rules_dir = rules_dir or os.path.join(os.path.dirname(__file__))
        self._cache: Dict[str, Any] = {}
    
    def load_yaml_rules(self, yaml_path: str) -> Dict[str, Any]:
        """加载 YAML 规则文件"""
        if yaml_path in self._cache:
            return self._cache[yaml_path]
        
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            self._cache[yaml_path] = data
            return data
        except Exception as e:
            raise RuntimeError(f"Failed to load YAML rules from {yaml_path}: {e}")
    
    def parse_extended_rules(self, yaml_data: Dict[str, Any]) -> List[ExtendedRule]:
        """解析扩展规则，支持新字段和向后兼容
        - 兼容 rules 为 dict 或 list
        - 同时支持 budget.rules / final_account.rules / decision.rules
        - 根级 rules 也兼容 dict/list
        """
        rules: List[ExtendedRule] = []
        
        # 处理预算规则
        if 'budget' in yaml_data and 'rules' in yaml_data['budget']:
            budget_rules = yaml_data['budget']['rules']
            if isinstance(budget_rules, dict):
                rules.extend(self._parse_rule_section(budget_rules, 'budget'))
            elif isinstance(budget_rules, list):
                rules.extend(self._parse_rule_list(budget_rules, 'budget'))
        
        # 处理决算规则（final_account 或 decision 别名）
        if 'final_account' in yaml_data and 'rules' in yaml_data['final_account']:
            final_rules = yaml_data['final_account']['rules']
            if isinstance(final_rules, dict):
                rules.extend(self._parse_rule_section(final_rules, 'final_account'))
            elif isinstance(final_rules, list):
                rules.extend(self._parse_rule_list(final_rules, 'final_account'))
        if 'decision' in yaml_data and 'rules' in yaml_data['decision']:
            decision_rules = yaml_data['decision']['rules']
            if isinstance(decision_rules, dict):
                rules.extend(self._parse_rule_section(decision_rules, 'decision'))
            elif isinstance(decision_rules, list):
                rules.extend(self._parse_rule_list(decision_rules, 'decision'))
        
        # 处理根级别规则（向后兼容）
        if 'rules' in yaml_data:
            root_rules = yaml_data['rules']
            if isinstance(root_rules, dict):
                rules.extend(self._parse_rule_section(root_rules, 'general'))
            elif isinstance(root_rules, list):
                rules.extend(self._parse_rule_list(root_rules, 'general'))
        
        return rules
    
    def _parse_rule_section(self, rules_data: Dict[str, Any], section: str) -> List[ExtendedRule]:
        """解析规则段落"""
        rules = []
        
        for rule_id, rule_config in rules_data.items():
            if not isinstance(rule_config, dict):
                continue
            
            # 基础字段（必需）
            code = rule_config.get('code', rule_id)
            severity = rule_config.get('severity', 'warn')
            desc = rule_config.get('desc', rule_config.get('description', rule_config.get('title', '')))
            
            # 新增字段（可选，有默认值）
            executor = rule_config.get('executor', 'engine')
            ai_prompt = rule_config.get('ai_prompt')
            
            # 证据要求
            evidence_req_data = rule_config.get('evidence_requirements', {})
            evidence_req = EvidenceRequirement(
                page_number=evidence_req_data.get('page_number', True),
                text_snippet=evidence_req_data.get('text_snippet', True),
                bbox=evidence_req_data.get('bbox', False),
                amount=evidence_req_data.get('amount', False),
                percentage=evidence_req_data.get('percentage', False)
            )
            
            # 容差配置
            tolerance_data = rule_config.get('tolerance', {})
            tolerance = ToleranceConfig(
                money_rel=tolerance_data.get('money_rel', 0.005),
                pct_abs=tolerance_data.get('pct_abs', 0.002),
                page_tol=tolerance_data.get('page_tol', 1)
            )
            
            # 其他字段
            engine_hook = rule_config.get('engine_hook', {})
            aliases = rule_config.get('aliases', [])
            enabled = rule_config.get('enabled', True)
            priority = rule_config.get('priority', 100)
            tags = rule_config.get('tags', [section])
            category = rule_config.get('category', section)
            
            # AI 相关配置
            ai_model = rule_config.get('ai_model')
            ai_temperature = rule_config.get('ai_temperature', 0.1)
            ai_max_tokens = rule_config.get('ai_max_tokens', 1000)
            
            rule = ExtendedRule(
                code=code,
                severity=severity,
                desc=desc,
                executor=executor,
                ai_prompt=ai_prompt,
                evidence_requirements=evidence_req,
                tolerance=tolerance,
                engine_hook=engine_hook,
                aliases=aliases,
                enabled=enabled,
                priority=priority,
                tags=tags,
                category=category,
                ai_model=ai_model,
                ai_temperature=ai_temperature,
                ai_max_tokens=ai_max_tokens
            )
            
            rules.append(rule)
        
        return rules
    
    def _parse_rule_list(self, rules_list: List[Dict[str, Any]], section: str) -> List[ExtendedRule]:
        """解析列表结构的规则（如 v3_3.yaml 根级 rules 为列表）"""
        parsed: List[ExtendedRule] = []
        
        def map_severity(s: str) -> str:
            s = (s or '').lower()
            return {
                'low': 'info',
                'medium': 'warn',
                'mid': 'warn',
                'high': 'error',
                'error': 'error',
                'warn': 'warn',
                'warning': 'warn',
                'info': 'info',
                'critical': 'critical'
            }.get(s, 'warn')
        
        for idx, item in enumerate(rules_list):
            if not isinstance(item, dict):
                continue
            
            code = item.get('code') or item.get('rule_id') or f"{section}_R{idx+1:03d}"
            severity = map_severity(item.get('severity', 'warn'))
            desc = item.get('desc') or item.get('description') or item.get('title') or ''
            executor = item.get('executor', 'engine')
            if executor == 'hybrid':
                executor = 'both'
            
            # 构建证据需求（从 evidence_extract 推断）
            evidence_extract = item.get('evidence_extract', {})
            evidence_req = EvidenceRequirement(
                page_number=True,
                text_snippet=True if evidence_extract != {} else True,
                bbox=False,
                amount=False,
                percentage=False
            )
            
            # 容差配置（使用默认）
            tolerance = ToleranceConfig()
            
            # 引擎钩子：保留 detection / doc_scope 等，供引擎执行器使用
            engine_hook = {
                'detection': item.get('detection'),
                'doc_scope': item.get('doc_scope'),
                'examples': item.get('examples'),
                'false_positive_notes': item.get('false_positive_notes'),
                'auto_explain': item.get('auto_explain'),
            }
            
            enabled = item.get('enabled', True)
            # 依据严重程度设置默认优先级
            priority_map = {
                'critical': 300,
                'error': 200,
                'warn': 150,
                'info': 100
            }
            priority = item.get('priority', priority_map.get(severity, 100))
            
            tags = [section]
            doc_scope = item.get('doc_scope')
            if isinstance(doc_scope, list):
                tags.extend(doc_scope)
            category = item.get('category', section)
            
            ai_model = item.get('ai_model')
            ai_temperature = float(item.get('ai_temperature', 0.1))
            ai_max_tokens = int(item.get('ai_max_tokens', 1000))
            ai_prompt = item.get('ai_prompt')
            
            rule = ExtendedRule(
                code=code,
                severity=severity,
                desc=desc,
                executor=executor,
                ai_prompt=ai_prompt,
                evidence_requirements=evidence_req,
                tolerance=tolerance,
                engine_hook=engine_hook,
                aliases=item.get('aliases', []),
                enabled=enabled,
                priority=priority,
                tags=tags,
                category=category,
                ai_model=ai_model,
                ai_temperature=ai_temperature,
                ai_max_tokens=ai_max_tokens
            )
            parsed.append(rule)
        
        return parsed
    
    def load_rules_from_file(self, yaml_path: str) -> List[ExtendedRule]:
        """从文件加载扩展规则"""
        yaml_data = self.load_yaml_rules(yaml_path)
        return self.parse_extended_rules(yaml_data)
    
    def load_default_rules(self) -> List[ExtendedRule]:
        """加载默认规则文件"""
        default_path = os.path.join(self.rules_dir, 'v3_3.yaml')
        if os.path.exists(default_path):
            return self.load_rules_from_file(default_path)
        return []

    async def load_rules_async(self, rules_version: str) -> List[Dict[str, Any]]:
        """异步接口：按版本加载规则并返回字典列表（供双模式分析器使用）"""
        try:
            all_rules = []
            
            # 加载传统规则文件
            yaml_path = os.path.join(self.rules_dir, f"{rules_version}.yaml")
            if os.path.exists(yaml_path):
                extended_rules = self.load_rules_from_file(yaml_path)
                all_rules.extend(extended_rules)
            else:
                logger.warning(f"Rules version '{rules_version}' not found at {yaml_path}, fallback to default")
                extended_rules = self.load_default_rules()
                all_rules.extend(extended_rules)
            
            # 加载AI规则文件
            ai_rules_path = os.path.join(self.rules_dir, f"ai_rules_{rules_version}.yaml")
            if os.path.exists(ai_rules_path):
                logger.info(f"Loading AI rules from {ai_rules_path}")
                ai_rules = self.load_rules_from_file(ai_rules_path)
                all_rules.extend(ai_rules)
                logger.info(f"Loaded {len(ai_rules)} AI rules")
            else:
                logger.info(f"No AI rules file found: {ai_rules_path}")
            
            logger.info(f"Total loaded rules: {len(all_rules)}")
            # 转字典形式，便于analyze_dual按executor分离
            return [r.to_dict() for r in all_rules]
        except Exception as e:
            logger.error(f"Failed to load rules for version {rules_version}: {e}")
            # 失败时返回空列表，分析器会有降级逻辑
            return []
    
    def filter_rules(self, rules: List[ExtendedRule], 
                    enabled_only: bool = True,
                    executor_type: Optional[str] = None,
                    category: Optional[str] = None,
                    tags: Optional[List[str]] = None,
                    min_priority: Optional[int] = None) -> List[ExtendedRule]:
        """过滤规则
        
        Args:
            rules: 规则列表
            enabled_only: 只返回启用的规则
            executor_type: 执行器类型过滤 ('ai', 'engine', 'hybrid')
            category: 类别过滤
            tags: 标签过滤（包含任一标签即可）
            min_priority: 最小优先级过滤
        """
        filtered = rules
        
        if enabled_only:
            filtered = [r for r in filtered if r.enabled]
        
        if executor_type:
            filtered = [r for r in filtered if r.executor == executor_type]
        
        if category:
            filtered = [r for r in filtered if r.category == category]
        
        if tags:
            filtered = [r for r in filtered if any(tag in r.tags for tag in tags)]
        
        if min_priority is not None:
            filtered = [r for r in filtered if r.priority >= min_priority]
        
        logger.debug(f"Filtered {len(rules)} rules to {len(filtered)} rules")
        return filtered
    
    def get_ai_rules(self, rules: List[ExtendedRule]) -> List[ExtendedRule]:
        """获取AI规则"""
        return self.filter_rules(rules, executor_type='ai')
    
    def get_engine_rules(self, rules: List[ExtendedRule]) -> List[ExtendedRule]:
        """获取引擎规则"""
        return self.filter_rules(rules, executor_type='engine')
    
    def get_hybrid_rules(self, rules: List[ExtendedRule]) -> List[ExtendedRule]:
        """获取混合规则"""
        return self.filter_rules(rules, executor_type='hybrid')
    
    def get_rules_by_category(self, rules: List[ExtendedRule], category: str) -> List[ExtendedRule]:
        """按类别获取规则"""
        return self.filter_rules(rules, category=category)
    
    def get_high_priority_rules(self, rules: List[ExtendedRule], min_priority: int = 200) -> List[ExtendedRule]:
        """获取高优先级规则"""
        return self.filter_rules(rules, min_priority=min_priority)
    
    def sort_rules_by_priority(self, rules: List[ExtendedRule], descending: bool = True) -> List[ExtendedRule]:
        """按优先级排序规则"""
        return sorted(rules, key=lambda x: x.priority, reverse=descending)
    
    def create_legacy_compatible_rules(self, extended_rules: List[ExtendedRule]) -> List[Dict[str, Any]]:
        """创建与旧系统兼容的规则格式"""
        legacy_rules = []
        
        for rule in extended_rules:
            if rule.executor in ['engine', 'both']:
                legacy_rule = {
                    'code': rule.code,
                    'severity': rule.severity,
                    'desc': rule.desc,
                    'enabled': rule.enabled,
                    'priority': rule.priority,
                    'tags': rule.tags,
                    # 保留引擎钩子配置
                    **rule.engine_hook
                }
                legacy_rules.append(legacy_rule)
        
        return legacy_rules
    
    def validate_rules(self, rules: List[ExtendedRule]) -> List[str]:
        """验证规则配置"""
        errors = []
        
        codes = set()
        for rule in rules:
            # 检查必需字段
            if not rule.code:
                errors.append(f"Rule missing code: {rule}")
            elif rule.code in codes:
                errors.append(f"Duplicate rule code: {rule.code}")
            else:
                codes.add(rule.code)
            
            if not rule.desc:
                errors.append(f"Rule {rule.code} missing description")
            
            # 检查执行器
            if rule.executor not in ['ai', 'engine', 'both']:
                errors.append(f"Rule {rule.code} has invalid executor: {rule.executor}")
            
            # 检查 AI 规则必需的提示词
            if rule.executor in ['ai', 'both'] and not rule.ai_prompt:
                errors.append(f"AI rule {rule.code} missing ai_prompt")
            
            # 检查严重程度
            if rule.severity not in ['info', 'warn', 'error', 'critical']:
                errors.append(f"Rule {rule.code} has invalid severity: {rule.severity}")
        
        return errors


# 全局实例
rule_loader = RuleLoaderExt()


def load_extended_rules(yaml_path: str = None) -> List[ExtendedRule]:
    """便捷函数：加载扩展规则"""
    if yaml_path:
        return rule_loader.load_rules_from_file(yaml_path)
    return rule_loader.load_default_rules()


def get_rules_by_executor(executor: str, yaml_path: str = None) -> List[ExtendedRule]:
    """便捷函数：按执行器获取规则"""
    rules = load_extended_rules(yaml_path)
    # 修复参数名称：filter_rules使用executor_type
    return rule_loader.filter_rules(rules, executor_type=executor)


if __name__ == "__main__":
    # 测试代码
    try:
        rules = load_extended_rules()
        print(f"Loaded {len(rules)} rules")
        
        ai_rules = rule_loader.get_ai_rules(rules)
        engine_rules = rule_loader.get_engine_rules(rules)
        
        print(f"AI rules: {len(ai_rules)}")
        print(f"Engine rules: {len(engine_rules)}")
        
        errors = rule_loader.validate_rules(rules)
        if errors:
            print("Validation errors:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("All rules valid")
            
    except Exception as e:
        print(f"Error: {e}")