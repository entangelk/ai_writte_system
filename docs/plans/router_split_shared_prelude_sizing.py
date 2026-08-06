#!/usr/bin/env python3
"""ⓑ(공유 prelude 추출)의 실제 크기를 잰다.

물음: `main.py` 의 prelude 정의 중 **라우터가 보는 것**은 몇 개인가?
      (= 잔여 7 도메인까지 옮기고 나면 main.py 밖으로 나가야 하는 집합)

방법:
  1. prelude = `create_app` 정의 앞의 모듈 수준 정의 전부.
  2. handler = `create_app` 본문 안에서 `@app.<method>` 데코레이터를 단 중첩 함수.
  3. handler 가 참조하는 이름(본문 · 시그니처 annotation · 데코레이터 인자) ∩ prelude
     = **잔여 도메인이 끌고 나갈 공유 심볼**.
  4. 이미 나간 2개 라우터가 `from ..main` 으로 가져가는 것과 합집합 = **최종 집합**.
  5. 나머지 prelude = main.py 에 남는 것(조립 helper·기본 협력자 팩토리 등).
"""

from __future__ import annotations

import ast
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]

APP = ROOT / "services" / "application" / "app"
MAIN = APP / "main.py"

tree = ast.parse(MAIN.read_text(encoding="utf-8"))
create_app = next(
    n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "create_app"
)


def _bound_names(node: ast.AST) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        return [t.id for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


# --- 1. prelude ------------------------------------------------------------
prelude: dict[str, ast.AST] = {}
imported: set[str] = set()
for node in tree.body:
    if node.lineno >= create_app.lineno:
        continue
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        imported |= {a.asname or a.name.split(".")[0] for a in node.names}
        continue
    for name in _bound_names(node):
        prelude[name] = node


# --- 2. handler 수집 -------------------------------------------------------
HTTP = {"get", "post", "put", "patch", "delete", "head", "options"}


def _is_route(dec: ast.AST) -> bool:
    call = dec.func if isinstance(dec, ast.Call) else dec
    return (
        isinstance(call, ast.Attribute)
        and call.attr in HTTP
        and isinstance(call.value, ast.Name)
        and call.value.id == "app"
    )


handlers = [
    node
    for node in ast.walk(create_app)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    and any(_is_route(d) for d in node.decorator_list)
]


# --- 3. handler 가 참조하는 prelude 심볼 -----------------------------------
used: dict[str, set[str]] = defaultdict(set)
for handler in handlers:
    for sub in ast.walk(handler):
        if isinstance(sub, ast.Name) and sub.id in prelude:
            used[sub.id].add(handler.name)

remaining = set(used)


# --- 4. 이미 나간 라우터가 가져가는 것 -------------------------------------
moved: set[str] = set()
for router in sorted((APP / "routers").glob("*.py")):
    rt = ast.parse(router.read_text(encoding="utf-8"))
    for node in ast.walk(rt):
        if isinstance(node, ast.ImportFrom) and node.module == "main" and node.level == 2:
            moved |= {a.name for a in node.names}

# ★ 전이 폐포 — 모델이 서로를 필드로 참조하므로 직접 참조만 세면 46개를 놓친다
#   (실측: 직접 88 → 폐포 134). 이 한 줄이 브리프 §4 의 숫자를 가른다.
terminal = set(remaining) | (moved & set(prelude))
frontier = set(terminal)
while frontier:
    nxt = {
        s.id
        for name in frontier
        for s in ast.walk(prelude[name])
        if isinstance(s, ast.Name) and s.id in prelude and s.id not in terminal
    }
    terminal |= nxt
    frontier = nxt
stays = set(prelude) - terminal


# --- 5. 범주 분류 ----------------------------------------------------------
def category(name: str) -> str:
    node = prelude.get(name)
    if node is None:
        return "재수출(다른 모듈 정의)"
    if isinstance(node, ast.ClassDef):
        bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
        bases |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
        if "BaseModel" in bases:
            return "요청/응답 모델"
        if any("Error" in b or "Exception" in b for b in bases):
            return "예외"
        return f"클래스({'/'.join(sorted(bases)) or 'plain'})"
    if name.startswith("_ERRORS"):
        return "_ERRORS_* (에러 선언 dict)"
    if name.startswith("_REQUIRE"):
        return "_REQUIRE_* (의존성 묶음)"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "함수(의존성·헬퍼)"
    return "상수/기타"


def report(title: str, names: set[str]) -> None:
    buckets: dict[str, list[str]] = defaultdict(list)
    lines: dict[str, int] = defaultdict(int)
    for n in sorted(names):
        buckets[category(n)].append(n)
        node = prelude.get(n)
        if node is not None:
            lines[category(n)] += node.end_lineno - node.lineno + 1
    print(f"\n{title} — 총 {len(names)}개 / {sum(lines.values()):,}줄")
    for cat, items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(items):3}개 {lines[cat]:>5}줄  {cat}")
        print(f"                   {', '.join(items[:5])}{' …' if len(items) > 5 else ''}")


print(f"main.py {len(MAIN.read_text(encoding='utf-8').splitlines()):,}줄 "
      f"· prelude 정의 {len(prelude)}개 · create_app 안 handler {len(handlers)}개")
print(f"이미 나간 라우터가 `from ..main` 으로 가져가는 것: {len(moved)}개")
report("[A] 잔여 handler 가 직접 쓰는 prelude 심볼(폐포 전)", set(remaining))
report("[B] 최종 이동 집합 (전이 폐포 포함) ← 브리프 §4", terminal)
report("[C] main.py 에 남는 것 = 조립 모듈", stays)

print(f"\n요약: prelude {len(prelude)}개 중 **{len(terminal)}개가 나가고 {len(stays)}개가 남는다** "
      f"(지금 나간 것은 {len(moved)}개).")
