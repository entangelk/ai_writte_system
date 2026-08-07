"""이동 정의 byte-동일 재현 — 라우터 분해 Slice 1 잔여 **2차**.

기록: docs/verifications/2026-08-07/router_split_slice1_remainder_2nd.md §Findings (2).

1차용 [`repro_byte_identical.py`](repro_byte_identical.py) 와 같은 방법을 2차가
옮긴 **30 정의**(handler 25 + 직렬화기 5)에 적용한다. 이동 직전 커밋(`46ae980`)의
main.py 와 HEAD 의 신규 라우터 3종에서 이름별로 추출해 `ast.unparse` 로 비교한다.

**왜 1차 스크립트를 확장하지 않고 파일을 나눴나**: 두 슬라이스는 **베이스 커밋이
다르다**(1차 `9bc06e3` · 2차 `46ae980`). 한 파일에 합치면 어느 쪽 기대값인지가
인자로 갈리고, 각 검증 기록의 §Reproduction 이 "이 명령 하나"를 가리키지 못한다.
슬라이스당 한 파일이면 기대 출력이 고정된다 — 1차는 12/12, 2차는 30/30.

이 검사가 `repro_router_split.py` 지문의 빈칸을 닫는다 — 지문은 `dict[str, object]`
응답의 직렬화기 본문을 못 본다(response_model 없음 → OpenAPI 에 안 잡힘).

실행:
    python3 docs/verifications/2026-08-07/repro_byte_identical_2nd.py
기대: "30/30 byte-동일(AST 정규화)", exit 0
"""
import ast
import subprocess
import sys

REPO = "/mnt/d/devel/에베베/ai_writte_system"
PRE_REV = "46ae980"  # 2차 이동(`131bc2a`) 직전 커밋


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
    "projects.py": read_file("services/application/app/routers/projects.py"),
    "drafts.py": read_file("services/application/app/routers/drafts.py"),
    "source_refs.py": read_file("services/application/app/routers/source_refs.py"),
}
new = {}
for s in new_srcs.values():
    for name, bodies in collect_funcs(s).items():
        new.setdefault(name, []).extend(bodies)

# (함수명, old index, new 파일)
TARGETS = [
    # --- projects (11 operation + 직렬화기 1) ---
    ("_project_payload", 0, "projects.py"),
    ("create_project", 0, "projects.py"),
    ("list_projects", 0, "projects.py"),
    ("get_access_log", 0, "projects.py"),
    ("get_project", 0, "projects.py"),
    ("get_project_brief", 0, "projects.py"),
    ("put_project_brief", 0, "projects.py"),
    ("list_project_brief_versions", 0, "projects.py"),
    ("get_project_brief_version", 0, "projects.py"),
    ("rename_project", 0, "projects.py"),
    ("archive_project", 0, "projects.py"),
    ("export_project", 0, "projects.py"),
    # --- drafts (10 operation + 직렬화기 2) ---
    ("_draft_payload", 0, "drafts.py"),
    ("_version_meta_payload", 0, "drafts.py"),
    ("rename_draft", 0, "drafts.py"),
    ("archive_draft", 0, "drafts.py"),
    ("list_drafts", 0, "drafts.py"),
    ("get_draft", 0, "drafts.py"),
    ("list_draft_versions", 0, "drafts.py"),
    ("get_draft_version", 0, "drafts.py"),
    ("export_draft_version", 0, "drafts.py"),
    ("create_draft", 0, "drafts.py"),
    ("put_draft_order", 0, "drafts.py"),
    ("save_draft", 0, "drafts.py"),
    # --- source refs (4 operation + 직렬화기 2) ---
    ("_source_ref_payload", 0, "source_refs.py"),
    ("_rebuild_source_block_index_payload", 0, "source_refs.py"),
    ("create_source_ref", 0, "source_refs.py"),
    ("list_source_refs", 0, "source_refs.py"),
    ("get_source_ref", 0, "source_refs.py"),
    ("rebuild_source_block_index", 0, "source_refs.py"),
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
    print(f"[{'OK ' if same else 'DIFF'}] {name:36s} old@main.py -> new@{nf}")
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
print(f"{len(TARGETS)}/{len(TARGETS)} byte-동일(AST 정규화)" if allok
      else "DIFF 존재 — 위를 검토")
sys.exit(0 if allok else 1)
