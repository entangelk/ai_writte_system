"""제품명은 **노출되는 모든 자리에서 하나여야 한다** (Phase 10 D5 · HANDOFF H2).

프론트에는 이미 짝이 있다([`frontend/src/productName.test.ts`]) — 이 파일은 그
**백엔드 쪽 짝**이다. 10.0 이 화면을 "에-라잇" 으로 통일했지만 **화면이 아닌 노출면**
셋이 옛 작업 제목으로 남아 있었다: FastAPI 가 서비스마다 들고 있는 ``title=`` 이며,
`/docs`·`/redoc` 과 그 원본 OpenAPI 문서 상단에 그대로 뜬다. 렌더 테스트의 사정거리
밖이라 289셀이 전부 green 인 채로 열 달을 살아남았다 — 프론트에서 `<title>` 이 그랬던
것과 **같은 병**이고, 그래서 처방도 같다: DOM 이 아니라 **앱과 파일을 읽는다.**

**양방향**:
- under-strict — 세 title 중 하나라도 옛 이름으로 되돌아가면 첫 셀이 실패한다.
  구분자만 흔들려도(`Application` → `App`) 마찬가지다 — 첫 셀은 **정확 일치**이고,
  그 기대값 표가 규칙을 벗어나는 것은 둘째 셀이 잡는다(2026-08-21 검증 M8·H-P2).
- over-strict — 이름 통일을 **식별자까지** 밀어붙이면 세 번째 셀이 실패한다.
  ``ai_writing_system`` 은 표시명이 아니라 **Mongo DB 이름**이고, 바꾸면 앱은 조용히
  빈 DB 를 가리킨다(이 저장소가 실제로 밟은 함정 — `ai_writing` 이 0건을 냈다).

**스캔 범위** — 저장소 전체의 `.py` 와 compose `.yml`, 그리고 **저장소 정문 두 파일**
(`README.md`·`LICENSE`, 2026-08-21 검증 H-P1)에서 아래를 뺀다.
``tests`` 는 부재를 단정하려면 그 문자열을 적어야 하므로 제외하고(이 파일 자신이 그
예다), ``docs`` 는 이력 기록이라 옛 이름이 **남아 있는 것이 맞다.** 범위를
`services`·`scripts` 로 하드코딩하지 않은 것은 의도다 — 네 번째 최상위 패키지가
생겼을 때 가드가 조용히 그것을 안 보는 모양("세 번째 파일" 계열)을 피한다.
"""

import pathlib
import re
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

#: 은퇴명의 **표기 변형**까지 잡는다 — 대소문자와 공백 폭만 다른 것은 같은 이름이다
#: (2026-08-21 독립 검증 M7 이 `"AI writing System"` 주입으로 종전 침묵을 실증했다.
#: 그때 잔존은 0건이라 이론적 맹점이었고, 닫는 비용이 한 줄이라 닫는다).
#:
#: **★ 밑줄·하이픈 형태는 일부러 안 잡는다** — `ai_writing_system`(Mongo DB 이름) ·
#: `ai-writing-system-frontend`(npm 패키지명)는 **식별자**이고, 그것을 개명하면 앱이
#: 조용히 빈 DB 를 가리킨다. 그래서 여기서 금지하는 것은 **띄어 쓴 표시명**뿐이다.
#: 줄바꿈을 건너뛰지 않는 것(`[ \t]+`)도 같은 이유다 — 우연한 적중을 만들지 않는다.
_RETIRED_VARIANTS = re.compile(r"ai[ \t]+writing[ \t]+system", re.IGNORECASE)

#: **오너가 D-2026-08-21-a 로 정한 정확한 글자.** `startswith` 만으로는
#: `"에-라잇 App"` 같은 **서비스 구분자 드리프트**를 아무 셀도 못 본다
#: (2026-08-21 독립 검증 M8 이 실증했다 — 그때 3셀 전부 침묵했다).
#: 새 서비스가 생기면 **여기에 글자를 더하는 것이 정상 경로**이며, 그 추가가
#: 의식적일 것 하나만 요구한다(`_ALLOWED_KEYS` 계열의 트립와이어와 같은 형태).
_DECIDED_TITLES = {
    "application": "에-라잇 Application",
    "embedding": "에-라잇 Embedding Service",
    "llm_gateway": "에-라잇 LLM Gateway",
}

_SKIPPED_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", "tests", "docs", "frontend",
})

#: **저장소 정문** — 확장자로는 안 걸리지만 사람이 가장 먼저 읽는 두 자리.
#: 2026-08-21 독립 검증 H-P1 이 여기서 은퇴명을 찾았다: 백엔드 스윕은 `.py`+compose 만,
#: 프론트 스윕은 `frontend/` 만 봐서 **README H1 은 어느 쪽 사정거리에도 없었다**.
#: 이 슬라이스가 치유하려던 병과 정확히 같은 모양이라 오너가 교체를 택했다
#: (D-2026-08-21-d). 확장자 규칙으로 열면 `HANDOFF.md`·`CHANGELOG.md` 가 함께 들어오는데
#: 그 둘은 **이력이라 은퇴명이 남아 있는 것이 맞다** — 그래서 이름으로 둘만 더한다.
_FRONT_DOOR = ("README.md", "LICENSE")


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
    return found + [_ROOT / name for name in _FRONT_DOOR]


class ProductNameTest(unittest.TestCase):
    def test_every_service_titles_its_api_docs_with_the_decided_letters(self):
        """`/docs`·`/redoc` 상단에 뜨는 글자. 세 서비스가 각각 들고 있다.

        **정확 일치로 잠근다.** 종전에는 `startswith(제품명)` + 은퇴명 부재만 봐서
        `"에-라잇 App"` 으로 바꿔도 세 셀이 전부 침묵했다(2026-08-21 검증 M8).
        구분자는 취향이 아니라 **오너 결정 D-2026-08-21-a 가 정한 글자**이고,
        그 결정의 근거는 코드·로그·compose 서비스명과 글자가 이어지는 것이었다 —
        `Application` 을 `App` 으로 줄이면 그 근거가 조용히 사라진다.
        """
        apps = {
            "application": create_application_app(),
            "embedding": create_embedding_app(),
            "llm_gateway": create_gateway_app(provider=FakeLLMProvider([])),
        }
        self.assertEqual(sorted(apps), sorted(_DECIDED_TITLES))

        for service, app in apps.items():
            with self.subTest(service=service):
                self.assertEqual(
                    app.title, _DECIDED_TITLES[service],
                    f"{service} 의 FastAPI title 이 결정된 글자가 아니다 — "
                    "/docs 상단에 그대로 뜬다.",
                )

    def test_the_decided_letters_themselves_follow_the_naming_rule(self):
        """위 표는 **데이터**다 — 그 데이터가 규칙을 벗어나면 잠금이 무의미하다.

        표를 `"AI Writing App"` 으로 고치면 위 셀은 통과하고 제품명만 사라진다.
        일반 규칙(*"제품명으로 시작한다"* · §Active Decisions)은 여기서 잠근다.
        새 서비스를 표에 더할 때 이 셀이 그 규칙을 자동으로 적용한다.
        """
        for service, title in _DECIDED_TITLES.items():
            with self.subTest(service=service):
                self.assertTrue(title.startswith(_PRODUCT_NAME), title)
                self.assertIsNone(_RETIRED_VARIANTS.search(title), title)

    def test_the_retired_working_title_survives_in_no_backend_source(self):
        """세 자리를 고쳐도 네 번째가 생기면 소용없다 — 완전성 셀."""
        offenders = [
            str(path.relative_to(_ROOT))
            for path in _source_files()
            if _RETIRED_VARIANTS.search(path.read_text(encoding="utf-8"))
        ]

        self.assertEqual(
            offenders, [],
            f"옛 작업 제목 {_RETIRED_NAME!r}(대소문자·공백 변형 포함)이 남아 있다. "
            f"제품명은 {_PRODUCT_NAME!r} 하나다(Phase 10 D5).",
        )

    def test_the_front_door_files_are_actually_there_to_be_swept(self):
        """이름으로 더한 두 자리는 **파일이 사라지면 조용히 스윕에서 빠진다.**

        확장자 규칙과 달리 이름 목록은 자기가 비는 것을 스스로 못 본다 — 그래서
        트립와이어를 둔다. `README.md` 를 옮기거나 이름을 바꾸면 여기서 실패하고,
        그때 `_FRONT_DOOR` 를 고치는 것이 정상 경로다.
        """
        for name in _FRONT_DOOR:
            with self.subTest(file=name):
                self.assertTrue(
                    (_ROOT / name).is_file(),
                    f"{name} 이 없다 — 스윕이 그 자리를 조용히 안 보게 된다.",
                )

    def test_the_rename_does_not_reach_the_database_identifier(self):
        """표시명 통일이 식별자를 건드리면 앱이 조용히 빈 DB 를 본다."""
        self.assertEqual(DEFAULT_DB_NAME, "ai_writing_system")


if __name__ == "__main__":
    unittest.main()
