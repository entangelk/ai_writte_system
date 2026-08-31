"""D8-6 전수 가드: project 파기 경로를 가진 모든 repository가 purge_project 를 노출한다.

D5=A 로 project 파기는 **전체 그래프**(mongo 19 컬렉션)를 지운다. 이 컬렉션들을 관리하는
repository 계약(9개)이 모두 ``purge_project`` 를 노출하지 않으면 project 파기가 **고아 데이터**를
남긴다(D5 "부분 삭제는 조용한 고아"). 이 가드는 그 누락을 잡는다 — 새 repository 가 project-scoped
컬렉션을 추가하면 이 목록에도 넣어야 한다(under-strict: 빠지면 실패).

D8-6a(core_sot 8, v1.8.11 `scene_notes` 합류로 9) + D8-6b-1(memory 1·analysis 3) +
D8-6b-2(writing 3·observability 1·context_search 1·review 1) = 9 repository 계약 / 19 컬렉션.
"""

from __future__ import annotations

import unittest

from services.application.app.analysis.repository import AnalysisRepository
from services.application.app.analysis.review_queue import ReviewQueueRepository
from services.application.app.context_search.gate_findings import GateFindingRepository
from services.application.app.core_sot.repository import CoreSotRepository
from services.application.app.memory.repository import MemoryRepository
from services.application.app.observability.llm_call_audit import LlmCallAuditRepository
from services.application.app.writing.generation_job import (
    WritingGenerationJobRepository,
)
from services.application.app.writing.loop_audit import WritingLoopAuditRepository
from services.application.app.writing.scratch import WritingScratchRepository

# D8-6c hardening: indexing vector/lexical 백엔드 계약(Protocol + composite) —
# D5 부분 삭제 금지의 indexing 층.
from services.application.app.indexing.candidate_index import (
    CandidateVectorIndexAdapter,
    CompositeCandidateIndexSyncAdapter,
)
from services.application.app.indexing.candidate_lexical_index import (
    CandidateLexicalIndexAdapter,
)
from services.application.app.indexing.memory_index import (
    CompositeMemoryIndexSyncAdapter,
    MemoryVectorIndexAdapter,
)
from services.application.app.indexing.memory_lexical_index import (
    MemoryLexicalIndexAdapter,
)
# D8-6c-2: source_block archive adapter joined the purge roster (6c-2 added
# purge_project to ArchiveIndexMutationAdapter).
from services.application.app.indexing.service import ArchiveIndexMutationAdapter

# (repository 이름, 계약 클래스). Mongo 단일 구현체도 같은 이름의 컬렉션을 쓰지만,
# 파기 계약은 Protocol 에서 선언되므로 계약 클래스로 단정한다.
_PURGE_REPOSITORIES = [
    ("CoreSotRepository", CoreSotRepository),
    ("MemoryRepository", MemoryRepository),
    ("AnalysisRepository", AnalysisRepository),
    ("WritingGenerationJobRepository", WritingGenerationJobRepository),
    ("WritingScratchRepository", WritingScratchRepository),
    ("WritingLoopAuditRepository", WritingLoopAuditRepository),
    ("LlmCallAuditRepository", LlmCallAuditRepository),
    ("GateFindingRepository", GateFindingRepository),
    ("ReviewQueueRepository", ReviewQueueRepository),
]


class PurgeProjectCoverageTest(unittest.TestCase):
    def test_all_purge_repositories_expose_purge_project(self):
        missing = [
            name
            for name, cls in _PURGE_REPOSITORIES
            if "purge_project" not in dir(cls)
        ]
        self.assertEqual(
            missing,
            [],
            f"repositories missing purge_project (project 파기가 고아를 남김): {missing}",
        )

    def test_purge_repository_roster_is_complete(self):
        # 과잉 교정 가드(over-strict): 실수로 이 목록에 project-scoped 가 아닌 repository
        # 를 끼워넣거나 빼면, 9 라는 수 자체가 의도임을 고정한다(19 컬렉션 = 9 계약).
        self.assertEqual(len(_PURGE_REPOSITORIES), 9)


class IndexingBackendPurgeCoverageTest(unittest.TestCase):
    """D8-6c hardening: vector/lexical 백엔드 계약이 purge_project 를 노출한다.

    D5 부분 삭제 금지의 indexing 층 — project 파기 시 memory/candidate 의
    vector(Chroma)·lexical(ES) 백엔드가 모두 project 단위 파기를 노출하지 않으면
    정본은 지워졌는데 derived 인덱스가 남는 **vector/index 잔류 고아**가 생긴다.
    6c-1(memory)·6c-1b(candidate) 가 이 백엔드들에 purge_project 를 추가했다.

    범위: source_block archive 1종(6c-2 합류) + memory/candidate vector·lexical Protocol
    4종 + worker 가 drain 에서 부르는 composite 2종 = 7. 새 indexing 백엔드가 project-scoped
    파기를 추가하면 이 목록과 아래 카운트를 함께 올린다(빠지면 _drain_purge 가 고아를 남긴다).
    """

    _INDEXING_PURGE_CONTRACTS = [
        # D8-6c-2: source_block archive adapter joined once it gained purge_project.
        ("ArchiveIndexMutationAdapter", ArchiveIndexMutationAdapter),
        ("MemoryVectorIndexAdapter", MemoryVectorIndexAdapter),
        ("CandidateVectorIndexAdapter", CandidateVectorIndexAdapter),
        ("MemoryLexicalIndexAdapter", MemoryLexicalIndexAdapter),
        ("CandidateLexicalIndexAdapter", CandidateLexicalIndexAdapter),
        ("CompositeMemoryIndexSyncAdapter", CompositeMemoryIndexSyncAdapter),
        ("CompositeCandidateIndexSyncAdapter", CompositeCandidateIndexSyncAdapter),
    ]

    def test_all_indexing_backends_expose_purge_project(self):
        missing = [
            name
            for name, cls in self._INDEXING_PURGE_CONTRACTS
            if "purge_project" not in dir(cls)
        ]
        self.assertEqual(
            missing,
            [],
            f"indexing backends missing purge_project "
            f"(project 파기가 vector/index 고아를 남김): {missing}",
        )

    def test_indexing_purge_roster_is_complete(self):
        # over-strict: 7(archive 1 + vector/lexical Protocol 4 + composite 2) 이라는
        # 수 자체를 고정. 새 indexing 백엔드가 project-scoped 파기를 추가하면 이 목록과
        # 함께 올린다(빠지면 _drain_purge 가 그 백엔드를 못 지운다).
        self.assertEqual(len(self._INDEXING_PURGE_CONTRACTS), 7)


if __name__ == "__main__":
    unittest.main()
