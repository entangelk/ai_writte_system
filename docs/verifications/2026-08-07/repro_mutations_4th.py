"""뮤테이션 5종 재현 — 라우터 분해 Slice 1 잔여 **4차 (writing)**(N1~N5).

기록: docs/daily_logs/2026-08-07/work_log.md Task 7.

1~3차용과 같은 절차를 4차가 옮긴 `routers/writing.py` 에 적용한다. 4차는
**partial envelope 5곳**과 **유료 6경로** 가 특징이라 N3(partial envelope 분류
오염)·N4(유료 의존성 순서) 를 추가 의심축으로 잡는다(3차 독립 검증이 미리 지목).

순서: preflight(clean) → mutate → focused pytest → git checkout 원복 → 원복 clean 확인.
★ 커밋된 트리에서만 돌린다.

실행:
    python3 docs/verifications/2026-08-07/repro_mutations_4th.py
기대: N1~N5 전부 FAIL(=가드가 문다), 마지막 preflight 재확인 통과
"""
import pathlib
import subprocess
import sys

REPO = "/mnt/d/devel/에베베/ai_writte_system"
PY = ["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header"]


def sh(cmd):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)


def preflight():
    st = sh(["git", "status", "--short"]).stdout
    if st.strip():
        print("PREFLIGHT FAIL: dirty tree:\n" + st); sys.exit(1)
    print("preflight: tree clean ✓\n")


def restore(path):
    sh(["git", "checkout", "--", path])
    st = sh(["git", "status", "--short"]).stdout
    if st.strip():
        print(f"!! RESTORE FAIL ({path}):\n" + st); sys.exit(1)
    print(f"  [restored] {path} → clean\n")


def run(args, label):
    print(f"── {label} ──")
    print("   $ pytest " + " ".join(args))
    r = sh(PY + args)
    out = (r.stdout + r.stderr).splitlines()
    for l in out[-14:]:
        print("   " + l)
    print(f"   returncode={r.returncode}")
    return r.returncode


def mutate(path, fn):
    p = pathlib.Path(REPO) / path
    before = p.read_text(encoding="utf-8")
    after = fn(before)
    assert after != before, f"mutation produced no change in {path}"
    p.write_text(after, encoding="utf-8")


def N1_circ(s):
    """순환 복귀 — routers/writing 이 다시 main 을 본다."""
    return s.replace("from ..api.payloads import _analysis_job_payload",
                     "from ..main import _analysis_job_payload")


_REGISTER_WRITING_BLOCK = (
    "    register_writing(\n"
    "        app,\n"
    "        core_sot=core_sot,\n"
    "        writing=writing,\n"
    "        writing_gate=writing_gate,\n"
    "        writing_report=writing_report,\n"
    "        writing_revision=writing_revision,\n"
    "        writing_revise_gate=writing_revise_gate,\n"
    "        writing_accept=writing_accept,\n"
    "        writing_generation_jobs=writing_generation_jobs,\n"
    "        writing_scratch=writing_scratch,\n"
    "        writing_loop_audit=writing_loop_audit,\n"
    "        context_search=context_search,\n"
    "        llm_call_audit=llm_call_audit,\n"
    "        model_capabilities=model_capabilities,\n"
    "        report_output_cap=report_output_cap,\n"
    "    )\n"
)


def N2_dropreg(s):
    """register_writing 배선 삭제 — 13 operation 이 통째로 사라진다."""
    assert _REGISTER_WRITING_BLOCK in s, "register_writing block not found verbatim"
    return s.replace(_REGISTER_WRITING_BLOCK, "")


def N3_partial(s):
    """accept 의 partial envelope(analysis_error) 상태코드 502 → 500 — H3 분류
    오염. partial envelope 계약(되돌릴 수 없는 성공 부분 + 실패 상태코드)을 셀이
    잡는가."""
    needle = '                return JSONResponse(status_code=502, content={\n                    "accepted": True,'
    assert needle in s, "accept partial envelope (502) not found"
    return s.replace(needle,
        '                return JSONResponse(status_code=500, content={\n                    "accepted": True,')


def N4_swaporder(s):
    """_REQUIRE_PROJECT_OWNER_BILLABLE 소유권·시행 순서 뒤집기(3차와 동일)."""
    return s.replace(
        "_REQUIRE_PROJECT_OWNER_BILLABLE = [\n    *_REQUIRE_PROJECT_OWNER,\n    Depends(enforce_quota),\n]",
        "_REQUIRE_PROJECT_OWNER_BILLABLE = [\n    Depends(enforce_quota),\n    *_REQUIRE_PROJECT_OWNER,\n]",
    )


def N5_droptier(s):
    """GET /writing/budget 의 소유권 tier 선언 제거 — 무인증으로 새는 방향."""
    return s.replace(
        '    @app.get("/projects/{project_id}/writing/budget",\n'
        "             response_model=WritingContextBudgetPayload,\n"
        "             responses=_owned(_ERRORS_404),\n"
        "             dependencies=_REQUIRE_PROJECT_OWNER)",
        '    @app.get("/projects/{project_id}/writing/budget",\n'
        "             response_model=WritingContextBudgetPayload,\n"
        "             responses=_owned(_ERRORS_404))",
    )


def main():
    preflight()

    print("###### N1: from ..main import (순환 복귀) in routers/writing.py ######")
    mutate("services/application/app/routers/writing.py", N1_circ)
    rc = run(["tests/test_app_import_paths.py"],
             "N1 / import paths (expect FAIL + SUBFAILED module=…routers.writing)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/writing.py")

    print("###### N2: drop register_writing call ######")
    mutate("services/application/app/main.py", N2_dropreg)
    rc = run(["tests/test_auth_api.py::CombinedBoundaryMatrixTest"
              "::test_every_operation_lands_in_exactly_one_named_tier"],
             "N2 / tier full guard (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/main.py")

    print("###### N3: accept partial envelope 502 → 500 (H3 분류 오염) ######")
    mutate("services/application/app/routers/writing.py", N3_partial)
    rc = run(["tests/test_writing_accept.py", "-k", "partial"],
             "N3 / partial envelope cells (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/writing.py")

    print("###### N4: swap ownership/enforcement order in _REQUIRE_PROJECT_OWNER_BILLABLE ######")
    mutate("services/application/app/api/dependencies.py", N4_swaporder)
    rc = run(["tests/test_quota_enforcement_api.py::BillableRouteWiringTest"
              "::test_enforcement_is_declared_after_ownership"],
             "N4 / billable wiring order (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/api/dependencies.py")

    print("###### N5: drop dependencies on GET /writing/budget ######")
    mutate("services/application/app/routers/writing.py", N5_droptier)
    rc = run(["tests/test_auth_api.py::AuthenticationBoundaryTest"
              "::test_every_operation_is_either_protected_or_a_named_exemption"],
             "N5 / auth tier exhaustive guard (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/writing.py")

    print("\n=== pre-flight re-check (all restored) ===")
    preflight()


if __name__ == "__main__":
    main()
