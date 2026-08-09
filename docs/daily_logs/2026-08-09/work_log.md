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

---

## Task 4 — Phase 9 Slice 9.0 구현 (서비스 활동 로그)

### User Decisions and Rationale

- 오너 지시: *"일단 브리프 결정되었으니까 작업 진행해줘."* Task 3 에서 확정한
  A1~A8 을 그대로 구현했다. **새로 결정한 것은 없다.**
- **★ 다만 브리프 안에서 두 기준이 어긋나는 자리를 하나 발견했다 — 오너 확인이 필요하다**
  (아래 "Issues found").

### Completed work

| 파일 | 변경 |
|---|---|
| [`app/activity/actions.py`](../../../services/application/app/activity/actions.py) | **신규** — mutating **40 전수** 분류표(`logged` 19 / `excluded` 21 + 사유) |
| [`app/activity/log.py`](../../../services/application/app/activity/log.py) | **신규** — `ActivityEvent` · Protocol · in-memory · 서비스(격리 경계·짧은 값 상한) |
| [`app/activity/log_mongo.py`](../../../services/application/app/activity/log_mongo.py) | **신규** — `activity_events` 어댑터(인덱스 1 · TTL 없음 · naive 날짜 재부착) |
| `routers/{projects,drafts,source_refs,analysis}.py` | **19 endpoint 배선** + `current=Depends(require_authenticated_user)` |
| [`routers/admin.py`](../../../services/application/app/routers/admin.py) | purge 에 `activity.purge_project(...)` 한 줄 |
| [`routers/projects.py`](../../../services/application/app/routers/projects.py) | **`GET /projects/{project_id}/activity`(operation 77, A5=B)** |
| [`api/models.py`](../../../services/application/app/api/models.py) | `ActivityEventPayload`·`ActivityLogResponse` |
| [`main.py`](../../../services/application/app/main.py) | `_default_activity_log_service()` + `activity_log_service` 인자 + 조립 |
| `tests/test_activity_{actions,log,api}.py` · `test_purge_reconciler.py` · `test_auth_api.py` | 회귀 **+36 cells**, tier 리터럴 76→77·61→62 |
| `docs/mongo_collections.md` | **§43 `system_events` 폐기 포인터** + **§43G `activity_events`** 신설 |
| `docs/system-contract-sot.md` | **v1.7.92** + tier 분할 숫자 갱신 |
| `frontend/src/api/schema.d.ts` | `gen:api` 재생성(+118줄, operation 77) — 화면 작업은 없다 |

### 설계에서 실제로 판단한 것

- **`current` 인자는 19곳에만 붙였다.** 브리프 §0.4 는 "project 경로 34곳"을 예상했는데,
  기록하는 경로만 주체가 필요하므로 **그 절반이면 된다**. 나머지 route 는 종전대로
  `dependencies=_REQUIRE_PROJECT_OWNER` 선언만 갖는다.
- **격리 경계를 서비스 안 한 곳에 뒀다**(호출부 19곳이 아니라). 각자 `try/except` 를
  쓰면 한 곳이 빠지는 순간 그 경로만 fail-closed 가 되고, 그 차이는 **저장소가 죽기
  전까지 아무 테스트도 못 본다**.
- **gate-finding 두 handler 는 헬퍼(`_transition_gate_finding`)가 아니라 handler 본문에서
  기록한다.** 전수 가드가 `inspect.getsource(route.endpoint)` 를 보므로 헬퍼에 넣으면
  가드가 못 본다 — 가드가 볼 수 있는 자리에 두는 것이 배선 규칙의 일부다.
- **auto-promote 는 새로 승격된 것이 있을 때만 기록한다**(전부 replay 면 바뀐 게 없다).
  **알려진 공백**: 그 handler 의 503 partial envelope 두 경로는 mint 가 durable 한데도
  기록하지 않는다 — envelope 이 이미 "무엇이 저장됐는지"를 말하므로 두 정본을 피했다.

### Issues found — ★ `writing/accept` 에서 브리프의 두 기준이 어긋난다 (오너 확인 필요)

- **사실**: `POST …/writing/accept` 는 **정본 draft version 을 실제로 저장한다**
  (`WritingAcceptService.accept` → `start_next_unit` → `SaveDraftResult`, 코드로 확인).
- **어긋남**: 브리프 §0.2 는 이 경로를 성격으로 **"AI·작업 요청 14"** 에 넣었고, 그래서
  A2=B(정본 10 + 검토 9)에서 빠진다. 그런데 **A2 의 기준은 "사용자가 무엇을 *바꿨는가*"**
  이고 accept 는 정본을 바꾼다. 부모 계획 §2 의 목표 질문 *"특정 원고가 마지막으로 저장된
  것은 언제인가"* 에 정면으로 걸리는 자리다 — **accept 는 주 저작 흐름의 저장 경로**이고,
  지금 로그에 남는 저장은 수동 `POST …/drafts/{id}/versions` 뿐이다.
- **처리**: **오너가 승인한 것은 "B = 19" 라 그 숫자를 지켰다.** 임의로 20 으로 넓히지
  않고, 분류표의 그 행에 **어긋남과 근거를 주석으로 달아** `excluded(ai_request)` 로 두고
  **오너 확인 대기**로 남긴다. 넓히는 것은 A2 확장 조건 그대로 **행 하나를 옮기는 일**이다
  (그때 action 리터럴은 `draft_version_accepted` 같은 이름이 자연스럽다).
- **왜 지금 막지 않았나**: 되돌리기가 싸고(행 하나) 잘못돼도 다른 18 행이 무용해지지
  않는다. 반대로 승인 숫자를 말없이 바꾸는 것은 결정 기록을 훼손한다.

### Issues found — 404 셀은 순서를 잠그지 않는다 (뮤테이션 N2 가 드러냄)

- `test_a_failed_request_leaves_no_trace`(없는 project 에 PATCH → 404)를 "A7=A 의 핵심"
  이라 적었는데, **N2(기록을 handler 맨 앞으로 이동)에서 이 셀이 통과했다.**
- **원인**: 없는 project 의 404 는 `require_project_owner` **dependency** 가 낸다 —
  handler 본문이 아예 안 돈다. 순서를 실제로 잠그는 것은 **409 셀**
  (`test_a_conflicting_request_leaves_no_trace`, archive 된 프로젝트 개명)이다.
- **처리**: 셀을 지우지 않고 **문서를 실측에 맞게 고쳤다** — 404 셀은 반대 방향을 잠근다
  (기록을 dependency 로 옮기면 그때는 여기가 문다). 두 셀을 함께 읽어야 A7=A 가 덮인다.

### 뮤테이션 (8종)

**순서 준수**: 구현을 먼저 커밋(`65507d9`) → `git status --short` empty 확인 → 뮤테이션 →
`git checkout --` 원복 → 매 회 clean 확인. **결과는 `FAILED|SUBFAILED` 로 읽었다**
(2026-08-09 검증이 올린 그 함정 — `grep FAILED` 만으로는 subtest 실패를 통째로 놓친다).

| # | 방향 | 적용한 diff | file | 실패한 셀 |
|---|---|---|---|---|
| N1 | under | 개명 endpoint 의 `activity.record(...)` 삭제 | `routers/projects.py` | `test_every_logged_route_actually_records`·`test_the_recorded_action_literal_matches_the_table`(각 1 SUBFAIL) · `test_renaming_records_both_the_old_and_the_new_name` · `test_the_owner_reads_…_newest_first` · `test_the_response_carries_the_value_change` (5) |
| N2 | under | `activity.record(...)` 를 `try:` **앞에 삽입**(원래 호출은 그대로 두었으므로 **중복 기록**이 된다) | `routers/projects.py` | `test_a_conflicting_request_leaves_no_trace` · `test_the_owner_reads_…_newest_first` (2). **404 셀은 안 물었다 — 위 Issues 참조.** 아래 Task 5 가 이 행을 정밀화한다 |
| N3 | **over** | A4=A 격리를 걷어내 fail-closed 로 | `activity/log.py` | `test_a_broken_activity_store_does_not_break_the_request` · `test_a_write_failure_does_not_reach_the_caller` (2) |
| N4 | under | purge 배선 한 줄 삭제 | `routers/admin.py` | `ActivityPurgeTest::test_purging_a_project_removes_its_activity` (1) |
| N5 | under(**I1**) | 문서 필드를 `project_id` → `target_project_id`(8.2c 흉내) | `activity/log_mongo.py` | 어댑터 5 + 실 Mongo 조립 1 + **`test_the_activity_log_is_swept`**(reconciler 가 못 찾는다) (7) |
| N6 | **over(A8)** | 기록 안 하기로 한 `writing/accept` 에 `activity.record(` 추가 | `routers/writing.py` | `test_no_excluded_route_records`(1 SUBFAIL) |
| N7 | under(A3) | 짧은 값 200자 상한 제거 | `activity/log.py` | `test_a_long_value_is_cut_to_the_short_value_cap` (1) |
| N8 | under(A6) | TTL 인덱스 추가 | `activity/log_mongo.py` | `test_the_collection_has_no_ttl_index` (1) |

**N5 가 이 슬라이스의 핵심 증거다.** 8.2c 와 정반대 방향을 잠근다 — `project_name_history`
는 reconciler 에 **발견되면 안 되고**, 활동 로그는 **반드시 발견돼야 한다**. 두 셀이 나란히
있어서, 다음 사람이 `_id` 트릭을 여기 복사하면 즉시 드러난다.

### Verification

| 검사 | 결과 |
|---|---|
| 전수 회귀(알파, test-mongo ON) | `2244 passed / 4 skipped / 2322 subtests in 180s` → **보정 `2247 / 1 / 2322`** |
| 직전 기준선 `2211/1/2247` 대비 | **셀 +36**(가드 7 · 저장 16 · HTTP 12 · reconciler 1) · **subtest +75** |
| operation | **76 → 77**(A5=B). tier = public 4 · auth 3 · admin 8 · **project 62** |
| 프론트 | `gen:api` 재생성(+118줄) · `tsc --noEmit` clean · **265 passed / 18 files**(무변) |
| 뮤테이션 | 8종(under 6 · over 2) 전부 재실패 |

### 아직 안 한 것 (의도)

- **`writing/accept` 분류** — 위 Issues, 오너 확인 대기.
- **화면 0줄.** A5=B 는 API 까지다(브리프 §범위 밖: "프론트 화면은 다음").
- **기록 실패 진단 카운터** — A4=A 의 "조용한 구멍"에 대한 후속 고려이며 범위 밖.
- **503 partial envelope 경로의 기록**(auto-promote) — 위 설계 판단 참조.

### Next steps

1. **독립 검증**(다른 작업자). 볼 만한 축: N5 방향(8.2c 와의 대칭) · 404/409 셀의 역할
   분담 · 19 배선이 전부 결과 뒤인지 · `writing/accept` 판단.
2. **`writing/accept` 오너 확인** 뒤 필요하면 행 하나 이동.
3. 화면(활동 타임라인)은 별도 슬라이스.

---

## Task 5 — 독립 검증 반영 (`ad195e5` 대상) · 비차단 2건 처리

독립 세션이 **합격 · Blocking 0** 으로 검증했다
([기록](../../verifications/2026-08-09/service_activity_log.md)). 되돌림은 없고
비차단 지적을 닫는 것이 범위다.

### 처리

| 지적 | 처리 |
|---|---|
| ① **N2 뮤테이션의 셀 수가 내 보고(2)와 하나 다르다(1)** — 검증자는 "rename 호출 직전 이동" 으로 시위했고 1 셀(409)이 물었다 | **두 변이를 각각 다시 재서 원인을 특정했다**(아래). 내 표기 *"기록을 handler 맨 앞으로"* 가 부정확했다 — 실제 diff 는 **이동이 아니라 삽입**이었다 |
| ② **`writing/accept` 분류** | 오너 결정 대기 유지. 검증자도 *"넓히는 것이 자연스럽다"* 로 같은 판단이고, **A8 을 함께 다시 봐야 한다**는 조건까지 일치한다 |

### ★ ① 의 원인 — 삽입과 이동은 **다른 뮤테이션**이다

두 변이를 같은 초점 스위트에서 각각 실측했다:

| 변이 | 적용한 diff | 실패 셀 |
|---|---|---|
| **N2a**(내가 돌린 것) | `activity.record(...)` 를 `try:` **앞에 삽입** — 원래 호출을 **지우지 않았다** | `test_a_conflicting_request_leaves_no_trace` · `test_the_owner_reads_…_newest_first` (**2**) |
| **N2b**(검증자) | record 블록을 **rename 호출 직전으로 이동**(원래 자리에서 제거) | `test_a_conflicting_request_leaves_no_trace` (**1**) |

**둘째 셀이 무는 이유는 순서가 아니라 중복이었다** — N2a 에서는 성공한 개명 하나가
`project_renamed` **두 행**을 남기므로 최신순 목록 단정이 깨진다. 즉 내 N2a 는
*"결과 뒤에 쓴다"* 와 *"한 번만 쓴다"* 를 **동시에** 흔든 변이였고, A7 계약을 겨냥한
쪽은 **409 셀 하나**다(양쪽 변이에서 모두 물린 그 셀).

**계약 검증에는 영향이 없다** — 핵심 셀이 두 변이 모두에서 물었다. 틀린 것은 **표기**이며
N2 행을 실제 diff 로 고쳤다.

**★ 일반화해서 절차 정본에 올렸다**: 뮤테이션은 **적용한 diff 를 그대로** 적어야 하고
요약어(*"앞으로 옮겼다"*)로 적으면 안 된다 — **삽입과 이동은 다른 변이**라 재현자가
다른 셀 수를 얻고, 그러면 매트릭스의 차이가 *가드의 약함* 때문인지 *변이의 범위* 때문인지
가릴 수 없다(2026-08-04 Slice 8.4 에서 다섯 중 셋이 갈라진 것과 같은 병이다).
[`docs/guides/verification.md`](../../guides/verification.md) §"Mutation testing" 에 한 줄 추가.

### 검증이 채운 것 (내가 안 잰 축)

- **분류표 40 전수를 `app.routes` 에서 직접 재유도**했다 — 나는 가드가 통과하는 것으로
  갈음했는데, 검증자는 미등재 0·stale 0 을 손으로 대조했다.
- **8.2c 와의 대칭을 두 셀 이름으로 확인**했다(`test_the_project_name_history_is_not_swept`
  ↔ `test_the_activity_log_is_swept`). 내가 "나란히 둔 것이 의도" 라고만 적은 자리를
  실제로 마주 놓고 읽었다.
- **openapi·tier 를 별도로 대조**해 operation 77·project 62 를 재확인했다.

### 아직 안 한 것 (의도)

- **검증 기록 본문은 고치지 않았다** — 남의 산출물이고 판정·근거가 정확하다.
- **`writing/accept`** — 오너 결정 대기 그대로.

---

## Task 6 — A2 추가 확정: `writing/accept` 를 활동 로그에 포함 (19 → 20) · 하루 마무리

### User Decisions and Rationale

- **오너 결정(2026-08-09)**: *"그래 그러면 넓히는 걸로 하자."* Task 4 가 물어 둔 자리와
  독립 검증이 같은 판단을 낸 자리를 오너가 확정했다. **A2 = 정본 변경 11 + 검토 결정 9
  = 20 경로.**
- **오너 지시**: 재빌드는 다음에. 오늘은 여기까지 하고 다음 작업자를 위한 메모를 남기고 마무리.

### Completed work

| 파일 | 변경 |
|---|---|
| [`activity/actions.py`](../../../services/application/app/activity/actions.py) | accept 행을 `EXCLUDED_OPERATIONS` → `_CANONICAL` 로. 리터럴 **`draft_version_accepted`**, `target_type="draft_version"`. 정본 11 / 검토 9 / `ai_request` 14 → **13** |
| [`routers/writing.py`](../../../services/application/app/routers/writing.py) | `current=Depends(...)` + **두 경로**에 기록 — 성공(`result.saved is not None`)과 **502 partial**(version 은 저장되고 분석 job 만 실패) |
| [`main.py`](../../../services/application/app/main.py) | `register_writing(..., activity=activity)` |
| [`tests/test_writing_accept.py`](../../../tests/test_writing_accept.py) | **+2 cells** — 저장되면 남는다 · **Gate 거부(200·`saved=null`)면 안 남는다**(over-strict) |
| `tests/test_activity_actions.py` | 리터럴 19 → **20**, `ai_request` 14 → **13** |
| 브리프·부모 계획·plans 인덱스 | "A2 추가 확정" 블록 · 상태 `Done` · 인덱스 두 행 |
| `docs/system-contract-sot.md` · `mongo_collections.md` §43G · README · CHANGELOG | **v1.7.93** · 20 경로 |

### 왜 이것이 A8 개정이 아닌가 (중요 — 다음 사람이 헷갈릴 자리)

**남기는 것은 *AI 요청* 이 아니라 *정본 저장* 이다.** `llm_call_audits`(호출 단위)·
`request_usage_ledger`(과금 단위)가 담는 사건과 **다른 사실**이므로 두 정본이 생기지 않는다.
**A2=C 확장과 축이 다르다** — C 는 "AI 를 불렀다"를 담는 것이고 대상은 `ai_request` **13 행**
이며, 그때는 확정 조건 ③(**A8 을 함께 다시 본다**)이 그대로 살아 있다.

### 기록 조건은 상태코드가 아니라 "정본이 바뀌었는가"

- Gate 가 거부하면 200 이지만 `saved` 가 없다 → **기록 없음**.
- **502 partial envelope**(version 은 저장되고 분석 job 만 실패) → **기록한다**. 상태코드로
  판정했다면 실제로 일어난 저장을 빠뜨렸을 자리다.
- **auto-promote 의 503 partial 두 경로와는 다르게 처리했다**(그쪽은 여전히 미기록). 판단
  근거: accept 의 partial 은 **정본 version 하나**라 `exc.saved` 로 대상이 특정되고 한 행이
  정확하지만, auto-promote 의 partial 은 envelope 이 열거하는 **목록**이라 행 하나가 담을 수
  있는 것이 개수뿐이고 재시도와 대조되지 않는다. **판단 사안이며 대안(양쪽 다 기록)을 함께
  적어 둔다.**

### 뮤테이션 (2종 추가 — 누적 10종)

| # | 방향 | 적용한 diff | file | 실패한 셀 |
|---|---|---|---|---|
| N9 | under | 성공 경로의 `activity.record(...)` **블록 삭제** | `routers/writing.py` | `WritingAcceptApiTest::test_a_saved_accept_is_recorded_in_the_activity_log` (1) |
| N10 | **over** | `if result.saved is not None:` → `if True:`(Gate 거부에도 기록) | `routers/writing.py` | `::test_a_bounced_accept_is_not_recorded` · `::test_a_saved_accept_is_recorded_in_the_activity_log` (2) |

**★ N9 가 드러낸 가드의 한계 — 다음 사람이 알아야 한다**: 성공 경로의 record 를 지워도
**전수 가드(`test_every_logged_route_actually_records`)는 통과한다.** 같은 handler 안 502
분기에 `activity.record(` 가 남아 **소스 스캔이 만족되기 때문**이다. 즉 그 가드는 배선의
**존재**를 보지 **분기**를 보지 못한다 — 무는 것은 행위 셀이다. 한 handler 가 기록 분기를
여럿 가지면 **분기마다 행위 셀이 필요**하다.

### Verification

| 검사 | 결과 |
|---|---|
| 전수 회귀(알파, test-mongo ON) | `2246 passed / 4 skipped / 2324 subtests in 187s` → **보정 `2249 / 1 / 2324`** |
| 직전 `2247/1/2322` 대비 | **셀 +2 · subtest +2**(전수 가드가 logged 20 을 도는 subtest 증가) |
| operation | **77 무변** |
| 뮤테이션 | N9·N10 재실패 |

### 아직 안 한 것 (의도)

- **스택 재빌드·nginx 관통 한 홉** — 오너가 다음으로 미뤘다.
- **화면(활동 타임라인)** — 별도 슬라이스.
- **auto-promote 503 partial 기록** — 위 판단 사안.
- **A2=C 확장** — `ai_request` 13 행이 대상이고 A8 재검토가 함께 간다.

### Next steps (다음 작업자에게)

1. **미검증 구간 = 이 두 커밋**(accept 확장 + 문서). 앞의 Phase 9 본체는 검증 합격(`ad195e5`).
2. **오너 대기 두 건**: 스택 재빌드 후 `curl :5520/api/admin/users` = **401** 확인(Slice 2 관통
   한 홉) · dogfood 착수(GATE-1).
3. **자연스러운 다음 슬라이스는 화면**(활동 타임라인) — API 는 `GET /projects/{id}/activity`
   (operation 77)로 이미 서 있고 `schema.d.ts` 도 재생성돼 있다.
