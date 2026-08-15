# 2026-08-15 작업 로그 (알파)

## Goals

- **베타 → 알파 머신 전환.** 오너 문언: *"알파머신으로 돌아왔다. 지금까지 업데이트 된거
  빌드해보자. API는 아직이고 로컬로 빌드하면 돼."* → 외부 API override 는 쓰지 않고
  base compose 로 이미지를 갱신한다.
- 이어서 오너 문언: *"핸드오프랑 데일리로그 확인해서 코드쪽이나 뭐 이런걸로 내 개입없이
  작업할 수 있는게 있는지 확인해봐."* → **오너 결정이 필요 없는 작업**만 골라 진행한다.

## Completed work

### Task 1 — 알파 이미지 전량 재빌드 (코드 변경 0줄)

**전환 절차를 HANDOFF 대로 밟았다** — `git status --short`(공백) · `git log -1`(`9e2f1ef`) ·
`nvidia-smi`(**RTX 3060 12GB** = 알파 확정) · `docker compose ps` · 이미지 날짜.

**착수 전 실측 — 이 머신의 이미지가 260커밋 뒤처져 있었다.**

| 이미지 | 빌드 전 | 빌드 후 |
|---|---|---|
| `ai_writte_system-app` | **없음** | 새로 생성(510MB) — application·admin·worker·generation_worker **4개가 공유** |
| `ai_writte_system-frontend` | 13일 전 | 재빌드(49.1MB) |
| `ai_writte_system-gateway`·`-embedding` | 3주 전 | 재빌드 |
| `ai_writte_system-elasticsearch` | 4주 전 | **캐시 전량 히트** — 컨텍스트 무변이라 태그 그대로 |

**★ 이미지 태그 통합이 이 머신에 처음 반영됐다.** 종전 알파에는
`-application`/`-worker`/`-generation_worker` 세 태그가 따로 있었는데, compose 가
`image: ai_writte_system-app` 로 넷을 묶은 뒤로 그 태그들은 **아무도 참조하지 않는다.**
HANDOFF 부채 *"worker 이미지가 15일 뒤처진 채 PROJECT_PURGED drain 없이 돌고 있었다"*
가 구조적으로 닫히는 자리이며, 이 머신에서는 오늘 처음 실물이 됐다.

**★ `admin` 이미지는 이 머신에 아예 없었다** — Slice 2(2026-08-09)가 더한 여덟 번째
서비스이고, 알파의 마지막 빌드가 그보다 앞섰다.

**프론트 빌드 지표가 기준선과 전부 일치했다**(2026-08-13 베타 실측과 동일):
704 modules · 진입 421.78 kB · 관측 lazy 387.43 kB · AdminConsole 8.50 kB ·
CSS 30.79 kB. **260커밋이 쌓이는 동안 번들이 한 자리도 안 움직였다.**

**`.env` 가 이 머신에 없다.** 모든 compose 변수에 기본값이 있어 빌드·`config` 는 경고
없이 통과하지만(`docker compose config` rc=0), **in-stack llama 로 `long` 을 돌리기
전에는 `LLAMA_CTX_SIZE=16384` 가 필요하다**(HANDOFF 알파 함정). `.env.example:68` 이
이제 그 항목을 주석으로 들고 있다 — HANDOFF 가 *"`.env.example` 에 항목이 없다"* 고
적은 것은 그 사이 해소됐다.

### Task 2 — 2026-08-14 미검증 7커밋 독립 검증 (`33dbdd2`)

**미검증 목록을 인계 문구에서 베끼지 않고 git 에서 다시 유도했다**(어제 마감 메모가
경고한 그 함정). 마지막 검증 기록이 `docs/verifications/2026-08-13/` 이고 그 뒤 커밋이
**7개**다 — 어제 마감 메모는 *"2커밋"* 이라 적었는데 그것은 `8e57369` **이전에 쓴
문장**이라 이미 낡아 있었다. **같은 함정이 이틀 연속으로 걸렸다.**

기록: [`verifications/2026-08-15/deploy_externalization_axes_1_2.md`](../../verifications/2026-08-15/deploy_externalization_axes_1_2.md).
판정 **조건부 합격** — Blocking 2(아래 Issues).

**재현된 것**: 축 ① 짝 규칙은 코드 5자리를 직접 읽어 확인했고 **콜론 42곳 전수 대조에서
추가 위반 0건**이다. 축 ②③ 실측도 전부 재현됐다 — rc=1 + 한국어 사유 · 서비스
**10 → 7** · base diff 무변 · `:?` 셀 **3 SUBFAILED**.

### Task 3 — backend 전수 회귀, 새 기준선 (알파 실측)

**★ 돌리기 전에 예상값을 세우고 맞췄다.**

| 기여분 | 셀 | subtest |
|---|---|---|
| 축 ① `ExternalBackendEnvTest` | +4 | +30 |
| 축 ① `InStackLlamaOverrideTest` | +2 | 0 |
| 축 ② `ExternalOverrideTest` | +4 | +18 |
| 축 ② `test_compose_exposure` 새 셀 | +1 | 0 |
| Task 2 검증 기록(242 → 243) | 0 | +1 |
| **합** | **+11** | **+49** |

예상 **2281 / 4 / 2515**(알파 원시), 실측 **2281 passed / 4 skipped / 2515 subtests**,
**192.76초**. 베타 보정값(= `elasticsearch` 패키지 3건을 되돌린 값)은 **2284 / 1 / 2515**.

**★ 어제 work_log 의 예상값 *"셀 +6 · subtest +30"* 은 그 시점에서는 정확했다** —
측정해 보니 축 ①이 정확히 6셀 / 30 subtests 다. 낡은 것은 예측이 아니라 **범위**이며,
`8e57369`(축 ②)가 그 뒤에 5셀 / 18 을 더 얹었다. 예상값을 물려받을 때는 **그 값이
어느 커밋까지를 세었는지**를 함께 본다.

알파가 베타보다 **4.8배 빠르다**(192초 ↔ 922초). skip 4 = live Chroma 1(호스트에서
구조적으로 항상 skip) + `elasticsearch` 패키지 부재 3.

## Issues found

**두 발견 모두 같은 변수(`LLAMA_BASE_URL`)에서 나왔고, 축 ①의 판단이 옳았다는 것과는
별개다.** 상세·근거·file:line 은 검증 기록에 있고 여기서는 성질만 남긴다.

**B1 — 계약이 파일이 아니라 변수에 걸리는데, 셀은 파일에 걸려 있었다.**

- *문제*: base [`docker-compose.yml:202`](../../../docker-compose.yml#L202) 의
  `LLAMA_BASE_URL` 표기를 잠그는 셀이 **0건**이다.
- *원인*: `InStackLlamaOverrideTest` 가 `docker-compose.llama.yml` 만 읽고,
  `ExternalBackendEnvTest` 는 base 를 읽지만 `_EXTERNALIZABLE`(백엔드 3종)만 순회한다.
  `LLAMA_BASE_URL` 은 어느 목록에도 없다.
- *실증*: **문자 그대로 같은 diff** 를 두 파일에 넣었더니 llama override 에서는 2셀이
  물고 base 에서는 **0셀**이 물었다(M-A ↔ M-B).
- *왜 중요한가*: 어제 work_log 가 경고한 *"이 파일의 다른 40여 항목이 전부 콜론이라
  표기 통일이 자연스러워 보인다"* 의 **그 파일이 base** 이고, base gateway 는 override
  없이도 늘 뜨는 **기본 기동 경로**다. 위험이 큰 쪽이 안 잠겼다.
- *상태*: **미해소.** 검증자는 결함을 조용히 고치지 않는다(`verification.md`).

**B2 — 문서가 실제 동작보다 강하게 약속한다.**

- *문제*: [`.env.example:96-109`](../../../.env.example) 가 *"값이 없으면 기동을
  거부한다"* 를 적고 주소 다섯을 나열하는데, `LLAMA_BASE_URL` 은 거부하지 않는다.
- *대비*: 같은 목록의 `EXTERNAL_CHROMA_PORT` 는 *"생략하면 8000"* 이라고 **자기 예외를
  밝혔다.** 즉 누락이 대비되는 자리다.
- *결과*: 배포 서버에서 이 값을 빠뜨리면 조용히 `host.docker.internal:9080` 으로
  떨어져 **파일 자신이 배격한 실패 형태**(뜨지도 않는 자리를 가리키고 연결 실패로만
  드러남)가 된다.
- *상태*: **오너/구현자 결정 대기.** 해소 방향 둘 다 타당하다 — (a) external override
  에서 gateway `LLAMA_BASE_URL` 을 `:?` 로 필수화(배포 서버가 호스트 llama 를 쓰는
  선택지를 배제한다) · (b) `.env.example` 이 예외를 명시(문서가 실제를 반영하되
  fail-fast 는 셋에만 남는다).

## Mutation testing

커밋된 트리(HEAD `9e2f1ef`) 위에서 수행했고, **뮤테이션 사이마다 `git status --short`
를 찍어 4회 전부 공백**을 확인했다. 트리가 clean 이므로 `git checkout -- <path>` 분기.

| # | 적용한 diff | 자리 | 재실패한 셀 |
|---|---|---|---|
| M-A | `${LLAMA_BASE_URL:-http://host.docker.internal:9080}` → `${LLAMA_BASE_URL-…}` | [`docker-compose.yml:202`](../../../docker-compose.yml#L202) | **없음** — compose 를 읽는 가드 전부(`test_compose_backend_env`·`test_compose_exposure`·`test_admin_surface_separation`) **27 passed / 135 subtests 전원 green** |
| M-B | `${LLAMA_BASE_URL:-http://llama:9080}` → `${LLAMA_BASE_URL-…}` (**M-A 와 문자 그대로 같은 변경**) | [`docker-compose.llama.yml:76`](../../../docker-compose.llama.yml#L76) | `test_an_empty_value_falls_back_to_the_in_stack_model` · `test_an_explicit_base_url_wins_over_the_in_stack_model` |
| M-C | `${ELASTICSEARCH_URL:?…}` → `${ELASTICSEARCH_URL:-http://elasticsearch:9200}` (3자리) | `docker-compose.external.yml` | `test_external_addresses_are_required_not_defaulted` — **3 SUBFAILED**(application·worker·generation_worker) |
| M-D | (복원 후 기준선 재측정) | — | 17 passed / 55 subtests 복귀 |

**M-A ↔ M-B 의 대비가 이 검증의 산출물이다** — 같은 변수·같은 서비스·같은 코드 읽기·
같은 diff 인데 셀 수가 2 와 0 으로 갈린다. 뮤테이션을 **한 자리에만** 넣었으면
"가드가 문다" 로 끝났을 자리다.

**★ M-C 가 `grep FAILED` 사각지대를 실제로 재현했다.** `pytest-subtests` 는
`SUBFAILED` 로 찍으므로 `^FAILED` 필터였다면 **아무것도 안 나와** "가드가 안 물었다"
로 오독했을 것이다. 요약 줄(`3 failed`)로 읽었다 — `verification.md` 가 경고한 그대로다.

## Decisions

**D-2026-08-15-a. 오너 개입이 필요 없는 작업을 셋으로 추려 오너가 순서를 골랐다.**

- *결정*: 오너가 **①독립 검증 → ②전수 회귀** 순서를 선택했다.
- *후보와 제외 사유*: HANDOFF·데일리로그를 훑어 오너 결정이 **선행하지 않는** 것만
  골랐다 — ① 미검증 7커밋 검증 · ② 전수 회귀 재측정 · ③ `AUTH_SESSION_TTL_HOURS`
  회귀 가드 2셀(계약이 2026-07-27 에 보안 근거까지 달아 확정돼 새 결정이 필요 없다).
  제외한 것: 리랭커 슬라이스(**승인 전 코드 금지**) · dogfood 착수(GATE-1) ·
  H2 API 문서 제품명(**착수 전 오너 설명 필수**) · Phase 10 육안 확인(오너 눈이 판단
  자리) · 타이포 리터럴 이관(트리거 = 그 화면을 다시 그릴 때) · `timeline_demo` 정리.
- *근거*: 검증을 먼저 두면 결함이 나왔을 때 회귀 기준선이 어차피 달라진다. 순서가
  이쪽이라야 기준선을 두 번 재지 않는다.
- *결과*: ③은 착수하지 않았다 — 검증에서 Blocking 2 가 나와 그 처리 방향이 먼저다.

## Next steps

- **★ B1·B2 처리 방향 결정.** B1 은 셀 하나를 더하면 닫히고(제안: `_EXTERNALIZABLE`
  의 반대 방향 목록 `_COLON_REQUIRED = {"LLAMA_BASE_URL": …}` 을 두어 base·llama
  **두 파일에서 함께** 단정 — 세 번째 파일이 생겨도 규칙이 따라간다), **B2 는 오너
  결정이 먼저**다(위 (a)/(b)).
- **착수 가능한 채로 남은 것**: `AUTH_SESSION_TTL_HOURS` 회귀 가드 2셀(추적 부채).
- **여전히 오너 대기**: 리랭커 브리프 결정 1~4 · dogfood 착수(GATE-1) · H2 · Phase 10
  끝 육안 확인.
- **알파 스택은 아직 안 띄웠다** — 이미지만 갱신했다. 띄우려면
  `docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d` 이고,
  `long` 을 돌리기 전에 `.env` 에 `LLAMA_CTX_SIZE=16384` 를 넣는다.
