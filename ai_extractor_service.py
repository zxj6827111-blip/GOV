#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI抽取器微服务 - GLM4.5 Flash信息抽取服务
用于规则 V33-110：R33110_BudgetVsFinal_TextConsistency 的三元组抽取
"""

import os
import json
import hashlib
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import re

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Extractor Service",
    description="GLM4.5 Flash信息抽取微服务",
    version="1.0.0"
)

# ==================== 配置 ====================
# GLM4.5 Flash客户端配置 - 兼容OPENAI和GLM环境变量
# 环境变量读取优先级：OPENAI_* -> GLM_* -> 默认值
OPENAI_BASE = os.getenv("OPENAI_BASE") or os.getenv("GLM_BASE_URL") or "https://open.bigmodel.cn/api/paas/v4"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("GLM_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("GLM_MODEL") or "glm-4-flash"

# 滑窗参数 - 按需求调整
WINDOW_SIZE = 1700  # 每窗口字符数（调整为1600-1800范围）
OVERLAP_SIZE = 200  # 重叠字符数（调整为200）
MAX_CLIP_LENGTH = 120  # clip最大长度（调整为≤120字）

# ==================== 数据模型 ====================
class ExtractRequest(BaseModel):
    task: str = Field(..., description="任务类型，固定为 R33110_pairs_v1")
    section_text: str = Field(..., description="（三）小节全文")
    language: str = Field(default="zh", description="语言")
    doc_hash: str = Field(..., description="文档哈希")
    max_windows: int = Field(default=3, description="最大窗口数")

class ExtractHit(BaseModel):
    budget_text: str = Field(..., description="预算数字原文")
    budget_span: List[int] = Field(..., description="预算数字span [start, end)")
    final_text: str = Field(..., description="决算数字原文")
    final_span: List[int] = Field(..., description="决算数字span [start, end)")
    stmt_text: str = Field(..., description="比较语句原文")
    stmt_span: List[int] = Field(..., description="比较语句span [start, end)")
    reason_text: Optional[str] = Field(None, description="原因说明原文")
    reason_span: Optional[List[int]] = Field(None, description="原因说明span [start, end)")
    item_title: Optional[str] = Field(None, description="项目标题（可选）")
    clip: str = Field(..., description="原文截取片段")

class ExtractResponse(BaseModel):
    hits: List[ExtractHit] = Field(default_factory=list, description="抽取结果")
    meta: Dict[str, Any] = Field(default_factory=dict, description="元数据")

# ==================== GLM调用 ====================
class GLMClient:
    def __init__(self):
        # 使用统一的配置变量
        logger.info(f"使用GLM4.5 Flash API: {OPENAI_BASE}")
        self.client_type = "openai"
        self.api_key = OPENAI_API_KEY
        self.base_url = OPENAI_BASE
        self.model = OPENAI_MODEL
        
        self.timeout = httpx.Timeout(60.0)  # 设置60秒超时
        
    async def extract_pairs(self, text: str) -> List[Dict[str, Any]]:
        """调用GLM4.5 Flash进行信息抽取，支持60秒超时和一次备选模型重试。
        当未配置OPENAI_API_KEY/GLM_API_KEY时，提供离线正则回退以保障联调可用性。"""
        # 离线回退：无API Key时直接用正则抽取三元组
        if not self.api_key:
            logger.info("未检测到OPENAI_API_KEY/GLM_API_KEY，启用离线正则回退以生成抽取结果")
            # 复用与后端规则一致的配对模式，尽可能贴近真实结果
            PAT = re.compile(
                r"(?:年初?\s*预算|预算|年初预算数|预算数)(?:数)?[为是]?\s*"  # 预算词形
                r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:亿元|万元|元)?"       # 预算数字
                r"(?:[^决]{0,80}?)?"                                       # 间隔
                r"(?:支出\s*决算|决算|决算支出)(?:数)?[为是]?\s*"         # 决算词形
                r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:亿元|万元|元)?"       # 决算数字
                r"(?:[^。]{0,80}?)?"                                       # 间隔
                r"(决算(?:数)?(?:大于|小于|等于|持平|基本持平)预算(?:数)?)", # 结论短语
                re.S
            )
            results: List[Dict[str, Any]] = []
            for m in PAT.finditer(text):
                try:
                    budget_text = m.group(1)
                    final_text = m.group(2)
                    stmt_text = m.group(3)
                    results.append({
                        "budget_text": budget_text,
                        "budget_span": [m.start(1), m.end(1)],
                        "final_text": final_text,
                        "final_span": [m.start(2), m.end(2)],
                        "stmt_text": stmt_text,
                        "stmt_span": [m.start(3), m.end(3)],
                        "reason_text": None,
                        "reason_span": None,
                        "item_title": None
                    })
                except Exception:
                    continue
            return results

        prompt = self._build_prompt(text)
        
        try:
            # 第一次尝试：优先使用函数调用
            result = await self._call_with_function(prompt, text)
            if result:
                return result
                
            # 第二次尝试：降级到JSON模式
            result = await self._call_with_json(prompt, text)
            if result:
                return result
                
            # 第三次尝试：备选模型重试（如果配置了不同模型）
            backup_model = os.getenv("OPENAI_BACKUP_MODEL") or os.getenv("GLM_BACKUP_MODEL")
            if backup_model and backup_model != self.model:
                logger.info(f"使用备选模型重试: {backup_model}")
                original_model = self.model
                self.model = backup_model
                
                try:
                    result = await self._call_with_json(prompt, text)
                    if result:
                        return result
                finally:
                    self.model = original_model  # 恢复原模型
                
            logger.warning("GLM4.5 Flash调用失败，返回空列表")
            return []
            
        except Exception as e:
            logger.error(f"GLM4.5 Flash调用异常: {e}")
            return []
    
    def _build_prompt(self, text: str) -> str:
        """构建提示词"""
        return f"""你是专业的财政文档信息抽取专家。请从以下文本中抽取"预算数字、决算数字、结论短语"三者同时存在的三元组信息。

【强制约束】：
1. 预算数字、决算数字、结论短语三者必须同时存在才输出
2. 逐字抄写原文数字与短语，不做任何改写或格式化
3. 给出准确的[start,end)字符位置span（从0开始计数）
4. 只抽取信息，不做大小比较判断
5. 如果没有原因说明，reason_text和reason_span设为null

【词形识别】：
- 预算词形：年初预算|预算|年初预算数|预算数（任意一种）
- 决算词形：支出决算|决算|决算支出（任意一种）
- 结论短语：决算数大于预算数|决算数小于预算数|决算数等于预算数|决算数持平预算数|决算数基本持平预算数

【顺序支持】：
- 既可能"预算→决算→结论"顺序
- 也可能"决算→预算→结论"顺序
- 也可能其他混合顺序

【数字要求】：
- 逐字抄写（含千分位、小数、全角空格）
- 附准确的[start,end)span位置
- 必须包含单位（万元|元|亿元）

【原因说明】：
- 有则给出reason_text/reason_span
- 无则设为null
- 关键词：主要原因|增减原因|变动原因（必须含"原因"二字）

文本内容：
{text}

请严格按照上述约束抽取所有符合条件的三元组。

返回严格JSON格式：
{{
  "pairs": [
    {{
      "budget_text": "232.02万元",
      "budget_span": [58, 66],
      "final_text": "219.24万元", 
      "final_span": [86, 94],
      "stmt_text": "决算数小于预算数",
      "stmt_span": [100, 109],
      "reason_text": "主要原因：年中按实际需求调整预算",
      "reason_span": [120, 145],
      "item_title": "公安支出"
    }}
  ]
}}"""

    async def _call_with_function(self, prompt: str, text: str) -> Optional[List[Dict[str, Any]]]:
        """使用函数调用模式"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,  # 降低温度提高一致性
                        "max_tokens": 2000,  # 增加最大token数
                        "functions": [{
                            "name": "extract_budget_pairs",
                            "description": "抽取预算决算对比信息",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "pairs": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "budget_text": {"type": "string"},
                                                "budget_span": {"type": "array", "items": {"type": "integer"}},
                                                "final_text": {"type": "string"},
                                                "final_span": {"type": "array", "items": {"type": "integer"}},
                                                "stmt_text": {"type": "string"},
                                                "stmt_span": {"type": "array", "items": {"type": "integer"}},
                                                "reason_text": {"type": ["string", "null"]},
                                                "reason_span": {"type": ["array", "null"]},
                                                "item_title": {"type": ["string", "null"]}
                                            },
                                            "required": ["budget_text", "budget_span", "final_text", "final_span", "stmt_text", "stmt_span"]
                                        }
                                    }
                                },
                                "required": ["pairs"]
                            }
                        }],
                        "function_call": {"name": "extract_budget_pairs"}
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if "choices" in result and result["choices"]:
                        choice = result["choices"][0]
                        if "function_call" in choice["message"]:
                            args = json.loads(choice["message"]["function_call"]["arguments"])
                            pairs = args.get("pairs", [])
                            # 二次校验
                            return self._validate_spans(pairs, text)
                            
        except Exception as e:
            logger.warning(f"函数调用模式失败: {e}")
            
        return None
    
    async def _call_with_json(self, prompt: str, text: str) -> Optional[List[Dict[str, Any]]]:
        """使用JSON模式"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,  # 降低温度提高一致性
                        "max_tokens": 2000,  # 增加最大token数
                        "response_format": {"type": "json_object"}
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if "choices" in result and result["choices"]:
                        content = result["choices"][0]["message"]["content"]
                        try:
                            data = json.loads(content)
                            pairs = data.get("pairs", [])
                            # 二次校验
                            return self._validate_spans(pairs, text)
                        except json.JSONDecodeError:
                            logger.warning("JSON解析失败")
                            
        except Exception as e:
            logger.warning(f"JSON模式失败: {e}")
            
        return None
    
    def _validate_spans(self, pairs: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
        """二次校验：修正span并验证文本一致性"""
        validated = []
        
        for pair in pairs:
            try:
                # 校验必需字段
                budget_text = pair.get("budget_text", "").strip()
                final_text = pair.get("final_text", "").strip()
                stmt_text = pair.get("stmt_text", "").strip()
                
                if not budget_text or not final_text or not stmt_text:
                    continue
                
                # 验证数字格式（必须包含数字和单位）
                import re
                budget_num_match = re.search(r'\d+(?:,\d{3})*(?:\.\d+)?', budget_text)
                final_num_match = re.search(r'\d+(?:,\d{3})*(?:\.\d+)?', final_text)
                budget_unit_match = re.search(r'万元|元|亿元', budget_text)
                final_unit_match = re.search(r'万元|元|亿元', final_text)
                
                if not budget_num_match or not final_num_match or not budget_unit_match or not final_unit_match:
                    logger.warning(f"数字或单位格式不正确: budget={budget_text}, final={final_text}")
                    continue
                
                # 验证结论短语格式
                stmt_pattern = r'决算(?:数)?(?:大于|小于|等于|持平|基本持平)预算(?:数)?'
                if not re.search(stmt_pattern, stmt_text):
                    logger.warning(f"结论短语格式不正确: {stmt_text}")
                    continue
                
                # 尝试在文本中找到正确的位置
                budget_span = self._find_text_span(text, budget_text)
                final_span = self._find_text_span(text, final_text)
                stmt_span = self._find_text_span(text, stmt_text)
                
                if not budget_span or not final_span or not stmt_span:
                    logger.warning(f"无法找到文本位置: budget={budget_text}, final={final_text}, stmt={stmt_text}")
                    continue
                
                # 验证span的合理性（不能重叠太多）
                spans = [budget_span, final_span, stmt_span]
                if self._spans_overlap_too_much(spans):
                    logger.warning(f"span重叠过多，跳过: {spans}")
                    continue
                
                # 更新正确的span
                pair["budget_span"] = budget_span
                pair["final_span"] = final_span
                pair["stmt_span"] = stmt_span
                
                # 处理reason（如果存在）- 必须包含"原因"二字
                reason_text = pair.get("reason_text")
                if reason_text and reason_text.strip():
                    reason_clean = reason_text.strip()
                    if "原因" in reason_clean:
                        reason_span = self._find_text_span(text, reason_clean)
                        if reason_span:
                            pair["reason_text"] = reason_clean
                            pair["reason_span"] = reason_span
                        else:
                            pair["reason_text"] = None
                            pair["reason_span"] = None
                    else:
                        logger.warning(f"原因说明不包含'原因'二字: {reason_clean}")
                        pair["reason_text"] = None
                        pair["reason_span"] = None
                else:
                    pair["reason_text"] = None
                    pair["reason_span"] = None
                
                validated.append(pair)
                
            except Exception as e:
                logger.warning(f"校验pair失败: {e}")
                continue
                
        return validated
    
    def _spans_overlap_too_much(self, spans: List[List[int]]) -> bool:
        """检查span是否重叠过多"""
        for i, span1 in enumerate(spans):
            for j, span2 in enumerate(spans[i+1:], i+1):
                overlap = max(0, min(span1[1], span2[1]) - max(span1[0], span2[0]))
                min_length = min(span1[1] - span1[0], span2[1] - span2[0])
                if min_length > 0 and overlap / min_length > 0.8:  # 重叠超过80%
                    return True
        return False
    
    def _find_text_span(self, text: str, target: str) -> Optional[List[int]]:
        """在文本中查找目标字符串的位置"""
        try:
            # 直接查找
            start = text.find(target)
            if start != -1:
                return [start, start + len(target)]
            
            # 去除空格后查找
            target_clean = target.replace(" ", "")
            text_clean = text.replace(" ", "")
            start_clean = text_clean.find(target_clean)
            if start_clean != -1:
                # 需要映射回原文本位置
                original_start = self._map_clean_to_original(text, start_clean)
                if original_start != -1:
                    return [original_start, original_start + len(target_clean)]
            
            # 模糊匹配：查找包含关键数字的部分
            import re
            if re.search(r'\d+\.?\d*', target):
                numbers = re.findall(r'\d+\.?\d*', target)
                for num in numbers:
                    start = text.find(num)
                    if start != -1:
                        # 扩展到包含单位等
                        end = start + len(num)
                        while end < len(text) and text[end] in '万元千亿':
                            end += 1
                        return [start, end]
            
            return None
            
        except Exception:
            return None
    
    def _map_clean_to_original(self, original: str, clean_pos: int) -> int:
        """将清理后文本的位置映射回原文本位置"""
        clean_count = 0
        for i, char in enumerate(original):
            if char != ' ':
                if clean_count == clean_pos:
                    return i
                clean_count += 1
        return -1

# ==================== 滑窗处理 ====================
class SlidingWindowProcessor:
    def __init__(self, window_size: int = WINDOW_SIZE, overlap: int = OVERLAP_SIZE):
        self.window_size = window_size
        self.overlap = overlap
        
    def create_windows(self, text: str, max_windows: int = 3) -> List[Tuple[str, int]]:
        """创建滑窗，返回(窗口文本, 全局偏移)列表"""
        if len(text) <= self.window_size:
            return [(text, 0)]
            
        windows = []
        start = 0
        
        while start < len(text) and len(windows) < max_windows:
            end = min(start + self.window_size, len(text))
            window_text = text[start:end]
            windows.append((window_text, start))
            
            if end >= len(text):
                break
                
            start = end - self.overlap
            
        return windows
    
    def merge_results(self, window_results: List[Tuple[List[Dict[str, Any]], int]]) -> List[Dict[str, Any]]:
        """合并多窗口结果，去重"""
        all_pairs = []
        
        # 收集所有结果并调整span
        for pairs, offset in window_results:
            for pair in pairs:
                adjusted_pair = pair.copy()
                # 调整span到全局位置
                adjusted_pair["budget_span"] = [pair["budget_span"][0] + offset, pair["budget_span"][1] + offset]
                adjusted_pair["final_span"] = [pair["final_span"][0] + offset, pair["final_span"][1] + offset]
                adjusted_pair["stmt_span"] = [pair["stmt_span"][0] + offset, pair["stmt_span"][1] + offset]
                
                if pair.get("reason_span"):
                    adjusted_pair["reason_span"] = [pair["reason_span"][0] + offset, pair["reason_span"][1] + offset]
                    
                all_pairs.append(adjusted_pair)
        
        # 去重：重叠>60%视为同一命中
        return self._deduplicate(all_pairs)
    
    def _deduplicate(self, pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """优化去重处理 - 基于多维度相似度"""
        if not pairs:
            return []
            
        unique_pairs = []
        
        for pair in pairs:
            is_duplicate = False
            
            for existing in unique_pairs:
                # 多维度相似度检测
                overlap_ratio = self._calculate_overlap(pair, existing)
                text_similarity = self._calculate_text_similarity(pair, existing)
                
                # 综合判断：span重叠>0.5 或 文本相似度>0.8
                if overlap_ratio > 0.5 or text_similarity > 0.8:
                    is_duplicate = True
                    # 优先保留有原因说明的版本
                    if pair.get("reason_text") and not existing.get("reason_text"):
                        unique_pairs.remove(existing)
                        unique_pairs.append(pair)
                    # 或者保留span更精确的版本
                    elif not pair.get("reason_text") and not existing.get("reason_text"):
                        if self._is_more_precise(pair, existing):
                            unique_pairs.remove(existing)
                            unique_pairs.append(pair)
                    break
                    
            if not is_duplicate:
                unique_pairs.append(pair)
                
        return unique_pairs
    
    def _calculate_text_similarity(self, pair1: Dict[str, Any], pair2: Dict[str, Any]) -> float:
        """计算文本相似度"""
        # 比较预算和决算数字
        budget_sim = 1.0 if pair1["budget_text"] == pair2["budget_text"] else 0.0
        final_sim = 1.0 if pair1["final_text"] == pair2["final_text"] else 0.0
        
        # 比较结论短语
        stmt1 = pair1["stmt_text"].replace("数", "").replace("决算", "").replace("预算", "")
        stmt2 = pair2["stmt_text"].replace("数", "").replace("决算", "").replace("预算", "")
        stmt_sim = 1.0 if stmt1 == stmt2 else 0.0
        
        # 加权平均
        return (budget_sim * 0.4 + final_sim * 0.4 + stmt_sim * 0.2)
    
    def _is_more_precise(self, pair1: Dict[str, Any], pair2: Dict[str, Any]) -> bool:
        """判断哪个pair更精确（span更紧凑）"""
        span1_len = (pair1["stmt_span"][1] - pair1["stmt_span"][0])
        span2_len = (pair2["stmt_span"][1] - pair2["stmt_span"][0])
        return span1_len < span2_len
    
    def _calculate_overlap(self, pair1: Dict[str, Any], pair2: Dict[str, Any]) -> float:
        """计算两个pair的重叠度"""
        # 基于stmt_span计算重叠
        span1 = pair1["stmt_span"]
        span2 = pair2["stmt_span"]
        
        overlap_start = max(span1[0], span2[0])
        overlap_end = min(span1[1], span2[1])
        
        if overlap_start >= overlap_end:
            return 0.0
            
        overlap_len = overlap_end - overlap_start
        total_len = max(span1[1] - span1[0], span2[1] - span2[0])
        
        return overlap_len / total_len if total_len > 0 else 0.0

# ==================== Clip生成 ====================
def generate_clip(text: str, stmt_span: List[int], max_length: int = MAX_CLIP_LENGTH) -> str:
    """优化clip生成逻辑"""
    start, end = stmt_span
    
    # 智能扩展策略
    expand_before = min(30, start)  # 向前最多30字符
    expand_after = min(50, len(text) - end)  # 向后最多50字符
    
    # 计算实际扩展范围
    clip_start = max(0, start - expand_before)
    clip_end = min(len(text), end + expand_after)
    
    # 提取初始clip
    clip = text[clip_start:clip_end].strip()
    
    # 如果超长，智能截断
    if len(clip) > max_length:
        # 优先保留stmt_text部分
        stmt_text = text[start:end]
        remaining_length = max_length - len(stmt_text) - 6  # 预留"..."空间
        
        if remaining_length > 0:
            before_length = min(remaining_length // 2, start - clip_start)
            after_length = remaining_length - before_length
            
            before_part = text[start - before_length:start] if before_length > 0 else ""
            after_part = text[end:end + after_length] if after_length > 0 else ""
            
            clip = f"{before_part}{stmt_text}{after_part}"
            if len(clip) > max_length:
                clip = clip[:max_length - 3] + "..."
        else:
            # 如果stmt_text本身就超长，截断它
            clip = stmt_text[:max_length - 3] + "..."
    
    # 清理格式
    clip = re.sub(r'\s+', ' ', clip)  # 合并多余空白
    clip = clip.replace('\n', ' ').replace('\r', ' ')
    
    return clip.strip()

# ==================== 主服务 ====================
glm_client = GLMClient()
window_processor = SlidingWindowProcessor()

@app.post("/ai/extract/v1", response_model=ExtractResponse)
async def extract_pairs(request: ExtractRequest) -> ExtractResponse:
    """AI信息抽取接口"""
    start_time = time.time()
    
    try:
        # 参数验证
        if request.task != "R33110_pairs_v1":
            raise HTTPException(status_code=400, detail="不支持的任务类型")
            
        if not request.section_text.strip():
            logger.info(f"[{request.doc_hash}] 空文本，直接返回")
            return ExtractResponse(hits=[], meta={"model": OPENAI_MODEL, "cached": False})
        
        # 创建滑窗
        windows = window_processor.create_windows(request.section_text, request.max_windows)
        window_count = len(windows)
        
        # 估算tokens（粗略估算：中文1字符≈1token，英文1单词≈1.3token）
        estimated_tokens = len(request.section_text) * 1.2
        
        logger.info(f"[{request.doc_hash}] 开始处理 - 窗口数: {window_count}, 估算tokens: {int(estimated_tokens)}")
        
        # 并发处理各窗口
        window_results = []
        for i, (window_text, offset) in enumerate(windows):
            window_start = time.time()
            pairs = await glm_client.extract_pairs(window_text)
            window_duration = time.time() - window_start
            
            logger.info(f"[{request.doc_hash}] 窗口{i+1}/{window_count} 完成 - 耗时: {window_duration:.2f}s, 抽取数: {len(pairs)}")
            window_results.append((pairs, offset))
        
        # 合并结果
        merged_pairs = window_processor.merge_results(window_results)
        
        # 生成hits
        hits = []
        for pair in merged_pairs:
            try:
                clip = generate_clip(request.section_text, pair["stmt_span"])
                
                hit = ExtractHit(
                    budget_text=pair["budget_text"],
                    budget_span=pair["budget_span"],
                    final_text=pair["final_text"],
                    final_span=pair["final_span"],
                    stmt_text=pair["stmt_text"],
                    stmt_span=pair["stmt_span"],
                    reason_text=pair.get("reason_text"),
                    reason_span=pair.get("reason_span"),
                    item_title=pair.get("item_title"),
                    clip=clip
                )
                hits.append(hit)
                
            except Exception as e:
                logger.warning(f"[{request.doc_hash}] 生成hit失败: {e}")
                continue
        
        total_duration = time.time() - start_time
        hit_count = len(hits)
        
        # 记录详细日志
        logger.info(f"[{request.doc_hash}] 处理完成 - 总耗时: {total_duration:.2f}s, 窗口数: {window_count}, "
                   f"估算tokens: {int(estimated_tokens)}, 命中数: {hit_count}, 模型: {OPENAI_MODEL}")
        
        return ExtractResponse(
            hits=hits,
            meta={
                "model": OPENAI_MODEL, 
                "cached": False,
                "doc_hash": request.doc_hash,
                "window_count": window_count,
                "estimated_tokens": int(estimated_tokens),
                "duration_seconds": round(total_duration, 2),
                "hit_count": hit_count
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"抽取失败: {e}")
        raise HTTPException(status_code=500, detail=f"抽取失败: {str(e)}")

@app.get("/health")
async def health():
    """健康检查接口，返回服务状态和配置信息"""
    # 提取接入点ID（从BASE URL中提取区域信息）
    endpoint_id = "unknown"
    if "cn-beijing" in OPENAI_BASE:
        endpoint_id = "cn-beijing"
    elif "us-east" in OPENAI_BASE:
        endpoint_id = "us-east"
    elif "localhost" in OPENAI_BASE or "127.0.0.1" in OPENAI_BASE:
        endpoint_id = "local-gateway"
    
    return {
        "status": "ok", 
        "base": OPENAI_BASE, 
        "model": OPENAI_MODEL,
        "endpoint_id": endpoint_id
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9009)