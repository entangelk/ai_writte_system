"""`10_layout_probe.sh` 가 넘긴 측정 JSON 을 표로 찍는다 (Slice 10.4)."""
import json
import sys

data = json.load(sys.stdin)
print(f"viewport {data['viewport']}px · 헤더 오른쪽 끝 {data['headerRight']}")
for row in data["rows"]:
    print(
        f"  {row['screen']:<16} 콘텐츠까지 {row['chromeToContent']:>4}px"
        f" · h1 {row['h1Height']:>3}px"
        f" · 첫 화면의 {row['firstScreenPct']:>2}%"
        f" · 오른쪽 끝 {row['rightEdge']}"
    )
