"""이동 정의 byte-동일 재현 — 라우터 분해 Slice 1 잔여 **4차 (writing)**.

기록: docs/daily_logs/2026-08-07/work_log.md Task 7.

1~3차용과 같은 방법을 4차가 옮긴 **25 정의**(handler 13 + 직렬화기 9 + 헬퍼 3)에
적용한다. 이동 직전 커밋(`2a5a52c`)의 main.py 와 HEAD 의 신규 `routers/writing.py`
에서 이름별로 추출해 `ast.unparse` 로 비교한다. 헬퍼 3종(`_derive`·
`_record_loop_audit`·`_clear_scratch_for_saved_accept`)은 handler 내부 중첩이라
handler 와 함께 옮겨갔고, `ast.walk` 가 중첩을 잡으므로 같이 비교한다.
**★ [2026-08-07 독립 검증 정정]** 종전 이 스크립트는 헬퍼를 2종으로 세어
`_derive`(`get_writing_context_budget` 안 중첩)를 TARGETS 에 빠뜨렸다(24). 독립
검증의 전수 추출(25/25)이 잡아 3종으로 정정했다.

실행:
    python3 docs/verifications/2026-08-07/repro_byte_identical_4th.py
기대: "25/25 byte-동일(AST 정규화)", exit 0
"""
import ast
import subprocess
import sys

REPO = "/mnt/d/devel/에베베/ai_writte_system"
PRE_REV = "2a5a52c"  # 4차 이동 직전 커밋


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

new_src = read_file("services/application/app/routers/writing.py")
new = collect_funcs(new_src)

TARGETS = [
    # --- 직렬화기 9종 ---
    ("_writing_candidate_payload", 0),
    ("_writing_generation_job_payload", 0),
    ("_writing_gate_payload", 0),
    ("_writing_loop_payload", 0),
    ("_writing_stages_payload", 0),
    ("_writing_loop_audit_summary_payload", 0),
    ("_writing_loop_audit_payload", 0),
    ("_accepted_save_payload", 0),
    ("_writing_scratch_payload", 0),
    # --- 헬퍼 3종 (handler 내부 중첩) ---
    ("_derive", 0),
    ("_record_loop_audit", 0),
    ("_clear_scratch_for_saved_accept", 0),
    # --- handler 13 ---
    ("writing_generate_endpoint", 0),
    ("get_writing_generation_job", 0),
    ("get_writing_context_budget", 0),
    ("retry_writing_generation_job", 0),
    ("writing_gate_endpoint", 0),
    ("writing_report_endpoint", 0),
    ("writing_revise_endpoint", 0),
    ("writing_revise_and_gate_endpoint", 0),
    ("writing_loop_audits_endpoint", 0),
    ("writing_loop_audit_detail_endpoint", 0),
    ("writing_accept_endpoint", 0),
    ("writing_scratch_list_endpoint", 0),
    ("writing_scratch_discard_endpoint", 0),
]

allok = True
for name, oi in TARGETS:
    ob = old.get(name)
    nb = new.get(name)
    if ob is None:
        print(f"MISSING OLD: {name}"); allok = False; continue
    if nb is None:
        print(f"MISSING NEW: {name}"); allok = False; continue
    ob = ob[oi]; nb = nb[0]
    same = (ob == nb)
    print(f"[{'OK ' if same else 'DIFF'}] {name:38s} old@main.py -> new@writing.py")
    if not same:
        allok = False
        import difflib
        for line in difflib.unified_diff(
            ob.splitlines(), nb.splitlines(),
            fromfile=f"old main.py::{name}", tofile=f"new writing.py::{name}",
            lineterm="", n=2):
            print("    " + line)

print()
print("=== summary ===")
print(f"{len(TARGETS)}/{len(TARGETS)} byte-동일(AST 정규화)" if allok
      else "DIFF 존재 — 위를 검토")
sys.exit(0 if allok else 1)
