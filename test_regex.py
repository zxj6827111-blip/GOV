import re

# 当前的正则表达式
_PAIR = re.compile(
    r"(?:年初?\s*预算|预算|年初预算数|预算数)(?:数)?[为是]?\s*"
    r"(\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?\s*万?元?"
    r"(?:[\s\S]{0,160}?)?"
    r"(?:支出\s*)?决算(?:数)?[为是]?\s*"
    r"(\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?\s*万?元?"
    r"(?:[\s\S]{0,240}?)?"
    r"(决算(?:数)?(?:大于|小于|等于|持平|基本持平)预算(?:数)?)",
    re.S
)

# 测试文本
with open('test_text.txt', 'r', encoding='utf-8') as f:
    text = f.read()

print("=== 当前正则表达式匹配结果 ===")
matches = list(_PAIR.finditer(text))
print(f"找到 {len(matches)} 个匹配")

for i, match in enumerate(matches, 1):
    budget = float(match.group(1).replace(",", ""))
    actual = float(match.group(2).replace(",", ""))
    phrase = match.group(3)
    
    # 计算实际关系
    tol = max(0.5, 0.003 * max(abs(actual), abs(budget)))
    calc = "大于" if actual > budget + tol else ("小于" if actual < budget - tol else "持平")
    
    # 提取文中描述
    stated = (
        "持平" if "持平" in phrase
        else ("大于" if "大于" in phrase else ("小于" if "小于" in phrase else "等于"))
    )
    
    print(f"\n匹配 {i}:")
    print(f"  预算: {budget} 万元")
    print(f"  决算: {actual} 万元") 
    print(f"  实际关系: {calc}")
    print(f"  文中描述: {stated}")
    print(f"  是否一致: {'✅' if calc == stated else '❌'}")
    print(f"  匹配文本: {match.group(0)[:100]}...")

print(f"\n=== 总结 ===")
print(f"应该找到6个问题，实际找到{len(matches)}个")
