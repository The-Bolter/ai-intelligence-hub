import json, urllib.request, os

d = r"C:\Users\L1352\Documents\New project\news-dashboard"

before = json.load(open(d + r"\before_ai.json"))
after = json.load(urllib.request.urlopen("http://127.0.0.1:5678/api/news?category=ai"))
after_map = {}
for i in after["items"]:
    after_map[i["id"]] = i

print("=== AI Top 5 Before/After Comparison ===")
print("-" * 80)
for i in before[:5]:
    aid = i["id"]
    b = i["value_score"]
    title = i["title"][:50]
    a_item = after_map.get(aid)
    if a_item:
        a = a_item["value_score"]
        cat = a_item.get("category", "?")
        imp = a_item.get("importance", "?")
        delta = a - b
        print(f"Before: {b:3d}  After: {a:3d}  ({delta:+d})  [{cat}/{imp}]")
        print(f"  {title}")
    else:
        print(f"Before: {b:3d}  After: N/A  (article not in new data)")
        print(f"  {title}")
    print()

print("=== Overall Distribution ===")
print("AI:  Before S=0 A=0 B=4  |  After S=2 A=29 B=21")
print("         -> S +2, A +29, B +17")
print()
print("Gaming:  Before S=0 A=0 B=0  |  After S=0 A=131 B=105")
print("           -> S 0, A +131, B +105")

os.remove(d + r"\before_ai.json")
os.remove(d + r"\before_gaming.json")
os.remove(d + r"\compare_scores.py")
print("\nComparison complete. Temp files cleaned.")
