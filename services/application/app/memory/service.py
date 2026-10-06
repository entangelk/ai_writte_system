"""Infrastructure-free Phase 2B.1 canonical memory service.

Promotes Phase 2A ``needs_review`` candidates into canonical ``MemoryEntry``
records. Two promotion paths exist:

* manual approval — the user approves a candidate; it always becomes canonical
  regardless of confidence (explicit human override).
* deterministic threshold gate — a system policy (not the Analysis AI) promotes
  a candidate only when its confidence meets an injected threshold. Below the
  threshold the candidate stays ``needs_review`` and the manual path is
  preserved. The threshold defaults to ``None`` (auto-promotion disabled) so no
  canon is minted from a guessed value; real thresholds await quality fixtures
  (SoT v1.6.39 D2=B).

정본 기억 수동 수정(2026-10-06)은 승격이 아니라 **이미 canonical 인 항목의 새
버전 발행**이다 — ``edit_canonical_version`` 이 그 경로다(append-only 유지).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Protocol

from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateType,
    AnalysisProvenance,
    immutable_payload,
)
from services.application.app.analysis.schema import validate_candidate_payload
from services.application.app.memory.models import (
    MemoryEntry,
    MemoryStatus,
    PromoteMemoryResult,
    PromotionMode,
)
from services.application.app.memory.repository import (
    DuplicatePromotionRequest,
    MemoryRepository,
)
from services.application.app.memory.scope import derive_scope


def _union_source_refs(
    existing: tuple[str, ...], incoming: tuple[str, ...]
) -> tuple[str, ...]:
    """Order-preserving union: existing refs first, then new ones, deduped."""
    merged = dict.fromkeys(existing)
    for ref in incoming:
        merged.setdefault(ref, None)
    return tuple(merged)


class MemoryReindexOutbox(Protocol):
    """Phase 2B.5 (D3=B): enqueue a memory reindex when a canonical version is
    minted. Structural type (defined here, not imported from ``indexing``) so the
    memory service stays free of an indexing dependency."""

    def enqueue_memory_upserted(
        self, *, project_id: str, memory_id: str, version: int
    ) -> object: ...


class MemoryError(ValueError):
    pass


class MemoryNotFound(MemoryError):
    pass


class MemoryReindexEnqueueFailed(RuntimeError):
    """The canonical mint succeeded; the reindex outbox write did not.

    The two writes of a promotion are not one transaction — ``put_memory`` makes
    the memory durable and ``_enqueue_reindex`` then writes the outbox. When only
    the second fails, the entry exists and is never rolled back, so a caller that
    reports "promotion failed" without naming the mint would describe a state the
    store does not have. This carries the completed ``PromoteMemoryResult`` so
    the caller can report what it actually minted.

    Deliberately **not** a ``MemoryError``: that base is a ``ValueError``, and
    endpoints that map ``ValueError`` to 400 would turn an infrastructure failure
    into "the client sent a bad request". ``RuntimeError`` follows the
    ``DuplicatePromotionRequest`` precedent in ``repository.py``.
    """

    def __init__(self, result, cause: BaseException) -> None:
        super().__init__(
            f"canonical memory {result.memory.id} was minted, but its reindex "
            f"enqueue failed: {cause}"
        )
        self.result = result


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self._seq = 0
        self.memories: dict[str, MemoryEntry] = {}
        self._candidate_index: dict[tuple[str, str], str] = {}

    def next_memory_id(self) -> str:
        self._seq += 1
        return f"memory-{self._seq}"

    def get_memory(self, memory_id: str) -> MemoryEntry | None:
        return self.memories.get(memory_id)

    def find_memory_by_candidate(
        self, project_id: str, source_candidate_id: str
    ) -> str | None:
        return self._candidate_index.get((project_id, source_candidate_id))

    def put_memory(self, entry: MemoryEntry) -> None:
        key = (entry.project_id, entry.source_candidate_id)
        if key in self._candidate_index:
            raise DuplicatePromotionRequest(
                "candidate already promoted to a memory entry"
            )
        self.memories[entry.id] = entry
        self._candidate_index[key] = entry.id

    def update_memory(self, entry: MemoryEntry) -> None:
        # In-place replacement of an existing entry (e.g. superseding a prior
        # version). The candidate index is keyed on source_candidate_id, which
        # a status transition does not change, so it stays intact.
        self.memories[entry.id] = entry

    def list_memories_for_project(
        self, project_id: str
    ) -> tuple[MemoryEntry, ...]:
        return tuple(
            entry
            for entry in self.memories.values()
            if entry.project_id == project_id
        )

    def purge_project(self, project_id: str) -> None:
        # D8-6b: project 의 memory 전부 파기(직접 project_id 스코프). MemoryEntry 도
        # project_id 를 보관하므로 경유 없이 지운다.
        ids = [mid for mid, m in self.memories.items() if m.project_id == project_id]
        for mid in ids:
            del self.memories[mid]
        self._candidate_index = {
            key: mid
            for key, mid in self._candidate_index.items()
            if key[0] != project_id
        }


class MemoryService:
    def __init__(
        self,
        repository: MemoryRepository,
        *,
        auto_promotion_threshold: float | None = None,
        reindex_outbox: MemoryReindexOutbox | None = None,
    ) -> None:
        self._repo = repository
        self._auto_promotion_threshold = auto_promotion_threshold
        # Phase 2B.5 (D3=B): the single choke point for memory reindexing. Every
        # canonical version mint (manual promote, auto-promote, versioned upsert
        # via apply) enqueues here, so no write path can forget to index. Owner
        # decision 2026-07-07: promote paths reindex too, not backfill-only.
        self._reindex_outbox = reindex_outbox

    def purge_project(self, *, project_id: str) -> None:
        # D8-6b: project 전체 파기의 memory 다리. endpoint(D8-6d)가 core_sot 파기와 함께
        # 호출한다. memory 는 project 존재를 모르므로 NotFound 매핑은 없다(core_sot 가 잡는다).
        self._repo.purge_project(project_id)

    @property
    def auto_promotion_threshold(self) -> float | None:
        return self._auto_promotion_threshold

    def evaluate_auto_promotion(self, candidate: AnalysisCandidate) -> bool:
        """Deterministic threshold gate. Off by default (``None``)."""
        threshold = self._auto_promotion_threshold
        return threshold is not None and candidate.confidence >= threshold

    def is_candidate_promoted(self, project_id: str, candidate_id: str) -> bool:
        """Whether an analysis candidate has been promoted to a canonical entry.

        The promotion link is deterministic: a promote mints a MemoryEntry with
        ``source_candidate_id == candidate.id`` (see ``promote_candidate``). This
        is the canonical↔candidate dedup key ((e), v1.6.60): a promoted candidate
        still carries ``needs_review`` status (the transition is Phase 6), so the
        candidate retriever keeps surfacing it — context search suppresses it here
        instead. See docs/plans/04-canonical-candidate-dedup-decisions.md."""
        return (
            self._repo.find_memory_by_candidate(project_id, candidate_id)
            is not None
        )

    def memory_for_candidate(
        self, *, project_id: str, candidate_id: str
    ) -> "MemoryEntry | None":
        """The memory linked to a candidate (promote or versioned apply), if any.

        정체성 그룹 Slice 5(그룹 승인): ``is_candidate_promoted`` 의 판전면 —
        그룹 승인은 존재만이 아니라 그 memory가 현재 canonical인지 보고, 멤버가
        이미 가진 canonical을 채택해 두 번째 canonical을 만들지 않는다.
        """
        memory_id = self._repo.find_memory_by_candidate(project_id, candidate_id)
        if memory_id is None:
            return None
        return self._require_memory(project_id, memory_id)

    def promote_candidate(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        mode: PromotionMode,
    ) -> PromoteMemoryResult:
        if candidate.project_id != project_id:
            raise MemoryNotFound("analysis candidate not found")

        existing_id = self._repo.find_memory_by_candidate(project_id, candidate.id)
        if existing_id is not None:
            # SoT v1.7.37 (owner decision 2026-07-24): a replay re-enqueues too,
            # making this an *unconditional* choke point — every promotion path
            # leaves an index request behind, which is the invariant Phase 2B.5
            # (D3=B) wanted and v1.6.46 weakened by exempting replays.
            #
            # It closes the only way a canonical memory could stay unindexed: when
            # the enqueue following the original mint failed, nothing ever retried
            # it. The cost is bounded — while an entry is still PENDING/RUNNING the
            # outbox dedups on (project, event, mongo_id) so this is a no-op; only
            # after that entry has drained does a replay create a fresh one and
            # reindex the memory a second time. Reindex is an upsert, so the
            # redundant pass is wasted work, never corruption.
            #
            # Failures here are deliberately NOT wrapped in
            # MemoryReindexEnqueueFailed: no memory was minted by this call, so a
            # caller must not report one. The raw storage error propagates and the
            # HTTP layer maps it to the plain 503 arm.
            existing = self._require_memory(project_id, existing_id)
            self._enqueue_reindex(existing)
            return PromoteMemoryResult(memory=existing, idempotent_replay=True)

        applied_threshold = (
            self._auto_promotion_threshold
            if mode is PromotionMode.AUTO_THRESHOLD
            else None
        )
        entry = MemoryEntry(
            id=self._repo.next_memory_id(),
            project_id=project_id,
            memory_type=candidate.candidate_type,
            status=MemoryStatus.CANONICAL,
            provenance=candidate.provenance,
            confidence=candidate.confidence,
            source_ref_ids=candidate.source_ref_ids,
            payload=immutable_payload(candidate.payload),
            version=1,
            analysis_job_id=candidate.job_id,
            source_candidate_id=candidate.id,
            promotion_mode=mode,
            applied_threshold=applied_threshold,
            scope=derive_scope(candidate.candidate_type, candidate.payload),
        )
        try:
            self._repo.put_memory(entry)
        except DuplicatePromotionRequest:
            # Concurrent promotion of the same candidate: replay the winner.
            return PromoteMemoryResult(
                memory=self._require_memory_by_candidate(project_id, candidate.id),
                idempotent_replay=True,
            )
        result = PromoteMemoryResult(memory=entry, idempotent_replay=False)
        # The mint above is already durable. Any failure from here on leaves a
        # stored memory behind, so the failure must carry the result rather than
        # discard it (see MemoryReindexEnqueueFailed). The catch is broad on
        # purpose: every enqueue failure leaves the same state regardless of its
        # type, and this re-raises with context instead of mapping or swallowing.
        try:
            self._enqueue_reindex(entry)
        except Exception as exc:  # noqa: BLE001 — re-raised with the mint attached
            raise MemoryReindexEnqueueFailed(result, exc) from exc
        return result

    def auto_promote_candidate(
        self, *, project_id: str, candidate: AnalysisCandidate
    ) -> PromoteMemoryResult | None:
        """Promote only if the deterministic threshold gate fires.

        Returns ``None`` when the candidate is below threshold, leaving it
        ``needs_review`` with the manual path intact.
        """
        if not self.evaluate_auto_promotion(candidate):
            return None
        return self.promote_candidate(
            project_id=project_id,
            candidate=candidate,
            mode=PromotionMode.AUTO_THRESHOLD,
        )

    def record_updated_version(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        target_memory_id: str,
    ) -> PromoteMemoryResult:
        """Phase 2B.4 ``update``: value changed → new version.

        Replaces the payload with the candidate's, unions source refs, and takes
        the candidate's confidence/provenance (D3).
        """
        return self._versioned_upsert(
            project_id=project_id,
            candidate=candidate,
            target_memory_id=target_memory_id,
            evidence_only=False,
        )

    def record_evidence_version(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        target_memory_id: str,
    ) -> PromoteMemoryResult:
        """Phase 2B.4 ``add_evidence``: same value, new source → new version.

        Preserves the prior payload/provenance, unions source refs, and keeps the
        higher confidence (D3).
        """
        return self._versioned_upsert(
            project_id=project_id,
            candidate=candidate,
            target_memory_id=target_memory_id,
            evidence_only=True,
        )

    def edit_canonical_version(
        self,
        *,
        project_id: str,
        target_memory_id: str,
        base_version: int,
        idempotency_key: str,
        payload: Mapping[str, Any],
    ) -> PromoteMemoryResult:
        """정본 기억 수동 수정(오너 결정 2026-10-06, B안): 사람이 후보 절차 없이
        canonical 값을 직접 고친다. append-only 는 그대로다 — 고친 값은 **새
        canonical 버전**이고 대상은 ``SUPERSEDED`` 로 남는다(``record_updated_version``
        과 같은 모양)므로 아무 것도 덮어써지지 않고 감사 사슬이 보존된다.

        후보 주도 versioned upsert 와 다른 세 가지:

        * ``provenance`` 는 ``HUMAN_EDITED`` — ``source_observed``/``ai_inferred``
          둘 다 "누가 이 값을 주장했나"에 대해 거짓말을 한다.
        * ``source_candidate_id`` 는 합성 리터럴 ``manual:{idempotency_key}`` 다.
          사람 편집에 후보는 없고, 저장소의 후보 유일 인덱스가 바로 그 키로
          중복을 막으므로 **재시도는 새 버전이 아니라 replay** 가 된다 — 별도의
          idempotency 저장소 없이 brief PUT 과 같은 멱등 모양.
        * ``scope`` 는 고친 payload 로 **재계산**한다 — 이름이 바뀐 인물이 옛
          정체성 키에 묶이면 compare·별칭 매처가 옛 이름을 계속 본다.
          ``base_version``(정수)은 lost update 가드다: 클라이언트가 편집을
          시작한 버전을 되돌려 보내고, 서버 정본과 다르면 거절한다.
        """
        if not idempotency_key:
            raise MemoryError("idempotency_key is required")

        synthetic_candidate_id = f"manual:{idempotency_key}"
        existing_id = self._repo.find_memory_by_candidate(
            project_id, synthetic_candidate_id
        )
        if existing_id is not None:
            # Same unconditional choke point as promote_candidate's replay branch
            # (SoT v1.7.37): a replay re-enqueues too, so no canonical version can
            # stay unindexed just because the first enqueue already drained.
            existing = self._require_memory(project_id, existing_id)
            self._enqueue_reindex(existing)
            return PromoteMemoryResult(memory=existing, idempotent_replay=True)

        target = self._require_memory(project_id, target_memory_id)
        if target.status is not MemoryStatus.CANONICAL:
            raise MemoryError("cannot version a non-canonical memory entry")
        if base_version != target.version:
            raise MemoryError("canonical memory base is stale")

        # 후보 경로와 같은 taxonomy 검증 — 사람 편집이라고 정본 스키마가 느슨해지면
        # 안 된다(키 추가·제거·빈 문자열 모두 거절).
        normalized = validate_candidate_payload(target.memory_type, payload)

        new_entry = MemoryEntry(
            id=self._repo.next_memory_id(),
            project_id=project_id,
            memory_type=target.memory_type,
            status=MemoryStatus.CANONICAL,
            provenance=AnalysisProvenance.HUMAN_EDITED,
            confidence=target.confidence,
            source_ref_ids=target.source_ref_ids,
            payload=immutable_payload(normalized),
            version=target.version + 1,
            analysis_job_id=target.analysis_job_id,
            source_candidate_id=synthetic_candidate_id,
            promotion_mode=PromotionMode.MANUAL,
            applied_threshold=None,
            scope=derive_scope(target.memory_type, normalized),
            supersedes=target.id,
        )
        try:
            self._repo.put_memory(new_entry)
        except DuplicatePromotionRequest:
            # Concurrent retry of the same idempotency key: replay the winner.
            return PromoteMemoryResult(
                memory=self._require_memory_by_candidate(
                    project_id, synthetic_candidate_id
                ),
                idempotent_replay=True,
            )
        # Append-only: mint the new version first (canonical), then supersede the
        # prior entry so it is preserved immutably rather than overwritten.
        self._repo.update_memory(
            replace(target, status=MemoryStatus.SUPERSEDED)
        )
        self._enqueue_reindex(new_entry)
        return PromoteMemoryResult(memory=new_entry, idempotent_replay=False)

    def merge_canonical_entries(
        self,
        *,
        project_id: str,
        survivor_memory_id: str,
        absorbed_memory_id: str,
        base_survivor_version: int,
        base_absorbed_version: int,
        idempotency_key: str,
        payload: Mapping[str, Any],
    ) -> PromoteMemoryResult:
        """정본 기억 병합(오너 결정 2026-10-06, A안): 같은 인물인데 분석이 갈라
        만든 두 canonical 을 하나로 통합한다("나"/"주인공" 사례).

        사슬 연결 — 두 쪽 모두 데이터로 보존된다:

        * 병합 결과는 **생존(survivor) 쪽의 다음 버전**이다(``version+1``,
          ``supersedes``=생존 현재) — 버전 사슬이 리셋되지 않는다.
        * 흡수(absorbed) 항목은 ``SUPERSEDED`` 로 보존되되 ``merged_into`` 가
          병합 결과를 앞으로 가리킨다 — 흡수된 사슬이 조용한 막다름이 되지
          않는다.

        본문은 편집 기반이다: 호출자가 양쪽 관찰을 이미 합쳐 다듬은 payload 를
        보낸다(서비스는 이어붙이지 않는다). 근거는 양쪽 유니온, 나머지 이어받기
        규칙은 ``edit_canonical_version`` 과 같다(신뢰도·분석 잡·합성 멱등 키
        ``manual:{idempotency_key}``·scope 재계산). 1차 대상은 인물
        (character_observation)이다 — 사건·떡밥은 같은 기계의 후속 확장.
        """
        if not idempotency_key:
            raise MemoryError("idempotency_key is required")
        if survivor_memory_id == absorbed_memory_id:
            raise MemoryError("cannot merge an entry with itself")

        synthetic_candidate_id = f"manual:{idempotency_key}"
        existing_id = self._repo.find_memory_by_candidate(
            project_id, synthetic_candidate_id
        )
        if existing_id is not None:
            # edit_canonical_version 의 replay 분기와 같은 무조건 초크 포인트
            # (SoT v1.7.37) — 재시도도 재색인을 다시 건다.
            existing = self._require_memory(project_id, existing_id)
            self._enqueue_reindex(existing)
            return PromoteMemoryResult(memory=existing, idempotent_replay=True)

        survivor = self._require_memory(project_id, survivor_memory_id)
        absorbed = self._require_memory(project_id, absorbed_memory_id)
        for target, base_version, label in (
            (survivor, base_survivor_version, "survivor"),
            (absorbed, base_absorbed_version, "absorbed"),
        ):
            if target.status is not MemoryStatus.CANONICAL:
                raise MemoryError("cannot version a non-canonical memory entry")
            if base_version != target.version:
                raise MemoryError(
                    f"canonical memory base is stale ({label})"
                )
        if survivor.memory_type is not absorbed.memory_type:
            raise MemoryError(
                "merge requires both entries to share a memory type"
            )
        # 1차 정책(2026-10-06): 인물만. reconciliation 의 character-only 제한과
        # 같은 이유 — 사건·떡밥의 통합 의미(사건 합침? 떡밥 중복?)는 아직 정의된
        # 적이 없다.
        if survivor.memory_type is not AnalysisCandidateType.CHARACTER_OBSERVATION:
            raise MemoryError("merge is character-only for now")

        normalized = validate_candidate_payload(survivor.memory_type, payload)

        merged = MemoryEntry(
            id=self._repo.next_memory_id(),
            project_id=project_id,
            memory_type=survivor.memory_type,
            status=MemoryStatus.CANONICAL,
            provenance=AnalysisProvenance.HUMAN_EDITED,
            confidence=survivor.confidence,
            source_ref_ids=_union_source_refs(
                survivor.source_ref_ids, absorbed.source_ref_ids
            ),
            payload=immutable_payload(normalized),
            version=survivor.version + 1,
            analysis_job_id=survivor.analysis_job_id,
            source_candidate_id=synthetic_candidate_id,
            promotion_mode=PromotionMode.MANUAL,
            applied_threshold=None,
            scope=derive_scope(survivor.memory_type, normalized),
            supersedes=survivor.id,
        )
        try:
            self._repo.put_memory(merged)
        except DuplicatePromotionRequest:
            # Concurrent retry of the same idempotency key: replay the winner.
            return PromoteMemoryResult(
                memory=self._require_memory_by_candidate(
                    project_id, synthetic_candidate_id
                ),
                idempotent_replay=True,
            )
        # Append-only: mint first, then retire both parents — the survivor steps
        # down like a plain edit, the absorbed entry additionally records where
        # it lives on now (merged_into).
        self._repo.update_memory(
            replace(survivor, status=MemoryStatus.SUPERSEDED)
        )
        self._repo.update_memory(
            replace(
                absorbed, status=MemoryStatus.SUPERSEDED, merged_into=merged.id
            )
        )
        self._enqueue_reindex(merged)
        return PromoteMemoryResult(memory=merged, idempotent_replay=False)

    def _versioned_upsert(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        target_memory_id: str,
        evidence_only: bool,
    ) -> PromoteMemoryResult:
        if candidate.project_id != project_id:
            raise MemoryNotFound("analysis candidate not found")

        # D5 idempotency: a candidate produces at most one memory write. A
        # re-application replays the version it already created.
        existing_id = self._repo.find_memory_by_candidate(project_id, candidate.id)
        if existing_id is not None:
            # Same unconditional choke point as promote_candidate's replay branch
            # (SoT v1.7.37) — see the reasoning there. Applying it to only one of
            # the two write paths would leave the invariant half true, which is
            # worse than either extreme.
            existing = self._require_memory(project_id, existing_id)
            self._enqueue_reindex(existing)
            return PromoteMemoryResult(memory=existing, idempotent_replay=True)

        target = self._require_memory(project_id, target_memory_id)
        if target.status is not MemoryStatus.CANONICAL:
            raise MemoryError("cannot version a non-canonical memory entry")
        if candidate.candidate_type is not target.memory_type:
            raise MemoryError(
                "candidate type does not match the target memory type"
            )

        source_ref_ids = _union_source_refs(
            target.source_ref_ids, candidate.source_ref_ids
        )
        if evidence_only:
            payload = target.payload
            confidence = max(target.confidence, candidate.confidence)
            provenance = target.provenance
        else:
            payload = immutable_payload(candidate.payload)
            confidence = candidate.confidence
            provenance = candidate.provenance

        new_entry = MemoryEntry(
            id=self._repo.next_memory_id(),
            project_id=project_id,
            memory_type=target.memory_type,
            status=MemoryStatus.CANONICAL,
            provenance=provenance,
            confidence=confidence,
            source_ref_ids=source_ref_ids,
            payload=payload,
            version=target.version + 1,
            analysis_job_id=candidate.job_id,
            source_candidate_id=candidate.id,
            promotion_mode=PromotionMode.MANUAL,
            applied_threshold=None,
            scope=target.scope,
            supersedes=target.id,
        )
        try:
            self._repo.put_memory(new_entry)
        except DuplicatePromotionRequest:
            # Concurrent apply of the same candidate: replay the winner.
            return PromoteMemoryResult(
                memory=self._require_memory_by_candidate(project_id, candidate.id),
                idempotent_replay=True,
            )
        # Append-only: mint the new version first (canonical), then supersede the
        # prior entry so it is preserved immutably rather than overwritten.
        self._repo.update_memory(
            replace(target, status=MemoryStatus.SUPERSEDED)
        )
        self._enqueue_reindex(new_entry)
        return PromoteMemoryResult(memory=new_entry, idempotent_replay=False)

    def _enqueue_reindex(self, memory: MemoryEntry) -> None:
        # Only fresh canonical mints reach here (replays return earlier). Enqueue
        # is idempotent (dedup per memory_id) so this is safe under retries.
        if self._reindex_outbox is not None:
            self._reindex_outbox.enqueue_memory_upserted(
                project_id=memory.project_id,
                memory_id=memory.id,
                version=memory.version,
            )

    def get_memory(self, *, project_id: str, memory_id: str) -> MemoryEntry:
        return self._require_memory(project_id, memory_id)

    def list_memories(self, *, project_id: str) -> tuple[MemoryEntry, ...]:
        return self._repo.list_memories_for_project(project_id)

    def _require_memory(self, project_id: str, memory_id: str) -> MemoryEntry:
        memory = self._repo.get_memory(memory_id)
        if memory is None or memory.project_id != project_id:
            raise MemoryNotFound("memory entry not found")
        return memory

    def _require_memory_by_candidate(
        self, project_id: str, source_candidate_id: str
    ) -> MemoryEntry:
        memory_id = self._repo.find_memory_by_candidate(
            project_id, source_candidate_id
        )
        if memory_id is None:
            raise MemoryNotFound("memory entry not found")
        return self._require_memory(project_id, memory_id)
