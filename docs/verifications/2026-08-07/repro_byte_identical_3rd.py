"""이동 정의 byte-동일 재현 — 라우터 분해 Slice 1 잔여 **3차 (analysis)**.

기록: docs/daily_logs/2026-08-07/work_log.md Task 5.

1·2차용(`repro_byte_identical.py`·`repro_byte_identical_2nd.py`)과 같은 방법을
3차가 옮긴 **35 정의**(handler 21 + 직렬화기 13 + 헬퍼 1)에 적용한다. 이동 직전
커밋(`5aaf202`)의 main.py 와 HEAD 의 신규 `routers/analysis.py` 에서 이름별로 추출해
`ast.unparse` 로 비교한다. 공유 직렬화기 `_analysis_job_payload` 1종은
`api/payloads.py` 로 내려갔으므로 그곳과 비교한다(→ 36개).

슬라이스당 한 파일(베이스 커밋이 다르므로). 지문(`repro_router_split.py`)이
`dict[str, object]` 응답 직렬화기 본문을 못 보는 빈칸을 이 검사가 닫는다.

실행:
    python3 docs/verifications/2026-08-07/repro_byte_identical_3rd.py
기대: "36/36 byte-동일(AST 정규화)", exit 0
"""
import ast
import subprocess
import sys

REPO = "/mnt/d/devel/에베베/ai_writte_system"
PRE_REV = "5aaf202"  # 3차 이동 직전 커밋(현재 HEAD)


def get_blob(rev, path):
    return subprocess.check_output(
        ["git", "-C", REPO, "show", f"{rev}:{path}"]
    ).decode("utf-8")


def read_file(path):
    with open(f"{REPO}/{path}", encoding="utf-8") as fh:
        return fh.read()


def collect_funcs(src):
    tree = ast.parse(src)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, []).append(ast.unparse(node))
    return out


OLD_MAIN = get_blob(PRE_REV, "services/application/app/main.py")
old = collect_funcs(OLD_MAIN)

new_srcs = {
    "analysis.py": read_file("services/application/app/routers/analysis.py"),
    "payloads.py": read_file("services/application/app/api/payloads.py"),
}
new = {}
for s in new_srcs.values():
    for name, bodies in collect_funcs(s).items():
        new.setdefault(name, []).extend(bodies)

# (함수명, old index, new 파일)
TARGETS = [
    # --- 공유 직렬화기 1종 (api/payloads.py 로 내림) ---
    ("_analysis_job_payload", 0, "payloads.py"),
    # --- 직렬화기 13종 (analysis 전용) ---
    ("_analysis_candidate_payload", 0, "analysis.py"),
    ("_analysis_run_payload", 0, "analysis.py"),
    ("_candidate_review_payload", 0, "analysis.py"),
    ("_candidate_edit_payload", 0, "analysis.py"),
    ("_prior_memory_item_payload", 0, "analysis.py"),
    ("_analysis_context_payload", 0, "analysis.py"),
    ("_action_proposal_payload", 0, "analysis.py"),
    ("_applied_proposal_payload", 0, "analysis.py"),
    ("_review_queue_entry_payload", 0, "analysis.py"),
    ("_review_source_pointer", 0, "analysis.py"),
    ("_affordance_payload", 0, "analysis.py"),
    ("_review_inbox_payload", 0, "analysis.py"),
    ("_gate_finding_payload", 0, "analysis.py"),
    # --- 헬퍼 1종 ---
    ("_transition_gate_finding", 0, "analysis.py"),
    # --- handler 21개 ---
    ("create_analysis_job", 0, "analysis.py"),
    ("get_analysis_job", 0, "analysis.py"),
    ("list_analysis_candidates", 0, "analysis.py"),
    ("retry_analysis_job", 0, "analysis.py"),
    ("run_analysis_job", 0, "analysis.py"),
    ("promote_candidate", 0, "analysis.py"),
    ("confirm_candidate", 0, "analysis.py"),
    ("reject_candidate", 0, "analysis.py"),
    ("edit_candidate", 0, "analysis.py"),
    ("auto_promote_job", 0, "analysis.py"),
    ("analysis_context_endpoint", 0, "analysis.py"),
    ("analysis_compare_endpoint", 0, "analysis.py"),
    ("analysis_apply_endpoint", 0, "analysis.py"),
    ("analysis_review_queue_endpoint", 0, "analysis.py"),
    ("reconcile_character_conflict", 0, "analysis.py"),
    ("list_review_inbox", 0, "analysis.py"),
    ("get_review_inbox_item", 0, "analysis.py"),
    ("list_gate_findings", 0, "analysis.py"),
    ("get_gate_finding", 0, "analysis.py"),
    ("resolve_gate_finding", 0, "analysis.py"),
    ("dismiss_gate_finding", 0, "analysis.py"),
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
