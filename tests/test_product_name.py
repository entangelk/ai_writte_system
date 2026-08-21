"""제품명은 **노출되는 모든 자리에서 하나여야 한다** (Phase 10 D5 · HANDOFF H2).

프론트에는 이미 짝이 있다([`frontend/src/productName.test.ts`]) — 이 파일은 그
**백엔드 쪽 짝**이다. 10.0 이 화면을 "에-라잇" 으로 통일했지만 **화면이 아닌 노출면**
셋이 옛 작업 제목으로 남아 있었다: FastAPI 가 서비스마다 들고 있는 ``title=`` 이며,
`/docs`·`/redoc` 과 그 원본 OpenAPI 문서 상단에 그대로 뜬다. 렌더 테스트의 사정거리
밖이라 289셀이 전부 green 인 채로 열 달을 살아남았다 — 프론트에서 `<title>` 이 그랬던
것과 **같은 병**이고, 그래서 처방도 같다: DOM 이 아니라 **앱과 파일을 읽는다.**

**양방향**:
- under-strict — 세 title 중 하나라도 옛 이름으로 되돌아가면 첫 셀이 실패한다.
- over-strict — 이름 통일을 **식별자까지** 밀어붙이면 세 번째 셀이 실패한다.
  ``ai_writing_system`` 은 표시명이 아니라 **Mongo DB 이름**이고, 바꾸면 앱은 조용히
  빈 DB 를 가리킨다(이 저장소가 실제로 밟은 함정 — `ai_writing` 이 0건을 냈다).

**스캔 범위** — 저장소 전체의 `.py` 와 compose `.yml` 에서 아래를 뺀다.
``tests`` 는 부재를 단정하려면 그 문자열을 적어야 하므로 제외하고(이 파일 자신이 그
예다), ``docs`` 는 이력 기록이라 옛 이름이 **남아 있는 것이 맞다.** 범위를
`services`·`scripts` 로 하드코딩하지 않은 것은 의도다 — 네 번째 최상위 패키지가
생겼을 때 가드가 조용히 그것을 안 보는 모양("세 번째 파일" 계열)을 피한다.
"""

import pathlib
import unittest

from services.application.app.core_sot.mongo_repository import DEFAULT_DB_NAME
from services.application.app.main import create_app as create_application_app
from services.embedding.app.main import create_app as create_embedding_app
from services.llm_gateway.app.main import create_app as create_gateway_app
from services.llm_gateway.app.provider import FakeLLMProvider

_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 오너가 2026-08-10 에 명명한 정본. 프론트 스윕의 ``PRODUCT_NAME`` 과 같은 글자다.
_PRODUCT_NAME = "에-라잇"
#: 그 전의 작업 제목. 노출되는 자리에 남아 있으면 안 된다.
_RETIRED_NAME = "AI Writing System"

_SKIPPED_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", "tests", "docs", "frontend",
})


def _source_files() -> list[pathlib.Path]:
    found = []
    stack = [_ROOT]
    while stack:
        for entry in stack.pop().iterdir():
            if entry.is_dir():
                if entry.name not in _SKIPPED_DIRS:
                    stack.append(entry)
            elif entry.suffix == ".py" or entry.name.startswith("docker-compose"):
                found.append(entry)
    return found


class ProductNameTest(unittest.TestCase):
    def test_every_service_titles_its_api_docs_with_the_product_name(self):
        """`/docs`·`/redoc` 상단에 뜨는 글자. 세 서비스가 각각 들고 있다."""
        apps = {
            "application": create_application_app(),
            "embedding": create_embedding_app(),
            "llm_gateway": create_gateway_app(provider=FakeLLMProvider([])),
        }

        for service, app in apps.items():
            with self.subTest(service=service):
                self.assertTrue(
                    app.title.startswith(_PRODUCT_NAME),
                    f"{service} 의 FastAPI title 이 제품명으로 시작하지 않는다: "
                    f"{app.title!r} — /docs 상단에 그대로 뜬다.",
                )
                self.assertNotIn(_RETIRED_NAME, app.title)

    def test_the_retired_working_title_survives_in_no_backend_source(self):
        """세 자리를 고쳐도 네 번째가 생기면 소용없다 — 완전성 셀."""
        offenders = [
            str(path.relative_to(_ROOT))
            for path in _source_files()
            if _RETIRED_NAME in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(
            offenders, [],
            f"옛 작업 제목 {_RETIRED_NAME!r} 이 남아 있다. 제품명은 "
            f"{_PRODUCT_NAME!r} 하나다(Phase 10 D5).",
        )

    def test_the_rename_does_not_reach_the_database_identifier(self):
        """표시명 통일이 식별자를 건드리면 앱이 조용히 빈 DB 를 본다."""
        self.assertEqual(DEFAULT_DB_NAME, "ai_writing_system")


if __name__ == "__main__":
    unittest.main()
