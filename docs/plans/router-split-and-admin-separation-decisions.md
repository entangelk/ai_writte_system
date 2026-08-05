# 라우터 분해 + 관리자 주소 분리 — 착수 결정 브리프

상태: `Resolved (2026-08-05) — R1·A1 확정, 구현 대기`

> **오너 결정 (2026-08-05)**
>
> - **R1 = "register 함수" 패턴.** 라우터 모듈마다 `def register_xxx(app, *, core_sot, writing, …)` 형태로
>   협력자를 **명시 인자**로 받고, 안에서 `@app.X(...)` 데코레이터를 그대로 둔다. handler 본문은 byte-동일로
>   옮긴다(최소 diff·최소 위험). HANDOFF가 명시한 방향이다.
> - **A1 = ⓑ 별도 compose 서비스.** `application` 이미지를 재사용해 `command:`만 바꾼 네 번째 서비스로
>   관리자 표면을 담고, **호스트 포트는 게시하지 않는다**(nginx `/api/admin/` 경유로만 도달).
>   product 앱에는 `/admin` 라우트가 남지 않아 LAN에서 `application:8520`을 직접 hit 해도 404다.
>
> 두 추천안을 그대로 채택했다.

계기: HANDOFF "★ 다음 작업 = `main.py` 라우터 정리 + 관리자 표면 주소 분리"(오너 2026-08-04,
*"이건 기본이잖아"*). 8.3·8.4·8.2c가 닫혔으므로 **지금이 옮기기 가장 안전한 시점**이다 — 경계는 파일 배치가
아니라 **dependency tier + 전수 가드**로 서 있고, 그 가드가 선 채로 파일을 쪼갠다. Phase 9(활동 로그)의
A7 가드도 `main.py`를 파일로 읽을 가능성이 커서, 라우터 정리를 먼저 하면 같은 부채를 세 번째로 만들지
않는다.

---

## 0. 이 브리프가 정하지 않는 것 (이미 결정됨)

- **HTTP 인증·인가·관리자 경계는 끝났다**(D8-1~6). 세션·소유권·`require_admin_user`는 서 있고 여기서
  다시 열지 않는다. 이 작업은 **인증이 아니라 파일 구조 + 네트워크 토폴로지**다.
- **DI 컨테이너를 도입하지 않는다** — 이 저장소가 피해 온 것이다. R1의 "명시 인자 등록 함수"는 그
  원칙을 그대로 지킨다(`APIRouter` 자체가 DI 컨테이너는 아니지만, handler 본문을 안 건드린다는 점에서
  register 함수가 더 안전하다).
- **Phase 9 서비스 활동 로그는 별도 페이즈다.** 이 작업과 직교하며, 라우터 정리 **뒤**에 착수한다.
- **1 project 1 owner(D3=A)**·**삭제 계약(D8-6)** 등 도메인 결정은 건드리지 않는다.

---

## 1. 착수 전 실측 (추정 아님 — 2026-08-05, HEAD `98e3e93`에서 직접 잰 값)

| 표면 | 실측 | 분리 시 생기는 일 |
|---|---|---|
| **main.py 규모** | **6,183줄**. route decorator `@app.(get\|post\|put\|patch\delete)` **= 76개**(전체 `@app.` 78 = 76 route + 2 exception_handler). **APIRouter·include_router 0회** | 76 operation이 한 파일 `create_app()` 안에 있다. (HANDOFF·8.2c 작업로그의 "데코레이터 77"은 1개 차이 — 정확값은 76이며 가드 `len(tiers)==76`이 못박은 값이다.) |
| **operation 76 / project tier 61** | `tests/test_auth_api.py::CombinedBoundaryMatrixTest`가 `len(tiers)==76`·`len(by_tier["project"])==61`을 하드코딩 | 라우트 이동 중 경로·메서드가 바뀌면 즉시 적발. **논리 무변이라 이 숫자들은 그대로여야 한다.** |
| **create_app 시그니처** | 서비스 인자 **26개**(전부 `Optional`, env 기본값). handler 본문은 내부 협력자(≈33)를 **클로저**로 끌어쓴다 | register 함수는 그 클로저를 **명시 인자**로 받는다. handler 본문은 한 글자 안 고친다 |
| **인가 가드의 실제 모양** | `require_authenticated_user`·`require_project_owner`·`require_admin_user`·`enforce_quota`는 **모듈 수준 함수**로 `request.app.state.*`에서 읽는다(`app.state`는 `main.py:2953-2964`에서 채워진다). **클로저가 아니다** | 파일이 쪼개져도 app.state만 채워지면 그대로 동작한다. R1이 안전한 근거 |
| **`QuotaSettledRoute`** | `app.router.route_class = QuotaSettledRoute`(`main.py:2732`) — **모든 route**가 이 클래스를 쓴다. settle은 `request.app.state.quota`(`1832`) | admin 전용 앱에도 같은 route_class를 줄지(일관) 안 줄지(admin은 billable 아니라 settle no-op)는 구현 중 결정 |
| **★ D8-7 G1=C 정정** | **2차 ASGI 앱이 아니다.** compose `127.0.0.1:` 호스트 포트 바인딩 접두어(코드 **0줄**, compose 3파일). 저장소 5종 + test-mongo가 이 접두어로 게시된다 | HANDOFF가 ⓐ를 "재료 그대로·코드 변경 최소"라고 한 건 **루프백 바인딩 트릭만 공짜**라는 뜻이다. 2차 앱·2차 uvicorn 기동·프론트 재라우팅은 전부 **신규**다. 이 정정이 A1의 비용 평가를 뒤집는다 |
| **세션 저장소** | **Mongo**(`MongoSessionRepository`, `CORE_SOT_MONGO_URI`). 토큰은 256-bit CSPRNG, sha256 저장. **프로세스 시크릿/JWT 아님**. 쿠키 `session`, `Secure`(기본 true)·`HttpOnly`·`SameSite=Lax`·`Path=/` | 주소(포트·서비스)가 달라도 **세션 공유가 공짜** — 시크릿을 env로 나를 필요 없다. `Secure` 때문에 `http://127.0.0.1:NNNN` 직접 접속엔 브라우저가 쿠키를 안 실을 수 있음(`localhost`는 예외) |
| **이미지 공유 선례** | `application` 이미지를 `worker`·`generation_worker`가 `command:`만 바꿔 공유. 둘 다 **호스트 포트 미게시** | ⓑ(네 번째 서비스)는 **이 패턴 그대로**. 새로운 운영 형태가 아니다 |
| **프론트 단일 origin** | `API_BASE="/api"`(`frontend/src/api/client.ts:5`). nginx가 `/api/` → `application:8000` 프록시. `/admin` 호출도 `/api/admin/...`로 같은 origin·같은 쿠키 | admin을 nginx `/api/admin/` → admin 서비스로 돌리면 **브라우저 origin이 안 바뀌어** 쿠키가 자연스럽게 흐른다 |
| **깨지는 가드** | `tests/test_billable_actions.py`가 `main.py`를 **정규식**으로 파싱(`_ROUTE`, route 본문에서 `llm_call_scope(` 분류) → `app.routes`와 대조. `tests/test_auth_api.py`는 **런타임** `app.routes`·`route.dependencies` 조회(안전), 깨지는 건 `ForcedPasswordChangeTest` 1행(AST로 `create_user` 찾는 경로)뿐 | billable 가드는 정규식 → **route-driven**(`app.routes` 순회하며 `route.endpoint` 소스 읽기)으로 전환. 이쪽이 **현행보다 단단**하다(파일 배치·prefix 무관). auth 가드는 경로 1행 갱신 |
| **관리자 op = 8** | `CombinedBoundaryMatrixTest.ADMIN`(8쌍)와 일치: `/admin/users`(get,post)·`deactivate`·`observability/kpi`·`audit-events`·`/admin/projects`·`access-grants`·`purge`. purge handler가 **14개 서비스**를 쓰는 가장 무거운 handler | admin 앱 factory에 주입할 협력자가 많다 — register_admin 인자가 가장 길다 |

**규모 감각**: 라우터 분해는 기계적이다(논리 변경 0). **실제 작업량의 대부분은 가드 2종 갱신**이다.
관리자 분리(ⓑ)는 코드 양은 작지만(admin app factory + compose 서비스 + nginx location 1개 + product 앱
`/admin` 제거) 네트워크 토폴로지를 바꾼다.

---

## R1 — 라우터 분해 패턴

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. register 함수** | 모듈마다 `def register_xxx(app, *, core_sot, writing, …):` 안에 `@app.X(...)`를 그대로 둔다. `create_app`이 협력자를 넘겨 호출 | **handler 본문 byte-동일 이동** → diff·위험 최소. `@app.X` 유지라 정규식 가드가 마이그레이션 중에도 부분 동작. HANDOFF가 명시한 방향. admin 분리 = `register_admin()` 호출 분기 한 줄 | "전달받은 app을 N개 모듈에서 가감"이 FastAPI 관용(APIRouter)은 아니라 약간 생소 |
| **B. APIRouter + include_router** | `def build_xxx_router(*, deps) -> APIRouter` 반환, `app.include_router(...)`. `@router.X` | FastAPI 관용. 모듈 경계가 깔끔. admin 라우터가 자연스러운 분리 단위 | 데코레이터 76개 전부 `@app.X`→`@router.X` 수정. handler 본문도 클로저→인자로 손댈 여지. **repo APIRouter 0건에서의 도입**(문화 전환)이라 되돌리기 비쌈 |
| **C. 현행 유지** | 한 파일 `create_app()` | 비용 0 | 6,183줄 단일 파일. Phase 9·이후 작업이 계속 이 파일에 압력 |

> **구현자 추천: A(register 함수).** 세 가지 근거다. ① **위험**: handler 본문을 안 고치면 동작이 변할
> 수가 없다 — 이 저장소의 경계는 tier 가드가 잠그고 있고, 그 가드가 선 채로 본문을 옮기는 것이 가장
> 안전하다(8.2c가 "회귀가 통과한다"와 "회귀가 무언가를 잠근다"가 다르다는 것을 방금 보였다). ② **저장소
> 원칙**: DI 컨테이너를 피해왔고, register 함수는 협력자를 명시 인자로 받아 그 원칙을 지킨다. ③ **되돌림
> 비용**: B는 76개 데코레이터를 전부 고쳐야 해서 한 번 가면 되돌리기 비싸지만, A는 `create_app`에서
> register 호출을 없애고 본문을 돌려놓으면 끝이라 가역적이다.
> **A를 고르면 admin 분리(A1)도 자연스럽다** — `create_app(include_admin=False)`로 product 앱을,
> `create_admin_app()`으로 admin 앱을 만들고, 둘이 같은 서비스 생성 코드를 공유한다.

---

## A1 — 관리자 주소 분리 토폴로지

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **ⓐ 같은 컨테이너·2차 ASGI** | 한 컨테이너에 uvicorn 2개(product `:8000` + admin `:8001`). `create_admin_app()` 신규 | 컨테이너 수 무변 | **supervisord/래퍼로 2 프로세스 관리 = repo에 없는 다중프로세스 패턴** 신규 도입. 2차 앱·프론트 재라우팅도 전부 신규. HANDOFF가 "재료 그대로·최소 변경"이라 한 건 루프백 바인딩만 해당(§1 정정) |
| **ⓑ 별도 compose 서비스** | `application` 이미지 재사용, `command:`만 변경(= `worker`·`generation_worker`와 동일 패턴). **호스트 포트 미게시**, nginx `/api/admin/` 경유 전용 | 기존 3서비스-이미지공유 패턴에 **정확히 부합**. product 앱에 `/admin` 없어 LAN 직접 hit = 404(= 요구한 겹). 세션 Mongo 공유로 **공짜**. nginx 경유라 **브라우저 origin·쿠키 무변**. 프로세스 격리. 포트 미게시라 `test_compose_exposure` 영향 없음 | 컨테이너 하나 증가(이미 3개 공유 중이라 증분 작음) |
| **ⓒ nginx 레벨 only** | 앱 무변, nginx가 `/api/admin/`만 통제 | 앱 코드 0 | 현 토폴로지(`application:8520`이 LAN 공개)에서 **분리가 안 된다** — LAN에서 앱 포트 직접 hit 시 `/admin` 노출. 달성하려면 app 포트를 LAN에서 철수해야(= 직접접근 모델 폐기, 대공사) |
| **ⓓ 완전 별도 서비스 코드 분리** | admin을 독립 코드베이스로 | 최대 격리 | 세션·저장소 공유 재설계. **범위 밖** |

> **구현자 추천: ⓑ(별도 compose 서비스).** 다섯 가지 근거다. ① **패턴 부합**: 이미지를 `command:`만
> 바꿔 공유하는 것은 이 저장소의 확립된 패턴이고, `worker`·`generation_worker`가 포트 없이 돌아가는
> 것과 같은 모양이다. ② **목표 달성**: product 앱(8520, LAN 공개)에 `/admin` 라우트가 남지 않으므로
> LAN에서 직접 접근해도 404 — "관리자 표면은 애초에 다른 주소"라는 겹이 진짜로 선다. ③ **세션 공짜**:
> 세션이 Mongo에 있으므로 네 번째 서비스가 같은 `CORE_SOT_MONGO_URI`를 읽기만 하면 쿠키가 그대로
> 유효하다. 시크릿을 나를 필요가 없다. ④ **브라우저 무변**: nginx가 `/api/admin/`을 admin 서비스로
> 돌리면 브라우저는 여전히 frontend origin 하나만 보고, `Secure` 쿠키가 자연스럽게 흐른다(ⓐ의
> `http://127.0.0.1` 직접 접속 쿠키 함정 회피). ⑤ **ⓐ보다 단순**: 같은 격리를 다중프로세스
> 패턴(supervisord) 없이 달성한다.
> **ⓒ가 안 되는 이유**: `application` 포트가 D8-7 G1=C에 의해 **의도적으로 LAN 공개**되어 있고, 그
> 근거가 "세션 뒤에 있다"는 것이다. `/admin`을 그 포트에서 통째로 빼지 않으면 nginx 통제는 우회 가능한
> 반쪽짜리 방어다.

---

## 2. 구현 순서 (두 슬라이스로 분리 — 독립 검증 단위 작게)

이 작업은 **논리 변경이 없는 기계적 이동(Slice 1)**과 **토폴로지 변경(Slice 2)** 두 축이며, 각각
별도의 회귀·검증 단위로 둔다(이 저장소의 관례).

### Slice 1 — 라우터 분해 (기계적, 논리 무변)

1. **회귀 먼저**(기준선): backend 2191/1/1931 · 카운트 76/61 무변를 선언.
2. `app/routers/` 신규 패키지에 도메인별 register 모듈(`health`·`auth`·`admin`·`projects`·`drafts`·
   `analysis`·`memory`·`context_search`·`writing`·`observability`). handler 본문 byte-동일 이동.
3. `create_app`은 협력자를 만들고 `register_xxx(app, …)` 호출로 교체.
4. **가드 갱신**(작업량의 대부분):
   - `test_billable_actions.py`: `_route_bodies()`를 정규식 단일 파일 → **route-driven**(`app.routes`
     순회하며 `inspect.getsource(route.endpoint)`로 본문 읽기)로 전환. `llm_call_scope(` 분류 유지.
   - `test_auth_api.py`: `ForcedPasswordChangeTest`의 main.py 경로 1행 → admin 라우트가 옮겨간 모듈로.
5. 회귀 전수 + **뮤테이션**(route-driven 가드가 새 구조에서도 라우트 누락을 잡는지).

### Slice 2 — 관리자 주소 분리 (ⓑ)

1. `create_admin_app()`(또는 `create_app(include_admin=False)` + admin 전용 factory) — admin 라우트만.
2. `docker-compose.yml`에 `admin` 서비스 추가(이미지 재사용, `command`로 admin app 기동, **포트 미게시**).
3. `frontend/nginx.conf`에 `location /api/admin/` → admin 서비스 업스트림.
4. product `create_app()`에서 `/admin` 등록 제거(= product 앱에 admin 라우트 부재).
5. 노출 가드·회귀 갱신. **핵심 단정**: product 앱 `app.routes`에 `/admin/*` 0건, admin 앱엔 8건.

---

## 3. Follow-up considerations (열어 둘 문)

- **`QuotaSettledRoute`를 admin 앱에도 줄 것인가.** admin은 billable이 아니라 settle이 no-op지만, route
  클래스 일관성 vs 불필요한 의존. 구현 중 결정(기본: 준다 — quota 앱 상태 누락 시 실패하지 않게).
- **admin 서비스 직접 접근(디버그).** 포트 미게시가 기본이지만, 호스트 디버깅용으로 `127.0.0.1:${ADMIN_PORT:-8524}`
  바인드를 *선택적*으로 둘 수 있다(`.env.example`에 주석). 그 경우 `test_compose_exposure`가 분류를 요구.
- **`/tokenize` 등 worker·스크립트가 admin port를 안 쓰는지** 확인(이 슬라이스에서 admin은 HTTP 미게시).
- **Phase 9 A7 가드.** 라우터 정리 뒤면 A7 가드가 `main.py` 단일 파일이 아니라 `app.routes`를 읽게
  설계할 수 있다 — 이 브리프가 그 부채를 닫는다.

## 4. Deferred / out of scope

- 관리자 표면의 **완전 코드 분리(ⓓ)** — 세션·저장소 공유 재설계. 원격 다중 호스트 배포 시점.
- Phase 9 **서비스 활동 로그**(A1~A8 오너 결정 별도).
- nginx/TLS 종단 강화·WAF — 원격 배포 시점(D8-7 G2~G6과 같은 축).
- admin 서비스의 독자적 로깅·메트릭 — 운영 부담이 실제로 생기면.

## 5. 이 브리프가 막고 있던 것

- **라우터 정리**는 R1(A vs B vs C)이 갈라지는 동안 아무 코드도 쓸 수 없었다 — 패턴이 파일 수와
  diff 크기를 전부 결정하기 때문이다. **A 확정으로 Slice 1 착수 가능.**
- **관리자 주소 분리**는 ⓐ~ⓓ가 네 가지 전혀 다른 산출물(compose 줄 vs 다중프로세스 vs nginx vs 재설계)을
  낳는 진짜 fork였다. **ⓑ 확정으로 Slice 2 착수 가능.**
