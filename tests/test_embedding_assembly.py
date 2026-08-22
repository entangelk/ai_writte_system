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
    KeyRotatingEmbeddingProvider,
    OpenAIEmbeddingProvider,
    RemoteEmbeddingProvider,
    _embeddings_endpoint,
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


#: 최상위 코드 디렉터리 중 **일부러 범위 밖**인 것과 그 이유. 새 디렉터리가 생기면
#: 아래 `test_the_scan_covers_every_top_level_code_directory` 가 실패하므로, 조용히
#: 빠지는 대신 여기서 분류를 강요한다("세 번째 compose 파일" 계열의 처방 — 2026-08-20
#: 검증 H2). 이 저장소의 `test_compose_exposure` 가 새 서비스에 쓰는 방식과 같다.
_OUT_OF_SCOPE = {
    "tests": "테스트는 provider 를 직접 만드는 것이 정당하다(단위 테스트가 그 일이다)",
    "frontend": "TypeScript 표면 — 파이썬 조립 지점이 아니다",
    "docs": "문서. 재현 스크립트가 뮤테이션으로 생성자를 적는 자리가 있다",
    "schemas": "계약 파일",
}

#: 스캔하는 최상위 디렉터리.
_SCANNED = ("services", "scripts")


def _top_level_python_dirs() -> set[str]:
    found = set()
    for child in _ROOT.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name == "node_modules":
            continue
        if next(child.rglob("*.py"), None) is not None:
            found.add(child.name)
    return found


def _sources() -> list[Path]:
    paths = [q for name in _SCANNED for q in (_ROOT / name).rglob("*.py")]
    return sorted(p for p in paths if p != _ASSEMBLY_MODULE)


def _constructor_names(tree: ast.AST) -> set[str]:
    """이 파일 안에서 provider 생성자를 가리키는 **모든 이름**.

    ★ 원이름만 보면 `import … as REP` 뒤의 `REP(…)` 를 놓친다. 2026-08-20 독립
    검증이 실제로 그것으로 가드를 뚫었고(조건 B1), `import … as …` 는 이 저장소
    스크립트에서 쓰이는 평범한 관행이라 벡터가 현실적이었다.

    **잔여(의도적으로 안 잡는 것): 할당 별칭** — `P = RemoteEmbeddingProvider`
    뒤의 `P(…)`. 잡으려면 이름 재결합을 따라가야 하고 그것은 타입체커의 일이다.
    여기서 멈추는 것이 이 셀의 계약이며, 아래 docstring 이 그렇게 말한다.
    """

    names = set(_PROVIDER_CONSTRUCTORS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in _PROVIDER_CONSTRUCTORS and alias.asname:
                    names.add(alias.asname)
    return names


class NoDirectProviderConstructionTest(unittest.TestCase):
    def test_no_site_builds_an_embedding_provider_by_hand(self):
        """under-strict: 생성자를 직접 부르는 자리가 있으면 이 셀이 실패한다.

        `import` 나 문서에 이름이 나오는 것은 무관하다 — **호출**만 본다. 그래서
        문자열 검색이 아니라 AST 로 `Call` 노드의 피호출자 이름을 본다(2026-08-20
        mypy 가드에서 배운 것: 문자열 매칭은 표기 하나만 보고 나머지를 놓친다).

        **잡는 형태 셋**: 원이름 호출 · 모듈 속성 호출(`emb.RemoteEmbeddingProvider(…)`)
        · **`import … as REP` 뒤의 `REP(…)`**. 셋째는 2026-08-20 독립 검증이 조건
        B1 으로 뚫은 자리다 — 원이름 집합과만 비교하던 초판이 침묵했고, `as` 는
        이 저장소에서 쓰이는 평범한 관행이라 벡터가 현실적이었다.

        **★ 잔여 하나 — 할당 별칭은 안 잡는다.** `P = RemoteEmbeddingProvider` 뒤의
        `P(…)` 는 통과한다. 이름 재결합을 따라가는 것은 타입체커의 일이고, 여기서
        멈추는 것이 이 셀의 계약이다. **계약 문언을 잠금보다 넓게 쓰지 않으려고
        적어 둔다** — 오늘 두 번 그 실수를 했다(정본 산출물 문언 · 셀 실패 메시지).
        """
        offenders = []
        for path in _sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            # 원이름 + 이 파일이 붙인 별칭. 파일마다 다시 만든다 — 별칭은 파일
            # 스코프이고, 한 파일의 `as REP` 가 다른 파일의 `REP` 를 뜻하지 않는다.
            local_names = _constructor_names(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = (func.id if isinstance(func, ast.Name)
                        else func.attr if isinstance(func, ast.Attribute) else None)
                if name in local_names:
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


class ScanScopeTest(unittest.TestCase):
    def test_the_scan_covers_every_top_level_code_directory(self):
        """새 최상위 코드 디렉터리가 조용히 범위 밖으로 빠지지 않게 한다.

        경로를 하드코딩한 스캔은 "세 번째 compose 파일" 과 같은 병이다 — 계약이
        디렉터리에 걸려 있는데 목록이 둘만 알고 있으면, 셋째가 생기는 날 가드가
        아무 말도 안 한다(2026-08-20 검증 H2). 그래서 **분류를 강요한다**:
        스캔하거나, 이유와 함께 범위 밖으로 적거나 둘 중 하나다.
        """
        classified = set(_SCANNED) | set(_OUT_OF_SCOPE)
        unclassified = _top_level_python_dirs() - classified
        self.assertEqual(
            unclassified, set(),
            "새 최상위 파이썬 디렉터리다 — _SCANNED 에 넣거나 _OUT_OF_SCOPE 에 "
            "이유와 함께 적는다")

    def test_the_scanned_directories_still_exist(self):
        # over-strict 반대쪽: 목록만 남고 디렉터리가 사라지면 스캔이 0파일이 되고
        # 위 셀은 조용히 통과한다.
        for name in _SCANNED:
            with self.subTest(directory=name):
                self.assertTrue((_ROOT / name).is_dir())
                self.assertTrue(next((_ROOT / name).rglob("*.py"), None))


class HelperBehaviourTest(unittest.TestCase):
    def setUp(self):
        self._saved = {
            name: os.environ.pop(name, None)
            for name in ("EMBEDDING_SERVICE_URL", "EMBEDDING_DIMENSIONS",
                         "EMBEDDING_TIMEOUT_SECONDS", "EMBEDDING_TRUST_ENV",
                         "EMBEDDING_API_FORMAT", "EMBEDDING_API_MODEL",
                         "EMBEDDING_API_KEY", "EMBEDDING_API_KEYS",
                         "EMBEDDING_KEY_RPM")
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




class WireFormatSelectionTest(unittest.TestCase):
    """어느 형식을 고르는가 — env 하나로 명시하고 추론하지 않는다."""

    def setUp(self):
        self._saved = {
            name: os.environ.pop(name, None)
            for name in ("EMBEDDING_SERVICE_URL", "EMBEDDING_API_FORMAT",
                         "EMBEDDING_API_MODEL", "EMBEDDING_API_KEY",
                         "EMBEDDING_DIMENSIONS", "EMBEDDING_API_KEYS",
                         "EMBEDDING_KEY_RPM")
        }
        os.environ["EMBEDDING_SERVICE_URL"] = "https://api.example.com"

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_the_default_is_our_own_format(self):
        """기존 배포가 env 를 하나도 안 건드려도 그대로 돌아야 한다."""
        self.assertIsInstance(
            build_embedding_provider_from_env(), RemoteEmbeddingProvider)

    def test_openai_format_is_chosen_explicitly(self):
        os.environ["EMBEDDING_API_FORMAT"] = "openai"
        os.environ["EMBEDDING_API_MODEL"] = "text-embedding-3-small"
        provider = build_embedding_provider_from_env()
        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertEqual(provider._model, "text-embedding-3-small")

    def test_the_key_alone_does_not_switch_the_format(self):
        """★ 형식을 키 유무로 추론하지 않는다.

        추론하면 키를 지운 순간 형식이 조용히 바뀌고, 그 실패는 "왜 갑자기 404 인가"
        로 나타난다 — 원인에서 가장 먼 자리다.
        """
        os.environ["EMBEDDING_API_KEY"] = "sk-test"
        self.assertIsInstance(
            build_embedding_provider_from_env(), RemoteEmbeddingProvider)

    def test_openai_format_without_a_model_fails_fast(self):
        # 모델은 요청마다 보내므로 기본값이 있을 수 없다. 여기서 안 멈추면
        # 벤더 오류를 읽게 되고, 그 메시지는 우리 설정을 말하지 않는다.
        os.environ["EMBEDDING_API_FORMAT"] = "openai"
        with self.assertRaises(ValueError) as raised:
            build_embedding_provider_from_env()
        self.assertIn("EMBEDDING_API_MODEL", str(raised.exception))

    def test_an_unknown_format_fails_fast_and_names_the_valid_values(self):
        # 오타(`openAI`, `open-ai`)가 조용히 자체 형식으로 떨어지면
        # "키를 넣었는데 왜 안 나가나" 가 된다.
        os.environ["EMBEDDING_API_FORMAT"] = "open-ai"
        with self.assertRaises(ValueError) as raised:
            build_embedding_provider_from_env()
        self.assertIn("native", str(raised.exception))
        self.assertIn("openai", str(raised.exception))

    def test_a_pasted_vendor_base_url_does_not_double_the_version_prefix(self):
        """벤더 문서는 base 를 `…/v1` 로 인쇄한다 — 그대로 붙여도 404 가 아니어야."""
        os.environ["EMBEDDING_API_FORMAT"] = "openai"
        os.environ["EMBEDDING_API_MODEL"] = "m"
        for pasted, expected in (
            ("https://api.example.com/v1", "https://api.example.com"),
            ("https://api.example.com/v1/", "https://api.example.com"),
            ("https://api.example.com", "https://api.example.com"),
            # over-strict: 경로 안의 v1 은 접미가 아니다.
            ("https://api.example.com/v1/proxy", "https://api.example.com/v1/proxy"),
        ):
            with self.subTest(base_url=pasted):
                os.environ["EMBEDDING_SERVICE_URL"] = pasted
                self.assertEqual(
                    build_embedding_provider_from_env()._base_url, expected)

    def test_the_dimension_guard_reaches_the_openai_provider_too(self):
        os.environ["EMBEDDING_API_FORMAT"] = "openai"
        os.environ["EMBEDDING_API_MODEL"] = "m"
        os.environ["EMBEDDING_DIMENSIONS"] = "1536"
        self.assertEqual(
            build_embedding_provider_from_env()._expected_dimensions, 1536)


class KeyListAssemblyTest(unittest.TestCase):
    """EMBEDDING_API_KEYS — 키 리스트 조립 (오너 2026-08-22).

    ★ 총괄 over-strict 가드: 리스트 없는 세계는 오늘의 단일 provider 그 자체다.
    1개도 마찬가지 — 폴백 조합이 없을 때 래퍼를 얹는 것은 과설계다.
    """

    def setUp(self):
        self._saved = {
            name: os.environ.pop(name, None)
            for name in ("EMBEDDING_SERVICE_URL", "EMBEDDING_API_FORMAT",
                         "EMBEDDING_API_MODEL", "EMBEDDING_API_KEY",
                         "EMBEDDING_DIMENSIONS", "EMBEDDING_API_KEYS",
                         "EMBEDDING_KEY_RPM")
        }
        os.environ["EMBEDDING_SERVICE_URL"] = "https://api.example.com"
        os.environ["EMBEDDING_API_FORMAT"] = "openai"
        os.environ["EMBEDDING_API_MODEL"] = "text-embedding-3-small"

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_keys_unset_still_builds_the_bare_provider(self):
        provider = build_embedding_provider_from_env()
        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertNotIsInstance(provider, KeyRotatingEmbeddingProvider)

    def test_a_single_key_in_the_list_builds_the_bare_provider(self):
        os.environ["EMBEDDING_API_KEYS"] = "sk-1"
        self.assertIsInstance(
            build_embedding_provider_from_env(), OpenAIEmbeddingProvider)

    def test_multiple_keys_build_the_rotating_wrapper(self):
        # 쉼표 분리·공백·중복 제거가 조립 지점에서 함께 걸린다.
        os.environ["EMBEDDING_API_KEYS"] = " sk-1 , sk-2 ,,sk-1 "
        provider = build_embedding_provider_from_env()
        self.assertIsInstance(provider, KeyRotatingEmbeddingProvider)
        self.assertEqual(
            [inner._api_key for inner in provider._providers],
            ["sk-1", "sk-2"],
        )

    def test_the_legacy_single_key_variable_is_still_honoured(self):
        os.environ["EMBEDDING_API_KEY"] = "sk-legacy"
        provider = build_embedding_provider_from_env()
        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertEqual(provider._api_key, "sk-legacy")

    def test_keys_with_the_native_format_fail_fast(self):
        # native 서비스는 키를 안 쓴다 — 리스트가 명시됐는데 조용히 무시되면
        # "넣었는데 왜 회전하지 않나"가 된다.
        os.environ["EMBEDDING_API_KEYS"] = "sk-1,sk-2"
        os.environ["EMBEDDING_API_FORMAT"] = "native"
        with self.assertRaises(ValueError) as raised:
            build_embedding_provider_from_env()
        self.assertIn("EMBEDDING_API_KEYS", str(raised.exception))
        self.assertIn("openai", str(raised.exception))

    def test_non_positive_rpm_fails_fast(self):
        os.environ["EMBEDDING_API_KEYS"] = "sk-1,sk-2"
        os.environ["EMBEDDING_KEY_RPM"] = "0"
        with self.assertRaisesRegex(ValueError, "EMBEDDING_KEY_RPM"):
            build_embedding_provider_from_env()

    def test_a_google_root_builds_the_google_shaped_endpoint(self):
        # 구글은 /v1/embeddings 경로가 없다(2026-08-22 실측) — /v1beta/openai 루트를
        # 넣으면 경로가 /embeddings 로 바뀐다. 호스트 루트만 넣으면 동작하지 않는다.
        os.environ["EMBEDDING_SERVICE_URL"] = (
            "https://generativelanguage.googleapis.com/v1beta/openai"
        )

        provider = build_embedding_provider_from_env()

        self.assertIsInstance(provider, OpenAIEmbeddingProvider)
        self.assertEqual(
            provider._base_url,
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )
        self.assertEqual(provider._embeddings_path, "/embeddings")


class EmbeddingsEndpointTests(unittest.TestCase):
    """붙여넣은 벤더 주소가 그대로 동작해야 한다 — 게이트웨이 `_chat_endpoint`와 같은 관례.

    under-strict: 구글 루트에 /v1 을 얹으면 재실패한다(404). over-strict: 경로 안의
    `v1` 을 접미로 오인해 벗기면 재실패한다.
    """

    def test_pasted_addresses_reach_the_right_endpoint(self):
        cases = {
            # 구글 — 문서가 인쇄하는 OpenAI 호환 루트(접미 /v1 이 없다)
            "https://generativelanguage.googleapis.com/v1beta/openai": (
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "/embeddings",
            ),
            "https://generativelanguage.googleapis.com/v1beta/openai/": (
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "/embeddings",
            ),
            # 전체 엔드포인트를 통째로 붙여넣기
            "https://generativelanguage.googleapis.com/v1beta/openai/embeddings": (
                "https://generativelanguage.googleapis.com/v1beta/openai",
                "/embeddings",
            ),
            # OpenAI — 문서가 …/v1 까지 인쇄한다
            "https://api.openai.com/v1": (
                "https://api.openai.com",
                "/v1/embeddings",
            ),
            # OpenRouter — …/api/v1 까지 인쇄한다
            "https://openrouter.ai/api/v1": (
                "https://openrouter.ai/api",
                "/v1/embeddings",
            ),
            # 호스트 루트(우리 관례의 기본형)
            "https://api.example.com": (
                "https://api.example.com",
                "/v1/embeddings",
            ),
            # over-strict: 경로 안의 v1 은 접미가 아니다
            "https://proxy.example.com/v1/proxy": (
                "https://proxy.example.com/v1/proxy",
                "/v1/embeddings",
            ),
        }
        for pasted, (base, path) in cases.items():
            with self.subTest(pasted=pasted):
                self.assertEqual(_embeddings_endpoint(pasted), (base, path))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
