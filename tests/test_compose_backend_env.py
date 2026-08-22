"""배포 서버 전용 배선 가드: 외부 백엔드 3종은 compose 하드코딩이 아니라 env 로 정해진다.

오너 결정 **D-10.5-d**(2026-08-13 방향, 2026-08-14 배선 시행) — *"실제 서비스 서버는 모델을
받지 않고 **외부 API 로만** 빌드해야 하고, **모델이 로컬에 있더라도 API 가 있으면 API 로**
물려야 한다."*

코드는 원래부터 준비돼 있었다 — `_build_embedding_provider()` 등 세 자리가 전부
``if not os.environ.get(...)`` 라 **빈 문자열을 미설정으로 취급**한다(main.py:1123·1024·1047).
막고 있던 것은 코드가 아니라 **compose 하드코딩**이었다. 이 가드가 그 배선을 잠근다.

잡으려는 것 셋:

- **under-strict**: 하드코딩(``EMBEDDING_SERVICE_URL: "http://embedding:8002"``)으로 되돌리면
  실패한다. 종전 상태가 정확히 그것이었으므로 이 방향이 원래 결함의 재현이다.
- **★ 콜론 회귀**: ``${VAR:-default}`` 로 바꿔도 실패한다. **이 파일의 다른 40여 항목이 전부
  콜론 형태라 그쪽이 이 저장소의 관례처럼 보이는데, 여기서는 그것이 기능을 죽인다** —
  콜론 형태는 *빈 값*을 default 로 되돌리므로 ``EMBEDDING_SERVICE_URL=`` 로 끄는 것이
  **불가능**해진다. 겉보기에는 올바르게 고친 것과 구별되지 않아 배포 서버에서야 발견된다.
  그래서 이 축은 사람 눈이 아니라 셀이 봐야 한다.
- **over-strict**: 반대 방향의 과잉 교정도 실패한다. **기본값(env 미설정)은 여전히 in-stack
  서비스여야 한다** — default 를 지우면 개발 머신의 기본 기동이 조용히 fake 임베딩·벡터
  없음·Mongo 직조회로 내려가는데, 그것은 에러가 아니라 **조용한 품질 저하**라 아무도 못 본다.

그리고 목록을 믿지 않는다: **이 변수들을 선언하는 서비스 집합 자체를 파일에서 읽어** 검사한다
(`test_compose_exposure.py` 와 같은 원리). 네 번째 서비스가 같은 백엔드를 하드코딩으로 물면
그 자리에서 실패한다 — 지금까지 셋이 나란히 틀려 있었던 것이 바로 그 형태다.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# 서비스 키(2칸)와 environment 항목(6칸)만 읽는다. compose 는 따옴표 3종을 다 받는다.
_SERVICE_RE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
_ENVIRONMENT_RE = re.compile(r"^    environment:\s*$")
_ENV_ITEM_RE = re.compile(r"""^      ([A-Z0-9_]+):\s*['"]?(.*?)['"]?\s*$""")

# 외부화 대상 — 배포 서버가 API 로 갈아끼우거나 꺼야 하는 백엔드.
#   변수명 → env 미설정일 때의 in-stack 기본값
_EXTERNALIZABLE = {
    "EMBEDDING_SERVICE_URL": "http://embedding:8002",
    "CHROMA_HOST": "chroma",
    "ELASTICSEARCH_URL": "http://elasticsearch:9200",
}

# ★ CHROMA_PORT 는 일부러 대상이 아니다. 같은 이름이 아래 host publish
# (`127.0.0.1:${CHROMA_PORT:-8523}:8000`)에서 **호스트 포트**를 뜻하고 여기서는
# **컨테이너 내부 포트**를 뜻한다. 이름을 공유시키면 호스트 포트를 바꾼 사람이
# 앱을 아무도 안 듣는 포트로 조용히 돌리게 된다.
_DELIBERATELY_HARDCODED = {"CHROMA_PORT": "8000"}


def _env_by_service(text: str) -> dict[str, dict[str, str]]:
    """compose 본문에서 서비스별 environment 매핑을 뽑는다."""

    service: str | None = None
    in_environment = False
    found: dict[str, dict[str, str]] = {}

    for line in text.splitlines():
        matched_service = _SERVICE_RE.match(line)
        if matched_service:
            service = matched_service.group(1)
            in_environment = False
            continue
        if service is None:
            continue
        if _ENVIRONMENT_RE.match(line):
            in_environment = True
            continue
        # 같은 깊이의 다른 키(ports:·depends_on: …)를 만나면 environment 는 끝났다.
        if in_environment and re.match(r"^    [A-Za-z]", line):
            in_environment = False
            continue
        if not in_environment:
            continue
        matched_item = _ENV_ITEM_RE.match(line)
        if matched_item:
            name, value = matched_item.groups()
            found.setdefault(service, {})[name] = value

    return found


def _dash_form(name: str, default: str) -> str:
    """끄기가 가능한 유일한 표기 — 콜론이 없어야 빈 값이 빈 채로 통과한다."""

    return "${" + f"{name}-{default}" + "}"


class ExternalBackendEnvTest(unittest.TestCase):
    """`docker-compose.yml` 의 백엔드 3종은 env 로 갈아끼울 수 있어야 한다."""

    def setUp(self) -> None:
        self.text = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.by_service = _env_by_service(self.text)

    def test_every_service_declaring_a_backend_takes_it_from_env(self) -> None:
        """선언하는 서비스를 **파일에서 읽어** 전수로 본다 — 새 서비스도 강제된다."""

        declaring = {
            service: env
            for service, env in self.by_service.items()
            if _EXTERNALIZABLE.keys() & env.keys()
        }
        # 지금은 셋이지만 수를 단정하지 않는다. 단정하면 네 번째 서비스가 생겼을 때
        # "숫자를 고치면 통과"가 되어 분류 강제가 무력해진다.
        self.assertTrue(declaring, "백엔드 3종을 선언하는 서비스가 하나도 없다")

        for service, env in sorted(declaring.items()):
            for name, default in _EXTERNALIZABLE.items():
                with self.subTest(service=service, variable=name):
                    self.assertIn(
                        name,
                        env,
                        f"{service} 가 백엔드 일부만 선언한다 — 셋은 함께 간다",
                    )
                    self.assertEqual(
                        env[name],
                        _dash_form(name, default),
                        f"{service}.{name} 이 env 로 갈아끼울 수 없다. "
                        f"하드코딩이거나 콜론 형태(${{{name}:-…}})다 — "
                        "콜론은 빈 값을 default 로 되돌려 '끄기'를 불가능하게 만든다",
                    )

    def test_the_colon_form_is_rejected_because_it_cannot_express_off(self) -> None:
        """★ 이 파일의 관례(`${VAR:-x}`)를 여기 그대로 적용하면 기능이 죽는다."""

        for service, env in sorted(self.by_service.items()):
            for name in _EXTERNALIZABLE:
                value = env.get(name)
                if value is None:
                    continue
                with self.subTest(service=service, variable=name):
                    self.assertNotIn(
                        f"{name}:-",
                        value,
                        f"{service}.{name} 이 콜론 형태다. "
                        f"`{name}=` (빈 값)이 default 로 되돌아가므로 배포 서버가 "
                        "이 백엔드를 끌 수 없다 — 코드의 `if not ...` fallback 에 "
                        "영영 도달하지 못한다",
                    )

    def test_the_default_is_still_the_in_stack_service(self) -> None:
        """over-strict — default 를 지우면 기본 기동이 **조용히** 강등된다."""

        for service, env in sorted(self.by_service.items()):
            for name, default in _EXTERNALIZABLE.items():
                value = env.get(name)
                if value is None:
                    continue
                with self.subTest(service=service, variable=name):
                    self.assertTrue(
                        value.endswith(f"-{default}" + "}"),
                        f"{service}.{name} 의 기본값이 in-stack({default}) 이 아니다. "
                        "env 를 안 준 개발 머신이 fake 임베딩·벡터 없음·Mongo 직조회로 "
                        "내려가는데 그것은 에러가 아니라 조용한 품질 저하다",
                    )

    def test_chroma_port_stays_hardcoded_because_the_name_is_taken(self) -> None:
        """★ 이름 충돌 — 같은 `CHROMA_PORT` 가 host publish 에서는 호스트 포트다."""

        for service, env in sorted(self.by_service.items()):
            for name, literal in _DELIBERATELY_HARDCODED.items():
                value = env.get(name)
                if value is None:
                    continue
                with self.subTest(service=service, variable=name):
                    self.assertEqual(
                        value,
                        literal,
                        f"{service}.{name} 을 env 화하면, host publish "
                        f"(`127.0.0.1:${{{name}:-8523}}:8000`)가 같은 이름을 쓰므로 "
                        "호스트 포트를 바꾼 사람이 앱을 아무도 안 듣는 포트로 돌리게 된다. "
                        "외부 Chroma 는 override 파일로 붙인다",
                    )
        # 호스트 publish 쪽이 같은 이름을 계속 쓰고 있다는 것 자체가 이 셀의 전제다.
        self.assertIn(
            "${CHROMA_PORT:-8523}",
            self.text,
            "host publish 가 CHROMA_PORT 를 안 쓰면 이름 충돌이 사라진다 — "
            "그때는 위 예외를 다시 볼 것",
        )


class InStackLlamaOverrideTest(unittest.TestCase):
    """`docker-compose.llama.yml` — 모델이 있어도 API 가 있으면 API 가 이긴다.

    ★ 여기는 **콜론 형태**가 맞고 위 백엔드 3종은 dash 형태가 맞다. 표기는 취향이 아니라
    **코드가 그 변수를 읽는 방식**을 따라간다:

    - gateway 는 ``os.environ.get("LLAMA_BASE_URL", DEFAULT)`` — 기본값 *인자*라
      빈 문자열이 미설정으로 취급되지 **않는다**. dash 형태로 두면 빈 값이 그대로
      base URL 이 되어 모든 호출이 실패한다. 콜론 형태라야 빈 값이 in-stack 으로 돌아간다.
    - 백엔드 3종은 ``if not os.environ.get(...)`` — 빈 값 == 미설정 == 문서화된 fallback.
      거기서는 콜론 형태가 '끄기' 를 불가능하게 만든다.

    즉 **같은 실수의 두 방향**이고, 어느 쪽이든 배포에서만 드러난다.
    """

    def setUp(self) -> None:
        self.by_service = _env_by_service(
            (_REPO_ROOT / "docker-compose.llama.yml").read_text(encoding="utf-8")
        )

    def test_an_explicit_base_url_wins_over_the_in_stack_model(self) -> None:
        """종전에는 하드코딩이라 in-stack llama 가 `.env` 를 **무조건** 이겼다."""

        gateway = self.by_service.get("gateway", {})
        self.assertEqual(
            gateway.get("LLAMA_BASE_URL"),
            "${LLAMA_BASE_URL:-http://llama:9080}",
            "이 override 를 쓰는 순간 in-stack llama 가 무조건 이긴다 — "
            "오너 규칙 '모델이 있어도 API 가 있다면 API 로' 의 반대다",
        )

    def test_an_empty_value_falls_back_to_the_in_stack_model(self) -> None:
        """over-strict — dash 형태로 '통일' 하면 빈 값이 깨진 base URL 이 된다.

        gateway 의 읽기가 기본값 *인자* 라서, 빈 값은 fallback 이 아니라 ``""`` 그대로
        전달된다. 백엔드 3종과 표기를 맞추려는 리팩터링이 정확히 이 방향이다.
        """

        gateway = self.by_service.get("gateway", {})
        self.assertNotEqual(
            gateway.get("LLAMA_BASE_URL"),
            _dash_form("LLAMA_BASE_URL", "http://llama:9080"),
            "dash 형태는 `LLAMA_BASE_URL=` 을 빈 base URL 로 흘려보낸다 — "
            "gateway 는 `os.environ.get(name, DEFAULT)` 로 읽어 빈 값을 "
            "미설정으로 보지 않는다",
        )


class ExternalOverrideTest(unittest.TestCase):
    """`docker-compose.external.yml` — 배포 서버는 모델을 하나도 받지 않는다.

    base 를 **복제하지 않고 덮는** override 다(`docker-compose.llama.yml` 과 같은 패턴,
    방향만 반대). 여기서 잠그는 것은 그 파일이 실제로 *외부 전용* 인가이며, 네 축이다:
    주소 필수 · 모델 서비스 비기동 · 꺼진 것을 기다리지 않음 · 이름 충돌 회피.
    """

    PATH = "docker-compose.external.yml"
    #: 모델·플러그인을 들고 오는 서비스 — 배포 서버에서 기동도 빌드도 되면 안 된다.
    MODEL_SERVICES = ("embedding", "chroma", "elasticsearch")
    #: 외부 주소를 반드시 받아야 하는 변수.
    REQUIRED = ("EMBEDDING_SERVICE_URL", "CHROMA_HOST", "ELASTICSEARCH_URL")

    def setUp(self) -> None:
        self.text = (_REPO_ROOT / self.PATH).read_text(encoding="utf-8")
        self.by_service = _env_by_service(self.text)

    def test_external_addresses_are_required_not_defaulted(self) -> None:
        """`:?` — 값이 없으면 기동을 거부한다.

        default 를 주면 배포 서버가 **뜨지도 않는 in-stack 서비스**를 조용히 가리키고,
        그것은 기동 실패가 아니라 첫 검색에서야 연결 오류로 드러난다.
        """

        declaring = {s: e for s, e in self.by_service.items() if set(self.REQUIRED) & e.keys()}
        self.assertTrue(declaring, "외부 주소를 선언하는 서비스가 없다")
        for service, env in sorted(declaring.items()):
            for name in self.REQUIRED:
                with self.subTest(service=service, variable=name):
                    self.assertIn(name, env, f"{service} 가 외부 백엔드 일부만 덮는다")
                    self.assertIn(
                        f"${{{name}:?",
                        env[name],
                        f"{service}.{name} 이 필수가 아니다 — 값이 없을 때 "
                        "in-stack 기본값으로 조용히 떨어진다",
                    )

    def test_the_llm_address_is_required_because_nothing_can_fall_back(self) -> None:
        """★ 배포 서버에는 폴백할 모델이 없다 — 그래서 주소가 없으면 기동을 거부한다.

        오너 규칙(2026-08-16): *"① env 에 외부 API 가 있으면 그거 사용 ② 없다면 내부
        LLM 모델 다운로드 시도 ③ 다운로드가 에러나거나 시도되지 못했다면 당연히 실패."*
        `docker-compose.llama.yml` 에서는 ①②③이 이미 그대로 돈다(콜론 폴백 → in-stack
        llama → healthcheck 실패 시 gateway 가 `depends_on` 에 걸려 안 뜬다). **이
        override 는 모델을 하나도 받지 않는 것이 목적이라 ②가 구조적으로 불가능**하고,
        따라서 남는 것은 ③뿐이다.

        안 잠그면: base 의 `${LLAMA_BASE_URL:-http://host.docker.internal:9080}` 이
        살아 있어 배포 서버가 **자기 자신의 9080**(아무것도 없는 자리)을 조용히 가리킨다.
        스택은 healthy 로 뜨고 생성만 전부 실패하므로 원인이 주소 누락으로 안 보인다.
        """

        gateway = self.by_service.get("gateway", {})
        self.assertIn(
            "${LLAMA_BASE_URL:?",
            gateway.get("LLAMA_BASE_URL", ""),
            "배포 override 가 LLM 주소를 필수로 잡지 않는다 — 빠뜨리면 스택은 뜨는데 "
            "`host.docker.internal:9080`(그 서버에 없는 자리)을 조용히 가리키고 "
            "생성만 전부 실패한다. `.env.example` 이 배격한 그 실패 형태다",
        )

    def test_the_base_file_still_falls_back_so_dev_machines_keep_booting(self) -> None:
        """over-strict — 이 필수화를 base 에까지 '통일' 하면 개발 머신이 안 뜬다.

        같은 변수가 **파일마다 다른 계약**을 갖는 자리다. 배포(이 override)는 폴백할
        모델이 없어서 필수이고, base 는 호스트 llama·외부 LAN 서버로 폴백하는 것이
        옳아서 콜론 형태다(베타·감마가 그 경로로 돈다). 한쪽 규칙을 다른 쪽에 복사하는
        것이 이 슬라이스에서 가장 자연스러워 보이는 과잉 교정이다.

        ★ 이 단정은 base `docker-compose.yml:202` 의 표기를 잠그는 **첫 셀**이기도 하다
        (2026-08-15 검증 B1 — 종전에는 그 자리를 dash 로 바꿔도 무는 셀이 0건이었다).
        다만 잠그는 방식이 '이 두 파일' 이라 세 번째 compose 파일이 생기면 따라가지
        않는다 — 그 일반화는 여전히 열린 항목이다.
        """

        base = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn(
            '"${LLAMA_BASE_URL:-http://host.docker.internal:9080}"',
            base,
            "base 의 LLAMA_BASE_URL 이 콜론 폴백을 잃었다. `:?` 로 필수화하면 배포 서버 "
            "규칙을 개발 머신에 강요하는 것이고, dash 로 바꾸면 빈 값이 깨진 base URL 로 "
            "흘러간다(gateway 는 `os.environ.get(name, DEFAULT)` 로 읽는다)",
        )

    def test_the_embedding_api_env_uses_the_notation_its_reader_needs(self) -> None:
        """새 임베딩 API env 3종의 표기 — 콜론/대시가 취향이 아니라 코드를 따라간다.

        `EMBEDDING_API_FORMAT` 은 코드가 `get(name, DEFAULT)` 로 읽으므로 **콜론**이
        맞다. 대시로 두면 `EMBEDDING_API_FORMAT=` (빈 값)이 그대로 넘어가 코드가
        `ValueError` 를 던진다 — 끄려던 사람이 기동 실패를 본다.

        `EMBEDDING_API_MODEL`·`EMBEDDING_API_KEY` 는 `get(name)` + falsy 검사라
        **대시**다. 지금은 기본값이 비어 있어 두 표기의 행동이 같지만, **표기 규칙을
        지키는 것 자체가 다음 사람이 기본값을 넣을 때의 안전장치**다 — 콜론에
        기본값이 붙는 순간 "빈 값으로 끄기" 가 조용히 불가능해진다.

        선례: `EMBEDDING_SERVICE_URL` 의 대시(위 `_dash_form`) · `LLAMA_BASE_URL`
        의 콜론. 이 저장소는 같은 이유로 두 번 다 형태를 셀로 잠갔다.
        """
        expected = {
            "EMBEDDING_API_FORMAT": ("${EMBEDDING_API_FORMAT:-native}", "콜론"),
            "EMBEDDING_API_MODEL": ("${EMBEDDING_API_MODEL-}", "대시"),
            "EMBEDDING_API_KEY": ("${EMBEDDING_API_KEY-}", "대시"),
            # 키 폴백(오너 2026-08-22) — 같은 규칙이 4종에 더 붙는다.
            "EMBEDDING_API_KEYS": ("${EMBEDDING_API_KEYS-}", "대시"),
            "EMBEDDING_KEY_RPM": ("${EMBEDDING_KEY_RPM:-30}", "콜론"),
            "RERANK_API_KEYS": ("${RERANK_API_KEYS-}", "대시"),
            "RERANK_KEY_RPM": ("${RERANK_KEY_RPM:-30}", "콜론"),
        }
        services = [name for name, env in self.by_service.items()
                    if "EMBEDDING_SERVICE_URL" in env]
        self.assertEqual(len(services), 3, "임베딩을 받는 서비스가 셋이어야 한다")
        for service in services:
            for name, (literal, form) in expected.items():
                with self.subTest(service=service, variable=name):
                    self.assertEqual(
                        self.by_service[service].get(name), literal,
                        f"{service}.{name} 은 {form} 형태여야 한다 — "
                        "표기는 코드가 그 변수를 읽는 방식을 따라간다")

    def test_the_gateway_fallback_env_uses_the_notation_its_reader_needs(self) -> None:
        """게이트웨이 키 폴백 env 3종(base) — 역시 코드를 따라간다.

        `LLAMA_API_KEYS`·`LLAMA_MODELS` 는 parse_env_list 가 빈 값을 unset 으로
        읽으므로 **대시**, `LLAMA_KEY_RPM` 은 `_env_float` 이 빈 값을 `float()` 로
        바꾸다 크래시하므로 **콜론**(기본 30). override 들(external·llama)은 base
        와 병합되고 LLAMA_* 를 덮지 않으므로 base 하나가 셋을 다 덮는다.
        """
        base = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for literal in (
            '"${LLAMA_API_KEYS-}"',
            '"${LLAMA_MODELS-}"',
            '"${LLAMA_KEY_RPM:-30}"',
        ):
            with self.subTest(literal=literal):
                self.assertIn(
                    literal, base,
                    "표기는 코드가 그 변수를 읽는 방식을 따라간다"
                    "(대시=빈 값 허용, 콜론=빈 값 방지)")

    def test_model_carrying_services_are_behind_a_profile(self) -> None:
        """profile 뒤에 있어야 기동에서도 `build` 에서도 빠진다(2026-08-14 실측)."""

        for service in self.MODEL_SERVICES:
            with self.subTest(service=service):
                block = self.text.split(f"\n  {service}:\n", 1)
                self.assertEqual(len(block), 2, f"{service} 를 override 가 안 덮는다")
                self.assertIn(
                    "profiles:",
                    block[1].split("\n  ", 1)[0],
                    f"{service} 가 profile 뒤에 없다 — 배포 서버가 이 이미지를 "
                    "빌드하고 띄운다(embedding 은 torch 를 끌고 온다)",
                )

    def test_nothing_waits_on_the_services_that_are_off(self) -> None:
        """`depends_on` 에 꺼진 셋이 남아 있으면 앱이 영영 안 뜬다."""

        for service in self.MODEL_SERVICES:
            with self.subTest(service=service):
                self.assertNotIn(
                    f"      {service}:\n        condition:",
                    self.text,
                    f"꺼져 있는 {service} 를 무언가가 기다린다 — "
                    "`depends_on: !override` 로 대체하는 것을 빠뜨렸다",
                )

    def test_the_internal_chroma_port_does_not_reuse_the_host_port_name(self) -> None:
        """★ `CHROMA_PORT` 는 base 에서 **호스트 게시 포트** 이름으로 이미 쓰인다."""

        for service, env in sorted(self.by_service.items()):
            value = env.get("CHROMA_PORT")
            if value is None:
                continue
            with self.subTest(service=service):
                self.assertNotIn(
                    "${CHROMA_PORT",
                    value,
                    "호스트 게시 포트와 이름을 공유하면, 그 포트를 바꾼 사람이 "
                    "앱을 아무도 안 듣는 포트로 돌린다. 별도 이름을 쓴다",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
