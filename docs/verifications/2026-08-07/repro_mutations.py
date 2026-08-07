"""뮤테이션 5종 독립 검증 재현.

기록: docs/verifications/2026-08-07/router_split_slice1_remainder_1st.md §Findings (5).

슬라이스 검증용 뮤테이션 5종 재실행. 각 셀이 (이 슬라이스가 잠갔다고 주장하는)
결함에 실제로 물리는지를 되돌려 확인한다.

순서: preflight(clean) → mutate → focused pytest → git checkout 원복 → 원복 clean 확인.
트리는 커밋된 상태(HEAD)이므로 `git checkout -- <path>` 가 정확히 HEAD 로 되돌린다.
★ 이 스크립트는 검증자가 감사하는 커밋된 트리에서만 돌린다 — 남의 미커밋 트리에서는
git checkout 이 미커밋 구현을 지울 수 있으므로 cp 백업 절차를 따를 것(verification.md §뮤테이션).

실행:
    python3 docs/verifications/2026-08-07/repro_mutations.py
기대: 5종 모두 주장대로 (M5 memory PASS·analysis FAIL / M1·M2·M4·M3 각 FAIL)
"""
import pathlib
import subprocess
import sys
import re

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
    before = p.read_text()
    after = fn(before)
    assert after != before, f"mutation produced no change in {path}"
    p.write_text(after)


def M5_mem(s):
    return s.replace(
        'return {"scope_type": scope.scope_type, "scope_id": scope.scope_id}',
        'return {"scope_type": scope.scope_type})')


def M1_circ(s):
    return s.replace("from ..api.payloads import _memory_payload",
                     "from ..main import _memory_payload")


def M2_dropreg(s):
    return s.replace("    register_memory(app, core_sot=core_sot, memory=memory)\n", "")


def M4_dropstorage(s):
    lines = s.splitlines(keepends=True)
    out, skip = [], False
    for ln in lines:
        if re.match(r'^                except _STORAGE_ERRORS:', ln):
            skip = True
            continue
        if skip and re.match(r'^                except Exception as exc:', ln):
            skip = False
            out.append(ln)
            continue
        if skip:
            continue
        out.append(ln)
    return "".join(out)


def M3_flip(s):
    s = s.replace(
        "from ..api.dependencies import (\n    _REQUIRE_PROJECT_OWNER_BILLABLE,\n    project_existence_check,\n)",
        "from fastapi import Depends\nfrom ..api.dependencies import (\n    _REQUIRE_PROJECT_OWNER_BILLABLE,\n    _REQUIRE_PROJECT_OWNER,\n    enforce_quota,\n    project_existence_check,\n)")
    s = s.replace("dependencies=_REQUIRE_PROJECT_OWNER_BILLABLE)",
                  "dependencies=[Depends(enforce_quota), *_REQUIRE_PROJECT_OWNER])")
    return s


def main():
    preflight()

    # M5: scope_id 제거 → memory 전부 통과, analysis 셀 1개 재실패
    print("###### M5: drop scope_id from _scope_payload ######")
    mutate("services/application/app/api/payloads.py", M5_mem)
    rc_mem = run(["tests/test_memory_api.py"], "M5 / test_memory_api (expect PASS)")
    rc_ana = run(["tests/test_analysis_compare_api.py::AnalysisCompareApiTest::test_promoted_character_memory_serializes_scope"],
                 "M5 / analysis scope cell (expect FAIL)")
    print(f"   >> memory PASS={rc_mem==0}  analysis FAIL={rc_ana!=0}")
    restore("services/application/app/api/payloads.py")

    # M1: 순환 복귀 → test_app_import_paths 재실패
    print("###### M1: from ..main import _memory_payload (순환) ######")
    mutate("services/application/app/routers/memory.py", M1_circ)
    rc = run(["tests/test_app_import_paths.py"], "M1 / import paths (expect FAIL)")
    print(f"   >> FAIL={rc!=0}")
    restore("services/application/app/routers/memory.py")

    # M2: register_memory 호출 삭제 → tier 전수 가드 재실패
    print("###### M2: drop register_memory call ######")
    mutate("services/application/app/main.py", M2_dropreg)
    rc = run(["tests/test_auth_api.py::CombinedBoundaryMatrixTest::test_every_operation_lands_in_exactly_one_named_tier"],
             "M2 / tier full guard (expect FAIL)")
    print(f"   >> FAIL={rc!=0}")
    restore("services/application/app/main.py")

    # M4: except _STORAGE_ERRORS re-raise 제거 → storage-503 셀 재실패(502 로)
    print("###### M4: drop except _STORAGE_ERRORS re-raise ######")
    mutate("services/application/app/routers/context_search.py", M4_dropstorage)
    rc = run(["tests/test_context_search_api.py::ContextSearchApiTest::test_gate_finding_storage_failure_is_503"],
             "M4 / storage-503 cell (expect FAIL)")
    print(f"   >> FAIL={rc!=0}")
    restore("services/application/app/routers/context_search.py")

    # M3: context-search dependency 순서 뒤집기 → enforcement-order 셀 서브테스트 1개 재실패
    print("###### M3: flip context-search dependency order ######")
    mutate("services/application/app/routers/context_search.py", M3_flip)
    rc = run(["tests/test_quota_enforcement_api.py::BillableRouteWiringTest::test_enforcement_is_declared_after_ownership"],
             "M3 / enforcement-order cell (expect FAIL)")
    print(f"   >> FAIL={rc!=0}")
    restore("services/application/app/routers/context_search.py")

    print("\n=== pre-flight re-check (all restored) ===")
    preflight()


if __name__ == "__main__":
    main()
