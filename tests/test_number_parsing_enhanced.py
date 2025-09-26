#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''增强版数字解析器测试.'''

from decimal import Decimal
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from engine.robust_number_parser import RobustNumberParser


class TestEnhancedNumberParsing:
    '''覆盖中文数字、百分比与 OCR 场景的解析测试.'''

    def setup_method(self):
        self.parser = RobustNumberParser()

    @pytest.mark.parametrize(
        "chinese_text, expected",
        [
            ("三万五千", Decimal("35000")),
            ("十二万八千", Decimal("128000")),
            ("一千二百三十四万五千六百七十八", Decimal("12345678")),
            ("五千万", Decimal("50000000")),
            ("二千三百万", Decimal("23000000")),
        ],
    )
    def test_chinese_numbers(self, chinese_text, expected):
        result = self.parser.parse_number(chinese_text)
        assert result is not None, f"Failed to parse: {chinese_text}"
        assert Decimal(result) == expected, f"{chinese_text} -> {result}, expected {expected}"

    @pytest.mark.parametrize(
        "percent_text, expected",
        [
            ("12.5%", Decimal("12.5")),
            ("100%", Decimal("100")),
            ("0.25%", Decimal("0.25")),
            ("-5.5%", Decimal("-5.5")),
            ("(3.2%)", Decimal("-3.2")),
        ],
    )
    def test_percentage_formats(self, percent_text, expected):
        result = self.parser.parse_number(percent_text)
        assert result is not None, f"Failed to parse: {percent_text}"
        assert abs(Decimal(result) - expected) < Decimal("0.001"), (
            f"{percent_text} -> {result}, expected {expected}"
        )

    @pytest.mark.parametrize(
        "negative_text, expected",
        [
            ("(1,234.56)", Decimal("-1234.56")),
            ("-5,678.90", Decimal("-5678.90")),
            ("负一百二十三万", Decimal("-1230000")),
            ("下降2.5%", Decimal("-2.5")),
        ],
    )
    def test_negative_number_formats(self, negative_text, expected):
        result = self.parser.parse_number(negative_text)
        assert result is not None, f"Failed to parse: {negative_text}"
        assert abs(Decimal(result) - expected) < Decimal("0.001"), (
            f"{negative_text} -> {result}, expected {expected}"
        )

    @pytest.mark.parametrize(
        "complex_text, expected",
        [
            ("1,234,567.89", Decimal("1234567.89")),
            ("12.34亿", Decimal("1234000000")),
            ("5.6亿", Decimal("560000000")),
            ("三万二千", Decimal("32000")),
            ("二千三百四十五万六千七百八十九", Decimal("23456789")),
        ],
    )
    def test_complex_formats(self, complex_text, expected):
        result = self.parser.parse_number(complex_text)
        assert result is not None, f"Failed to parse: {complex_text}"
        assert abs(Decimal(result) - expected) < Decimal("1"), (
            f"{complex_text} -> {result}, expected {expected}"
        )

    @pytest.mark.parametrize(
        "ocr_text, expected",
        [
            ("l23,456", Decimal("123456")),
            ("O.5", Decimal("0.5")),
            ("1Z3.45", Decimal("123.45")),
            ("5OO", Decimal("500")),
            ("1O34", Decimal("1034")),
        ],
    )
    def test_ocr_common_errors(self, ocr_text, expected):
        result = self.parser.parse_number(ocr_text)
        assert result is not None, f"Failed to parse after OCR fix: {ocr_text}"
        assert abs(Decimal(result) - expected) < Decimal("0.001"), (
            f"{ocr_text} -> {result}, expected {expected}"
        )

    def test_parsing_error_tracking(self):
        invalid_texts = ["abc", "无效", "###", ""]
        failures = sum(
            1 for text in invalid_texts if self.parser.parse_number(text) is None
        )
        assert failures == len(invalid_texts), (
            f"Expected all {len(invalid_texts)} to fail, but only {failures} failed"
        )

    @pytest.mark.parametrize(
        "baseline, candidate, tolerance, expected",
        [
            (Decimal("1000"), Decimal("1005"), Decimal("0.01"), True),
            (Decimal("1000"), Decimal("1015"), Decimal("0.01"), False),
            (Decimal("100"), Decimal("101"), Decimal("0.005"), False),
            (Decimal("100"), Decimal("100.4"), Decimal("0.005"), True),
        ],
    )
    def test_tolerance_calculation(self, baseline, candidate, tolerance, expected):
        result = self.parser.calculate_tolerance(baseline, candidate, tolerance)
        assert result == expected, (
            f"tolerance({baseline}, {candidate}, {tolerance}) = {result}, expected {expected}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
