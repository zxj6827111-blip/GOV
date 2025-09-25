# services/text_extractor.py
"""
文本抽取与OCR兜底服务
优先使用pdfminer/fitz抽取，当页面质量不足时触发OCR兜底
"""

import io
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

logger = logging.getLogger(__name__)


@dataclass
class TextSpan:
    """文本片段"""

    text: str
    bbox: Tuple[float, float, float, float]  # x0, y0, x1, y1
    font_size: float = 0.0
    font_name: str = ""


@dataclass
class PageInfo:
    """页面信息"""

    page_no: int
    text: str
    spans: List[TextSpan]
    width: float
    height: float
    ocr_used: bool = False
    quality_score: float = 1.0


class TextExtractor:
    """文本抽取器"""

    def __init__(
        self,
        missing_char_threshold: float = 0.3,
        non_chinese_threshold: float = 0.8,
        enable_ocr: bool = True,
        tesseract_config: str = "--oem 3 --psm 6",
    ):
        self.missing_char_threshold = missing_char_threshold
        self.non_chinese_threshold = non_chinese_threshold
        self.enable_ocr = enable_ocr
        self.tesseract_config = tesseract_config

        # 检查依赖
        if fitz is None:
            raise ImportError("PyMuPDF is required: pip install PyMuPDF")

        if enable_ocr and pytesseract is None:
            logger.warning("pytesseract not available, OCR disabled")
            self.enable_ocr = False

    def extract_from_pdf(self, pdf_path: str, save_extracted_text: bool = True) -> List[PageInfo]:
        """从PDF提取文本"""
        pages = []

        try:
            if fitz is None:
                raise ImportError("PyMuPDF not available")
            doc = fitz.open(pdf_path)

            for page_no in range(len(doc)):
                page = doc[page_no]
                page_info = self._extract_page(page, page_no + 1)
                pages.append(page_info)

            doc.close()
            logger.info(f"Successfully extracted text from {len(pages)} pages")

            # 保存提取的文本到文件供调试使用
            if save_extracted_text:
                self._save_extracted_text(pdf_path, pages)

        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise

        return pages

    def _extract_page(self, page, page_no: int) -> PageInfo:
        """提取单页文本"""
        # 获取页面尺寸
        rect = page.rect
        width, height = rect.width, rect.height

        # 首先尝试文本抽取
        text, spans = self._extract_text_with_spans(page)

        # 评估文本质量
        quality_score = self._evaluate_text_quality(text)
        need_ocr = quality_score < 0.5

        # 如果需要OCR且启用了OCR
        if need_ocr and self.enable_ocr:
            logger.info(f"Page {page_no} quality low ({quality_score:.2f}), using OCR fallback")
            ocr_text, ocr_spans = self._extract_with_ocr(page)

            # 如果OCR结果更好，使用OCR结果
            if self._evaluate_text_quality(ocr_text) > quality_score:
                text, spans = ocr_text, ocr_spans
                ocr_used = True
            else:
                ocr_used = False
        else:
            ocr_used = False

        return PageInfo(
            page_no=page_no,
            text=text,
            spans=spans,
            width=width,
            height=height,
            ocr_used=ocr_used,
            quality_score=quality_score,
        )

    def _extract_text_with_spans(self, page) -> Tuple[str, List[TextSpan]]:
        """使用fitz提取文本和spans"""
        try:
            # 获取文本块
            text_dict = page.get_text("dict")
            text_content = []
            spans = []

            for block in text_dict["blocks"]:
                if "lines" in block:  # 文本块
                    for line in block["lines"]:
                        line_text = ""
                        for span in line["spans"]:
                            span_text = span["text"]
                            line_text += span_text

                            # 创建TextSpan对象
                            bbox = span["bbox"]
                            text_span = TextSpan(
                                text=span_text,
                                bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                                font_size=span.get("size", 0),
                                font_name=span.get("font", ""),
                            )
                            spans.append(text_span)

                        if line_text.strip():
                            text_content.append(line_text)

            full_text = "\n".join(text_content)
            return full_text, spans

        except Exception as e:
            logger.warning(f"Failed to extract text with spans: {e}")
            # 回退到简单文本提取
            text = page.get_text() or ""
            return text, []

    def _extract_with_ocr(self, page) -> Tuple[str, List[TextSpan]]:
        """使用OCR提取文本"""
        if not self.enable_ocr:
            return "", []

        try:
            if not self.enable_ocr or fitz is None or pytesseract is None:
                return "", []

            # 将页面转换为图片
            mat = fitz.Matrix(2.0, 2.0)  # 2倍分辨率
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")

            # 使用PIL加载图片
            image = Image.open(io.BytesIO(img_data))

            # OCR识别
            ocr_data = pytesseract.image_to_data(
                image,
                config=self.tesseract_config,
                output_type=pytesseract.Output.DICT,
                lang="chi_sim+eng",  # 中英文
            )

            # 处理OCR结果
            text_content = []
            spans = []

            for i in range(len(ocr_data["text"])):
                word = ocr_data["text"][i].strip()
                if word:
                    # 坐标需要从图片坐标转换回PDF坐标
                    x = ocr_data["left"][i] / 2.0  # 除以放大倍数
                    y = ocr_data["top"][i] / 2.0
                    w = ocr_data["width"][i] / 2.0
                    h = ocr_data["height"][i] / 2.0

                    bbox = (x, y, x + w, y + h)

                    span = TextSpan(
                        text=word,
                        bbox=bbox,
                        font_size=h,  # 高度作为字体大小
                        font_name="OCR",
                    )
                    spans.append(span)
                    text_content.append(word)

            full_text = " ".join(text_content)
            return full_text, spans

        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")
            return "", []

    def _evaluate_text_quality(self, text: str) -> float:
        """评估文本质量"""
        if not text:
            return 0.0

        # 计算中文字符比例
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        total_chars = len(text.replace(" ", "").replace("\n", ""))

        if total_chars == 0:
            return 0.0

        chinese_ratio = chinese_chars / total_chars

        # 计算缺字率（通过常见的乱码字符判断）
        garbled_chars = len(re.findall(r"[□▢▣▤▥▦▧▨▩]", text))
        garbled_ratio = garbled_chars / total_chars if total_chars > 0 else 0

        # 计算质量分数
        quality_score = chinese_ratio * (1 - garbled_ratio)

        # 如果非中文字符过多且不是数字/标点，降低分数
        non_chinese_non_punct = len(re.findall(r"[a-zA-Z]", text))
        if non_chinese_non_punct / total_chars > self.non_chinese_threshold:
            quality_score *= 0.5

        return min(1.0, quality_score)

    def get_page_text_at_bbox(
        self, page_info: PageInfo, bbox: Tuple[float, float, float, float]
    ) -> str:
        """获取指定区域的文本"""
        x0, y0, x1, y1 = bbox
        texts = []

        for span in page_info.spans:
            sx0, sy0, sx1, sy1 = span.bbox

            # 检查是否在指定区域内
            if sx0 >= x0 and sy0 >= y0 and sx1 <= x1 and sy1 <= y1:
                texts.append(span.text)

        return "".join(texts)

    def find_text_in_page(self, page_info: PageInfo, target_text: str) -> List[TextSpan]:
        """在页面中查找指定文本"""
        matching_spans = []
        target_text = target_text.strip()

        if not target_text:
            return matching_spans

        # 简单的文本匹配
        for span in page_info.spans:
            if target_text in span.text:
                matching_spans.append(span)

        # 如果没有直接匹配，尝试模糊匹配
        if not matching_spans:
            from rapidfuzz import fuzz

            for span in page_info.spans:
                if len(span.text) > 3 and fuzz.partial_ratio(target_text, span.text) > 80:
                    matching_spans.append(span)

        return matching_spans

    def _save_extracted_text(self, pdf_path: str, pages: List[PageInfo]) -> None:
        """保存提取的文本到文件"""
        try:
            pdf_dir = Path(pdf_path).parent
            text_file = pdf_dir / "extracted_text.txt"

            # 合并所有页面的文本
            full_text_parts = []
            for page in pages:
                full_text_parts.append(f"--- PAGE {page.page_no} ---")
                full_text_parts.append(page.text)
                full_text_parts.append("")  # 空行

            full_text = "\n".join(full_text_parts)

            with open(text_file, "w", encoding="utf-8") as f:
                f.write(full_text)

            logger.info(f"Extracted text saved to: {text_file}")

        except Exception as e:
            logger.warning(f"Failed to save extracted text: {e}")


# 便捷函数
def extract_text_from_pdf(
    pdf_path: str, enable_ocr: bool = True, quality_threshold: float = 0.5
) -> List[PageInfo]:
    """从PDF提取文本的便捷函数"""
    extractor = TextExtractor(enable_ocr=enable_ocr)
    return extractor.extract_from_pdf(pdf_path)


def create_page_summary(pages: List[PageInfo]) -> Dict[str, Any]:
    """创建页面提取摘要"""
    total_pages = len(pages)
    ocr_pages = sum(1 for p in pages if p.ocr_used)
    total_chars = sum(len(p.text) for p in pages)
    avg_quality = sum(p.quality_score for p in pages) / total_pages if total_pages > 0 else 0

    return {
        "total_pages": total_pages,
        "ocr_pages": ocr_pages,
        "ocr_ratio": ocr_pages / total_pages if total_pages > 0 else 0,
        "total_characters": total_chars,
        "average_quality": avg_quality,
        "quality_distribution": {
            "high": sum(1 for p in pages if p.quality_score > 0.8),
            "medium": sum(1 for p in pages if 0.5 <= p.quality_score <= 0.8),
            "low": sum(1 for p in pages if p.quality_score < 0.5),
        },
    }
