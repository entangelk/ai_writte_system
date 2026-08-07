"""도메인 객체 → 응답 dict 직렬화기 중 **여러 도메인이 공유하는 것**.

`main.py` 의 `create_app()` 안에 있던 중첩 함수를 옮겨왔다(라우터 분해 2·3차,
2026-08-07). 본문 byte-동일이며, 여기 있는 것은 전부 **순수 함수**다 —
협력자(`core_sot`·`memory` …)를 클로저로 잡지 않으므로 파일이 어디에 있든
같은 값을 낸다.

**여기에 오는 기준은 "공유"다.** 한 도메인만 쓰는 직렬화기는 그 라우터 모듈에
둔다(예: `_context_*_payload` 는 `routers/context_search.py`). 전부 여기로
모으면 이 파일이 두 번째 `main.py` 가 된다. 공유 멤버 현황 —
`_project_brief_payload`(projects·context_search) · `_memory_payload`+`_scope_payload`
(memory·analysis) · **`_analysis_job_payload`(analysis·writing, 3차 신설)**.

의존 방향은 `api/` 의 나머지와 같다 — 이 모듈은 아무것도 import 하지 않으므로
`errors → models → env` 사슬 어디에도 얹히지 않는다. **`main` 이나 `routers` 를
import 하면 안 된다**(그 방향이 뒤집히면 2026-08-06 에 없앤 순환이 형태만
바꿔 돌아온다).
"""

from __future__ import annotations


def _project_brief_payload(brief) -> dict[str, object]:
    return {
        "id": brief.id,
        "project_id": brief.project_id,
        "version_number": brief.version_number,
        "premise": brief.premise,
        "genre": brief.genre,
        "tone": brief.tone,
        "pov": brief.pov,
        "constraints": list(brief.constraints),
        "style_rules": list(brief.style_rules),
        "preferred_patterns": list(brief.preferred_patterns),
        "forbidden_patterns": list(brief.forbidden_patterns),
        "style_examples": list(brief.style_examples),
    }


def _memory_payload(entry) -> dict[str, object]:
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "memory_type": str(entry.memory_type),
        "status": str(entry.status),
        "provenance": str(entry.provenance),
        "confidence": entry.confidence,
        "source_ref_ids": list(entry.source_ref_ids),
        "payload": dict(entry.payload),
        "version": entry.version,
        "analysis_job_id": entry.analysis_job_id,
        "source_candidate_id": entry.source_candidate_id,
        "promotion_mode": str(entry.promotion_mode),
        "applied_threshold": entry.applied_threshold,
        "scope": _scope_payload(entry.scope),
        "supersedes": entry.supersedes,
    }


def _analysis_job_payload(job) -> dict[str, object]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "snapshot_id": job.snapshot_id,
        "status": str(job.status),
        "failure_reason": (
            str(job.failure_reason) if job.failure_reason is not None else None
        ),
        "failure_detail": job.failure_detail,
    }


def _scope_payload(scope) -> dict[str, object] | None:
    if scope is None:
        return None
    return {"scope_type": scope.scope_type, "scope_id": scope.scope_id}
