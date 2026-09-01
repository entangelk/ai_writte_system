"""Regression repro for final-save analysis flow.

D4=A 계약(final-save-analysis-decisions.md 확정 계약)의 실행 경로를 인메모리
TestClient 로 직접 두드려 본다. 커밋된 회귀 셀이 없는 상태에서 계약 행렬을 임시로
채우는 검증용 스크립트다.

Run:  python3 docs/verifications/2026-09-01/repro_final_save_flow.py

출력: 시나리오별 기대/관측 한 줄. 어느 하나라도 기대와 다르면 rc=1.

시나리오:
  S1  성공 runner: 저장+marker+job 실행(200, status succeeded, runner 1회)
  S2  같은 키 재전송(confirm 헤더): 동일 version 수렴, runner 재실행 없음
  S3  다른 키 재최종화: 409 AlreadyFinalized
  S4  final 뒤 일반 저장: 허용, 새 snapshot 에 분석 job 없음(analysis_status null)
  S5  S4 새 snapshot 수동 분석: 상태 succeeded 로 전환
  S6  runner 예외: 저장·marker 보존, job failed, analysis_error 통지(200)
  S7  runner 미구성(0922a24): 저장·marker 보존, job pending, analysis_error 통지
  S8  source-ref 서버 준비: final snapshot 의 모든 block span 이 커버되는가
  S9  4001자: 일반 저장과 같은 거부(422)
  S10 보관 프로젝트: 409
  S11 활동 로그: draft_finalized 행
  S12 S6 실패 job의 수동 재실행 문(retry → pending)
  S13 없는 draft: 404

독립 검증에서 B1(dedupe 표)·B2(`None` 반환값 오용)를 찾아낸 뒤, 이 파일을 현재
커밋을 직접 검증하는 회귀 프로브로 전환했다. 런타임 패치는 사용하지 않는다.
"""
import os
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from services.application.app.analysis.models import (
    AnalysisCandidateAction,
    AnalysisCandidateType,
    AnalysisJobFailureReason,
    AnalysisProvenance,
)
from services.application.app.analysis.runner import AnalysisExtractionRunResult
from services.application.app.analysis.service import (
    AnalysisService,
    InMemoryAnalysisRepository,
)
from services.application.app.core_sot.service import (
    CoreSotService,
    InMemoryCoreSotRepository,
)
from services.application.app.api.dependencies import (
    require_authenticated_user,
    require_project_owner,
)
from services.application.app.main import create_app
from tests.auth_support import TEST_USER

FAILURES = []


def check(name, expected, observed):
    ok = expected == observed
    print(f"{'PASS' if ok else 'FAIL'}  {name}: expected={expected!r} observed={observed!r}")
    if not ok:
        FAILURES.append(name)


class SucceedingRunner:
    def __init__(self):
        self._analysis = None
        self.calls = []

    def bind(self, analysis):
        self._analysis = analysis

    async def run_job(self, *, project_id, job_id):
        self.calls.append(job_id)
        running = self._analysis.mark_job_running(
            project_id=project_id, job_id=job_id)
        task = self._analysis.create_task(
            project_id=project_id, job_id=running.id,
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION)
        recorded = self._analysis.record_candidate(
            project_id=project_id, task_id=task.id,
            logical_key="character:min-a",
            candidate_type=AnalysisCandidateType.CHARACTER_OBSERVATION,
            action=AnalysisCandidateAction.CREATE,
            provenance=AnalysisProvenance.SOURCE_OBSERVED,
            confidence=0.9, source_ref_ids=("source-ref-1",),
            payload={"name": "Mina", "observation": "Keeps a hidden notebook."})
        succeeded = self._analysis.mark_job_succeeded(
            project_id=project_id, job_id=job_id)
        return AnalysisExtractionRunResult(
            job=succeeded, candidates=(recorded.candidate,),
            job_idempotent_replay=False,
            candidate_idempotent_replays=(recorded.idempotent_replay,))


class ExplodingRunner:
    """실제 AnalysisExtractionRunner 처럼 실패를 mark_job_failed 로 남기고 재발한다."""

    def __init__(self):
        self._analysis = None
        self.calls = []

    def bind(self, analysis):
        self._analysis = analysis

    async def run_job(self, *, project_id, job_id):
        self.calls.append(job_id)
        self._analysis.mark_job_running(
            project_id=project_id, job_id=job_id)
        self._analysis.mark_job_failed(
            project_id=project_id, job_id=job_id,
            failure_reason=AnalysisJobFailureReason.PROVIDER_ERROR,
            failure_detail="provider exploded")
        raise RuntimeError("provider exploded")


def make_client(runner):
    core_sot = CoreSotService(InMemoryCoreSotRepository())
    analysis = AnalysisService(InMemoryAnalysisRepository())
    if isinstance(runner, (SucceedingRunner, ExplodingRunner)):
        runner.bind(analysis)
    app = create_app(core_sot, analysis_service=analysis, analysis_runner=runner)
    # 인증 경계만 우회한다(검증 대상이 아니므로). enforce_quota 는 **실제**로
    # 돌린다 — dedupe 표·402/429 시행이 이 슬라이스의 계약_surface이기 때문이다.
    # tests.auth_support.authenticate 을 쓰면 enforce_quota 까지 덮여 S0 이 가려진다.
    app.dependency_overrides[require_authenticated_user] = lambda: TEST_USER
    app.dependency_overrides[require_project_owner] = lambda: None
    # 서버 예외는 스크립트를 죽이지 않고 상태코드로 관측한다.
    client = TestClient(app, raise_server_exceptions=False)
    project = client.post("/projects", json={"name": "Novel"}).json()
    chapter = client.post(
        f"/projects/{project['id']}/chapters", json={"title": "1장"}).json()
    draft = client.post(
        f"/projects/{project['id']}/drafts",
        json={"title": "Episode 1", "chapter_id": chapter["id"]}).json()
    return client, project["id"], draft["id"]


def main():
    os.environ.pop("LLM_GATEWAY_BASE_URL", None)
    runner = SucceedingRunner()

    # --- S1 happy path (fresh app so runner state is clean).
    runner = SucceedingRunner()
    client, pid, did = make_client(runner)
    response = client.post(
        f"/projects/{pid}/drafts/{did}/finalize",
        json={"raw_text": "민아는 밤에 일기를 쓴다.", "idempotency_key": "final-key-1"})
    body = response.json()
    check("S1 status", 200, response.status_code)
    check("S1 envelope keys",
          {"draft_version", "snapshot", "analysis_job", "analysis_error",
           "idempotent_replay"}, set(body))
    check("S1 idempotent_replay", False, body["idempotent_replay"])
    check("S1 analysis_job status", "succeeded", body["analysis_job"]["status"])
    check("S1 analysis_error", None, body["analysis_error"])
    check("S1 runner called once", 1, len(runner.calls))
    snapshot_id = body["snapshot"]["id"]
    version_id = body["draft_version"]["id"]
    draft = client.get(f"/projects/{pid}/drafts/{did}").json()
    check("S1 marker set", snapshot_id, draft["finalized_snapshot_id"])
    check("S1 finalized_at present", True, draft["finalized_at"] is not None)
    check("S1 analysis_status", "succeeded", draft["analysis_status"])
    check("S1 analysis_snapshot_id", snapshot_id, draft["analysis_snapshot_id"])

    # --- S2 same-key retry through the dedupe window (confirm header).
    response = client.post(
        f"/projects/{pid}/drafts/{did}/finalize",
        json={"raw_text": "다른 본문을 보내도", "idempotency_key": "final-key-1"},
        headers={"X-Confirm-Duplicate": "1"})
    body2 = response.json()
    check("S2 status", 200, response.status_code)
    check("S2 same version", version_id, body2["draft_version"]["id"])
    check("S2 same snapshot", snapshot_id, body2["snapshot"]["id"])
    check("S2 idempotent_replay", True, body2["idempotent_replay"])
    check("S2 runner not re-run", 1, len(runner.calls))

    # --- S3 second finalize with a different key.
    response = client.post(
        f"/projects/{pid}/drafts/{did}/finalize",
        json={"raw_text": "민아는 밤에 일기를 쓴다.",
              "idempotency_key": "final-key-2"},
        headers={"X-Confirm-Duplicate": "1"})
    check("S3 re-finalize status", 409, response.status_code)

    # --- S4 ordinary save after final: allowed, no auto analysis.
    saved = client.post(
        f"/projects/{pid}/drafts/{did}/versions",
        json={"raw_text": "민아는 다음 날 아침에도 일기를 쓴다.",
              "idempotency_key": "save-key-2"})
    check("S4 ordinary save status", 200, saved.status_code)
    new_snapshot = saved.json()["snapshot"]["id"]
    draft = client.get(f"/projects/{pid}/drafts/{did}").json()
    check("S4 marker preserved", snapshot_id, draft["finalized_snapshot_id"])
    check("S4 analysis_status null on newer snapshot",
          None, draft["analysis_status"])
    check("S4 analysis_snapshot_id null", None, draft["analysis_snapshot_id"])

    # --- S5 manual analysis of the newest snapshot flips the status.
    job = client.post(
        f"/projects/{pid}/analysis/jobs",
        json={"snapshot_id": new_snapshot,
              "idempotency_key": f"analyze:{new_snapshot}"}).json()
    client.post(f"/projects/{pid}/analysis/jobs/{job['job']['id']}/run")
    draft = client.get(f"/projects/{pid}/drafts/{did}").json()
    check("S5 analysis_status after manual run",
          "succeeded", draft["analysis_status"])
    check("S5 analysis_snapshot_id is newest",
          new_snapshot, draft["analysis_snapshot_id"])

    # --- S6 runner raises: save/marker preserved, job failed, 200 partial.
    runner6 = ExplodingRunner()
    client6, pid6, did6 = make_client(runner6)
    response = client6.post(
        f"/projects/{pid6}/drafts/{did6}/finalize",
        json={"raw_text": "결말 장면.", "idempotency_key": "final-key-6"})
    body6 = response.json()
    check("S6 status", 200, response.status_code)
    check("S6 analysis_job failed", "failed", body6["analysis_job"]["status"])
    check("S6 analysis_error set",
          True, isinstance(body6["analysis_error"], str)
          and len(body6["analysis_error"]) > 0)
    draft6 = client6.get(f"/projects/{pid6}/drafts/{did6}").json()
    check("S6 marker preserved", body6["snapshot"]["id"],
          draft6["finalized_snapshot_id"])
    check("S6 durable analysis_status is failed",
          "failed", draft6["analysis_status"])
    check("S6 version persisted", True,
          client6.get(
              f"/projects/{pid6}/drafts/{did6}/versions/"
              f"{body6['draft_version']['id']}").status_code == 200)
    failed_job_id = body6["analysis_job"]["id"]

    # --- S12 the failed job can be re-armed through the manual retry route.
    retried = client6.post(
        f"/projects/{pid6}/analysis/jobs/{failed_job_id}/retry")
    check("S12 retry status", 200, retried.status_code)
    check("S12 retry resets to pending", "pending",
          retried.json().get("status"))

    # --- S7 runner unconfigured (None) — the 0922a24 fix.
    client7, pid7, did7 = make_client(None)
    response = client7.post(
        f"/projects/{pid7}/drafts/{did7}/finalize",
        json={"raw_text": "또 다른 결말.", "idempotency_key": "final-key-7"})
    body7 = response.json()
    check("S7 status", 200, response.status_code)
    check("S7 analysis_job pending", "pending", body7["analysis_job"]["status"])
    check("S7 analysis_error names runner",
          True, "runner" in (body7["analysis_error"] or ""))
    draft7 = client7.get(f"/projects/{pid7}/drafts/{did7}").json()
    check("S7 marker preserved", body7["snapshot"]["id"],
          draft7["finalized_snapshot_id"])

    # --- S8 source-ref coverage of the final snapshot blocks.
    detail = client.get(
        f"/projects/{pid}/drafts/{did}/versions/{version_id}").json()
    refs = client.get(
        f"/projects/{pid}/snapshots/{snapshot_id}/source-refs").json()
    ref_items = refs.get("source_refs", refs.get("refs", refs))
    covered = {(r["start_offset"], r["end_offset"]) for r in ref_items}
    missing = [(b["start_offset"], b["end_offset"]) for b in detail["blocks"]
               if b["start_offset"] < b["end_offset"]
               and (b["start_offset"], b["end_offset"]) not in covered]
    check("S8 all final blocks have source refs", [], missing)

    # --- S9 4001-char body: same rejection face as ordinary save.
    oversized = "가" * 4001
    final_too_long = client.post(
        f"/projects/{pid}/drafts/{did}/finalize",
        json={"raw_text": oversized, "idempotency_key": "final-key-9"},
        headers={"X-Confirm-Duplicate": "1"})
    save_too_long = client.post(
        f"/projects/{pid}/drafts/{did}/versions",
        json={"raw_text": oversized, "idempotency_key": "save-key-9"})
    check("S9 finalize rejects like save",
          save_too_long.status_code, final_too_long.status_code)
    check("S9 rejection face is 422", 422, final_too_long.status_code)

    # --- S10 archived project.
    client10, pid10, did10 = make_client(SucceedingRunner())
    client10.delete(f"/projects/{pid10}")
    response = client10.post(
        f"/projects/{pid10}/drafts/{did10}/finalize",
        json={"raw_text": "보관된 장면.", "idempotency_key": "final-key-10"})
    check("S10 archived status", 409, response.status_code)

    # --- S11 activity row.
    feed = client.get(f"/projects/{pid}/activity").json()
    entries = feed.get("events", feed.get("entries", feed))
    actions = [e.get("action") for e in entries] if isinstance(
        entries, list) else []
    check("S11 draft_finalized recorded",
          True, "draft_finalized" in actions)

    # --- S13 unknown draft.
    response = client.post(
        f"/projects/{pid}/drafts/nope/finalize",
        json={"raw_text": "x", "idempotency_key": "final-key-13"},
        headers={"X-Confirm-Duplicate": "1"})
    check("S13 unknown draft status", 404, response.status_code)

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
