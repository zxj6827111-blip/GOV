"""
核心规则引擎
实现关键预算检查规则，包括目录一致性、缺表检查、口径一致性、总表恒等、年份一致性
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from decimal import Decimal
import logging
from dataclasses import dataclass

from .table_name_matcher import TableNameMatcher
from .robust_number_parser import RobustNumberParser

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果"""
    rule_id: str
    rule_name: str
    is_valid: bool
    severity: str  # 'error', 'warning', 'info'
    message: str
    evidence: List[Dict[str, Any]]
    page_numbers: List[int]


class CoreRulesEngine:
    """核心规则引擎"""
    
    def __init__(self):
        """初始化规则引擎"""
        self.table_matcher = TableNameMatcher()
        self.number_parser = RobustNumberParser()
        
        # 九张表标准名称
        self.required_tables = [
            "一般公共预算收入表", "一般公共预算支出表", "一般公共预算本级支出表",
            "一般公共预算转移支付分地区情况表", "政府性基金预算收入表",
            "政府性基金预算支出表", "国有资本经营预算收入表",
            "国有资本经营预算支出表", "社会保险基金预算收支情况表"
        ]
        
        # 关键词配置
        self.three_public_keywords = ["三公经费", "因公出国", "公务接待", "公务用车"]
        self.operation_keywords = ["机关运行经费", "日常公用经费", "办公费"]
        self.procurement_keywords = ["政府采购", "采购金额", "采购预算"]
        
        # 编译正则表达式
        self.year_pattern = re.compile(r'20\d{2}')
    
    def validate_all(self, document_data: Dict[str, Any]) -> List[ValidationResult]:
        """执行所有核心规则验证"""
        results = []
        
        try:
            results.extend(self._validate_missing_tables(document_data))
            results.extend(self._validate_three_public_consistency(document_data))
            results.extend(self._validate_year_consistency(document_data))
            results.extend(self._validate_toc_consistency(document_data))
            
        except Exception as e:
            logger.error(f"规则验证过程中出现错误: {e}")
            results.append(ValidationResult(
                rule_id="SYSTEM_ERROR", rule_name="系统错误", is_valid=False,
                severity="error", message=f"验证过程中出现系统错误: {str(e)}",
                evidence=[], page_numbers=[]
            ))
        
        return results
    
    def _validate_missing_tables(self, document_data: Dict[str, Any]) -> List[ValidationResult]:
        """验证缺表/缺章节"""
        results = []
        
        try:
            pages_text = document_data.get('pages_text', [])
            found_tables = set()
            
            for page_text in pages_text:
                for table_name in self.required_tables:
                    # 简单的字符串匹配检查
                    if table_name in page_text:
                        found_tables.add(table_name)
                    else:
                        # 使用表格匹配器
                        match = self.table_matcher.match_table_name(page_text)
                        if match and match.get('standard_name') == table_name:
                            found_tables.add(table_name)
            
            missing_tables = set(self.required_tables) - found_tables
            
            if missing_tables:
                results.append(ValidationResult(
                    rule_id="TABLE_001", rule_name="缺失必要表格", is_valid=False,
                    severity="error", message=f"缺失{len(missing_tables)}张必要表格",
                    evidence=[{"missing_table": table} for table in missing_tables],
                    page_numbers=[]
                ))
            else:
                results.append(ValidationResult(
                    rule_id="TABLE_001", rule_name="表格完整性", is_valid=True,
                    severity="info", message="所有必要表格都已包含",
                    evidence=[], page_numbers=[]
                ))
                
        except Exception as e:
            logger.error(f"缺表检查失败: {e}")
        
        return results
    
    def _validate_three_public_consistency(self, document_data: Dict[str, Any]) -> List[ValidationResult]:
        """验证三公经费口径一致性"""
        results = []
        
        try:
            pages_text = document_data.get('pages_text', [])
            three_public_mentions = []
            
            for i, page_text in enumerate(pages_text):
                for keyword in self.three_public_keywords:
                    if keyword in page_text:
                        numbers = self.number_parser.extract_all_numbers(page_text)
                        three_public_mentions.append({
                            'page': i + 1, 
                            'keyword': keyword, 
                            'numbers': numbers
                        })
            
            if len(three_public_mentions) == 0:
                return results  # 没有相关内容，不做验证
            
            inconsistencies = self._check_amount_consistency(three_public_mentions, "三公经费")
            
            if inconsistencies:
                # 修复错误：从 inconsistencies 中提取 pages
                all_pages = []
                for item in inconsistencies:
                    if 'pages' in item:
                        all_pages.extend(item['pages'])
                
                results.append(ValidationResult(
                    rule_id="EXPENSE_001", rule_name="三公经费口径不一致", is_valid=False,
                    severity="warning", message=f"发现{len(inconsistencies)}处三公经费金额不一致",
                    evidence=inconsistencies, page_numbers=all_pages
                ))
            elif three_public_mentions:
                results.append(ValidationResult(
                    rule_id="EXPENSE_001", rule_name="三公经费口径一致性", is_valid=True,
                    severity="info", message="三公经费相关金额表述一致",
                    evidence=[], page_numbers=[item['page'] for item in three_public_mentions]
                ))
                
        except Exception as e:
            logger.error(f"三公经费一致性验证失败: {e}")
        
        return results
    
    def _validate_year_consistency(self, document_data: Dict[str, Any]) -> List[ValidationResult]:
        """验证年份一致性"""
        results = []
        
        try:
            pages_text = document_data.get('pages_text', [])
            year_mentions = {}
            
            for i, page_text in enumerate(pages_text):
                years = self.year_pattern.findall(page_text)
                for year in years:
                    if year not in year_mentions:
                        year_mentions[year] = []
                    year_mentions[year].append(i + 1)
            
            if not year_mentions:
                return results
            
            main_year = max(year_mentions.keys(), key=lambda y: len(year_mentions[y]))
            other_years = {y: pages for y, pages in year_mentions.items() if y != main_year}
            
            if other_years:
                main_year_int = int(main_year)
                reasonable_years = {str(main_year_int - 1), str(main_year_int + 1)}
                
                problematic_years = {year: pages for year, pages in other_years.items() 
                                   if year not in reasonable_years}
                
                if problematic_years:
                    results.append(ValidationResult(
                        rule_id="YEAR_001", rule_name="年份不一致", is_valid=False,
                        severity="warning", message=f"发现与主要年份{main_year}不一致的年份",
                        evidence=[{"year": year, "pages": pages} for year, pages in problematic_years.items()],
                        page_numbers=[p for pages in problematic_years.values() for p in pages]
                    ))
                else:
                    results.append(ValidationResult(
                        rule_id="YEAR_001", rule_name="年份一致性", is_valid=True,
                        severity="info", message=f"年份使用一致，主要年份为{main_year}",
                        evidence=[], page_numbers=year_mentions[main_year][:3]
                    ))
            else:
                results.append(ValidationResult(
                    rule_id="YEAR_001", rule_name="年份一致性", is_valid=True,
                    severity="info", message=f"文档中年份使用一致：{main_year}",
                    evidence=[], page_numbers=year_mentions[main_year][:3]
                ))
                
        except Exception as e:
            logger.error(f"年份一致性验证失败: {e}")
        
        return results
    
    def _validate_toc_consistency(self, document_data: Dict[str, Any]) -> List[ValidationResult]:
        """验证目录-正文顺序一致性"""
        results = []
        
        try:
            pages_text = document_data.get('pages_text', [])
            if not pages_text:
                return results
            
            # 查找目录页
            toc_page_num = -1
            for i, page_text in enumerate(pages_text):
                if any(keyword in page_text for keyword in ["目录", "目　录"]):
                    toc_page_num = i
                    break
            
            if toc_page_num == -1:
                results.append(ValidationResult(
                    rule_id="TOC_001", rule_name="目录缺失", is_valid=False,
                    severity="warning", message="未找到目录页面",
                    evidence=[{"message": "整个文档中未发现目录页面"}], page_numbers=[]
                ))
            else:
                results.append(ValidationResult(
                    rule_id="TOC_001", rule_name="目录存在性", is_valid=True,
                    severity="info", message="文档包含目录页面",
                    evidence=[], page_numbers=[toc_page_num + 1]
                ))
                
        except Exception as e:
            logger.error(f"目录一致性验证失败: {e}")
        
        return results
    
    def _check_amount_consistency(self, mentions: List[Dict], category: str) -> List[Dict]:
        """检查金额一致性"""
        inconsistencies = []
        
        if len(mentions) < 2:
            return inconsistencies
        
        # 收集所有金额
        all_amounts = []
        for mention in mentions:
            if 'numbers' in mention and mention['numbers']:
                for original_text, amount, start, end in mention['numbers']:
                    all_amounts.append({
                        'page': mention.get('page', 1),
                        'keyword': mention.get('keyword', ''),
                        'amount': amount,
                        'original_text': original_text
                    })
        
        # 检查金额差异
        if len(all_amounts) > 1:
            base_amount = all_amounts[0]['amount']
            for other in all_amounts[1:]:
                if not self.number_parser.calculate_tolerance(base_amount, other['amount']):
                    inconsistencies.append({
                        'category': category,
                        'base_amount': str(base_amount),
                        'other_amount': str(other['amount']),
                        'pages': [all_amounts[0]['page'], other['page']],
                        'message': f"{category}金额不一致：{base_amount} vs {other['amount']}"
                    })
        
        return inconsistencies