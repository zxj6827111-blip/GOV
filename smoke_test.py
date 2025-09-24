#!/usr/bin/env python3
"""
冒烟测试脚本 - 快速验证系统基本功能
用于部署后的快速健康检查和基本功能验证
"""
import asyncio
import aiohttp
import json
import os
import sys
import time
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional


class SmokeTest:
    """冒烟测试类"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        self.results: Dict[str, Any] = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
            "start_time": None,
            "end_time": None
        }
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    def log(self, message: str, level: str = "INFO"):
        """日志记录"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
    
    def record_result(self, test_name: str, success: bool, error: str = None):
        """记录测试结果"""
        self.results["total_tests"] += 1
        if success:
            self.results["passed"] += 1
            self.log(f"✅ {test_name} - PASSED")
        else:
            self.results["failed"] += 1
            self.log(f"❌ {test_name} - FAILED: {error}", "ERROR")
            self.results["errors"].append({
                "test": test_name,
                "error": error
            })
    
    async def test_health_check(self):
        """测试健康检查端点"""
        test_name = "Health Check"
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "ok":  # 修正期望的状态值
                        self.record_result(test_name, True)
                    else:
                        self.record_result(test_name, False, f"Unhealthy status: {data}")
                else:
                    self.record_result(test_name, False, f"HTTP {response.status}")
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    async def test_api_endpoints(self):
        """测试API端点可访问性"""
        endpoints = [
            ("/docs", "API Documentation"),
            ("/openapi.json", "OpenAPI Schema")
        ]
        
        for endpoint, description in endpoints:
            test_name = f"API Endpoint - {description}"
            try:
                async with self.session.get(f"{self.base_url}{endpoint}") as response:
                    if response.status == 200:
                        self.record_result(test_name, True)
                    else:
                        self.record_result(test_name, False, f"HTTP {response.status}")
            except Exception as e:
                self.record_result(test_name, False, str(e))
    
    def create_test_pdf(self) -> str:
        """创建测试PDF文件"""
        pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
72 720 Td
(Test Budget Document) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
299
%%EOF"""
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
            f.write(pdf_content)
            return f.name
    
    async def test_analyze_endpoint_dual_mode(self):
        """测试双模式分析端点"""
        test_name = "Analyze Endpoint - Dual Mode"
        
        try:
            # 首先上传一个测试PDF文件
            pdf_path = self.create_test_pdf()
            
            # 上传文件获取job_id
            with open(pdf_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename='test.pdf', content_type='application/pdf')
                
                async with self.session.post(f"{self.base_url}/upload", data=data) as upload_response:
                    if upload_response.status != 200:
                        self.record_result(test_name, False, f"Upload failed: {upload_response.status}")
                        return
                    
                    upload_result = await upload_response.json()
                    job_id = upload_result["job_id"]
            
            # 清理测试文件
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            
            # 发送分析请求
            payload = {
                "use_local_rules": True,
                "use_ai_assist": True,
                "mode": "dual"
            }
            
            async with self.session.post(f"{self.base_url}/analyze2/{job_id}", 
                                       json=payload,
                                       headers={"Content-Type": "application/json"}) as response:
                if response.status == 200:
                    result = await response.json()
                    if self.validate_analyze_response(result, expected_mode='dual'):
                        self.record_result(test_name, True)
                    else:
                        self.record_result(test_name, False, "Invalid response structure")
                else:
                    error_text = await response.text()
                    self.record_result(test_name, False, f"HTTP {response.status}: {error_text}")
        
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    async def test_analyze_endpoint_ai_mode(self):
        """测试AI模式分析端点"""
        test_name = "Analyze Endpoint - AI Mode"
        
        try:
            # 首先上传一个测试PDF文件
            pdf_path = self.create_test_pdf()
            
            # 上传文件获取job_id
            with open(pdf_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename='test.pdf', content_type='application/pdf')
                
                async with self.session.post(f"{self.base_url}/upload", data=data) as upload_response:
                    if upload_response.status != 200:
                        self.record_result(test_name, False, f"Upload failed: {upload_response.status}")
                        return
                    
                    upload_result = await upload_response.json()
                    job_id = upload_result["job_id"]
            
            # 清理测试文件
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            
            payload = {
                "use_local_rules": False,
                "use_ai_assist": True,
                "mode": "ai"
            }
            
            async with self.session.post(f"{self.base_url}/analyze2/{job_id}", 
                                       json=payload,
                                       headers={"Content-Type": "application/json"}) as response:
                if response.status == 200:
                    result = await response.json()
                    if self.validate_analyze_response(result, expected_mode='ai'):
                        self.record_result(test_name, True)
                    else:
                        self.record_result(test_name, False, "Invalid response structure")
                else:
                    error_text = await response.text()
                    self.record_result(test_name, False, f"HTTP {response.status}: {error_text}")
        
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    async def test_analyze_endpoint_local_mode(self):
        """测试本地规则模式分析端点"""
        test_name = "Analyze Endpoint - Local Mode"
        
        try:
            # 首先上传一个测试PDF文件
            pdf_path = self.create_test_pdf()
            
            # 上传文件获取job_id
            with open(pdf_path, 'rb') as f:
                data = aiohttp.FormData()
                data.add_field('file', f, filename='test.pdf', content_type='application/pdf')
                
                async with self.session.post(f"{self.base_url}/upload", data=data) as upload_response:
                    if upload_response.status != 200:
                        self.record_result(test_name, False, f"Upload failed: {upload_response.status}")
                        return
                    
                    upload_result = await upload_response.json()
                    job_id = upload_result["job_id"]
            
            # 清理测试文件
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            
            payload = {
                "use_local_rules": True,
                "use_ai_assist": False,
                "mode": "local"
            }
            
            async with self.session.post(f"{self.base_url}/analyze2/{job_id}", 
                                       json=payload,
                                       headers={"Content-Type": "application/json"}) as response:
                if response.status == 200:
                    result = await response.json()
                    if self.validate_analyze_response(result, expected_mode='local'):
                        self.record_result(test_name, True)
                    else:
                        self.record_result(test_name, False, "Invalid response structure")
                else:
                    error_text = await response.text()
                    self.record_result(test_name, False, f"HTTP {response.status}: {error_text}")
        
        except Exception as e:
            self.record_result(test_name, False, str(e))
    
    def validate_analyze_response(self, response: Dict[str, Any], expected_mode: str = None) -> bool:
        """验证分析响应结构"""
        try:
            # 检查基本字段
            required_fields = ["mode"]
            for field in required_fields:
                if field not in response:
                    self.log(f"Missing required field: {field}", "ERROR")
                    return False
            
            # 检查模式
            if expected_mode and response.get("mode") != expected_mode:
                self.log(f"Expected mode {expected_mode}, got {response.get('mode')}", "ERROR")
                return False
            
            # 检查双模式结果结构
            if "dual_mode" in response:
                dual_mode = response["dual_mode"]
                dual_required = ["ai_findings", "rule_findings", "merged"]
                
                for field in dual_required:
                    if field not in dual_mode:
                        self.log(f"Missing dual_mode field: {field}", "ERROR")
                        return False
                
                # 检查merged结构
                merged = dual_mode["merged"]
                if "totals" not in merged:
                    self.log("Missing merged.totals field", "ERROR")
                    return False
                
                totals = merged["totals"]
                total_required = ["ai", "rule", "merged", "conflicts", "agreements"]
                for field in total_required:
                    if field not in totals:
                        self.log(f"Missing totals field: {field}", "ERROR")
                        return False
            
            return True
        
        except Exception as e:
            self.log(f"Response validation error: {e}", "ERROR")
            return False
    
    async def test_invalid_requests(self):
        """测试无效请求的处理"""
        # 先创建一个有效的job用于测试
        pdf_path = self.create_test_pdf()
        
        with open(pdf_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename='test.pdf', content_type='application/pdf')
            
            async with self.session.post(f"{self.base_url}/upload", data=data) as upload_response:
                if upload_response.status != 200:
                    self.record_result("Invalid Request Setup", False, "Failed to create test job")
                    return
                
                upload_result = await upload_response.json()
                job_id = upload_result["job_id"]
        
        # 清理测试文件
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
        
        test_cases = [
            ("Both modes disabled", {"use_local_rules": False, "use_ai_assist": False}, 400),
            ("Invalid mode", {"mode": "invalid"}, 200),  # 这个可能会成功，因为mode是可选的
            ("Empty request", {}, 200)  # 空请求会使用默认值
        ]
        
        for test_desc, data, expected_status in test_cases:
            test_name = f"Invalid Request - {test_desc}"
            try:
                async with self.session.post(f"{self.base_url}/analyze2/{job_id}", 
                                           json=data,
                                           headers={"Content-Type": "application/json"}) as response:
                    if response.status == expected_status:
                        self.record_result(test_name, True)
                    else:
                        self.record_result(test_name, False, 
                                         f"Expected HTTP {expected_status}, got {response.status}")
            except Exception as e:
                self.record_result(test_name, False, str(e))
    
    async def test_frontend_accessibility(self):
        """测试前端可访问性（如果前端服务运行在不同端口）"""
        frontend_url = "http://localhost:3000"  # Next.js默认端口
        test_name = "Frontend Accessibility"
        
        try:
            async with self.session.get(frontend_url) as response:
                if response.status == 200:
                    self.record_result(test_name, True)
                else:
                    self.record_result(test_name, False, f"HTTP {response.status}")
        except Exception as e:
            # 前端可能没有运行，这不是致命错误
            self.log(f"Frontend not accessible: {e}", "WARNING")
            self.record_result(test_name, False, f"Frontend not running: {e}")
    
    async def run_all_tests(self):
        """运行所有测试"""
        self.results["start_time"] = time.time()
        self.log("🚀 Starting smoke tests...")
        
        # 基础测试
        await self.test_health_check()
        await self.test_api_endpoints()
        
        # 功能测试
        await self.test_analyze_endpoint_dual_mode()
        await self.test_analyze_endpoint_ai_mode()
        await self.test_analyze_endpoint_local_mode()
        
        # 错误处理测试
        await self.test_invalid_requests()
        
        # 前端测试
        await self.test_frontend_accessibility()
        
        self.results["end_time"] = time.time()
        self.print_summary()
    
    def print_summary(self):
        """打印测试摘要"""
        duration = self.results["end_time"] - self.results["start_time"]
        
        print("\n" + "="*60)
        print("🧪 SMOKE TEST SUMMARY")
        print("="*60)
        print(f"Total Tests: {self.results['total_tests']}")
        print(f"✅ Passed: {self.results['passed']}")
        print(f"❌ Failed: {self.results['failed']}")
        print(f"⏱️  Duration: {duration:.2f} seconds")
        
        if self.results["failed"] > 0:
            print(f"\n🚨 FAILED TESTS ({self.results['failed']}):")
            for error in self.results["errors"]:
                print(f"  • {error['test']}: {error['error']}")
        
        success_rate = (self.results["passed"] / self.results["total_tests"]) * 100
        print(f"\n📊 Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 80:
            print("🎉 System appears to be healthy!")
            exit_code = 0
        elif success_rate >= 60:
            print("⚠️  System has some issues but core functionality works")
            exit_code = 1
        else:
            print("🚨 System has critical issues!")
            exit_code = 2
        
        print("="*60)
        return exit_code


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run smoke tests for GovBudgetChecker")
    parser.add_argument("--url", default="http://localhost:8000", 
                       help="Base URL for the API server")
    parser.add_argument("--timeout", type=int, default=30,
                       help="Request timeout in seconds")
    
    args = parser.parse_args()
    
    # 设置请求超时
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    
    async with SmokeTest(args.url) as smoke_test:
        smoke_test.session._timeout = timeout
        exit_code = await smoke_test.run_all_tests()
        sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())