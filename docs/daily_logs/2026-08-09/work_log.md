# 2026-08-09 작업 로그

## Goals

- 라우터 정리 **Slice 2 — 관리자 표면 주소 분리**(A1=ⓑ, 오너 2026-08-05). Slice 1 이
  76 operation 을 `routers/` 11 모듈로 옮겨 놓았으므로, 남은 것은 **파일 배치가 아니라
  네트워크 토폴로지**다: `/admin` 8 operation 을 제품 앱에서 들어내
  **같은 이미지·다른 command 의 네 번째 compose 서비스**로 옮기고 nginx 경유로만 닿게 한다.
- 선행 조건 **H-2(shim drift 가드)** 를 함께 닫는다. 2026-08-05 독립 검증이
  *"Slice 2 착수 전 오너 확인 사안"* 으로 올린 항목이며, 요구는 **"테스트가 보는 앱"과
  "배포되는 앱"이 갈라지는 것을 막는 가드** 다.
- 성공 기준: ① 제품 앱에 `/admin` 0건 ② 관리자 앱에 정확히 admin 8 + `/health`
  ③ **합집합(`create_app()`) 공개 표면 무변** — 지문 IDENTICAL ④ 토폴로지가 배선 파일에
  잠긴다 ⑤ 양방향 뮤테이션.

---

## Task 1 — 관리자 표면 주소 분리 (Slice 2, A1=ⓑ)

### User Decisions and Rationale

- **오너 지시**: HANDOFF·데일리로그를 읽고 다음 작업을 진행할 것. Next Tasks 2번이
  *"★ 그래서 다음은 2번의 Slice 2(`create_admin_app()`) — 선행은 H-2 하나다"* 로 지목한다.
- **새 결정 브리프는 만들지 않았다.** R1(register 함수)·A1(ⓑ 별도 compose 서비스)이
  2026-08-05 에 이미 확정돼 있고, 이 슬라이스는 그 결정의 **실행**이다.
  `CLAUDE.md` §1 의 "genuine fork" 에 해당하는 미결 선택지가 없다.
- 다만 브리프가 열어 둔 자리 셋은 구현 중 판단이었고, 근거를 아래 "판단한 것"에 적었다.

### 판단한 것 (브리프가 구현자에게 남긴 자리)

| 자리 | 판단 | 근거 |
|---|---|---|
| `create_app()` 의 운명 | **합집합으로 남긴다**(제품 68 + 관리자 8 + health) | 브라우저는 nginx 뒤에서 **한 origin** 만 본다. `scripts/dump_openapi.py` → `frontend/src/api/schema.d.ts` 가 그 origin 의 계약이라 **76 전부를 아는 앱이 계속 필요하다.** 제품 전용으로 바꾸면 스키마를 두 앱에서 뽑아 병합해야 하고, 경계 행렬 가드 세 겹도 쪼개진다 |
| shim drift 방지(H-2) | **세 factory 를 한 함수 본문으로** 두고(`include_product`·`include_admin`), 그 위에 성질 가드를 얹는다 | 검증자가 요구한 것은 "감시"였지만 **구조적으로 못 갈라지게** 하는 편이 강하다. 갈라질 수 있는 코드에 가드를 붙이는 것과, 갈라질 코드가 없는 것은 다르다 |
| 서비스 조립을 표면별로 잘라낼까 | **자르지 않는다** — 조립은 무조건 전부 돌고 `register_*` 호출만 갈린다 | 관리자 전용 조립 경로는 **아무도 구동하지 않는 두 번째 배선**이 된다(= `ObservedProvider` 계측 누락과 같은 형태). 대가는 관리자 컨테이너가 안 쓰는 객체를 몇 개 더 만드는 것뿐이고, env 를 안 주면 그 객체들은 in-memory fake 다 |
| `/health` 를 어느 표면에 | **둘 다** | 제품이 아니라 인프라다. 관리자 컨테이너가 healthcheck 를 가지려면 이것뿐이고, 빼면 `worker` 처럼 "Up 이지만 healthy 아님" 상태가 하나 더 는다 |
| admin 서비스 env | **Mongo 셋뿐** | 관리자 operation 전부가 Mongo 다. purge 도 벡터·lexical 파기를 **outbox 로 넘기고**(worker 가 드레인) 직접 부르지 않는다 — 코드로 확인했다. gateway·chroma·embedding 을 물리면 이 저장소에서 가장 좁은 표면에 기동 의존만 늘어난다 |
| 관리자 앱의 `/auth` | **두지 않는다** | 세션이 Mongo 라 쿠키가 공짜로 공유되고, nginx 는 `/api/admin/` 만 이 서비스로 보낸다 — 있어도 도달 불가다 |

### Completed work

| 파일 | 변경 |
|---|---|
| [`services/application/app/main.py`](../../../services/application/app/main.py) | `create_app(…, include_product=True, include_admin=True)` + **`create_product_app()`·`create_admin_app()`**. 모듈 수준 `app = create_product_app()` |
| [`services/application/app/admin_asgi.py`](../../../services/application/app/admin_asgi.py) | **신규** — compose `admin` 서비스의 ASGI 진입점 |
| [`docker-compose.yml`](../../../docker-compose.yml) | **`admin` 서비스 신설**(application 이미지 재사용 · command 만 변경 · **포트 미게시** · Mongo 셋 · healthcheck · `restart: unless-stopped`). `frontend` 의 `depends_on` 에 admin 추가 |
| [`frontend/nginx.conf`](../../../frontend/nginx.conf) | `location /api/admin/` → `admin:8000`(변수 upstream + 런타임 resolver, 제품 location 과 같은 형태) |
| [`tests/test_admin_surface_separation.py`](../../../tests/test_admin_surface_separation.py) | **신규 10 cells** — 표면 소속 · **H-2 합집합 성질** · 진입점 · compose/nginx 토폴로지 |
| [`tests/test_app_import_paths.py`](../../../tests/test_app_import_paths.py) | 새 배포 진입점 로드 셀 1 |
| [`docs/system-contract-sot.md`](../../system-contract-sot.md) | **v1.7.91** — 변경이력 + §"제품과 프로젝트 경계"에 표면 분리 계약 4항 |
| [`README.md`](../../../README.md) | 절차 표 ② 기준선 · ④ SoT 버전(가드가 잡는 두 자리) |

**등록 순서는 건드리지 않았다.** `if include_*:` 를 **제자리에** 두고 호출 목록을
재배열하지 않은 것이 계약이다 — 합집합 앱의 route 등록 순서가 곧 OpenAPI 문서의 순서이고,
그것이 프론트 TS 생성물의 입력이다. (초판에서 admin 을 auth 앞으로 옮겼다가 되돌렸다.)

### 왜 이 분리가 방어인가

제품 포트는 **일부러 LAN 에 게시**된다(D8-7 G1=C). 그 근거가 *"세션 뒤에 있다"* 이므로,
`/admin` 이 같은 포트에 있는 한 관리자 표면의 방어는 `require_admin_user` **한 겹**이었다.
분리 후 LAN 에서 그 경로를 치면 **가드가 아니라 라우터가 404** 로 답한다 — 가드는 없어지지
않고 두 번째 겹으로 남는다.

### 검증

| 검사 | 결과 |
|---|---|
| **공개 표면 무변** — `repro_router_split.py`(HEAD worktree vs 작업 트리) | **`diff` 출력 없음(pre ≡ post)** · route **76** · order-sensitive pairs **0** · openapi sha `f8b42ef1…` · stdout-only 지문 sha `c3dfb391…` |
| 표면 분할 실측 | 합집합 **76** = 제품 **68** ∪ 관리자 **9**, 교집합 = `{("/health","get")}` |
| `docker compose config` | 10 서비스 파싱 성공, `admin` 이 의도한 command·env·healthcheck 로 해석됨 |
| `nginx -t`(nginx:1.27-alpine 에 실 conf 마운트) | `syntax is ok` / `test is successful` |
| **소켓 라이브**(호스트 uvicorn 2개, in-memory 조립) | 관리자 8531: `/health` **200** · `/admin/users` **401** · `/projects` **404** · `/auth/login` **404** / 제품 8532: `/health` **200** · `/admin/users` **404** · `/projects` **401** · `/auth/login` **405** |
| 뮤테이션 | 7종(under 6 · over 1) 전부 재실패 — 아래 표 |
| 전수 회귀(test-mongo ON) | 아래 |

### 뮤테이션 (7종)

**순서 준수**: 구현을 먼저 커밋(`5bdaf15`·`878f24d`) → 뮤테이션 → `git checkout --` 원복 →
매 회 `git status --short` 로 clean 확인(§6 게이트). 초점 스위트는
`test_admin_surface_separation.py` + `test_compose_exposure.py`.

| # | 방향 | 적용한 diff | file | 실패한 셀 |
|---|---|---|---|---|
| M1 | under | `if include_admin:` → `if True:`(제품 앱이 `/admin` 을 다시 든다) | `main.py` | `SurfaceMembershipTest::test_the_product_surface_serves_no_admin_operation` · `::test_the_two_surfaces_partition_the_union_app` · `EntryPointTest::test_the_image_default_command_serves_the_product_app` (3) |
| M2 | under | `create_admin_app` 이 `include_product=False` 를 잊는다 | `main.py` | `::test_the_admin_surface_serves_exactly_the_admin_tier_and_health` · `::test_the_two_surfaces_partition_the_union_app` · `EntryPointTest::test_the_admin_container_entrypoint_serves_the_admin_app` (3) |
| M3 | under | 모듈 수준 `app = create_product_app()` → `create_app()`(이미지 기본 CMD 가 합집합) | `main.py` | `EntryPointTest::test_the_image_default_command_serves_the_product_app` (1) |
| M4 | under | admin 서비스에 `ports: ["8524:8000"]` 추가 | `docker-compose.yml` | `ComposeAndProxyTopologyTest::test_the_admin_service_publishes_no_host_port` · **`test_compose_exposure.py::ComposeExposureTest::test_every_publishing_service_is_classified`** (2) |
| M5 | under | admin location 의 rewrite 를 `^/api/admin/(.*)$` 로(= `/admin` 세그먼트 소실 → 업스트림 404) | `frontend/nginx.conf` | `ComposeAndProxyTopologyTest::test_nginx_sends_the_admin_prefix_to_the_admin_service` (1) |
| M6 | under(**drift**) | **배포 관리자 앱에만** `register_observability(...)` 추가 — 합집합이 모르는 표면이 배포에 생긴다 | `main.py` | `::test_the_admin_surface_serves_exactly_the_admin_tier_and_health` · `::test_the_two_surfaces_partition_the_union_app` · `EntryPointTest::test_the_admin_container_entrypoint_serves_the_admin_app` (3) |
| M7 | **over** | `register_health(app)` → `if include_product:`(관리자 컨테이너 healthcheck 가 조용히 죽는다) | `main.py` | 위 M6 과 같은 3 셀 |

**★ M1 은 한 번 다시 쟀다.** 첫 실행에서 출력을 `tail -3 | head -2` 로 잘라 받아 실패 셀
목록이 잘렸고, 그 상태로 표에 4 셀이라 적을 뻔했다. **실측은 3 셀**이며
`test_every_operation_keeps_its_guards_on_the_split_apps` 는 이 뮤테이션에 물지 않는다 —
관리자 route 가 양쪽에 다 실리면 `{**product, **admin}` 이 여전히 합집합의 계약을 덮기
때문이다(그 셀이 겨냥하는 것은 *가드가 다른* 경우이지 *어느 앱에 실렸는가* 가 아니다).
**재측정 때 작업 트리에 문서 3건이 미커밋 상태였다** — 뮤테이션·원복이 `main.py` 하나만
path 지정으로 건드렸으므로 손실은 없었지만, §6 게이트("첫 뮤테이션 전 `git status --short`
가 비어 있어야 한다")를 그대로 지킨 것은 아니다. 사실대로 적는다.

**M6 이 H-2 를 직접 겨냥한 축이다.** "배포 앱에만 있는 표면"은 합집합 앱을 쓰는 기존 가드
전체가 원리적으로 못 보는 자리이며, 그것을 보는 셀이 이 슬라이스의 존재 이유다.

**M4 는 두 파일의 가드가 함께 무는 것을 확인했다** — 기존 노출 가드는 *"분류해라"* 로 실패하고
새 셀은 *"게시하면 안 된다"* 로 실패한다. 둘은 다른 말을 한다.

### 회귀 기준선

**실측(알파, test-mongo ON, `878f24d` + 문서)**:

```
2208 passed, 4 skipped, 2247 subtests passed in 170.94s
```

**환경 보정하면 `2211 / 1 / 2247`.** skip 4 중 3건은 이 셸에 `elasticsearch` 패키지가 없어
`test_context_search_memory_lexical_retrieval.py` 가 건너뛴 것이고(알파의 정상값 — 2026-08-08
work_log 가 예고한 그대로), 남는 1건은 호스트에서 구조적으로 항상 skip 되는 live Chroma 다.

- **직전 기준선 `2200/1/2169`**(2026-08-08 검증 기록 반영 예고값) 대비 **셀 +11 · subtest +78**.
- **+11 = 신규 파일 10 + 진입점 로드 1.** operation 은 76 무변이고 셀 증감은 전부 신규 가드다.
- **+78 = 신규 파일의 subtest**(operation 76 전수 계약 대조 + `app.state`/handler 2).
- **★ 처음에 이 파일을 22 cells / 475 subtests 로 쟀다** — `from tests.test_auth_api import
  CombinedBoundaryMatrixTest` 로 **클래스를 이름공간에 끌어와** pytest 가 그 클래스를 여기서
  한 번 더 수집·실행하고 있었다. 모듈만 import 하도록 고쳤다(`878f24d`). 다음에 남의 테스트
  리터럴을 재사용할 사람은 **클래스가 아니라 모듈을 import 한다**.

프론트는 손대지 않았다 — `nginx.conf` 만 바뀌었고 `src/` 는 0줄이라 `265/18` 기준선과
`schema.d.ts` 가 그대로다(openapi sha 동일이 그 실측이다).

### Issues found — 등록 순서를 바꿀 뻔했다

- **문제**: 초판이 `if not include_product: return app` 을 auth 앞에 두어 **admin 이 auth 보다
  먼저 등록**됐다. 표면 집합은 같지만 route **순서**가 바뀐다.
- **왜 중요한가**: 합집합 앱의 route 순서가 `app.openapi()` 의 `paths` 순서이고, 그것이 프론트
  TS 생성물의 입력이다. 지문의 order-sensitive pairs 가 0 이라 동작은 안 바뀌지만 **계약 문서의
  바이트가 바뀐다** — Slice 1 이 4차에 걸쳐 지킨 `f8b42ef1…` 이 깨졌을 자리다.
- **처리**: `if` 를 제자리에 두는 형태로 고치고 주석으로 이유를 못박았다. 지문 IDENTICAL 로 확인.

### 아직 안 한 것 (의도)

- **컨테이너·nginx 관통 라이브 확인.** 알파 이미지가 2026-07-22 빌드라 재빌드가 선행되고,
  HANDOFF 가 그것을 **오너 판단 사안**으로 남겨 두었다. 대신 ① 호스트 소켓으로 두 앱을 실제로
  띄워 상태코드를 재고 ② `docker compose config` 로 서비스 해석을 확인하고 ③ 실 conf 를 nginx
  컨테이너에 마운트해 `nginx -t` 를 통과시켰다. **남은 미실측은 "nginx → admin 컨테이너" 한
  홉뿐**이며, 스택을 세울 때 `curl :5520/api/admin/users` 가 **401**(404 가 아니라)인지로 닫힌다.
- **프론트 admin 호출부 변경 0건** — URL 이 그대로 `/api/admin/...` 이라 바꿀 것이 없다.
  그것이 ⓑ 를 고른 이유 중 하나였다.
- **디버그용 `127.0.0.1:${ADMIN_PORT}` 게시**(브리프 §3 의 선택지) — 필요해진 적이 없고,
  열면 새 셀과 기존 분류 가드를 함께 고쳐야 한다.

### Next steps

1. **스택을 세우는 첫 사람이 관통 확인 1건**(위). 재빌드 대상은 `application`·`admin`·`frontend`.
2. **Phase 9 A1~A8 오너 결정** — 라우터 정리(Slice 1·2)가 끝나 A7 가드가 `main.py` 를 파일로
   읽을 이유가 완전히 없어졌다.
3. 추적 부채 2건은 그대로다(`AUTH_SESSION_TTL_HOURS` 계약 회귀 · 미사용 import 가드 ⓐ 유지).

---

## Task 2 — 독립 검증 반영 (`9ddff6e` 대상) · 비차단 3건 처리

독립 세션이 **합격 · Blocking 0** 으로 검증했다
([기록](../../verifications/2026-08-09/admin_surface_separation.md)). 판정이 합격이므로
되돌림은 없고 **비차단 지적을 닫는 것**이 범위다.

### User Decisions and Rationale

- 오너 지시: *"검증기록 확인해서 보강할 부분 보강해."* Task 1 의 2026-08-08 선례와 같은 형태다.

### 처리

| 지적 | 처리 |
|---|---|
| ① **뮤테이션 매트릭스에 A6(route_class) 축이 빠졌다** — 검증자가 M8 로 그 셀의 생존을 입증했다 | **재현해 매트릭스에 편입**(아래 M8 행). 내 7종은 `test_every_operation_keeps_its_guards_on_the_split_apps` 를 무는 변이를 하나도 갖고 있지 않았다 — **가드 하나가 뮤테이션으로 뒷받침되지 않은 채 있었다**는 뜻이고, 그 상태에서는 "혹시 dead cell 아닌가"를 반박할 근거가 없다 |
| ② **M1 재측정 때 §6 게이트 위반**(미커밋 문서 3건) | 사실 기록 유지. **이번 Task 는 검증 산물을 먼저 커밋(`9ddff6e`)하고 뮤테이션에 들어갔다** — 게이트를 지킨 상태로 M8 을 돌렸다 |
| ③ **nginx → admin 한 홉 미실측** | 오너 판단 사안으로 유지. 다만 **미실측의 범위가 줄었다** — 검증자가 실 application 이미지에 트리를 마운트해 `admin_asgi:app` 기동을 입증했으므로(`/admin/users` 401), 남은 것은 **nginx 홉 하나**다. HANDOFF·SoT 문구를 그 실측에 맞게 좁혔다 |

### ★ M8 재현 — 검증자 주장대로 A6 셀은 살아 있다

**순서 준수**: 검증 산물 커밋(`9ddff6e`) → `git status --short` empty 확인 → 뮤테이션 → 원복.

| # | 방향 | 적용한 diff | file | 실패한 셀 |
|---|---|---|---|---|
| M8 | under | `app.router.route_class = QuotaSettledRoute` 를 `if include_product:` 로 감싼다(관리자 앱의 route 클래스가 `APIRoute` 로 갈라진다) | `main.py` | `SurfaceMembershipTest::test_every_operation_keeps_its_guards_on_the_split_apps` — **9 SUBFAILED**(admin 8 + `/health`, 전부 관리자 앱이 서빙하는 operation) |

**이 변이가 현실적인 이유**: 관리자 표면은 유료가 아니므로 "정산 wrapper 를 제품에만 주자"는
최적화가 자연스러워 보인다. 그런데 `QuotaSettledRoute` 는 receipt 가 없으면 no-op 이라
**얻는 것이 없고**, route 클래스가 표면마다 달라지는 순간 합집합 계약과 배포 앱이 갈라진다
(브리프 §3 이 "기본: 준다"로 열어 둔 자리이며, 이제 그 선택이 가드로 잠겼다).

### ★ 방법론 부채 하나를 함께 닫았다 — `grep FAILED` 는 subtest 실패를 놓친다

검증자가 자기 추출 도구의 버그를 정직하게 적었다: `pytest-subtests` 는 실패한 subtest 를
**`SUBFAILED(...)`** 로 찍으므로 `^FAILED` 필터에 **한 줄도 안 걸린다**. 그래서 M8 을 처음에
*"재실패 없음"* 으로 읽었다.

- **내 Task 1 의 뮤테이션 7종도 같은 필터로 읽었다.** 이번에 M8 을 돌려 실측한 결과 그
  필터는 `SUBFAILED` 9줄을 전부 버리고 요약줄 `9 failed` 만 남긴다 — 즉 **요약줄을 안 봤으면
  나도 똑같이 오독했다**. 7종은 전부 cell 단위 실패라 결과는 무사했지만 **방법이 무사했던
  것은 아니다**.
- **가장 강한 가드가 정확히 이 사각에 든다** — 전수 대조 셀은 대개 `subTest` 로 돈다.
- **처리**: 절차 정본 [`docs/guides/verification.md`](../../guides/verification.md)
  §"Mutation testing" 에 절을 신설했다(요약 count 줄을 읽을 것 · 필터는 `FAILED|SUBFAILED`).
  *"물지 않았다"를 필터로 읽고 기록하면 다음 사람이 멀쩡한 가드를 지우러 온다.*

### 함께 정정 — 알파 application 이미지는 2026-07-22 가 아니라 2026-08-02 빌드다

검증자가 짚었고 직접 재확인했다(`docker images` = `2026-08-02 07:57:51`, 이미지 안에
`admin_asgi.py` **없음**). HANDOFF ★★ 항목이 "2026-07-22 빌드"라 적고 있었다 — 그 항목의
**결론(낡은 이미지는 인증 없는 제품으로 뜬다·재빌드 필요)은 그대로 유효**하지만 날짜가
틀렸으므로 고쳤다. 2026-08-02 는 D8-5~7 이후라 인증은 들어 있고, **Slice 2(08-09)보다
앞서므로 admin 진입점이 없다**는 것이 지금 관통을 막는 사유다.

### Verification (이번 Task)

| 검사 | 결과 |
|---|---|
| M8 재현 | 9 SUBFAILED · 요약 `9 failed` · 원복 후 `git status --short` empty |
| 검증자 건수 갱신 확인 | `test_docs_indexes.py` **13 passed / 238 subtests**(기록 1건 = subtest +1) |
| 이미지 사실 확인 | `ai_writte_system-application:latest` created **2026-08-02 07:57:51** · `admin_asgi.py` 부재 |

### 아직 안 한 것 (의도)

- **검증 기록 본문은 고치지 않았다.** 남의 산출물이고 판정·근거가 정확하다.
- **nginx 홉** — 오너 판단(재빌드) 사안 그대로.

---

## Task 3 — Phase 9 Slice 9.0 브리프 확정 (A1~A8)

구현 없음. **오너 결정을 받아 브리프를 `Resolved` 로 닫은 것**이 산출물이다.

### User Decisions and Rationale

- **오너 결정(2026-08-09)**: **A2 = B**(정본 10 + 검토 결정 9 = 19 경로), **나머지 일곱은
  구현자 추천 그대로** — A1=A(새 컬렉션 `activity_events`) · A3=B(고정 코어 + 짧은 값 변화) ·
  A4=A(격리 fail-open) · A5=B(소유자 조회 `GET /projects/{id}/activity`, operation 77) ·
  A6=A(TTL 없음) · A7=A(endpoint + 전수 가드) · A8=A(중복 없음).
- **★ A2 에 조건이 붙었다.** 오너 문언: *"A2에서 C까지 필요하다면 열어야 할 수 있을 것 같다.
  그래서 확장성 있게 하되 일단 B로 진행."* — **B 는 범위 판단이지 C 의 각하가 아니다.**
- **그 문언을 구현 조건 셋으로 번역해 브리프 상단에 못박았다**(추측 여지를 남기면 다음 사람이
  "확장성 있게"를 자기 식으로 읽는다):
  1. **분류표는 mutating 40 전수** — 각 route 가 `logged` / `excluded(사유)` 중 하나로 등재되고
     **미등재는 가드가 실패**시킨다(`quota/billable_actions.py` 선례). **C 로 넓히는 일 = AI 요청
     14 행의 값을 바꾸는 것**이어야 하고 구조 변경이어서는 안 된다.
  2. **문서 형태(A3=B)가 C 행을 그대로 받아야 한다** — 새 필드 없이. `before`/`after` 는
     값 변화가 있을 때만 채우는 선택 필드다.
  3. **★ C 를 열 때 A8 을 함께 다시 본다** — A8=A("중복 없음")가 성립하는 근거가 *"AI 요청은
     활동 로그 밖"* 이기 때문이다. C 를 열면 같은 사건이 `llm_call_audits`·원장·활동 로그
     **셋**에 살게 되므로, 그 판단을 A2 와 분리하면 이 저장소가 반복해 피해 온 **두 정본**이 생긴다.
- **D(조회 GET 36 기록)는 여전히 별도 결정**이다 — 축이 다르고 승격 감사와 성격이 섞인다.

### Completed work

| 파일 | 변경 |
|---|---|
| [`plans/09-0-service-activity-log-decisions.md`](../../plans/09-0-service-activity-log-decisions.md) | 상태 `Awaiting owner decision` → **`Resolved (2026-08-09)`** · 오너 결정 표 8행 · **"A2 확정 조건" 블록** · A2 절 안에 확정 주석 |
| [`plans/09-service-activity-log.md`](../../plans/09-service-activity-log.md) | 상태 `Planned` → **`Ready — 구현 대기`** |
| [`plans/README.md`](../../plans/README.md) | 두 행의 상태 열 갱신(인덱스 가드가 보는 자리) |

### 아직 안 한 것 (의도)

- **구현 0줄.** 브리프 §"결정 뒤 구현 순서" 1~7 이 그대로 다음 작업이며, **1번이 회귀 먼저**다.
- **SoT 개정 안 함.** 이 결정은 아직 계약 문언이 아니라 착수 승인이다 — `activity_events` 계약과
  operation 77 은 구현 슬라이스가 정본에 올린다(8.1~8.2c 가 전부 그 순서였다).
- **`mongo_collections.md` §43 처리**(폐기 포인터 + 새 절)도 구현과 함께 간다.

### Next steps

1. **Phase 9 구현 착수** — 브리프 §"결정 뒤 구현 순서": 회귀 먼저 → 저장소 한 쌍 → HTTP 19곳 +
   `current` 인자 → 조회 operation 77 → 정본 → 뮤테이션 → 독립 검증.
2. **A7 의 34곳 `current=Depends(...)` 인자 추가**가 이 슬라이스의 가장 넓은 diff 다(§0.4).
   라우터 정리가 끝나 이제 그 자리는 `routers/*` 안이다.
