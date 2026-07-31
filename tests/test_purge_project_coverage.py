"""D8-6 전수 가드: project 파기 경로를 가진 모든 repository가 purge_project 를 노출한다.

D5=A 로 project 파기는 **전체 그래프**(mongo 18 컬렉션)를 지운다. 이 컬렉션들을 관리하는
repository 계약(9개)이 모두 ``purge_project`` 를 노출하지 않으면 project 파기가 **고아 데이터**를
남긴다(D5 "부분 삭제는 조용한 고아"). 이 가드는 그 누락을 잡는다 — 새 repository 가 project-scoped
컬렉션을 추가하면 이 목록에도 넣어야 한다(under-strict: 빠지면 실패).

D8-6a(core_sot 8) + D8-6b-1(memory 1·analysis 3) + D8-6b-2(writing 3·observability 1·
context_search 1·review 1) = 9 repository 계약 / 18 컬렉션.
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
        # 를 끼워넣거나 빼면, 9 라는 수 자체가 의도임을 고정한다(18 컬렉션 = 9 계약).
        self.assertEqual(len(_PURGE_REPOSITORIES), 9)


if __name__ == "__main__":
    unittest.main()
