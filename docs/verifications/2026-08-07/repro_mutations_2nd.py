"""뮤테이션 5종 재현 — 라우터 분해 Slice 1 잔여 **2차**(N1~N5).

기록: docs/verifications/2026-08-07/router_split_slice1_remainder_2nd.md §Findings (6)
      · 작업 로그 docs/daily_logs/2026-08-07/work_log.md §Task 3.

1차용 [`repro_mutations.py`](repro_mutations.py)(M1~M5)와 같은 절차를 2차가 옮긴
세 라우터(`projects`·`drafts`·`source_refs`)에 적용한다.

순서: preflight(clean) → mutate → focused pytest → git checkout 원복 → 원복 clean 확인.
트리는 커밋된 상태(HEAD)이므로 `git checkout -- <path>` 가 정확히 HEAD 로 되돌린다.
★ 커밋된 트리에서만 돌린다 — 남의 미커밋 트리에서는 `git checkout` 이 미커밋 구현을
지우므로 `cp` 백업 절차를 따를 것(guides/verification.md §Mutation testing).

**N1 이 이 슬라이스의 핵심이다.** 1차가 `test_a_router_module_loads_before_main` 의
모듈 목록을 하드코딩(admin·auth)에서 `routers/*.py` 글롭으로 바꿨는데, 그 처방이
**2차의 신규 모듈을 자동으로 범위에 넣는가**를 N1 이 실증한다. 하드코딩이었다면
`routers/projects.py` 에 순환을 되살려도 그 셀은 조용히 통과한다.

실행:
    python3 docs/verifications/2026-08-07/repro_mutations_2nd.py
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
    """순환 복귀 — routers 가 다시 main 을 본다."""
    return s.replace("from ..api.payloads import _project_brief_payload",
                     "from ..main import _project_brief_payload")


def N2_dropreg(s):
    """register_projects 배선 삭제 — 11 operation 이 통째로 사라진다."""
    return s.replace(
        "    register_projects(\n"
        "        app,\n"
        "        core_sot=core_sot, access_grants=access_grants, sync_outbox=sync_outbox,\n"
        "    )\n\n", "")


def N3_drop503(s):
    """list_drafts 의 데이터 무결성 503 분기 제거 — 방어를 *없애는* 방향."""
    start = s.index("        except DraftOrderIntegrityError as exc:")
    end = s.index('        return {"drafts": [_draft_payload(d) for d in drafts]}')
    return s[:start] + s[end:]


def N4_502to500(s):
    """rebuild 의 임베딩 실패 매핑을 502 → 500 으로 오염."""
    i = s.index("        except EmbeddingProviderError as exc:")
    j = s.index("\n", s.index("raise HTTPException", i))
    seg = s[i:j + 1]
    return s[:i] + seg.replace("status_code=502", "status_code=500") + s[j + 1:]


def N5_droptier(s):
    """POST /projects 의 인증 tier 선언 제거 — 무인증으로 새는 방향."""
    return s.replace(
        '    @app.post("/projects", response_model=ProjectPayload,\n'
        "              responses=_ERRORS_STORAGE,\n"
        "              dependencies=_REQUIRE_AUTH)",
        '    @app.post("/projects", response_model=ProjectPayload,\n'
        "              responses=_ERRORS_STORAGE)")


def main():
    preflight()

    # N1: 순환 복귀 → 글롭 가드가 신규 모듈을 자동으로 잡는가
    print("###### N1: from ..main import (순환 복귀) in routers/projects.py ######")
    mutate("services/application/app/routers/projects.py", N1_circ)
    rc = run(["tests/test_app_import_paths.py"],
             "N1 / import paths (expect FAIL + SUBFAILED module=…routers.projects)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/projects.py")

    # N2: register 배선 삭제 → tier 전수 가드
    print("###### N2: drop register_projects call ######")
    mutate("services/application/app/main.py", N2_dropreg)
    rc = run(["tests/test_auth_api.py::CombinedBoundaryMatrixTest"
              "::test_every_operation_lands_in_exactly_one_named_tier"],
             "N2 / tier full guard (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/main.py")

    # N3: 데이터 무결성 503 분기 제거 (방어 제거 방향)
    print("###### N3: drop DraftOrderIntegrityError → 503 branch ######")
    mutate("services/application/app/routers/drafts.py", N3_drop503)
    rc = run(["tests/test_application_api.py::LegacyOrderedDraftMigration503Test"
              "::test_list_drafts_on_legacy_data_returns_503"],
             "N3 / migration-503 cell (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/drafts.py")

    # N4: 502 → 500 분류 오염
    print("###### N4: embedding failure 502 → 500 ######")
    mutate("services/application/app/routers/source_refs.py", N4_502to500)
    rc = run(["tests/test_application_api.py::SourceBlockRebuildEmbeddingFailureTest"
              "::test_embedding_failure_is_502_with_the_uniform_body"],
             "N4 / rebuild-502 cell (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/source_refs.py")

    # N5: 인증 tier 선언 제거
    print("###### N5: drop dependencies=_REQUIRE_AUTH on POST /projects ######")
    mutate("services/application/app/routers/projects.py", N5_droptier)
    rc = run(["tests/test_auth_api.py::AuthenticationBoundaryTest"
              "::test_every_operation_is_either_protected_or_a_named_exemption"],
             "N5 / auth tier exhaustive guard (expect FAIL)")
    print(f"   >> FAIL={rc != 0}")
    restore("services/application/app/routers/projects.py")

    print("\n=== pre-flight re-check (all restored) ===")
    preflight()


if __name__ == "__main__":
    main()
