# 2026-08-23 작업 로그 (알파)

> **[세션 3] 결정 대기 ③ 해소 + 배포 서버 동기화 (세부 미기재 — 오너 지시).**
> 오너 확인: *"아 상관없네 그러면. 도메인에서 제공하고있어서 필요없어."* — 서비스가
> 도메인(HTTPS) 경유로 제공되므로 **Secure 쿠키 충돌이 애초에 성립하지 않는다**.
> `AUTH_COOKIE_SECURE` 기본값 `true`(fail-closed)는 그대로. 오너가 남긴 후속 과제:
> **리랭커 없는 배치에서 임베딩만으로 end-to-end 동작 확인.**
> 배포 서버(접속 정보·주소·디렉토리는 기록하지 않는다)에 알파 HEAD를 동기화해
> 재빌드·재기동했고 — 정상 라우트 200, docs 4경로 404, 가입 라우트 422·관리자
> 라우트 401(가드)까지 전부 검증 통과. 서버 전용 파일(override·`.env`)은 무결 보존.

> **[세션 2] `/docs`·`/openapi.json` 비공개 이행 — 오너 결정 대기 ② 해소 (SoT v1.7.98).**
> 오너 결정: *"api 쪽과 docs는 공개되면 안되지."* 실측으로 노출 6곳(8520 직접 3 +
> nginx 경유 3)을 확인하고 `create_app`의 `FastAPI(docs_url=None, redoc_url=None,
> openapi_url=None)` 한 곳으로 닫았다 — 세 factory(제품·관리자·합집합)가 한 본문이라
> 한 번에 폐쇄(v1.7.91 구조가 여기서도 일했다). 관리자 앱은 nginx prefix 구조상
> 애초에 노출 없음(실측 404). **선행 확인 — HTTP 소비자 0건**: 프론트 TS 계약은
> `scripts/dump_openapi.py`(import 방식 `create_app().openapi()`), 테스트 5파일도
> 전부 `.openapi()` 직접 호출. 커밋 `14e9904`.
>
> - **가드**: `test_admin_surface_separation.py` 신규 1셀 — 세 앱의 네 docs 경로
>   (`/docs`·`/docs/oauth2-redirect`·`/redoc`·`/openapi.json`) 부재 +
>   `/health`·제품 `/auth/login` 생존(양방향). docs 라우트는 `APIRoute`가 아니라
>   일반 `Route`라 경로 집합으로 직접 잰다.
> - **뮤테이션**: FastAPI 기본값 복원(세 줄 제거) → 신규 셀 재실패 ✓ → 복구 ✓.
> - **회귀**: 전수 **2482 passed / 0 failed / skip 4** — 검산: 2480(08-22 세션 5) +
>   1(H-1 수리 셀, 세션 6) + 1(오늘) = 2482. 일치.
> - **실관통**(app 이미지 재빌드·4서비스 재생성 후): 6경로 전부 **404**,
>   `/health` 200 양쪽·프론트 200·`/projects` 401·로그인/가입 라우트 생존.
> - **함정(밟음)**: `docker compose build app` → 서비스명은 `application`(이미지
>   태그만 `ai_writte_system-app`). 빌드 없이 `up`하면 옛 이미지로 올라 차단이
>   안 보인다.

> **[세션 1] 오너 admin 계정 생성 + 시드 정리 — HANDOFF 오너 결정 대기 ① 이행.**
> 08-22 보안 점검 발견 ②(활성 admin 시드 계정·오너 본인 계정 부재)를 닫았다.
> 오너가 계정명 `owner-account`를 지정(아래 D-2026-08-23-a). **비밀번호는 이 문서 어디에도
> 없다** — 임시값은 채팅으로만 전달했고, 최종 비밀번호는 오너가 첫 로그인에서 직접
> 선택한다(C-6 1회용). backend·frontend 프로덕션 코드 변경 **0줄**.

## Goals

- HANDOFF "오너 결정 대기 ①": 오너 admin 계정 생성 → 시드·스모크·검증 계정 전부 비활성화.
- 순서 계약 준수: **오너 계정 먼저 → 시드 비활성화**(마지막 활성 관리자 보호 F2).

## Completed work

### Task 1 — 스택 사고 복구 (커밋 없음, 운영 조치)

착수 시 핵심 6컨테이너(mongo·application·gateway·chroma·elasticsearch·embedding)가
**11분 전 Exit 255**로 죽어 있었고 worker·admin만 mongo 없이 재시작 루프. 08-22 알파
세션 2와 같은 WSL/도커 사고 패턴이다. `docker compose up -d`로 전체 재기동 —
**healthy 8 + 워커 2** 정상 상태 복구.

### Task 2 — 오너 admin 계정 `owner-account` 생성

`create_user.py`(부트스트랩 스크립트)로 생성 — 관리자 quota 무제한 정책 행 동반(8.4 W1).
비밀번호는 env(`AUTH_BOOTSTRAP_PASSWORD`) 전달, argv·문서 기록 0건.

### Task 3 — 시드 계정 6개 비활성화 (admin API 실관통)

`owner-account` 첫 로그인(C-6 교체로 세션 확보) 뒤 `POST /admin/users/{id}/deactivate`로
6개 비활성화, 전부 200:

| 계정 | 출처 |
|---|---|
| `visual_demo`(admin) | 08-21 육안 확인용 시드 |
| `visual_user` | 〃 |
| `smoke_admin`(admin) | 08-22 승인제 가입 실관통 |
| `bob` | 〃 (활성) |
| `carol` | 〃 (거절) |
| `verif_0822` | 08-22 독립 검증 잔여 (pending) |

**정정**: HANDOFF·08-22 work_log는 잔여 **7개**로 적었으나 실측 **6개** — `verif2_0822`가
DB에 없다(검증 문서에는 생성 커맨드가 있으나 그 뒤 정리된 것으로 보임). 목록은 DB 실측이
정본이므로 6개로 진행.

### Task 4 — `owner-account` 재1회용화 + 검증

비활성화 후 `owner-account`를 다시 1회용 상태로 되돌렸다 — 정규 저장소 API로
(`MongoUserRepository` + `dataclasses.replace(must_change_password=True)` → `replace()`).
오너는 전달받은 임시 비밀번호로 로그인하면 **409 → `new_password`**를 요구받고,
자기 비밀번호를 넣는 순간 임시값은 무효화된다. 이 세션이 아는 값(P1 부트스트랩·P2 세션
확보용)은 그 교체 시점에 모두 죽는다.

**검증(전부 실측)**:
- Mongo users: **활성 계정 = `owner-account` 유일**(is_admin·1회용 대기), 6개 전부 is_active=false.
- `owner-account` + 임시 비밀번호(new_password 없이) → **409** (C-6).
- 계정 비활성화는 admin 감사 미기록이 **설계상 정확**(`routers/admin.py:124` 주석 —
  감사 컬렉션은 프로젝트 내용 예외(purge·grants)만 커버, 확장은 별도 결정).

## Issues found

- **admin API 도달 경로 함정을 직접 밟았다** — 8520(제품 앱)에 `/admin/...`를 치면
  **404**(route 자체가 없음). nginx 5520 경유 `/api/admin/...`만 도달한다. HANDOFF
  "배포되는 앱이 이제 둘이다" 항목의 실증 사례. 세션 취득도 nginx 경유 `/api/auth/login`.
- `docker exec -e VAR="$VAR"`로 **호스트 셸에 없는 변수를 덮어쓰면 빈 값**이 들어가
  pymongo `ConfigurationError` — 컨테이너에 이미 설정된 env는 생략해야 한다.

## Decisions

### D-2026-08-23-d — 결정 대기 ③: 해당 없음 — 도메인(HTTPS) 제공 (오너)

Secure 쿠키×http 충돌 항목은 **오너 환경에서 성립하지 않음**으로 종결. 근거 원문:
*"상관없네 그러면. 도메인에서 제공하고있어서 필요없어."* — HTTPS 경유 제공이므로
`Secure` 쿠키가 정상 동작한다. 따라서 `AUTH_COOKIE_SECURE=false`(의도적 약화)는
쓰지 않고 기본값 `true` 유지. nginx 보안 헤더(X-Frame-Options 등)는 별도 권고 사항으로
남는다(결정이 필요해지면 명시적으로).

### D-2026-08-23-c — docs 비공개, env 토글 없음 (오너 + 구현자)

오너: *"api 쪽과 docs는 공개되면 안되지."* — `/docs`·`/redoc`·`/openapi.json` 전부
비공개. 구현자 판단으로 **env 토글 없이 상시 차단** — 정당한 소비자가 전부 import
방식(dump 스크립트·테스트)이라 런타임 서빙의 수요가 0이고, 공개가 다시 필요해지면
그때 명시적 결정으로 연다(조용한 env 폴백이 아니라).

### D-2026-08-23-a — 오너 계정명 = `owner-account` (오너)

오너 질문 *"admin 계정을 매번 따로 만들어야하는거야? 어드민 계정이니까 그게 안전하겠지?"*에
대해 먼저 답한 뒤 진행: 계정은 **머신(=Mongo 볼륨)마다 별도**라 쓰는 머신마다 하나씩이 필요
(알파·홈서버·베타 각각). 세션마다 다시 만드는 것은 아니고 한 번 만들면 영구. 안전장치는
env 전달(히스토리·ps 무노출)·Argon2id 해시만 저장·C-6 1회용. 계정명 `owner-account` 확정.

### D-2026-08-23-b — 시드 정리는 비활성화(파기 아님) (구현자, 기존 계약 준수)

06-22 시드의 원래 정리 예정("정리는 파기·비활성화로") 중 **비활성화**를 택했다 —
계정 행은 남겨 audit·이력 추적성을 유지하고, 재활성화 API가 없어 단방향인 것도 계약(D6).
`visual_demo`·`visual_user`는 status 필드 없는 구형 행(1-a 이전 생성)이나 비활성화 무관.

## Next steps

- **오너**: `http://localhost:5520`에서 `owner-account` + 전달받은 임시 비밀번호로 로그인 →
  409 안내에 따라 새 비밀번호(12자 이상) 설정. 그때 임시값은 무효화된다.
- **오너 결정 대기 셋 전부 해소**(세션 1·2·3). 남은 부채: nginx 보안 헤더(권고)·
  SoT 부채(KEY_REJECTED·폴백 정책)·폴백 슬라이스 독립 검증·임베딩만 end-to-end 확인(오너).
- 폴백 슬라이스(`d8ba6e7…`) 독립 검증은 여전히 대기.
