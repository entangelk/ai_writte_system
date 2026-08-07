"""뮤테이션 5종 재현 — 라우터 분해 Slice 1 잔여 **3차 (analysis)**(N1~N5).

기록: docs/daily_logs/2026-08-07/work_log.md Task 5.

1·2차용(`repro_mutations.py`·`repro_mutations_2nd.py`)과 같은 절차를 3차가 옮긴
`routers/analysis.py` 와 공유 직렬화기에 적용한다.

순서: preflight(clean) → mutate → focused pytest → git checkout 원복 → 원복 clean 확인.
트리는 커밋된 상태(HEAD)이므로 `git checkout -- <path>` 가 정확히 HEAD 로 되돌린다.
★ 커밋된 트리에서만 돌린다 — 미커밋 트리에서는 `git checkout` 이 구현을 지우므로
`cp` 백업 절차를 따를 것(guides/verification.md §Mutation testing).

- **N1 이 핵심이다.** 1차가 모듈 목록을 하드코딩에서 `routers/*.py` 글롭으로 바꿨는데,
  그 처방이 **3차의 신규 모듈 analysis.py 를 자동으로 범위에 넣는가**를 N1 이 실증한다.
- **N3 가 공유를 증명한다.** `_analysis_job_payload` 를 `api/payloads.py` 에 내렸는데,
  analysis 와 writing(잔류) 이 **같은 정의 하나**를 보는지를 — payloads 본문을 망가뜨려
  양쪽 셀이 같이 물리는지로 본다. 사본이었다면 한쪽만 물린다.

실행:
    python3 docs/verifications/2026-08-07/repro_mutations_3rd.py
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
    """순환 복귀 — routers/analysis 가 다시 main 을 본다."""
    return s.replace(
        "from ..api.payloads import _analysis_job_payload, _memory_payload, _scope_payload",
        "from ..main import _analysis_job_payload, _memory_payload, _scope_payload",
    )


_REGISTER_ANALYSIS_BLOCK = (
    "    register_analysis(\n"
    "        app,\n"
    "        core_sot=core_sot,\n"
    "        analysis=analysis,\n"
    "        memory=memory,\n"
    "        runner=runner,\n"
    "        analysis_context=analysis_context,\n"
    "        compare=compare,\n"
    "        apply_service=apply_service,\n"
    "        review_queue=review_queue,\n"
    "        character_reconciliation=character_reconciliation,\n"
    "        review_inbox=review_inbox,\n"
    "        gate_findings=gate_findings,\n"
    "        llm_call_audit=llm_call_audit,\n"
    "        candidate_review=candidate_review,\n"
    "    )\n"
)


def N2_dropreg(s):
    """register_analysis 배선 삭제 — 21 operation 이 통째로 사라진다."""
    assert _REGISTER_ANALYSIS_BLOCK in s, "register_analysis block not found verbatim"
    return s.replace(_REGISTER_ANALYSIS_BLOCK, "")


def N3_dropfield(s):
    """공유 _analysis_job_payload 에서 failure_detail 키 제거 — analysis·writing 양쪽이
    같은 정의를 본다면 둘 다, 사본이면 한쪽만 영향."""
    needle = '        "failure_detail": job.failure_detail,\n'
    assert needle in s, "failure_detail line not found in payloads.py"
    return s.replace(needle, "")


def N4_swaporder(s):
    """_REQUIRE_PROJECT_OWNER_BILLABLE 의 소유권·시행 순서를 뒤집는다 — '404·403은
    무과금' 계약(=순서)을 route 선언에서 읽는 셀이 잡는가."""
    return s.replace(
        "_REQUIRE_PROJECT_OWNER_BILLABLE = [\n    *_REQUIRE_PROJECT_OWNER,\n    Depends(enforce_quota),\n]",
        "_REQUIRE_PROJECT_OWNER_BILLABLE = [\n    Depends(enforce_quota),\n    *_REQUIRE_PROJECT_OWNER,\n]",
    )


def N5_droptier(s):
    """create_analysis_job 의 소유권 tier 선언 제거 — 무인증으로 새는 방향."""
    return s.replace(
        '    @app.post("/projects/{project_id}/analysis/jobs", responses=_owned(_ERRORS_404),\n'
        "              dependencies=_REQUIRE_PROJECT_OWNER)",
        '    @app.post("/projects/{project_id}/analysis/jobs",\n'
        "              responses=_owned(_ERRORS_404))",
    )


def main():
    preflight()

    # N1: 순환 복귀 → 글롭 가드가 신규 모듈 analysis 를 자동으로 잡는가
    print("###### N1: from ..main import (순환 복귀) in routers/analysis.py ######")
    mutate("services/application/app/routers/analysis.py", N1_circ)
    rc = run(["tests/test_app_import_paths.py"],
             "N1 / import paths (expect FAIL + SUBFAILED module=…routers.analysis)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/analysis.py")

    # N2: register 배선 삭제 → tier 전수 가드
    print("###### N2: drop register_analysis call ######")
    mutate("services/application/app/main.py", N2_dropreg)
    rc = run(["tests/test_auth_api.py::CombinedBoundaryMatrixTest"
              "::test_every_operation_lands_in_exactly_one_named_tier"],
             "N2 / tier full guard (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/main.py")

    # N3: 공유 직렬화기 본문 망가뜨림 → analysis·writing 양쪽 셀이 같이 물리는가.
    # 양쪽을 다 돌린다 — analysis job payload 셀 + writing accept 의 analysis_job 필드.
    # (독립 검증 정정 2026-08-07: 종전 analysis 테스트만 돌려 docstring 의 "양쪽이
    #  물린다" 와 시위가 어긋났다. writing 반쪽을 추가해 일치시켰다.)
    print("###### N3: drop failure_detail from shared _analysis_job_payload ######")
    mutate("services/application/app/api/payloads.py", N3_dropfield)
    rc_a = run(["tests/test_application_api.py", "-k", "analysis"],
               "N3a / analysis job payload cells (expect FAIL)")
    rc_w = run(["tests/test_writing_accept.py"],
               "N3b / writing accept analysis_job 필드 (expect FAIL — 공유 증거)")
    print(f"   >> FAIL={rc_a != 0 and rc_w != 0}")
    restore("services/application/app/api/payloads.py")

    # N4: 유료 의존성 순서 뒤집기 → 시행이 소유권 앞으로(계약 위반)
    print("###### N4: swap ownership/enforcement order in _REQUIRE_PROJECT_OWNER_BILLABLE ######")
    mutate("services/application/app/api/dependencies.py", N4_swaporder)
    rc = run(["tests/test_quota_enforcement_api.py::BillableRouteWiringTest"
              "::test_enforcement_is_declared_after_ownership"],
             "N4 / billable wiring order (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/api/dependencies.py")

    # N5: 소유권 tier 선언 제거
    print("###### N5: drop dependencies on POST /analysis/jobs ######")
    mutate("services/application/app/routers/analysis.py", N5_droptier)
    rc = run(["tests/test_auth_api.py::AuthenticationBoundaryTest"
              "::test_every_operation_is_either_protected_or_a_named_exemption"],
             "N5 / auth tier exhaustive guard (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/analysis.py")

    print("\n=== pre-flight re-check (all restored) ===")
    preflight()


if __name__ == "__main__":
    main()
