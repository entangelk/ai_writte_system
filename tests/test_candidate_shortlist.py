"""event/open_question shortlist 어댑터 — 벡터 이웃을 pool 안에서 고른다.

Slice 1 이 `CandidateShortlistRetriever` seam 을 열면서 *"주입되지 않으면 이 타입의
shortlist 는 비게 된다(no-op)"* 로 계약했는데 조립부가 그것을 넘긴 적이 없어
**event/open_question 은 그룹으로 묶인 적이 없다.** 이 파일이 그 빈 칸을 채우는
어댑터를 잠근다. 잠그는 계약:

1. 벡터 이웃 **순서를 보존**해 pool 안의 후보만 돌려준다.
2. focal 자신은 자기 벡터가 색인돼 있어 거의 항상 1등으로 돌아온다 — **제외한다.**
3. pool 밖 hit(다른 타입·이미 전이된 후보·낡은 벡터)는 **버린다.**
4. pool 이 비면 embedding·질의를 **사지 않는다**(비교 대상이 없는데 돈을 쓰지 않는다).
5. 상한 K 는 의미적 컷오프가 아니라 팬아웃 예산이다 — 넘치면 앞에서 자른다.

양방향:
- under — focal 제외를 지우면 2가, pool 필터를 지우면 3이, 상한을 지우면 5가
  재실패한다.
- over — pool 이 빌 때 그래도 질의하면 4가, 이웃 순서를 정렬로 바꾸면 1이 실패한다.
"""

import unittest

from services.application.app.analysis.candidate_shortlist import (
    DEFAULT_CANDIDATE_SHORTLIST_LIMIT,
    VectorCandidateShortlistRetriever,
)
from services.application.app.analysis.models import (
    AnalysisCandidate,
    AnalysisCandidateAction,
    AnalysisCandidateStatus,
    AnalysisCandidateType,
    AnalysisProvenance,
)
from services.application.app.indexing.models import (
    CandidateIndexRecord,
    IndexRecordKind,
)


EVENT = AnalysisCandidateType.EVENT_OBSERVATION


class _CountingEmbeddings:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed(self, text: str) -> tuple[float, ...]:
        self.calls.append(text)
        return (1.0, 0.0)


class _ScriptedVectorIndex:
    """질의 결과를 대본대로 돌려주고 호출을 기록한다."""

    def __init__(self, candidate_ids: tuple[str, ...]) -> None:
        self._candidate_ids = candidate_ids
        self.calls: list[dict] = []

    def query_similar(self, *, project_id, candidate_type, vector, limit):
        self.calls.append(
            {"project_id": project_id, "candidate_type": candidate_type,
             "limit": limit}
        )
        return tuple(
            CandidateIndexRecord(
                id=f"rec-{candidate_id}",
                kind=IndexRecordKind.CANDIDATE,
                project_id=project_id,
                candidate_id=candidate_id,
                candidate_type=candidate_type,
                status="needs_review",
                text=f"text-{candidate_id}",
                vector=(1.0, 0.0),
            )
            for candidate_id in self._candidate_ids
        )


def _candidate(candidate_id: str, *, candidate_type=EVENT) -> AnalysisCandidate:
    return AnalysisCandidate(
        id=candidate_id,
        project_id="p1",
        job_id="job-1",
        task_id="task-1",
        candidate_type=candidate_type,
        action=AnalysisCandidateAction.CREATE,
        status=AnalysisCandidateStatus.NEEDS_REVIEW,
        provenance=AnalysisProvenance.SOURCE_OBSERVED,
        confidence=0.5,
        source_ref_ids=("source-ref-1",),
        payload={"event": f"happening {candidate_id}"},
    )


def _retriever(index, embeddings, *, limit=DEFAULT_CANDIDATE_SHORTLIST_LIMIT):
    return VectorCandidateShortlistRetriever(
        embeddings=embeddings, vector_index=index, limit=limit
    )


class ShortlistAdapterTest(unittest.TestCase):
    def test_preserves_vector_neighbour_order(self):
        """1: 관련도 순서가 곧 shortlist 순서다 — 정렬로 바꾸면 실패한다."""
        focal = _candidate("c-focal")
        pool = (_candidate("c-b"), _candidate("c-a"))
        index = _ScriptedVectorIndex(("c-b", "c-a"))
        got = _retriever(index, _CountingEmbeddings()).shortlist(
            project_id="p1", candidate=focal, pool=pool
        )
        self.assertEqual([c.id for c in got], ["c-b", "c-a"])

    def test_focal_itself_is_never_shortlisted(self):
        """2: focal 자신의 벡터가 1등으로 돌아와도 제외한다."""
        focal = _candidate("c-focal")
        pool = (_candidate("c-focal"), _candidate("c-b"))
        index = _ScriptedVectorIndex(("c-focal", "c-b"))
        got = _retriever(index, _CountingEmbeddings()).shortlist(
            project_id="p1", candidate=focal, pool=pool
        )
        self.assertEqual([c.id for c in got], ["c-b"])

    def test_hits_outside_the_pool_are_dropped(self):
        """3: over-strict 가드 — 낡은 벡터·전이된 후보를 데려오면 안 된다.

        pool 은 서비스가 이미 같은 project/type·``needs_review``·자기 제외로 거른
        것이다. 벡터는 그 진실보다 늦을 수 있다(재색인 드레인 전).
        """
        focal = _candidate("c-focal")
        pool = (_candidate("c-b"),)
        index = _ScriptedVectorIndex(("c-stale", "c-b", "c-gone"))
        got = _retriever(index, _CountingEmbeddings()).shortlist(
            project_id="p1", candidate=focal, pool=pool
        )
        self.assertEqual([c.id for c in got], ["c-b"])

    def test_empty_pool_buys_no_embedding_and_no_query(self):
        """4: 비교 대상이 없으면 embedding 도 질의도 사지 않는다."""
        embeddings = _CountingEmbeddings()
        index = _ScriptedVectorIndex(("c-b",))
        got = _retriever(index, embeddings).shortlist(
            project_id="p1", candidate=_candidate("c-focal"), pool=()
        )
        self.assertEqual(got, ())
        self.assertEqual(embeddings.calls, [])
        self.assertEqual(index.calls, [])

    def test_limit_caps_the_shortlist_and_asks_for_one_spare(self):
        """5: K 를 넘으면 앞에서 자른다. 질의는 focal 자리만큼 하나 더 받는다."""
        focal = _candidate("c-focal")
        pool = tuple(_candidate(f"c-{i}") for i in range(5))
        index = _ScriptedVectorIndex(tuple(f"c-{i}" for i in range(5)))
        got = _retriever(index, _CountingEmbeddings(), limit=2).shortlist(
            project_id="p1", candidate=focal, pool=pool
        )
        self.assertEqual([c.id for c in got], ["c-0", "c-1"])
        self.assertEqual(index.calls[0]["limit"], 3)

    def test_queries_the_focal_candidate_type_only(self):
        """타입 격리는 벡터 질의 인자로 간다 — 서비스 필터에만 기대지 않는다."""
        index = _ScriptedVectorIndex(())
        _retriever(index, _CountingEmbeddings()).shortlist(
            project_id="p1", candidate=_candidate("c-focal"), pool=(_candidate("c-b"),)
        )
        self.assertEqual(index.calls[0]["candidate_type"], EVENT.value)
        self.assertEqual(index.calls[0]["project_id"], "p1")


class ShortlistWiringTest(unittest.TestCase):
    def test_builder_is_none_without_vector_infrastructure(self):
        """벡터 다리가 없는 배포는 종전 no-op 그대로다 — 회귀를 만들지 않는다."""
        import os
        from unittest import mock

        from services.application.app.main import (
            _build_candidate_shortlist_retriever,
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(_build_candidate_shortlist_retriever())
        with mock.patch.dict(
            os.environ, {"CHROMA_HOST": "chroma"}, clear=True
        ):
            # embedding 서비스가 없으면 fake 차원이 실 collection 과 안 맞는다.
            self.assertIsNone(_build_candidate_shortlist_retriever())


if __name__ == "__main__":
    unittest.main()
