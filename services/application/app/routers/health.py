"""Health probe (``GET /health``).

``main.py`` 의 ``create_app()`` 에서 옮겨온 register 함수(R1). handler 본문은
byte-동일이다.

**협력자가 없는 유일한 route** 이며, 그래서 **인증 tier 밖**이기도 하다 —
`dependencies=_REQUIRE_AUTH` 를 달지 않는 두 곳(다른 하나는 공개 `/auth`) 중
하나다. compose healthcheck 가 세션 없이 치는 자리라 그렇다. 여기에 인증을
붙이면 스택 전체가 unhealthy 로 떨어진다.
"""

from __future__ import annotations


def register_health(app) -> None:
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}
