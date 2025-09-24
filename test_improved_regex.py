import re

# 改进后的正则表达式 - 增加更多匹配模式
_PAIR_IMPROVED = re.compile(
    r"(?:年初?\s*预算|预算|年初预算数|预算数)(?:数)?[为是]?\s*"
    r"(\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?\s*万?元?"
    r"(?:[\s\S]{0,200}?)?"  # 增加窗口大小
    r"(?:支出\s*)?决算(?:数)?[为是]?\s*"
    r"(\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?\s*万?元?"
    r"(?:[\s\S]{0,300}?)?"  # 增加窗口大小
    r"(决算(?:数)?(?:大于|小于|等于|持平|基本持平)预算(?:数)?)",
    re.S | re.I  # 添加忽略大小写
)

# 测试文本
with open('test_text.txt', 'r', encoding='utf-8') as f:
    text = f.read()

print("=== 改进后正则表达式匹配结果 ===")
matches = list(_PAIR_IMPROVED.finditer(text))
print(f"找到 {len(matches)} 个匹配")

for i, match in enumerate(matches, 1):
    budget = float(match.group(1).replace(",", ""))
    actual = float(match.group(2).replace(",", ""))
    phrase = match.group(3)
    
    # 计算实际关系（使用改进的容差）
    tol = max(0.5, 0.003 * max(abs(actual), abs(budget)))
    calc = "大于" if actual > budget + tol else ("小于" if actual < budget - tol else "持平")
    
    # 提取文中描述
    stated = (
        "持平" if "持平" in phrase
        else ("大于" if "大于" in phrase else ("小于" if "小于" in phrase else "等于"))
    )
    
    # 计算差额和百分比
    diff = abs(actual - budget)
    diff_pct = (diff / budget * 100) if budget != 0 else 0
    
    print(f"\n匹配 {i}:")
    print(f"  预算: {budget:.2f} 万元")
    print(f"  决算: {actual:.2f} 万元") 
    print(f"  差额: {diff:.2f} 万元 ({diff_pct:.1f}%)")
    print(f"  实际关系: {calc}")
    print(f"  文中描述: {stated}")
    print(f"  是否一致: {'✅' if calc == stated else '❌'}")
    if calc != stated:
        print(f"  ⚠️  问题: 实际为'{calc}'但文中描述为'{stated}'")

print(f"\n=== 分析总结 ===")
correct_count = sum(1 for m in matches if (
    lambda budget, actual, phrase: (
        "大于" if actual > budget + max(0.5, 0.003 * max(abs(actual), abs(budget))) 
        else ("小于" if actual < budget - max(0.5, 0.003 * max(abs(actual), abs(budget))) else "持平")
    ) == (
        "持平" if "持平" in phrase
        else ("大于" if "大于" in phrase else ("小于" if "小于" in phrase else "等于"))
    )
)(float(m.group(1).replace(",", "")), float(m.group(2).replace(",", "")), m.group(3)))

print(f"总共找到: {len(matches)} 个预算决算比较")
print(f"正确匹配: {correct_count} 个")
print(f"错误匹配: {len(matches) - correct_count} 个")
if len(matches) > 0:
    print(f"错误率: {(len(matches) - correct_count) / len(matches) * 100:.1f}%")
