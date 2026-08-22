"""Slice 2 (A1=ⓑ): 관리자 표면은 **다른 주소**에 있다.

오너 결정(2026-08-05, `plans/router-split-and-admin-separation-decisions.md`)은
`/admin` 11 operation 을 제품 앱에서 들어내 **같은 이미지·다른 command 의 네 번째
compose 서비스**로 옮기는 것이다. 제품 포트는 D8-7 G1=C 에 의해 **일부러 LAN 에
게시**돼 있고 그 근거가 "세션 뒤에 있다" 이므로, 관리자 표면이 그 포트에 남아 있는 한
방어는 `require_admin_user` 한 겹뿐이다. 분리하면 LAN 에서 그 경로는 **가드가 아니라
라우터가 404** 로 답한다.

이 파일이 잠그는 것은 셋이다.

1. **표면 소속** — 제품 앱에 `/admin` 0건, 관리자 앱에 정확히 admin tier + `/health`.
2. **★ H-2(shim drift)** — 2026-08-05 독립 검증이 Slice 2 의 선행 조건으로 올린 항목.
   테스트·`scripts/dump_openapi.py`(= 프론트 TS 계약)·경계 행렬 가드는 여전히 **합집합
   앱**(`create_app()`)을 쓰는데, 배포되는 것은 둘로 쪼갠 앱이다. 그 둘이 갈라지면
   **회귀는 전부 green 인데 배포에서만 틀린다** — 이 저장소가 `ObservedProvider` 계측
   누락으로 이미 데인 그 형태다. 그래서 세 factory 를 **한 함수 본문**으로 두어 구조적
   으로 못 갈라지게 하고, 그 성질(합집합 = 제품 ∪ 관리자, 교집합 = `/health`,
   operation 별 가드·계약 동일)을 여기서 단정한다.
3. **토폴로지** — compose 서비스가 **포트를 게시하지 않는가**, command 가 관리자
   진입점을 가리키는가, nginx `/api/admin/` 이 그 서비스로 가는가. 코드가 아니라 배선이
   목적인 슬라이스라 배선 파일을 읽는 것이 맞는 자리다.

**over-strict 방향**: 관리자 앱에서 `/health` 를 빼면(=" 관리자 앱은 admin 만") compose
healthcheck 가 죽는데 회귀는 조용하다 — 그래서 교집합을 `set()` 이 아니라 정확히
`{("/health", "get")}` 로 못박는다. 제품 앱에서 `/auth` 를 빼는 과잉 분리도 1번이 문다.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from fastapi.routing import APIRoute

from services.application.app import admin_asgi
from services.application.app.main import (
    app as image_default_app,
    create_admin_app,
    create_app,
    create_product_app,
)

# 두 목록이 결국 갈라지므로 admin tier 리터럴은 다시 적지 않고 정본을 가져온다
# (`CombinedBoundaryMatrixTest` 가 `AuthenticationBoundaryTest.PUBLIC` 을 재사용하는
# 것과 같은 이유). 그쪽이 tier 를 **dependency 로부터** 유도해 잠그고, 여기는 그 집합이
# **어느 앱에 실리는가**를 잠근다 — 두 축이 다르다.
#
# ★ 클래스를 이 모듈 이름공간으로 끌어오면 **pytest 가 그 클래스를 여기서 한 번 더
# 수집해 실행한다**(실측: 이 파일이 10 cells 인데 22 로 세어졌다). 모듈만 import 하고
# 속성으로 읽는다.
from tests import test_auth_api
from tests.test_compose_exposure import _published_ports

_REPO_ROOT = Path(__file__).resolve().parents[1]

_HEALTH = ("/health", "get")
_ADMIN_OPERATIONS = frozenset(test_auth_api.CombinedBoundaryMatrixTest.ADMIN)


def _operations(app) -> set[tuple[str, str]]:
    return {
        (route.path, method.lower())
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


def _dependency_names(dependant, out: list[str]) -> list[str]:
    if dependant.call is not None:
        out.append(getattr(dependant.call, "__qualname__", repr(dependant.call)))
    for sub in dependant.dependencies:
        _dependency_names(sub, out)
    return out


def _contract(app) -> dict[tuple[str, str], tuple]:
    """operation → (가드 트리, 상태코드, 선언된 에러 코드, route 클래스).

    "같은 operation 인가" 가 아니라 **"같은 계약으로 실려 있는가"** 를 본다. 경로만
    비교하면 합집합 앱에만 인증 dependency 가 붙는 종류의 drift 를 놓친다.
    """

    contracts: dict[tuple[str, str], tuple] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        guards = tuple(sorted(_dependency_names(route.dependant, [])))
        declared = tuple(sorted(str(code) for code in (route.responses or {})))
        for method in route.methods:
            contracts[(route.path, method.lower())] = (
                guards, route.status_code, declared, type(route).__name__,
            )
    return contracts


class SurfaceMembershipTest(unittest.TestCase):
    """어느 operation 이 어느 앱에 실리는가."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.union = create_app()
        cls.product = create_product_app()
        cls.admin = create_admin_app()

    def test_the_product_surface_serves_no_admin_operation(self) -> None:
        """분리의 목표 그 자체 — LAN 에 게시되는 앱에 `/admin` 이 없다."""

        leaked = sorted(
            operation for operation in _operations(self.product)
            if operation[0].startswith("/admin")
        )
        self.assertEqual(
            leaked, [],
            "제품 앱에 관리자 route 가 남아 있다 — 이 포트는 LAN 에 게시되므로 "
            "(D8-7 G1=C) 분리의 목적이 사라진다",
        )
        # 과잉 분리 방향: 제품 앱이 잃으면 안 되는 것들.
        product = _operations(self.product)
        self.assertIn(("/auth/login", "post"), product)
        self.assertIn(("/projects", "get"), product)
        self.assertIn(_HEALTH, product)

    def test_the_admin_surface_serves_exactly_the_admin_tier_and_health(self) -> None:
        """관리자 앱 = admin tier 11 + `/health`. 그 이상도 이하도 아니다."""

        self.assertEqual(
            _operations(self.admin), set(_ADMIN_OPERATIONS) | {_HEALTH},
            "관리자 앱의 표면이 admin tier + health 와 다르다 — 제품 route 가 따라왔거나"
            "(노출면 확대) 관리자 route 가 빠졌다",
        )

    def test_the_two_surfaces_partition_the_union_app(self) -> None:
        """★ H-2 — 배포되는 두 앱의 합이 곧 테스트·프론트 계약이 보는 앱이다.

        under-strict: 한쪽 surface 에만 register 를 더하면(= 합집합 앱이 모르는
        operation 이 배포에 생기면) 첫 단정이 실패한다.
        over-strict: `/health` 를 한쪽에서 빼면 교집합 단정이 실패한다 — 그것은
        관리자 컨테이너의 healthcheck 를 조용히 죽이는 변경이다.
        """

        product = _operations(self.product)
        admin = _operations(self.admin)

        self.assertEqual(
            _operations(self.union), product | admin,
            "합집합 앱 ≠ 배포 두 앱의 합 — 테스트가 보는 표면과 배포되는 표면이 "
            "갈라졌다(H-2 shim drift). `create_app` 의 include_* 분기를 본다",
        )
        self.assertEqual(
            product & admin, {_HEALTH},
            "두 표면이 공유하는 것은 health probe 하나여야 한다",
        )

    def test_every_operation_keeps_its_guards_on_the_split_apps(self) -> None:
        """같은 operation 은 어느 앱에 실리든 **같은 계약**이다.

        경로 집합만 맞고 가드가 다르면 그것이 정확히 H-2 가 경고한 사태다 —
        경계 행렬은 합집합 앱에서 tier 를 재는데, 배포 앱의 route 에 그 dependency 가
        없으면 아무 테스트도 실패하지 않는다.
        """

        union = _contract(self.union)
        deployed = {**_contract(self.product), **_contract(self.admin)}

        self.assertEqual(set(union), set(deployed))
        for operation, contract in sorted(union.items()):
            with self.subTest(operation=operation):
                self.assertEqual(
                    deployed[operation], contract,
                    f"{operation} 의 가드·상태코드·에러 선언·route 클래스가 배포 앱에서 "
                    "다르다",
                )

    def test_both_surfaces_carry_the_same_wiring_around_the_routes(self) -> None:
        """route 밖의 배선 — `app.state` 와 저장소 예외 handler.

        관리자 앱에 `app.state.sessions` 가 없으면 세션 해석이 죽고,
        `_STORAGE_ERRORS` handler 가 없으면 저장소 장애가 503 이 아니라 500 으로
        샌다(H3). 둘 다 route 를 세는 가드로는 안 보인다.
        """

        for app in (self.product, self.admin):
            with self.subTest(app=app.title):
                self.assertEqual(
                    sorted(vars(app.state).get("_state", {})),
                    sorted(vars(self.union.state).get("_state", {})),
                )
                self.assertEqual(
                    sorted(
                        exc.__name__ for exc in app.exception_handlers
                        if isinstance(exc, type)
                    ),
                    sorted(
                        exc.__name__ for exc in self.union.exception_handlers
                        if isinstance(exc, type)
                    ),
                )

    def test_the_interactive_docs_are_not_served_on_any_surface(self) -> None:
        """오너 2026-08-23(보안 점검 발견 ③·검증 H-3): docs 는 공개 표면이 아니다.

        FastAPI 기본값으로 두면 `/docs`·`/redoc`·`/openapi.json` 이 8520 직접은
        물론 nginx 경유(`/api/docs`·…)로도 **무인증 200** — 모든 route·가드·에러
        형태를 네트워크의 누구에게나 광고한다. 스키마의 정당한 소비자는 전부
        import 방식이다(`scripts/dump_openapi.py`·테스트의 `.openapi()`).

        docs 라우트는 `APIRoute` 가 아니라 일반 `Route` 라 `_operations()` 에 안
        잡히므로 경로 집합으로 직접 잰다. **under-strict**: 기본값을 되돌리면
        네 경로가 다시 살아 이 셀이 문다. **over-strict**: 문을 닫는다고 공개
        라우트(`/health`·제품의 `/auth/login`)까지 지워지면 안 된다.
        """
        docs_paths = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
        for app in (self.union, self.product, self.admin):
            served = {getattr(route, "path", None) for route in app.routes}
            self.assertEqual(
                served & docs_paths, set(),
                f"{app.title} must not serve the interactive docs",
            )
            self.assertIn(("/health", "get"), _operations(app))
        self.assertIn(("/auth/login", "post"), _operations(self.product))


class EntryPointTest(unittest.TestCase):
    """컨테이너가 실제로 부르는 이름이 맞는 앱을 준다."""

    def test_the_image_default_command_serves_the_product_app(self) -> None:
        """`Dockerfile` CMD = `...main:app`. 기본값이 안전한 표면이어야 한다.

        command 를 override 하지 않고 이미지를 띄우는 사람(= `application`
        서비스)이 관리자 표면을 LAN 포트에 얹으면 안 된다.
        """

        leaked = sorted(
            operation for operation in _operations(image_default_app)
            if operation[0].startswith("/admin")
        )
        self.assertEqual(leaked, [], "`main:app` 이 관리자 route 를 들고 있다")

    def test_the_admin_container_entrypoint_serves_the_admin_app(self) -> None:
        """`admin_asgi:app` = compose `admin` 서비스가 띄우는 그 객체."""

        self.assertEqual(
            _operations(admin_asgi.app), set(_ADMIN_OPERATIONS) | {_HEALTH},
        )


class ComposeAndProxyTopologyTest(unittest.TestCase):
    """배선 파일 — 이 슬라이스의 산출물 절반은 코드가 아니라 여기 있다."""

    def setUp(self) -> None:
        self.compose = (_REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.nginx = (
            _REPO_ROOT / "frontend" / "nginx.conf"
        ).read_text(encoding="utf-8")

    def _admin_service_block(self) -> str:
        match = re.search(
            r"^  admin:\n(?P<body>(?:    .*\n|\n)+)", self.compose, re.MULTILINE
        )
        self.assertIsNotNone(match, "compose 에 `admin` 서비스가 없다")
        return match.group("body")

    def test_the_admin_service_publishes_no_host_port(self) -> None:
        """ⓑ 의 핵심 — 도달 경로는 nginx 하나뿐이다.

        게시하면 `test_compose_exposure` 의 분류 강제가 먼저 실패하지만, 그 실패는
        "분류해라" 이지 "게시하면 안 된다" 가 아니다. 결정을 여기서 이름으로 적는다.
        """

        self.assertNotIn(
            "admin", _published_ports("docker-compose.yml"),
            "`admin` 서비스가 호스트 포트를 게시한다 — A1=ⓑ 는 nginx 경유 전용이다"
            "(디버그용 게시가 필요하면 127.0.0.1 바인드로 하고 이 결정을 함께 고친다)",
        )

    def test_the_admin_service_runs_the_admin_entrypoint(self) -> None:
        """이미지 재사용 + command 만 다름 = worker·generation_worker 와 같은 패턴."""

        body = self._admin_service_block()
        self.assertIn("services/application/Dockerfile", body)
        self.assertIn("services.application.app.admin_asgi:app", body)

    def test_nginx_sends_the_admin_prefix_to_the_admin_service(self) -> None:
        """`/api/admin/` → admin 컨테이너. 나머지 `/api/` 는 제품 앱 그대로."""

        match = re.search(
            r"location /api/admin/ \{(?P<body>.*?)\n    \}", self.nginx, re.DOTALL
        )
        self.assertIsNotNone(match, "nginx 에 `/api/admin/` location 이 없다")
        body = match.group("body")
        self.assertIn("set $admin_upstream admin;", body)
        self.assertIn("proxy_pass http://$admin_upstream:8000;", body)
        # `/admin` 세그먼트가 rewrite 에서 살아남아야 한다 — `^/api/admin/(.*)$` 로
        # 적으면 업스트림이 `/users` 를 받아 404 가 된다(제품 location 과 같은 형태로
        # `/api` 만 벗긴다).
        self.assertIn("rewrite ^/api/(.*)$ /$1 break;", body)
        # 제품 경로가 관리자 업스트림으로 새지 않는다(과잉 교정 방향).
        self.assertIn("set $application_upstream application;", self.nginx)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
