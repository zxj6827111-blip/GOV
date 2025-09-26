#!/usr/bin/env python3
"""
修复测试文件中的中文编码问题
"""

import glob
import os
import re


def fix_chinese_encoding_in_file(file_path):
    """修复单个文件中的中文编码问题"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查是否包含乱码的中文字符
        if re.search(r"[\u4e00-\u9fff]", content):
            # 尝试修复常见的编码问题
            # 这里只是简单替换，实际情况可能需要更复杂的处理
            fixed_content = content

            # 替换一些常见的乱码模式
            replacements = {
                "妫€娴嬮棶棰?": "检测问题",
                "妫€娴嬪埌鐨勯绠楁墽琛岄棶棰?": "检测到的预算执行问题",
                "棰勭畻鎵ц": "预算执行",
                "寮傚父": "异常",
                "妫€娴?": "检测",
                "娴嬭瘯": "测试",
                "鍒涘缓": "创建",
                "璁剧疆": "设置",
                "鍒濆鍖?": "初始化",
                "楠岃瘉": "验证",
                "鍒嗘瀽": "分析",
                "缁撴灉": "结果",
                "鎴愬姛": "成功",
                "澶辫触": "失败",
                "閿欒": "错误",
                "澶勭悊": "处理",
                "鍔熻兘": "功能",
                "妯″瀷": "模型",
                "鏁版嵁": "数据",
                "鏂囦欢": "文件",
                "鏂囨湰": "文本",
                "鍐呭": "内容",
                "淇℃伅": "信息",
                "娑堟伅": "消息",
                "闂": "问题",
                "鎻愮ず": "提示",
                "寤鸿": "建议",
                "鎶ュ憡": "报告",
                "缁熻": "统计",
                "鐘舵€?": "状态",
                "鏈嶅姟": "服务",
                "瀹㈡埛绔?": "客户端",
                "鏈嶅姟鍣?": "服务器",
                "鎺ュ彛": "接口",
                "璇锋眰": "请求",
                "鍝嶅簲": "响应",
                "杩炴帴": "连接",
                "閰嶇疆": "配置",
                "鍙傛暟": "参数",
                "杩斿洖": "返回",
                "鎵ц": "执行",
                "杩愯": "运行",
                "鍚姩": "启动",
                "鍋滄": "停止",
                "鍏抽棴": "关闭",
                "寮€鍚?": "开启",
                "鍚敤": "启用",
                "绂佺敤": "禁用",
                "鍙敤": "可用",
                "涓嶅彲鐢?": "不可用",
                "姝ｅ父": "正常",
                "璀﹀憡": "警告",
                "鎻愰啋": "提醒",
                "閫氱煡": "通知",
                "鏃ュ織": "日志",
                "璁板綍": "记录",
                "淇濆瓨": "保存",
                "鍔犺浇": "加载",
                "鍒锋柊": "刷新",
                "鏇存柊": "更新",
                "鍒犻櫎": "删除",
                "娣诲姞": "添加",
                "淇敼": "修改",
                "缂栬緫": "编辑",
                "鏌ョ湅": "查看",
                "鏌ヨ": "查询",
                "鎼滅储": "搜索",
                "杩囨护": "过滤",
                "鎺掑簭": "排序",
                "鍒嗙粍": "分组",
                "鍒嗙被": "分类",
                "鍒嗛〉": "分页",
                "缈婚〉": "翻页",
                "涓婁竴椤?": "上一页",
                "涓嬩竴椤?": "下一页",
                "棣栭〉": "首页",
                "鏈〉": "末页",
                "鎬昏": "总计",
                "鍚堣": "合计",
                "骞冲潎": "平均",
                "鏈€澶?": "最大",
                "鏈€灏?": "最小",
                "鏈€楂?": "最高",
                "鏈€浣?": "最低",
                "涓婂崌": "上升",
                "涓嬮檷": "下降",
                "澧為暱": "增长",
                "鍑忓皯": "减少",
                "澧炲姞": "增加",
                "鎻愰珮": "提高",
                "闄嶄綆": "降低",
                "鏀瑰杽": "改善",
                "浼樺寲": "优化",
                "鎻愬崌": "提升",
                "鍔犲己": "加强",
                "鍑忓急": "减弱",
                "澧炲己": "增强",
            }

            for old, new in replacements.items():
                fixed_content = fixed_content.replace(old, new)

            # 如果内容有变化，写回文件
            if fixed_content != content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(fixed_content)
                print(f"Fixed encoding in: {file_path}")
                return True

        return False
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """主函数"""
    test_dir = "tests"
    if not os.path.exists(test_dir):
        print(f"Test directory {test_dir} not found")
        return

    # 查找所有Python测试文件
    test_files = glob.glob(os.path.join(test_dir, "*.py"))
    test_files.extend(glob.glob(os.path.join(test_dir, "**", "*.py"), recursive=True))

    fixed_count = 0
    for file_path in test_files:
        if fix_chinese_encoding_in_file(file_path):
            fixed_count += 1

    print(f"Fixed encoding in {fixed_count} files")


if __name__ == "__main__":
    main()