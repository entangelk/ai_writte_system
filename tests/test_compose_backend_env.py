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
    """`docker-compose.llama.yml` — 모델이 있어도 API 가 있으면 API 가 이긴다."""

    def setUp(self) -> None:
        self.by_service = _env_by_service(
            (_REPO_ROOT / "docker-compose.llama.yml").read_text(encoding="utf-8")
        )

    def test_an_explicit_base_url_wins_over_the_in_stack_model(self) -> None:
        """종전에는 하드코딩이라 in-stack llama 가 `.env` 를 **무조건** 이겼다."""

        gateway = self.by_service.get("gateway", {})
        self.assertEqual(
            gateway.get("LLAMA_BASE_URL"),
            _dash_form("LLAMA_BASE_URL", "http://llama:9080"),
            "이 override 를 쓰는 순간 in-stack llama 가 무조건 이긴다 — "
            "오너 규칙 '모델이 있어도 API 가 있다면 API 로' 의 반대다",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
