"""미승인 후보 정체성 그룹 — event/open_question shortlist 어댑터.

Slice 1이 `CandidateShortlistRetriever` seam을 열어 두고 *"주입되지 않으면 이 타입의
shortlist는 비게 된다(no-op)"* 로 계약했는데(`identity_judging.py`), 조립부가 그것을
넘긴 적이 없어 **event/open_question은 그룹으로 묶인 적이 없다.** character는 정규화
이름이라는 결정적 신호가 있어 그 경로만 살아 있었다. 이 모듈이 빈 칸을 채운다.

**임계값을 두지 않는다.** 벡터 이웃 상위 K개를 그대로 shortlist로 주고 `same|different|
uncertain` 판정은 identity judge(LLM)가 한다. 이유:

- 2B.6 D4=A가 거부한 것은 *"추측 threshold로 canon을 병합하는 것"* 이다. 여기서 틀린
  선택의 대가는 정본 오염이 아니라 **리뷰 노이즈**이고, 의미 판정자는 이미 judge다.
  임계값을 새로 만들면 그 값이 무엇을 뜻하는지 아무도 못 말하는 상수가 하나 는다.
- 그래서 K는 **의미적 컷오프가 아니라 팬아웃 예산**이다. 비용은 이미 run당 새 판정
  20쌍 상한(S-1 D3)이 묶고 있고, 넘친 쌍은 다음 run으로 이월된다.

벡터가 없는 배포에서는 조립부가 이것을 만들지 않으므로 **종전 no-op 그대로**다 —
이 모듈이 배선을 바꾸지 회귀를 만들지 않는다.
"""

from __future__ import annotations

from typing import Protocol

from services.application.app.analysis.models import AnalysisCandidate
from services.application.app.indexing.memory_index import (
    EmbeddingProvider,
    derive_memory_index_text,
)
from services.application.app.indexing.models import CandidateIndexRecord


#: 한 focal이 데려올 이웃 수. run당 새 판정 상한(20)과 **함께 읽어야 하는 값**이다 —
#: K가 크면 첫 focal 한둘이 run 예산을 다 쓰고 나머지는 전부 이월된다. 5면 focal 4개가
#: 한 run 안에서 각자 이웃을 본다. 의미적 임계가 아니라 그 배분을 정하는 값이다.
DEFAULT_CANDIDATE_SHORTLIST_LIMIT = 5


class CandidateVectorSearch(Protocol):
    """`CandidateVectorIndexAdapter`의 검색면만 (읽기 전용 부분집합).

    전체 어댑터 Protocol은 `indexing/candidate_index.py`에 있으나 그 모듈은
    `analysis.service`를 import한다. 여기서 그것을 끌어오면 analysis→indexing→analysis
    import 고리가 생기므로, 이 어댑터가 **쓰는 한 메서드만** 구조적으로 받는다.
    """

    def query_similar(
        self,
        *,
        project_id: str,
        candidate_type: str,
        vector: tuple[float, ...],
        limit: int,
    ) -> tuple[CandidateIndexRecord, ...]: ...


class VectorCandidateShortlistRetriever:
    """`candidate_vectors`에서 focal과 가까운 같은 타입 후보를 골라 준다.

    쓰기(색인)와 읽기(질의)가 **같은 투영**을 써야 검색이 성립하므로 색인이 쓰는
    `derive_memory_index_text`를 그대로 부른다.
    """

    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        vector_index: CandidateVectorSearch,
        limit: int = DEFAULT_CANDIDATE_SHORTLIST_LIMIT,
    ) -> None:
        self._embeddings = embeddings
        self._vector_index = vector_index
        self._limit = limit

    def shortlist(
        self,
        *,
        project_id: str,
        candidate: AnalysisCandidate,
        pool: tuple[AnalysisCandidate, ...],
    ) -> tuple[AnalysisCandidate, ...]:
        if not pool:
            # 비교 대상이 없으면 embedding·질의를 살 이유가 없다.
            return ()
        text = derive_memory_index_text(candidate.candidate_type, candidate.payload)
        vector = self._embeddings.embed(text)
        hits = self._vector_index.query_similar(
            project_id=project_id,
            candidate_type=candidate.candidate_type.value,
            vector=vector,
            # focal 자신도 색인돼 있어 거의 항상 1등으로 돌아온다. 그 자리를 빼고도
            # K개를 채우려면 하나 더 받아야 한다.
            limit=self._limit + 1,
        )
        by_id = {member.id: member for member in pool}
        selected: list[AnalysisCandidate] = []
        for hit in hits:
            if hit.candidate_id == candidate.id:
                continue
            member = by_id.get(hit.candidate_id)
            # pool 밖(다른 타입·이미 전이된 후보·낡은 벡터)은 버린다. 서비스도 같은
            # 필터를 한 번 더 하지만, 여기서 버려야 **관련도 순서**가 보존된다.
            if member is None:
                continue
            selected.append(member)
            if len(selected) >= self._limit:
                break
        return tuple(selected)
