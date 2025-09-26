# -*- coding: utf-8 -*-
"""
AI抽取器微服务 v2.0 - 支持GLM和DeepSeek多模型容灾
用于规则 V33-110：R33110_BudgetVsFinal_TextConsistency 的三元组抽取
"""

import hashlib
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

# 加载环境变量
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

# 导入新的AI客户端v2
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from services.ai_client_v2 import AIError, ai_client_v2

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Extractor Service v2.0",
    description="GLM和DeepSeek多模型容灾信息抽取微服务",
    version="2.0.0"
)

@app.get("/")
@app.head("/")
async def root():
    """根路径 - 支持GET和HEAD请求"""
    return {"message": "AI Extractor Service v2.0", "status": "running"}

@app.get("/health")
@app.head("/health")
async def health_check():
    """健康检查端点 - 支持GET和HEAD请求"""
    try:
        # 检查AI客户端状态
        health_info = await ai_client_v2.health_check()
        return {
            "status": "healthy",
            "service": "AI Extractor Service v2.0",
            "ai_client": health_info,
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "service": "AI Extractor Service v2.0",
            "error": str(e),
            "timestamp": time.time()
        }

# ==================== 配置 ====================
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

# ==================== AI客户端 ====================
class AIExtractorClient:
    """AI抽取器客户端，使用新的AI客户端v2"""
    
    def __init__(self):
        # 使用全局AI客户端v2实例
        self.ai_client = ai_client_v2
        logger.info("使用AI客户端v2 - 支持GLM和DeepSeek多模型容灾")
        
    async def extract_pairs(self, text: str) -> List[Dict[str, Any]]:
        """调用AI进行信息抽取，支持多模型容灾。
        当未配置API Key时，提供离线正则回退以保障联调可用性。"""
        
        # 检查AI配置
        status = self.ai_client.get_model_status()
        if not status["valid"] or status["available_models"] == 0:
            logger.info("未检测到可用的AI模型配置，启用离线正则回退")
            # 离线回退：使用正则抽取三元组
            return self._regex_fallback(text)
        
        prompt = self._build_prompt(text)
        
        try:
            # 使用AI客户端v2进行抽取
            response = await self.ai_client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
                timeout=60
            )
            
            # 解析JSON响应
            result = self._parse_ai_response(response.content)
            if result:
                logger.info(f"AI抽取成功，使用模型: {response.provider}:{response.model}")
                return result
            else:
                logger.warning("AI响应解析失败，使用正则回退")
                return self._regex_fallback(text)
                
        except AIError as e:
            logger.error(f"AI调用失败: {e}")
            return self._regex_fallback(text)
        except Exception as e:
            logger.error(f"AI调用异常: {e}")
            return self._regex_fallback(text)
    
    def _regex_fallback(self, text: str) -> List[Dict[str, Any]]:
        """正则回退抽取"""
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
    
    def _parse_ai_response(self, content: str) -> Optional[List[Dict[str, Any]]]:
        """解析AI响应"""
        try:
            # 尝试解析JSON
            if '{' in content and '}' in content:
                # 提取JSON部分
                start = content.find('{')
                end = content.rfind('}') + 1
                json_str = content[start:end]
                data = json.loads(json_str)
                
                if "pairs" in data and isinstance(data["pairs"], list):
                    return data["pairs"]
            
            return None
        except Exception as e:
            logger.error(f"JSON解析失败: {e}")
            return None
    
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

# ==================== 全局实例 ====================
ai_extractor = AIExtractorClient()

# ==================== 滑窗处理 ====================
def create_sliding_windows(text: str, window_size: int = WINDOW_SIZE, overlap: int = OVERLAP_SIZE) -> List[str]:
    """创建滑窗"""
    if len(text) <= window_size:
        return [text]
    
    windows = []
    start = 0
    while start < len(text):
        end = start + window_size
        window = text[start:end]
        windows.append(window)
        
        if end >= len(text):
            break
            
        start = end - overlap
    
    return windows

def adjust_spans_for_window(pairs: List[Dict[str, Any]], window_start: int) -> List[Dict[str, Any]]:
    """调整span位置到全文坐标"""
    adjusted_pairs = []
    for pair in pairs:
        adjusted_pair = pair.copy()
        adjusted_pair["budget_span"] = [pair["budget_span"][0] + window_start, pair["budget_span"][1] + window_start]
        adjusted_pair["final_span"] = [pair["final_span"][0] + window_start, pair["final_span"][1] + window_start]
        adjusted_pair["stmt_span"] = [pair["stmt_span"][0] + window_start, pair["stmt_span"][1] + window_start]
        
        if pair.get("reason_span"):
            adjusted_pair["reason_span"] = [pair["reason_span"][0] + window_start, pair["reason_span"][1] + window_start]
        
        adjusted_pairs.append(adjusted_pair)
    
    return adjusted_pairs

def create_clip(text: str, spans: List[List[int]], max_length: int = MAX_CLIP_LENGTH) -> str:
    """创建文本片段"""
    if not spans:
        return ""
    
    # 找到最小和最大位置
    min_pos = min(span[0] for span in spans)
    max_pos = max(span[1] for span in spans)
    
    # 计算扩展范围
    total_span = max_pos - min_pos
    if total_span >= max_length:
        # 如果span本身就很长，只取关键部分
        return text[min_pos:max_pos][:max_length] + "..."
    
    # 向前后扩展
    expand = (max_length - total_span) // 2
    start = max(0, min_pos - expand)
    end = min(len(text), max_pos + expand)
    
    clip = text[start:end]
    if len(clip) > max_length:
        clip = clip[:max_length] + "..."
    
    return clip

# ==================== API端点 ====================
@app.post("/ai/extract/v1", response_model=ExtractResponse)
async def extract_v1(request: ExtractRequest):
    """AI信息抽取接口 v1.0"""
    
    try:
        section_text = request.section_text.strip()
        
        # 检查空文本
        if not section_text:
            logger.warning("收到空文本请求")
            return ExtractResponse(hits=[], meta={"model": "none", "cached": False})
        
        # 缓存检查
        doc_hash = request.doc_hash
        cache_key = f"extract_v1_{hashlib.md5(section_text.encode()).hexdigest()}"
        
        # 滑窗处理
        windows = create_sliding_windows(section_text, WINDOW_SIZE, OVERLAP_SIZE)
        all_pairs = []
        window_start = 0
        
        for i, window in enumerate(windows[:request.max_windows]):
            logger.info(f"处理窗口 {i+1}/{min(len(windows), request.max_windows)}, 长度: {len(window)}")
            
            # AI抽取
            pairs = await ai_extractor.extract_pairs(window)
            
            # 调整span到全文坐标
            if pairs:
                adjusted_pairs = adjust_spans_for_window(pairs, window_start)
                all_pairs.extend(adjusted_pairs)
            
            # 更新窗口起始位置
            if i < len(windows) - 1:
                window_start += WINDOW_SIZE - OVERLAP_SIZE
        
        # 去重和后处理
        unique_pairs = []
        seen_spans = set()
        
        for pair in all_pairs:
            span_key = tuple(pair["budget_span"] + pair["final_span"])
            if span_key not in seen_spans:
                seen_spans.add(span_key)
                
                # 创建clip
                spans = [pair["budget_span"], pair["final_span"], pair["stmt_span"]]
                if pair.get("reason_span"):
                    spans.append(pair["reason_span"])
                
                clip = create_clip(section_text, spans)
                pair["clip"] = clip
                
                unique_pairs.append(pair)
        
        # 转换为ExtractHit对象
        hits = []
        for pair in unique_pairs:
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
                clip=pair["clip"]
            )
            hits.append(hit)
        
        # 统计信息
        estimated_tokens = len(section_text) * 1.5  # 估算token数
        hit_count = len(hits)
        
        # 获取模型信息
        status = ai_extractor.ai_client.get_model_status()
        model_info = "AI_v2_fallback" if not status["valid"] else "AI_v2_multi_model"
        
        logger.info(f"抽取完成 - 窗口数: {len(windows)}, "
                   f"估算tokens: {int(estimated_tokens)}, 命中数: {hit_count}, 模型: {model_info}")
        
        return ExtractResponse(
            hits=hits,
            meta={
                "model": model_info, 
                "cached": False,
                "windows": len(windows),
                "estimated_tokens": int(estimated_tokens),
                "hit_count": hit_count
            }
        )
        
    except Exception as e:
        logger.error(f"抽取失败: {e}")
        raise HTTPException(status_code=500, detail=f"抽取失败: {str(e)}")

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查AI客户端健康状态
        health = await ai_extractor.ai_client.health_check()
        
        return {
            "status": "healthy" if health["healthy"] else "degraded",
            "ai_client": health,
            "version": "2.0.0",
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "version": "2.0.0",
            "timestamp": time.time()
        }

@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "AI Extractor Service v2.0",
        "description": "GLM和DeepSeek多模型容灾信息抽取微服务",
        "version": "2.0.0",
        "endpoints": [
            "/ai/extract/v1 (POST)",
            "/health (GET)"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    
    # 获取端口配置
    port = int(os.getenv("AI_EXTRACTOR_PORT", "9009"))
    
    logger.info(f"启动AI抽取器微服务v2.0，端口: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")