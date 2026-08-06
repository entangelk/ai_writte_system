"""라우터 분해 패키지 (R1 = register 함수, 2026-08-05).

``main.py`` 의 ``create_app()`` 안에 몰려 있던 ``@app.X`` route 를 도메인별
``register_xxx(app, *, <서비스 협력자>)`` 함수로 옮겨 담는다. handler 본문은
byte-동일로 이동하고 ``@app.X`` 데코레이터를 그대로 둔다(R1).

- **서비스 협력자**(``core_sot``·``writing``·…)는 ``create_app`` 이 만든 객체를
  **명시 인자**로 받는다 — 클로저를 흉내 내지 않고 DI 컨테이너도 들이지 않는다.
- **공유 심볼**(Pydantic 모델·에러 선언·``_REQUIRE_*``·인가 dep)은 ``main`` 이 아니라
  **``..api``**(``models``·``errors``·``dependencies``)와 ``..env`` 에서 가져온다
  (2026-08-06 공유 prelude 추출). **``from ..main import`` 를 되살리면 안 된다** —
  그것이 ``main ↔ routers`` 순환이었고, "필요한 심볼이 그 앞에 정의돼 있다"는 순서에만
  기대어 풀렸다. 그래서 이 패키지를 먼저 import 하는 모든 경로가 죽어 있었다(H-3-A).
- **인가 dep**(``require_authenticated_user``·``require_admin_user`` …)는
  ``app.state`` 를 읽는 모듈 수준 함수라 파일이 쪼개져도 그대로 동작한다.

분류 전수 가드(``tests/test_billable_actions.py``)는 route-driven 으로 전환돼
route 가 어느 파일에 있든 ``app.routes`` 만 본다.
"""
