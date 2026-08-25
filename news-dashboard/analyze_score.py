import pathlib, json, urllib.request, sys

d = pathlib.Path(__file__).parent
rules_mod = d / "rules.py"
code = rules_mod.read_text("utf-8")

print("=" * 60)
print("1. BASE_SCORE check")
print("=" * 60)
has_base = "BASE_SCORE" in code
print("BASE_SCORE exists in rules.py:", "YES" if has_base else "NO")
if not has_base:
    print(">> 结论: rules.py 中没有定义 BASE_SCORE")
    print(">> 类别基础分（如\"新模型发布\"=35）从未被实现")

print()
print("=" * 60)
print("2. _compute_value_score() 公式分析")
print("=" * 60)
print("公式: total += min(keyword_sum, max) * weight")
print("最终: return int(total)  ← 向下取整")
print()
print("问题1: int(total) 会截断小数。如果 total=0.99 → 返回 0")
print("问题2: 关键词分(5-15) x 权重(0.2-0.4) = 单次匹配仅贡献 1-6 分")
print("问题3: 3次关键词匹配才能产生 ~10 分，但很多文章匹配不到")
print("问题4: 分类基础分(BASE_SCORE)完全缺失")

print()
print("=" * 60)
print("3. 当前维度配置")
print("=" * 60)
sys.path.insert(0, str(d))
import importlib.util
spec = importlib.util.spec_from_file_location("rules", str(rules_mod))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

for name, cfg in r.AI_SCORE_DIMENSIONS.items():
    max_v = cfg["max"]
    weight = cfg["weight"]
    kws = cfg["keywords"]
    sample = dict(list(kws.items())[:3])
    max_possible = max_v * weight
    print(f"  {name}: max={max_v}, weight={weight}, max_contrib={max_possible:.1f}")
    print(f"    sample keywords: {sample}")

print()
print("=" * 60)
print("4. 一篇AI文章的完整评分追踪")
print("=" * 60)
api_data = json.load(urllib.request.urlopen("http://127.0.0.1:5678/api/news?category=ai"))
item = api_data["items"][0]

title = (item.get("title") or "")[:80]
summary = (item.get("summary") or "")[:120]
text = (title + " " + summary).lower()

print("Title:", title)
print("Summary:", summary)
print()
print("分类信息:")
print("  technology_type:", item.get("technology_type"))
print("  category:", item.get("category"))
print("  application:", item.get("application"))
print("  value_score:", item.get("value_score"))
print()

total = 0
for name, cfg in r.AI_SCORE_DIMENSIONS.items():
    raw_score = 0
    matches = []
    for kw, pts in cfg["keywords"].items():
        if kw.lower() in text:
            raw_score += pts
            matches.append((kw, pts))
    capped = min(raw_score, cfg["max"])
    contrib = capped * cfg["weight"]
    total += contrib
    print(f"  {name}:")
    print(f"    matched {len(matches)} keywords: {matches}")
    print(f"    raw={raw_score}, capped={capped}, weight={cfg['weight']}, contrib={contrib:.1f}")
    print()

print(f"  总分: {total:.2f}")
print(f"  int(total) = {int(total)}")
print(f"  importance 阈值: S>=60, A>=40, B>=20, C>=8")
print(f"  距离 A 级还需: {max(40 - total, 0):.1f} 分")

print()
print("=" * 60)
print("5. 为什么大部分文章低于20分？")
print("=" * 60)
print("a) 分类基础分为0: 原设计每个类别有BASE_SCORE(如35分)")
print("   但 _compute_value_score() 只靠关键词匹配，不读取类别基础分")
print()
print("b) 一篇典型的\"模型发布\"文章:")
print("   标题含\"gpt\"(10) + \"model\"(8) + \"new\"(8) + \"release\"(10)")
print("   practicality: 10+8=18 → min(18,100)=18 → 18*0.40=7.2")
print("   efficiency:   0 → 0*0.35=0")
print("   trend:        8+10=18 → min(18,100)=18 → 18*0.25=4.5")
print("   total: 7.2+0+4.5=11.7 → int(11.7)=11 → C级")
print()
print("c) 如果有 BASE_SCORE=35:")
print("   35 + 11.7 = 46.7 → int(46.7)=46 → A级")

import os
os.remove(str(d / "analyze_score.py"))
print("\\nSelf-cleaned")
