"""임베딩 조립 가드 — docs/plans/embedding-adapter-slice-decisions.md 결정 4=A.

**막는 것은 "provider 를 잘못 만드는 것" 이 아니라 "조립 자리가 여섯이라는 사실"
자체다.** 종전에는 여섯 자리가 각자 `EMBEDDING_SERVICE_URL`·`EMBEDDING_DIMENSIONS`·
`EMBEDDING_TIMEOUT_SECONDS` 를 읽고 생성자를 직접 불렀다. 그래서 ①기본값 `"1024"` 가
다섯 벌로 적혀 있었고(하나 고치고 넷을 잊으면 조용히 갈린다) ②그중 한 자리가
**한 달 넘게 `TypeError` 로 깨진 채 green** 이었다 — 그 파일을 부르는 테스트가 0건이라.

**★ 등재 목록 방식이 아니다.** 브리프가 선택지 B(자리 목록을 두고 리터럴 단정)를
기각한 이유가 M5 함정이다 — 새 자리가 생겼는데 목록에 안 넣으면 **가드가 침묵한다.**
여기서는 반대로 **"생성자를 직접 부르는 자리가 하나라도 있으면 실패"** 를 단정하므로
새 자리는 등재를 잊어도 걸린다.
"""

from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

from services.application.app.indexing.embedding import (
    RemoteEmbeddingProvider,
    build_embedding_provider_from_env,
)
from services.application.app.indexing.service import (
    DeterministicFakeEmbeddingProvider,
)

_ROOT = Path(__file__).resolve().parent.parent

#: 생성자를 직접 부르는 것이 정당한 유일한 파일 — 헬퍼가 사는 곳이다.
_ASSEMBLY_MODULE = _ROOT / "services" / "application" / "app" / "indexing" / "embedding.py"

#: 이름이 provider 인 클래스를 직접 조립하는 것으로 간주할 호출.
_PROVIDER_CONSTRUCTORS = frozenset({
    "RemoteEmbeddingProvider",
    "OpenAIEmbeddingProvider",
})


def _sources() -> list[Path]:
    paths = [*(_ROOT / "services").rglob("*.py"), *(_ROOT / "scripts").rglob("*.py")]
    return sorted(p for p in paths if p != _ASSEMBLY_MODULE)


class NoDirectProviderConstructionTest(unittest.TestCase):
    def test_no_site_builds_an_embedding_provider_by_hand(self):
        """under-strict: 어떤 자리든 생성자를 직접 부르면 이 셀이 실패한다.

        `import` 나 문서에 이름이 나오는 것은 무관하다 — **호출**만 본다. 그래서
        문자열 검색이 아니라 AST 로 `Call` 노드의 피호출자 이름을 본다(2026-08-20
        mypy 가드에서 배운 것: 문자열 매칭은 표기 하나만 보고 나머지를 놓친다).
        """
        offenders = []
        for path in _sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = (func.id if isinstance(func, ast.Name)
                        else func.attr if isinstance(func, ast.Attribute) else None)
                if name in _PROVIDER_CONSTRUCTORS:
                    offenders.append(
                        f"{path.relative_to(_ROOT)}:{node.lineno}: {name}(...)")
        self.assertEqual(
            offenders, [],
            "조립은 build_embedding_provider_from_env() 한 곳에서만 한다 — "
            "여기 걸린 자리는 env 해석을 자기 몫으로 복제하고 있다")

    def test_the_helper_itself_is_allowed_to_construct(self):
        """over-strict: 헬퍼가 사는 파일까지 물면 조립 자체가 불가능해진다."""
        tree = ast.parse(_ASSEMBLY_MODULE.read_text(encoding="utf-8"))
        built = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertTrue(
            built & _PROVIDER_CONSTRUCTORS,
            "헬퍼 파일이 provider 를 하나도 만들지 않는다면 가드가 겨눈 대상이 "
            "사라진 것이다 — 이 셀의 전제부터 다시 본다")

    def test_every_assembly_site_reaches_the_helper(self):
        """조립 자리 여섯이 실제로 헬퍼를 부르는가 (없어짐도 잡는다).

        위 셀은 '직접 만들지 않는다' 만 본다. 자리가 헬퍼도 안 부르고 provider 를
        아예 안 쓰게 되면 그것도 이 슬라이스의 계약이 깨진 것이므로 함께 잠근다.
        """
        sites = [
            "services/application/app/main.py",
            "scripts/index_sync_worker.py",
            "scripts/phase2b5_reindex_memory.py",
            "scripts/phase2b5_reindex_candidate.py",
            "scripts/phase2b7_character_alias_live_smoke.py",
            "scripts/calibrate_character_identity_threshold.py",
        ]
        for site in sites:
            with self.subTest(site=site):
                text = (_ROOT / site).read_text(encoding="utf-8")
                self.assertIn("build_embedding_provider_from_env", text)


class HelperBehaviourTest(unittest.TestCase):
    def setUp(self):
        self._saved = {
            name: os.environ.pop(name, None)
            for name in ("EMBEDDING_SERVICE_URL", "EMBEDDING_DIMENSIONS",
                         "EMBEDDING_TIMEOUT_SECONDS", "EMBEDDING_TRUST_ENV")
        }

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_no_address_falls_back_to_the_fake(self):
        provider = build_embedding_provider_from_env()
        self.assertIsInstance(provider, DeterministicFakeEmbeddingProvider)

    def test_no_address_raises_when_the_caller_requires_one(self):
        # live smoke 는 fake 로 조용히 내려가면 안 된다 — 실서비스에 붙는 도구다.
        with self.assertRaises(ValueError) as raised:
            build_embedding_provider_from_env(required=True)
        self.assertIn("EMBEDDING_SERVICE_URL", str(raised.exception))

    def test_an_explicit_address_wins_over_the_environment(self):
        # 보정 스크립트가 주소를 CLI 인자로 받는다.
        os.environ["EMBEDDING_SERVICE_URL"] = "http://from-env:8000"
        provider = build_embedding_provider_from_env(base_url="http://explicit:9000")
        self.assertIsInstance(provider, RemoteEmbeddingProvider)
        self.assertEqual(provider._base_url, "http://explicit:9000")

    def test_the_dimension_guard_default_is_read_in_one_place(self):
        """1024 라는 기본값이 다섯 벌로 적혀 있던 것이 이 슬라이스의 부채였다."""
        os.environ["EMBEDDING_SERVICE_URL"] = "http://embedding:8000"
        self.assertEqual(
            build_embedding_provider_from_env()._expected_dimensions, 1024)
        os.environ["EMBEDDING_DIMENSIONS"] = "768"
        self.assertEqual(
            build_embedding_provider_from_env()._expected_dimensions, 768)

    def test_timeout_and_trust_env_come_from_the_environment(self):
        os.environ["EMBEDDING_SERVICE_URL"] = "http://embedding:8000"
        os.environ["EMBEDDING_TIMEOUT_SECONDS"] = "5.5"
        os.environ["EMBEDDING_TRUST_ENV"] = "true"
        provider = build_embedding_provider_from_env()
        self.assertEqual(provider._timeout_seconds, 5.5)
        self.assertTrue(provider._trust_env)

    def test_trust_env_defaults_to_false(self):
        # 기본이 True 로 뒤집히면 프록시 env 가 조용히 호출 경로를 바꾼다.
        os.environ["EMBEDDING_SERVICE_URL"] = "http://embedding:8000"
        self.assertFalse(build_embedding_provider_from_env()._trust_env)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
