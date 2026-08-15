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

**착수 전 실측 — 이 머신의 이미지가 215커밋 뒤처져 있었다**(이미지 시각 08-02 기준.
초판의 "260" 은 `--since="14 days ago"` 결과이고 **앵커를 안 밝힌 값이었다** — 감사 F5).

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
CSS 30.79 kB. **215커밋이 쌓이는 동안 번들이 한 자리도 안 움직였다.**

**`.env` 가 이 머신에 없다.** 모든 compose 변수에 기본값이 있어 빌드·`config` 는 경고
없이 통과하지만(`docker compose config` rc=0), **in-stack llama 로 `long` 을 돌리기
전에는 `LLAMA_CTX_SIZE=16384` 가 필요하다**(HANDOFF 알파 함정). `.env.example:68` 이
이제 그 항목을 주석으로 들고 있다 — HANDOFF 가 *"`.env.example` 에 항목이 없다"* 고
적은 것은 그 사이 해소됐다.

### Task 2 — 미검증 구간 독립 검증 (`33dbdd2` + 추기로 9커밋)

**미검증 목록을 인계 문구에서 베끼지 않고 git 에서 다시 유도했다**(어제 마감 메모가
경고한 그 함정). 어제 마감 메모는 *"2커밋"* 이라 적었는데 그것은 `8e57369` **이전에 쓴
문장**이라 이미 낡아 있었고, git 에서 유도하니 **08-14 만 7커밋**이었다.

**★ 그런데 그 산정도 틀렸다(감사 F1 · 아래 §독립 감사).** 커밋 목록은 git 에서 유도했지만
**시작 지점을 날짜 디렉터리(`docs/verifications/2026-08-13/` 이 있으니 그날은 검증됐다)로
추정**했다 — 절반만 실행된 규칙이다. 진짜 앵커인 **마지막 검증 기록 커밋 `c08b0c2`**
(08-13 11:40) 기준으로는 미검증이 **9커밋**이었고, `6352121`·`3b71eac`(그날 오후, docs-only)
이 사각지대였다. **추기 검증으로 닫았다**(둘 다 Blocking 0 — 아래 §감사 반영).

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
  에서 gateway `LLAMA_BASE_URL` 을 `:?` 로 필수화 · (b) `.env.example` 이 예외를
  명시(문서가 실제를 반영하되 fail-fast 는 셋에만 남는다).
- **★ (a)의 비용 서술 정정(감사 F2)**: 초판은 (a)가 *"배포 서버가 호스트 llama 를 쓰는
  선택지를 배제한다"* 고 적었으나 **과대 서술이다.** `${VAR:?}` 는 값이 있으면 그 값을
  그대로 쓰므로 필수화 뒤에도 주소를 명시하면 호스트 llama 를 쓴다 — **사라지는 것은
  선택지가 아니라 암묵적 폴백이고, 실제 비용은 `.env` 에 한 줄이다.** 두 선택지의 무게가
  초판이 그린 것보다 훨씬 가깝다.

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

---

## 독립 감사 — 두 번째 세션 (오너 요청: "검증하고 의심하고 또 의심")

오너가 오늘 두 커밋(`33dbdd2`·`cfc7374`)과 세션 보고 전문의 독립 재검증을 요청했다(전수 재실행·
셀 수 산술은 오너 지시로 범위 밖). 기록:
[`verifications/2026-08-15/alpha_day_slice_audit.md`](../../verifications/2026-08-15/alpha_day_slice_audit.md).
판정 **조건부 합격 — F1 정정 조건**.

**재현된 것(전부)**: B1/B2 의 구조·계약·실증 — 뮤테이션 M-A′(base:202 → dash)는 **0셀**
(27 passed / 135 subtests 전원 green), M-B′(문자 그대로 같은 diff 를 [`llama.yml:76`](
../../../docker-compose.llama.yml#L76) 에)는 **2셀**(동일 셀 2개) — 대상 검증 기록과 수치까지 동일.
축 ③(rc=1·서비스 10 → 7) · "8e57369 base 무변"(파일 목록으로 증명) · 증분 범위 프로덕션 0줄
(services/frontend diff 공백) · 재빌드 실물(app 태그 오늘 18:19 생성 · 옛 태그 3종 잔존 · ES 태그
07-12 무변 = 캐시 히트) · `.env` 부재 · AUTH_SESSION_TTL_HOURS 계약(2026-07-27 "무한 세션" 근거 ·
tests 0건) · 어제 예상값 +6셀/+30의 축 ① 귀속(테스트 구조 유도: 3서비스×3변수×3셀+3=30).

**F1(Blocking) — "미검증 7커밋" 산정이 틀렸고 "오늘 기준 미검증 0"은 거짓이다.** 마지막 검증
커밋은 `c08b0c2`(08-13 11:40)이고 그 뒤(오늘 검증 개시 전) 10커밋 — 검증 세션 자기 반영
`d7e52c8` 제외 시 미검증은 **9커밋**이다. 이 검증은 08-14의 7커밋만 다뤘고 **`6352121`(08-13
12:09)·`3b71eac`(12:44)이 어느 검증에도 안 걸렸다**(둘 다 docs-only — 6352121의 기준선 수치는
오늘 예측 체인이, 3b71eac의 부채 등재는 어제·오늘 검증이 교차 검증했다). "7"의 앵커는 검증
커버리지가 아니라 **08-14 세션 시작 경계**다 — 08-13 마감의 "미검증 0"(11:49 문장)이 뒤이은 두
커밋에 낡아 있었던 것과 같은 병의 세 번째 변형. 정정 경로 (a) 추기 검증 / (b) 명시적 등재 +
문장 정정 — **오너 선택 대기**.

**비차단**: F2 — B2 옵션 (a)의 "호스트 llama 선택지 배제"는 과대(`:?` 후에도 주소를 명시하면
사용 가능, 사라지는 것은 암묵적 폴백 — **B2 결정 전 정정 권고**) · F3 "compose 읽는 가드 전부"는
4파일 중 3파일(`test_core_sot_mongo`는 test.yml만 언급, 결론 불변) · F4 "subtest +49 전부 가드"는
+1이 검증 기록 자리 · F5 "260커밋" 실측 ≈255. **이 감사가 안 돌린 것**: 알파 전수 원시값 ·
프론트 빌드 지표.

뮤테이션 2종 재실행 — 커밋된 트리(HEAD `cfc7374`) 위에서, 뮤테이션 전후 `git status --short`
공백 확인, 복원은 저장소 루트 절대경로(cwd 함정). 이 기록으로 검증 기록은 243 → **244건** —
README 2곳·인덱스 판정 분포를 함께 갱신했다.

---

## D-2026-08-16-a. B2 는 선택지가 아니라 **일반 규칙**으로 닫혔다 (오너)

- *오너 문언*: *"1. env에 외부 API가 있으면 그거 사용, 2. 그게 없다면 내부 LLM 모델 다운로드
  시도, 3. 모델 다운로드가 에러나 혹은 시도되지 못했다면 당연히 빌드 실패."*
- *★ 오너 질문이 짚은 것*: *"LLM 서버가 없다는 건 빌드할 때 선택하지 못했다는 것?"* — **반은
  맞다.** in-stack LLM 여부는 빌드 옵션이 아니라 **어떤 override 를 얹느냐**로 갈리고,
  모델은 빌드가 아니라 **첫 기동 때** 받는다(`llama` 는 pull 이미지이며 `-hf` 가 런타임
  다운로드다). 그래서 3번의 실패 지점은 `build` 가 아니라 **기동**이다.
- *실측한 것 — 규칙 ①②③은 알파에서 이미 돌고 있었다*: `llama.yml` 이
  `${LLAMA_BASE_URL:-http://llama:9080}` 라 ① env 우선 · ② 없으면 in-stack llama 가 받고 ·
  ③ 못 받으면 healthcheck 실패 → gateway 가 `depends_on: service_healthy` 에 걸려 안 뜬다.
- *결함이 있던 자리는 배포 override 하나*: 그 구성에는 llama 서비스가 **없어서 ②가 구조적으로
  불가능**한데, base 의 콜론 폴백이 살아 있어 ③ 대신 **자기 서버의 9080**(아무것도 없는 자리)을
  조용히 가리켰다. 규칙을 그대로 적용하면 **③이 강제**되므로 B2 는 (a)로 결정된다 —
  선택지를 물을 일이 아니었다.
- *시행*: [`docker-compose.external.yml`](../../../docker-compose.external.yml) gateway 에
  `LLAMA_BASE_URL: "${LLAMA_BASE_URL:?외부 LLM API 주소가 필요하다 (OpenAI 호환 /v1/chat/completions)}"`.
  **base·llama override 는 한 줄도 안 건드렸다.**
- *실측(전후)*:

  | 확인 | 결과 |
  |---|---|
  | 배포 override · 주소 없음 | **rc=1** + 한국어 사유(`required variable LLAMA_BASE_URL is missing a value: 외부 LLM API 주소가 필요하다 …`) |
  | 배포 override · 넷 다 지정 | **rc=0** |
  | 배포 override · 호스트 llama 명시 | `LLAMA_BASE_URL: http://host.docker.internal:9080` — **여전히 쓸 수 있다**(감사 F2 가 잡은 "선택지 배제" 서술이 과대였음의 실측) |
  | base 단독 · llama override | 둘 다 **rc=0**, 알파 주소 `http://llama:9080` 무변 |

- *가드 2셀(양방향)*: `test_the_llm_address_is_required_because_nothing_can_fall_back`(under-strict —
  필수화를 되돌리면 실패) · `test_the_base_file_still_falls_back_so_dev_machines_keep_booting`
  (over-strict — 이 필수화를 base 에 '통일' 하면 개발 머신이 안 뜬다).
- *★ 부수 효과 — B1 이 함께 닫혔다*: over-strict 셀이 base `docker-compose.yml:202` 의 콜론
  형태를 단정하므로, 검증 B1 이 지적한 *"그 자리를 잠그는 셀 0건"* 이 해소된다. **남는 한계**:
  잠그는 방식이 "이 두 파일" 이라 **세 번째 compose 파일에는 따라가지 않는다**(원 제안이던
  `_COLON_REQUIRED` 일반화는 미착수).
- *F1 관련*: 오너 지시는 *"장부만 고쳐 … 그냥 지나친 거는 나중에 잡던지"* 였으나, 그 시점에
  **이미 `7326d9e` 가 추기 검증으로 닫아 둔 상태**였다(6352121·3b71eac 둘 다 Blocking 0).
  장부가 이미 사실과 맞아 **추가 조치 없음.**

### 감사 반영 — 지적 다섯을 전부 처리했다 (오너: *"검증기록 확인해서 보강할 부분 있으면 보강해줘"*)

**지적을 그대로 옮기지 않고 전부 1차 자료로 재확인한 뒤 반영했다**(다른 세션의 보고도
검증 대상이라는 이 저장소의 기본 자세). **다섯 다 사실이었다.**

**F1 — 정정 경로 (a)(추기 검증)를 실행해 실제로 닫았다.** 사각지대였던 두 커밋을
[검증 기록 §추기 A1](../../verifications/2026-08-15/deploy_externalization_axes_1_2.md) 에서
검증했고 **둘 다 Blocking 0** 이다.

- **`6352121`(기준선 `2273/1/2466`) — 역산으로 검산했다.** 오늘 알파 실측
  `2281/4/2515`(베타 보정 `2284/1/2515`)에서 오늘 증분을 빼면 **2284 − 11 = 2273** ·
  **2515 − 49 = 2466** 으로 세 자리가 맞는다. 그 커밋의 근거 두 자리도 재현된다 —
  `test_design_token_provenance.py` **5 passed / 90 subtests** · 검증 기록 **244건**
  (= 주장 시점 242 + 오늘 2). **★ 오늘의 예측 체인이 이 값을 입력으로 삼아 맞았다는 것이
  가장 강한 교차 검증이다** — 이 값이 틀렸다면 오늘 예상이 맞을 수 없었다.
- **`3b71eac`(배포 외부화 지형 등재) — 코드로 확인했고, 추기 중 실질이 가장 컸다.**
  아직 아무도 코드로 대조하지 않은 위험 서술이었다. **★ 축 ③ 의 진짜 위험은 "안 뜨는
  것"이 아니라 "조용히 통과하는 것"이다**: `/props`·`/tokenize`·`/apply-template` 셋 다
  예외를 삼켜 `None` 을 반환하고([`client.py:75`](../../../services/llm_gateway/app/client.py#L75)·
  [`:224`](../../../services/llm_gateway/app/client.py#L224)·[`:262`](../../../services/llm_gateway/app/client.py#L262)),
  **262 줄 주석이 그 자리에서 말한다 — `# 셀 수 없으면 판정하지 않는다(통과)`.** 대체
  경로인 호출자 추정은 [`:237-238`](../../../services/llm_gateway/app/client.py#L237) 이
  **과소평가 방향(가드가 늦게 걸린다)** 이라고 명시한다. 오너가 외부 API 를 주는 날
  **"뜨긴 뜬다"로 끝내면 안 되는 이유**가 이것이며 HANDOFF 마감 메모에 옮겼다.

**★ 남은 규칙**: **미검증 구간의 시작점은 `docs/verifications/<날짜>/` 디렉터리가 아니라
마지막 검증 기록 *커밋* 이다.** 날짜 디렉터리는 *그날 쓰인 기록*을 뜻하지 그날 커밋 전부가
검증됐다는 뜻이 아니다 — 같은 계열 오류가 이것으로 **세 번째**다(08-13 "다섯"→셋 ·
08-14 "2"→7 · 오늘 "7"→9). **셋 다 다음 세션의 재측정이 잡았다.**

**F2 — 세 자리 전부 정정했다**(검증 기록 §추기 A2 · 위 Issues B2 · HANDOFF 오너 결정
항목). **오너가 B2 를 고르기 전에 읽는 자리가 HANDOFF 라 그곳을 반드시 포함시켰다.**

**F3~F5 — 검증 기록 §추기 A3 과 위 본문에서 정정했다**("compose 읽는 가드 전부" →
**base 를 읽는 3파일**(넷째 `test_core_sot_mongo` 는 `docker-compose.test.yml` 만 말한다.
**M-A 의 0셀 결론은 불변**) · "subtest +49 전부 신규 가드" → **+48 가드 / +1 검증 기록** ·
"260커밋" → **215커밋**(앵커 명시)).

**판정은 `조건부 합격` 유지이고 조건은 여전히 B1·B2 다** — F1 은 닫혔고 나머지는 서술
정정이다. **B1·B2 는 두 세션이 독립적으로 같은 결론에 도달했다**(감사 세션이 뮤테이션까지
재현해 수치가 동일했다).
