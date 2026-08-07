"""이동 정의 byte-동일 독립 검증 재현.

기록: docs/verifications/2026-08-07/router_split_slice1_remainder_1st.md §Findings (2).

라우터 분해 Slice 1 잔여 1차에서 옮겨간 12 정의(handler 5 + 직렬화기 7)를
이동 직전 main.py(`9bc06e3`) 와 HEAD 의 신규 파일에서 이름별로 추출해
`ast.unparse` 로 비교한다. 들여쓰기는 정규화, 리터럴/키/속성/호출인자는 그대로.
`ast.unparse` 출력이 동일 == 구조·내용 동일 == (순수 함수·동일 클로저 한) 행위 동일.

이 검사가 repro_router_split.py 의 빈칸을 닫는다 — repro 지문은 `dict[str, object]`
응답의 직렬화기 본문을 못 본다(response_model 없음 → OpenAPI 에 안 잡힘).
여기서 본문까지 동일함을 12/12 로 입증한다.

실행:
    python3 docs/verifications/2026-08-07/repro_byte_identical.py
기대: "12/12 byte-동일(AST 정규화)", exit 0
"""
import ast
import subprocess
import sys

REPO = "/mnt/d/devel/에베베/ai_writte_system"
PRE_REV = "9bc06e3"  # 이동 직전 커밋(슬라이스 베이스라인)


def get_blob(rev, path):
    return subprocess.check_output(
        ["git", "-C", REPO, "show", f"{rev}:{path}"]
    ).decode("utf-8")


def read_file(path):
    with open(f"{REPO}/{path}", encoding="utf-8") as fh:
        return fh.read()


def collect_funcs(src):
    """이름 -> [ast.unparse(func), ...] (중첩 함수 포함). 동명이면 모두 모은다."""
    tree = ast.parse(src)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, []).append(ast.unparse(node))
    return out


OLD_MAIN = get_blob(PRE_REV, "services/application/app/main.py")
old = collect_funcs(OLD_MAIN)

new_srcs = {
    "payloads.py": read_file("services/application/app/api/payloads.py"),
    "context_search.py": read_file("services/application/app/routers/context_search.py"),
    "health.py": read_file("services/application/app/routers/health.py"),
    "memory.py": read_file("services/application/app/routers/memory.py"),
    "observability.py": read_file("services/application/app/routers/observability.py"),
}
new = {}
for s in new_srcs.values():
    for name, bodies in collect_funcs(s).items():
        new.setdefault(name, []).extend(bodies)

# (함수명, old index, new 파일) 매핑
TARGETS = [
    ("_project_brief_payload", 0, "payloads.py"),
    ("_memory_payload", 0, "payloads.py"),
    ("_scope_payload", 0, "payloads.py"),
    ("_context_item_payload", 0, "context_search.py"),
    ("_context_trace_payload", 0, "context_search.py"),
    ("_context_package_payload", 0, "context_search.py"),
    ("_build_context_search_request", 0, "context_search.py"),
    ("health", 0, "health.py"),
    ("list_memory", 0, "memory.py"),
    ("get_memory", 0, "memory.py"),
    ("observability_kpi_endpoint", 0, "observability.py"),
    ("context_search_endpoint", 0, "context_search.py"),
]

allok = True
for name, oi, nf in TARGETS:
    ob = old.get(name)
    nb = new.get(name)
    if ob is None:
        print(f"MISSING OLD: {name}"); allok = False; continue
    if nb is None:
        print(f"MISSING NEW: {name}"); allok = False; continue
    ob = ob[oi]; nb = nb[0]
    same = (ob == nb)
    print(f"[{'OK ' if same else 'DIFF'}] {name:34s} old@main.py -> new@{nf}")
    if not same:
        allok = False
        import difflib
        for line in difflib.unified_diff(
            ob.splitlines(), nb.splitlines(),
            fromfile=f"old main.py::{name}", tofile=f"new {nf}::{name}",
            lineterm="", n=2):
            print("    " + line)

print()
print("=== summary ===")
print("12/12 byte-동일(AST 정규화)" if allok else "DIFF 존재 — 위를 검토")
sys.exit(0 if allok else 1)
