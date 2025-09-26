"""
证据截图与坐标提取服务 - 增强版
基于PyMuPDF(fitz)实现PDF文档的坐标定位和截图生成
新增：命中合并、分页展示、完整句高亮
"""
import hashlib
import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EvidenceCoordinate(BaseModel):
    """证据坐标信息"""
    page: int
    x1: float
    y1: float
    x2: float  
    y2: float
    text: str
    confidence: float = 1.0


class EvidenceScreenshot(BaseModel):
    """证据截图信息"""
    coordinate: EvidenceCoordinate
    image_path: str
    image_hash: str
    timestamp: float


class EvidenceEnhancer:
    """证据增强器 - 处理命中合并、分页展示、完整句高亮"""
    
    def __init__(self, sentence_expand_chars: int = 50):
        self.sentence_expand_chars = sentence_expand_chars
        
    def merge_nearby_hits(self, coordinates: List[EvidenceCoordinate], 
                         merge_distance: float = 100.0) -> List[List[EvidenceCoordinate]]:
        """
        合并相近的命中项
        
        Args:
            coordinates: 坐标列表
            merge_distance: 合并距离阈值
            
        Returns:
            合并后的坐标组列表
        """
        if not coordinates:
            return []
        
        # 按页面分组
        page_groups = {}
        for coord in coordinates:
            page = coord.page
            if page not in page_groups:
                page_groups[page] = []
            page_groups[page].append(coord)
        
        merged_groups = []
        
        for page, page_coords in page_groups.items():
            # 在同一页面内合并相近的坐标
            page_coords.sort(key=lambda c: (c.y1, c.x1))  # 按位置排序
            
            current_group = [page_coords[0]]
            
            for i in range(1, len(page_coords)):
                current = page_coords[i]
                previous = current_group[-1]
                
                # 计算距离
                distance = self._calculate_distance(previous, current)
                
                if distance <= merge_distance:
                    current_group.append(current)
                else:
                    # 开始新的组
                    merged_groups.append(current_group)
                    current_group = [current]
            
            # 添加最后一组
            if current_group:
                merged_groups.append(current_group)
        
        return merged_groups
    
    def _calculate_distance(self, coord1: EvidenceCoordinate, coord2: EvidenceCoordinate) -> float:
        """计算两个坐标的距离"""
        center1_x = (coord1.x1 + coord1.x2) / 2
        center1_y = (coord1.y1 + coord1.y2) / 2
        center2_x = (coord2.x1 + coord2.x2) / 2
        center2_y = (coord2.y1 + coord2.y2) / 2
        
        return ((center1_x - center2_x) ** 2 + (center1_y - center2_y) ** 2) ** 0.5
    
    def expand_to_complete_sentences(self, extractor: 'EvidenceExtractor', 
                                   coordinates: List[EvidenceCoordinate]) -> List[EvidenceCoordinate]:
        """
        扩展高亮范围到完整句子
        
        Args:
            extractor: 证据提取器实例
            coordinates: 原始坐标列表
            
        Returns:
            扩展后的坐标列表
        """
        expanded_coords = []
        
        for coord in coordinates:
            try:
                # 获取更大范围的文本
                page_num = coord.page
                expand_margin = self.sentence_expand_chars
                
                # 扩展搜索区域
                expanded_x1 = max(0, coord.x1 - expand_margin)
                expanded_y1 = max(0, coord.y1 - expand_margin) 
                expanded_x2 = coord.x2 + expand_margin
                expanded_y2 = coord.y2 + expand_margin
                
                # 提取扩展区域的文本
                expanded_text = extractor.find_text_in_area(
                    page_num, expanded_x1, expanded_y1, expanded_x2, expanded_y2
                )
                
                if expanded_text:
                    # 查找完整句子边界
                    sentence_start, sentence_end = self._find_sentence_boundaries(
                        expanded_text, coord.text
                    )
                    
                    if sentence_start >= 0 and sentence_end > sentence_start:
                        # 提取完整句子
                        complete_sentence = expanded_text[sentence_start:sentence_end]
                        
                        # 查找完整句子的坐标
                        sentence_coords = extractor.find_text_coordinates(
                            complete_sentence, page_num
                        )
                        
                        if sentence_coords:
                            # 使用第一个匹配的坐标
                            expanded_coord = sentence_coords[0]
                            expanded_coord.text = complete_sentence
                            expanded_coord.confidence = coord.confidence * 0.9  # 略降置信度
                            expanded_coords.append(expanded_coord)
                        else:
                            # 如果找不到完整句子坐标，使用原坐标
                            expanded_coords.append(coord)
                    else:
                        expanded_coords.append(coord)
                else:
                    expanded_coords.append(coord)
                    
            except Exception as e:
                logger.warning(f"Failed to expand sentence for coordinate: {e}")
                expanded_coords.append(coord)
        
        return expanded_coords
    
    def _find_sentence_boundaries(self, text: str, target_text: str) -> Tuple[int, int]:
        """查找目标文本所在句子的边界"""
        target_pos = text.find(target_text)
        if target_pos == -1:
            return -1, -1
        
        # 中文句子分隔符
        sentence_endings = ['。', '！', '？', '；', '\n', '.', '!', '?', ';']
        
        # 向前查找句子开始
        sentence_start = 0
        for i in range(target_pos - 1, -1, -1):
            if text[i] in sentence_endings:
                sentence_start = i + 1
                break
        
        # 向后查找句子结束
        sentence_end = len(text)
        for i in range(target_pos + len(target_text), len(text)):
            if text[i] in sentence_endings:
                sentence_end = i + 1
                break
        
        # 清理空白字符
        while sentence_start < len(text) and text[sentence_start].isspace():
            sentence_start += 1
        
        return sentence_start, sentence_end
    
    def create_paginated_evidence(self, merged_groups: List[List[EvidenceCoordinate]], 
                                 items_per_page: int = 10) -> List[Dict[str, Any]]:
        """
        创建分页的证据展示
        
        Args:
            merged_groups: 合并后的坐标组
            items_per_page: 每页显示的项目数
            
        Returns:
            分页数据列表
        """
        paginated_data = []
        
        for i in range(0, len(merged_groups), items_per_page):
            page_groups = merged_groups[i:i + items_per_page]
            
            page_data = {
                "page_number": len(paginated_data) + 1,
                "total_pages": (len(merged_groups) + items_per_page - 1) // items_per_page,
                "items_count": len(page_groups),
                "evidence_groups": []
            }
            
            for group_idx, group in enumerate(page_groups):
                group_data = {
                    "group_id": i + group_idx + 1,
                    "coordinates_count": len(group),
                    "pages_involved": list(set(coord.page for coord in group)),
                    "coordinates": [coord.dict() for coord in group],
                    "combined_text": self._combine_group_text(group),
                    "bounding_box": self._calculate_group_bounding_box(group)
                }
                page_data["evidence_groups"].append(group_data)
            
            paginated_data.append(page_data)
        
        return paginated_data
    
    def _combine_group_text(self, group: List[EvidenceCoordinate]) -> str:
        """合并组内文本"""
        texts = [coord.text for coord in group]
        return " ... ".join(texts)
    
    def _calculate_group_bounding_box(self, group: List[EvidenceCoordinate]) -> Dict[str, float]:
        """计算组的边界框"""
        if not group:
            return {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
        
        min_x1 = min(coord.x1 for coord in group)
        min_y1 = min(coord.y1 for coord in group)
        max_x2 = max(coord.x2 for coord in group)
        max_y2 = max(coord.y2 for coord in group)
        
        return {
            "x1": min_x1,
            "y1": min_y1, 
            "x2": max_x2,
            "y2": max_y2
        }


class EvidenceExtractor:
    """证据提取器 - 处理坐标定位和截图生成"""
    
    def __init__(self, pdf_path: str, output_dir: str):
        self.pdf_path = pdf_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查PyMuPDF可用性
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) not available. Install with: pip install PyMuPDF")
        
        self.doc = None
        self.enhancer = EvidenceEnhancer()
        self._init_document()
    
    def _init_document(self):
        """初始化PDF文档"""
        try:
            if fitz is not None:
                self.doc = fitz.open(self.pdf_path)
                logger.info(f"Successfully opened PDF: {self.pdf_path}, pages: {len(self.doc)}")
            else:
                raise ImportError("PyMuPDF not available")
        except Exception as e:
            logger.error(f"Failed to open PDF {self.pdf_path}: {e}")
            raise
    
    def find_text_coordinates(self, text: str, page_num: Optional[int] = None) -> List[EvidenceCoordinate]:
        """
        在PDF中查找文本并返回坐标信息
        
        Args:
            text: 要查找的文本
            page_num: 指定页码，None表示全文档搜索
            
        Returns:
            坐标信息列表
        """
        if not self.doc:
            return []
        
        coordinates = []
        pages_to_search = [page_num] if page_num is not None else range(len(self.doc))
        
        for page_idx in pages_to_search:
            if page_idx >= len(self.doc):
                continue
                
            try:
                page = self.doc[page_idx]
                
                # 搜索文本实例
                text_instances = page.search_for(text)
                
                for rect in text_instances:
                    # 验证矩形区域有效性
                    if rect.width > 0 and rect.height > 0:
                        coordinate = EvidenceCoordinate(
                            page=page_idx + 1,  # 1-based页码
                            x1=rect.x0,
                            y1=rect.y0, 
                            x2=rect.x1,
                            y2=rect.y1,
                            text=text,
                            confidence=1.0
                        )
                        coordinates.append(coordinate)
                        
            except Exception as e:
                logger.warning(f"Error searching text on page {page_idx}: {e}")
                continue
        
        logger.info(f"Found {len(coordinates)} text instances for: '{text}'")
        return coordinates
    
    def find_text_in_area(self, page_num: int, x1: float, y1: float, x2: float, y2: float) -> str:
        """
        获取指定区域内的文本内容
        
        Args:
            page_num: 页码 (1-based)
            x1, y1, x2, y2: 区域坐标
            
        Returns:
            区域内的文本
        """
        if not self.doc or page_num < 1 or page_num > len(self.doc):
            return ""
        
        try:
            page = self.doc[page_num - 1]  # Convert to 0-based
            rect = fitz.Rect(x1, y1, x2, y2)
            text = page.get_text("text", clip=rect)
            return text.strip()
        except Exception as e:
            logger.warning(f"Error extracting text from area on page {page_num}: {e}")
            return ""
    
    def capture_screenshot(self, coordinate: EvidenceCoordinate, 
                          margin: float = 20.0, 
                          highlight_color: Tuple[float, float, float] = (1.0, 0.0, 0.0)) -> Optional[EvidenceScreenshot]:
        """
        生成证据截图，包含红框高亮
        
        Args:
            coordinate: 证据坐标
            margin: 截图边距
            highlight_color: 高亮框颜色 (RGB, 0-1范围)
            
        Returns:
            截图信息，失败时返回None
        """
        if not self.doc:
            return None
        
        page_idx = coordinate.page - 1  # Convert to 0-based
        if page_idx < 0 or page_idx >= len(self.doc):
            logger.warning(f"Invalid page number: {coordinate.page}")
            return None
        
        try:
            page = self.doc[page_idx]
            
            # 计算截图区域（包含边距）
            evidence_rect = fitz.Rect(coordinate.x1, coordinate.y1, coordinate.x2, coordinate.y2)
            screenshot_rect = evidence_rect + (-margin, -margin, margin, margin)
            
            # 确保截图区域在页面范围内
            page_rect = page.rect
            screenshot_rect = screenshot_rect & page_rect
            
            # 生成截图
            mat = fitz.Matrix(2.0, 2.0)  # 2倍分辨率
            pix = page.get_pixmap(matrix=mat, clip=screenshot_rect)
            
            # 生成文件名
            text_hash = hashlib.md5(coordinate.text.encode()).hexdigest()[:8]
            image_filename = f"evidence_p{coordinate.page}_{text_hash}.png"
            image_path = self.output_dir / image_filename
            
            # 保存截图
            pix.save(str(image_path))
            pix = None  # 释放内存
            
            # 在原图上添加红框高亮（可选）
            if highlight_color:
                self._add_highlight_to_image(image_path, evidence_rect, screenshot_rect, 
                                           highlight_color, mat.a)
            
            # 计算文件哈希
            image_hash = self._calculate_file_hash(image_path)
            
            screenshot = EvidenceScreenshot(
                coordinate=coordinate,
                image_path=str(image_path),
                image_hash=image_hash,
                timestamp=os.path.getmtime(image_path)
            )
            
            logger.info(f"Generated screenshot: {image_filename}")
            return screenshot
            
        except Exception as e:
            logger.error(f"Failed to capture screenshot for page {coordinate.page}: {e}")
            return None
    
    def _add_highlight_to_image(self, image_path: Path, evidence_rect: fitz.Rect, 
                               screenshot_rect: fitz.Rect, color: Tuple[float, float, float], scale: float):
        """在截图上添加红框高亮"""
        try:
            # 使用PIL添加红框
            from PIL import Image, ImageDraw
            
            with Image.open(image_path) as img:
                draw = ImageDraw.Draw(img)
                
                # 计算红框在截图中的相对位置
                rel_x1 = (evidence_rect.x0 - screenshot_rect.x0) * scale
                rel_y1 = (evidence_rect.y0 - screenshot_rect.y0) * scale  
                rel_x2 = (evidence_rect.x1 - screenshot_rect.x0) * scale
                rel_y2 = (evidence_rect.y1 - screenshot_rect.y0) * scale
                
                # 绘制红框
                rgb_color = tuple(int(c * 255) for c in color)
                draw.rectangle([rel_x1, rel_y1, rel_x2, rel_y2], 
                             outline=rgb_color, width=3)
                
                img.save(image_path)
                
        except ImportError:
            logger.warning("PIL not available, skipping highlight overlay")
        except Exception as e:
            logger.warning(f"Failed to add highlight to {image_path}: {e}")
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """计算文件SHA256哈希"""
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            return file_hash
        except Exception:
            return ""
    
    def extract_evidence_batch(self, text_list: List[str], 
                              enable_screenshots: bool = True) -> Dict[str, Any]:
        """
        批量提取证据坐标和截图
        
        Args:
            text_list: 要查找的文本列表
            enable_screenshots: 是否生成截图
            
        Returns:
            提取结果
        """
        results = {
            "coordinates": [],
            "screenshots": [],
            "metadata": {
                "pdf_path": self.pdf_path,
                "total_pages": len(self.doc) if self.doc else 0,
                "processed_texts": len(text_list),
                "enable_screenshots": enable_screenshots
            }
        }
        
        for text in text_list:
            if not text.strip():
                continue
                
            # 查找坐标
            coordinates = self.find_text_coordinates(text)
            results["coordinates"].extend([coord.dict() for coord in coordinates])
            
            # 生成截图
            if enable_screenshots:
                for coord in coordinates:
                    screenshot = self.capture_screenshot(coord)
                    if screenshot:
                        results["screenshots"].append(screenshot.dict())
        
        logger.info(f"Batch extraction completed: {len(results['coordinates'])} coordinates, "
                   f"{len(results['screenshots'])} screenshots")
        
        return results
    
    def extract_evidence_enhanced(self, text_list: List[str], 
                                enable_screenshots: bool = True,
                                enable_sentence_expansion: bool = True,
                                enable_hit_merging: bool = True,
                                merge_distance: float = 100.0,
                                items_per_page: int = 10) -> Dict[str, Any]:
        """
        增强版证据提取，支持命中合并、句子扩展、分页展示
        
        Args:
            text_list: 要查找的文本列表
            enable_screenshots: 是否生成截图
            enable_sentence_expansion: 是否扩展到完整句子
            enable_hit_merging: 是否合并相近命中
            merge_distance: 合并距离阈值
            items_per_page: 每页显示项目数
            
        Returns:
            增强版提取结果
        """
        # 基础提取
        all_coordinates = []
        for text in text_list:
            if not text.strip():
                continue
            coords = self.find_text_coordinates(text)
            all_coordinates.extend(coords)
        
        # 句子扩展
        if enable_sentence_expansion:
            logger.info("Expanding to complete sentences...")
            all_coordinates = self.enhancer.expand_to_complete_sentences(
                self, all_coordinates
            )
        
        # 命中合并
        merged_groups = []
        if enable_hit_merging:
            logger.info("Merging nearby hits...")
            merged_groups = self.enhancer.merge_nearby_hits(
                all_coordinates, merge_distance
            )
        else:
            # 每个坐标单独成组
            merged_groups = [[coord] for coord in all_coordinates]
        
        # 分页展示
        paginated_evidence = self.enhancer.create_paginated_evidence(
            merged_groups, items_per_page
        )
        
        # 生成截图
        screenshots = []
        if enable_screenshots:
            logger.info("Generating enhanced screenshots...")
            for group in merged_groups:
                for coord in group:
                    screenshot = self.capture_screenshot(coord)
                    if screenshot:
                        screenshots.append(screenshot.dict())
        
        results = {
            "enhanced_coordinates": [coord.dict() for coord in all_coordinates],
            "merged_groups": [[coord.dict() for coord in group] for group in merged_groups],
            "paginated_evidence": paginated_evidence,
            "screenshots": screenshots,
            "metadata": {
                "pdf_path": self.pdf_path,
                "total_pages": len(self.doc) if self.doc else 0,
                "processed_texts": len(text_list),
                "total_coordinates": len(all_coordinates),
                "merged_groups_count": len(merged_groups),
                "pagination_pages": len(paginated_evidence),
                "enable_screenshots": enable_screenshots,
                "enable_sentence_expansion": enable_sentence_expansion,
                "enable_hit_merging": enable_hit_merging,
                "merge_distance": merge_distance,
                "items_per_page": items_per_page
            }
        }
        
        logger.info(f"Enhanced extraction completed: {len(all_coordinates)} coordinates, "
                   f"{len(merged_groups)} groups, {len(paginated_evidence)} pages")
        
        return results
    
    def create_evidence_zip(self, job_id: str, evidence_data: Dict[str, Any]) -> str:
        """
        创建证据文件压缩包
        
        Args:
            job_id: 任务ID
            evidence_data: 证据数据
            
        Returns:
            ZIP文件路径
        """
        zip_path = self.output_dir / f"evidence_{job_id}.zip"
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # 添加元数据
                metadata = {
                    "job_id": job_id,
                    "pdf_path": self.pdf_path,
                    "extraction_summary": evidence_data.get("metadata", {}),
                    "coordinates_count": len(evidence_data.get("coordinates", [])),
                    "screenshots_count": len(evidence_data.get("screenshots", []))
                }
                
                zipf.writestr("metadata.json", 
                             json.dumps(metadata, ensure_ascii=False, indent=2))
                
                # 添加坐标数据
                zipf.writestr("coordinates.json",
                             json.dumps(evidence_data.get("coordinates", []), 
                                       ensure_ascii=False, indent=2))
                
                # 添加截图文件
                for screenshot in evidence_data.get("screenshots", []):
                    image_path = screenshot.get("image_path")
                    if image_path and os.path.exists(image_path):
                        arc_name = f"screenshots/{os.path.basename(image_path)}"
                        zipf.write(image_path, arc_name)
            
            logger.info(f"Created evidence ZIP: {zip_path}")
            return str(zip_path)
            
        except Exception as e:
            logger.error(f"Failed to create evidence ZIP: {e}")
            return ""
    
    def close(self):
        """关闭文档资源"""
        if self.doc:
            self.doc.close()
            self.doc = None


# 便捷函数
def extract_evidence_from_pdf(pdf_path: str, output_dir: str, 
                             text_list: List[str], job_id: str,
                             enable_screenshots: bool = True) -> Dict[str, Any]:
    """
    从PDF提取证据的便捷函数
    
    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录  
        text_list: 要查找的文本列表
        job_id: 任务ID
        enable_screenshots: 是否生成截图
        
    Returns:
        提取结果，包含ZIP文件路径
    """
    extractor = None
    try:
        extractor = EvidenceExtractor(pdf_path, output_dir)
        
        # 批量提取证据
        evidence_data = extractor.extract_evidence_batch(text_list, enable_screenshots)
        
        # 创建ZIP包
        zip_path = extractor.create_evidence_zip(job_id, evidence_data)
        
        # 添加ZIP路径到结果
        evidence_data["zip_path"] = zip_path
        
        return evidence_data
        
    except Exception as e:
        logger.error(f"Evidence extraction failed: {e}")
        return {
            "coordinates": [],
            "screenshots": [],
            "zip_path": "",
            "error": str(e),
            "metadata": {
                "pdf_path": pdf_path,
                "total_pages": 0,
                "processed_texts": len(text_list),
                "enable_screenshots": enable_screenshots
            }
        }
    finally:
        if extractor:
            extractor.close()


def validate_pymupdf_available() -> bool:
    """验证PyMuPDF是否可用"""
    try:
        import fitz
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    # 测试代码
    if validate_pymupdf_available():
        print("✅ PyMuPDF is available")
    else:
        print("❌ PyMuPDF not found. Install with: pip install PyMuPDF")