"""D8-7 전수 가드: 데이터를 가진 저장소는 호스트의 loopback 밖으로 게시되지 않는다.

오너 결정 **G1=C**(`plans/auth-d8-7-infra-auth-decisions.md`) — 지금 실재하는 위험은
"LAN의 누구나 mongo·ES·chroma에 무인증으로 붙는다"이고, 그 위험을 자격증명(B)이 아니라
**노출면 축소(A)**로 없앤다. 자격증명은 원격 배포 시점의 사안이다.

시행 지점이 compose 한 곳뿐이라 회귀도 compose 파일을 읽는다. 잡으려는 것 두 가지:

- **under-strict**: 저장소의 `127.0.0.1:` 접두를 지우면(= 0.0.0.0 게시 복귀) 실패한다.
  종전 상태가 정확히 그것이었으므로 이 방향이 원래 결함의 재현이다.
- **over-strict**: 반대 방향의 과잉 교정도 실패한다. `application`·`frontend`는 **일부러**
  전 인터페이스에 게시한다 — 제품 표면이고 세션 뒤에 있다(v1.7.52/53/55). 그 둘을 loopback으로
  묶는 것은 "다른 기기에서 제품을 못 쓴다"는 별개 결정이므로 아래 리터럴을 함께 고쳐야 한다.
  `llama`도 같은 이유로 예외다 — GPU를 가진 머신이 LAN의 다른 머신에 모델을 준다.

그리고 목록을 믿지 않는다: **게시하는 서비스 집합 자체를 파일에서 읽어** 아래 두 리터럴의 합집합과
대조한다(2026-08-01 스크립트 로그인 슬라이스 교훈 — 리터럴만 보는 스윕은 목록 밖 항목을 못 본다).
새 서비스가 포트를 게시하면 어느 쪽인지 분류해야 하고, 분류하지 않으면 실패한다.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# compose 파일의 서비스 키(2칸 들여쓰기)와 ports 항목만 읽는다.
#
# ★ YAML 표기 전부를 받아야 한다(2026-08-02 독립 검증이 실증한 blind spot). 첫 판은
# `^    ports:\s*$`라 **한 줄 표기**(`ports: ["8599:8000"]`)를 아예 못 읽었고, 그러면 그
# 서비스가 게시 집합에서 조용히 빠져 아래 분류 강제를 우회할 수 있었다. 항목 따옴표도
# 마찬가지다 — compose는 큰따옴표·작은따옴표·무따옴표를 다 받는다. **파서가 못 읽는 표기가
# 곧 가드의 구멍**이므로 여기서 넓히는 것은 편의가 아니라 가드의 일부다.
_SERVICE_RE = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*$")
_PORTS_RE = re.compile(r"^    ports:(?P<inline>.*)$")
_PORT_ITEM_RE = re.compile(r"""^      - ['"]?([^'"\s]+)['"]?\s*$""")
_INLINE_ITEM_RE = re.compile(r"""[^\s,\[\]'"]+""")

# 데이터를 가졌거나(mongo·chroma·elasticsearch) 내부 경계일 뿐인(gateway·embedding)
# 서비스 — 컨테이너끼리는 compose 네트워크 이름으로 붙으므로 호스트 게시는 사람용이다.
_LOOPBACK_ONLY = frozenset(
    {"mongo", "gateway", "embedding", "chroma", "elasticsearch"}
)

# 일부러 전 인터페이스에 게시하는 것 — 제품 표면이고 인증이 서 있다.
_PUBLIC_ON_PURPOSE = frozenset({"application", "frontend"})

_LOOPBACK_PREFIX = "127.0.0.1:"


def _published_ports_in(text: str) -> dict[str, list[str]]:
    """compose 본문에서 **포트를 게시하는 서비스**만 뽑는다 (서비스명 → 매핑 문자열)."""

    service: str | None = None
    in_ports = False
    published: dict[str, list[str]] = {}

    for line in text.splitlines():
        matched_service = _SERVICE_RE.match(line)
        if matched_service:
            service = matched_service.group(1)
            in_ports = False
            continue
        if service is None:
            continue
        matched_ports = _PORTS_RE.match(line)
        if matched_ports:
            # ports 섹션이 있다는 것만으로 서비스를 집합에 넣는다 — 항목을 하나도
            # 못 읽어도 분류는 강제된다.
            published.setdefault(service, [])
            inline = matched_ports.group("inline").strip()
            if inline:
                published[service].extend(_INLINE_ITEM_RE.findall(inline))
            else:
                in_ports = True
            continue
        if not in_ports:
            continue
        matched_item = _PORT_ITEM_RE.match(line)
        if matched_item:
            published[service].append(matched_item.group(1))
        elif line.strip() and not line.strip().startswith("#"):
            in_ports = False

    return published


def _published_ports(relative_path: str) -> dict[str, list[str]]:
    return _published_ports_in((_REPO_ROOT / relative_path).read_text(encoding="utf-8"))


class ComposeParserTest(unittest.TestCase):
    """파서가 못 읽는 표기는 곧 가드의 구멍이다 (2026-08-02 독립 검증 hardening #1).

    검증자가 `ports: ["8599:8000"]` **한 줄 표기**로 분류 강제를 실제로 우회했다 — docker는
    받아들이는데 파서는 그 서비스를 아예 못 봐서 조용히 통과했다. compose 3파일이 지금 전부
    멀티라인이라 결함은 아니었지만, "분류가 규칙이 아니라 강제"라는 성질이 **표기 하나에만**
    성립하고 있었다. 아래는 docker가 받는 표기 전부를 파서도 받는다는 것을 잠근다.

    - under-strict: 어느 표기든 못 읽게 되면 그 서비스가 집합에서 빠져 이 셀이 실패한다.
    - over-strict: `ports`가 **없는** 서비스는 집합에 들어오면 안 된다(넓히다가 아무 리스트나
      삼키면 분류 리터럴이 무의미해진다). 마지막 단정이 그 방향이다.
    """

    _FIXTURE = """services:
  multiline_double:
    ports:
      - "127.0.0.1:1111:1111"
  multiline_single:
    ports:
      - '2222:2222'
  multiline_bare:
    ports:
      - 3333:3333
  inline_list:
    ports: ["127.0.0.1:4444:4444", '5555:5555']
  no_ports:
    image: busybox
"""

    def test_every_yaml_style_of_publishing_is_seen(self) -> None:
        published = _published_ports_in(self._FIXTURE)

        self.assertEqual(
            published,
            {
                "multiline_double": ["127.0.0.1:1111:1111"],
                "multiline_single": ["2222:2222"],
                "multiline_bare": ["3333:3333"],
                "inline_list": ["127.0.0.1:4444:4444", "5555:5555"],
            },
            "docker가 받는 게시 표기를 파서도 전부 봐야 한다 — 못 보는 표기가 "
            "분류 강제의 우회로가 된다. `no_ports`는 들어오면 안 된다",
        )


class ComposeExposureTest(unittest.TestCase):
    """배포 compose(`docker-compose.yml`)의 노출면."""

    def setUp(self) -> None:
        self.published = _published_ports("docker-compose.yml")

    def test_every_publishing_service_is_classified(self) -> None:
        """게시 서비스 집합 = 두 리터럴의 합집합. 새 서비스는 분류를 강제한다."""

        self.assertEqual(
            set(self.published),
            set(_LOOPBACK_ONLY | _PUBLIC_ON_PURPOSE),
            "포트를 게시하는 서비스가 분류 리터럴과 어긋난다 — 새 서비스라면 "
            "_LOOPBACK_ONLY / _PUBLIC_ON_PURPOSE 중 하나로 분류해야 한다",
        )

    def test_data_stores_are_published_to_loopback_only(self) -> None:
        """저장소·내부 서비스는 `127.0.0.1:` 접두를 가진다 (G1=C의 시행 자체)."""

        for service in sorted(_LOOPBACK_ONLY):
            with self.subTest(service=service):
                mappings = self.published[service]
                self.assertTrue(mappings, f"{service}가 아무 포트도 게시하지 않는다")
                for mapping in mappings:
                    self.assertTrue(
                        mapping.startswith(_LOOPBACK_PREFIX),
                        f"{service}의 {mapping!r}이 LAN에 열려 있다 — "
                        "127.0.0.1 바인드가 D8-7 G1=C의 시행 지점이다",
                    )

    def test_the_product_surface_stays_published_to_every_interface(self) -> None:
        """과잉 교정 방향: 제품 표면까지 loopback으로 묶으면 실패한다."""

        for service in sorted(_PUBLIC_ON_PURPOSE):
            with self.subTest(service=service):
                mappings = self.published[service]
                self.assertTrue(mappings, f"{service}가 아무 포트도 게시하지 않는다")
                for mapping in mappings:
                    self.assertFalse(
                        mapping.startswith(_LOOPBACK_PREFIX),
                        f"{service}는 다른 기기에서 쓰는 제품 표면이고 세션 뒤에 있다 — "
                        "loopback으로 묶는 것은 별개 결정이다",
                    )


class TestComposeExposureTest(unittest.TestCase):
    """테스트 compose(`docker-compose.test.yml`)의 노출면."""

    def test_test_mongo_is_published_to_loopback_only(self) -> None:
        """pytest가 호스트에서 도므로 게시는 필요하지만 호스트만 필요하다."""

        published = _published_ports("docker-compose.test.yml")
        self.assertEqual(set(published), {"test-mongo"})
        for mapping in published["test-mongo"]:
            self.assertTrue(mapping.startswith(_LOOPBACK_PREFIX), mapping)


class LlamaComposeExposureTest(unittest.TestCase):
    """in-stack llama override(`docker-compose.llama.yml`)의 노출면."""

    def test_llama_stays_reachable_from_the_lan(self) -> None:
        """유일한 크로스머신 의존 — GPU 머신이 다른 머신에 모델을 준다.

        데이터가 아니라 연산을 노출하는 것이라 G1=C의 축소 대상이 아니다. 여기를
        loopback으로 묶으면 12B를 못 올리는 머신이 스택을 못 돌린다.
        """

        published = _published_ports("docker-compose.llama.yml")
        self.assertEqual(set(published), {"llama"})
        for mapping in published["llama"]:
            self.assertFalse(mapping.startswith(_LOOPBACK_PREFIX), mapping)


class ExternalComposeExposureTest(unittest.TestCase):
    """외부 API override(`docker-compose.external.yml`)의 노출면.

    이 파일은 **포트를 하나도 게시하지 않는다** — 주소를 밖으로 돌리고 로컬 백엔드를
    profile 뒤로 넣을 뿐이라 새 노출면이 없다. 그 성질을 잠그는 이유는, 이 가드가
    **파일을 이름으로 하나씩** 읽기 때문이다: 목록에 없는 compose 파일은 아무리
    포트를 열어도 위 분류 강제(`_LOOPBACK_ONLY` / `_PUBLIC_ON_PURPOSE`)를 **통째로
    우회한다**. 배포 서버가 쓰는 파일이 바로 그 사각지대에 있으면 안 된다.
    """

    def test_the_external_override_publishes_no_new_ports(self) -> None:
        self.assertEqual(
            _published_ports("docker-compose.external.yml"),
            {},
            "외부 override 가 포트를 게시하기 시작했다면 그것은 새 노출면이다 — "
            "위 두 리터럴 중 어디에 속하는지 분류하고 이 셀을 그에 맞게 고친다",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
