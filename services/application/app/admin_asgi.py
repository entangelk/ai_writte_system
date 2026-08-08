"""관리자 표면 ASGI 진입점 (Slice 2, A1=ⓑ).

``docker-compose.yml`` 의 ``admin`` 서비스가 이것을 띄운다::

    uvicorn services.application.app.admin_asgi:app --host 0.0.0.0 --port 8000

**왜 별도 모듈인가.** ``main:app`` 은 제품 앱이어야 한다(이미지 기본 CMD 이고 그
포트가 LAN 에 게시된다). 관리자 앱을 같은 모듈의 두 번째 속성으로 두면 *제품*
컨테이너까지 두 앱을 조립하게 되므로, 관리자 컨테이너만 무는 진입점을 따로 둔다.

**알려진 비용**: 이 모듈을 import 하면 ``main`` 의 모듈 수준 ``app =
create_product_app()`` 도 함께 실행돼, 관리자 컨테이너는 **쓰지 않는 제품 앱 하나를
메모리에 더 든다**(Mongo 클라이언트 한 벌 추가). 서빙되는 것은 아래 ``app`` 뿐이다.
없애려면 ``main`` 에서 모듈 수준 앱을 걷어내고 제품 쪽도 진입점 모듈로 옮겨야
하는데(= ``Dockerfile`` CMD 변경), 이 슬라이스의 범위가 아니다.
"""

from __future__ import annotations

from .main import create_admin_app

app = create_admin_app()
