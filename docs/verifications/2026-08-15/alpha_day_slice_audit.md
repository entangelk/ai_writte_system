# 2026-08-15 작업 세션 산출물 감사 — 재빌드 · 미검증 검증 · 새 기준선 기록

## Subject metadata

- **날짜**: 2026-08-15 (알파, 두 번째 세션)
- **요청자**: 오너 (*"작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? 전수 회귀는 너무
  오래걸리니까 카운팅에 대한거는 신경쓰지 말고."* — 전수 재실행·셀 수 산술은 범위 밖)
- **검증자**: 이 세션(감사 대상 커밋 `33dbdd2`·`cfc7374`를 만들지 않았다)
- **대상**: 위 두 커밋과 그 세션이 오너에게 보고한 주장 전문 — ① 알파 이미지 재빌드 ② 2026-08-14
  미검증 7커밋 독립 검증(조건부 합격·Blocking B1/B2) ③ 전수 회귀 새 기준선 기록 ④ 잔여 판단
  (B1 무결정 마감 가능 · B2 결정 필요 · AUTH_SESSION_TTL_HOURS 착수 가능)
- **정본 참조**: [`guides/verification.md`](../../guides/verification.md) · CLAUDE.md §5·§6 ·
  HANDOFF §Next Tasks 마감메모 규칙("미검증 목록을 인계 문구에서 베끼지 말고 git 에서 유도" —
  HANDOFF 2026-08-13 마감메모에 명문화) · 대상 검증 기록
  [`deploy_externalization_axes_1_2.md`](2026-08-15/deploy_externalization_axes_1_2.md)
- **작업 트리 상태**: HEAD `cfc7374`, clean(시작·종료 모두 `git status --short` 공백)

## Scope

1. 트리·커밋 존재(clean, 오늘 2커밋)
2. B1/B2의 실체 — 구조(테스트 직독) · 계약(표기 규칙의 스코프) · 실증(뮤테이션 재현)
3. **미검증 산정** — "마지막 검증 기록 뒤 7커밋"·"오늘 기준 미검증 0" 주장의 git 산술
4. 기록 충실성 — work_log·HANDOFF·커밋 메시지가 측정·git 사실과 일치하는지
5. 부수 실측 주장 — 재빌드(app 태그·옛 태그·ES 캐시·`.env` 부재) · "backend 프로덕션 0줄" ·
   "8e57369 base 무변" · 어제 예상값(+6셀/+30)의 축 ① 귀속
6. 잔여 판단 주장 — B1 오너 불필요 · B2 옵션 (a)/(b) 프레이밍 · AUTH_SESSION_TTL_HOURS 계약

## Methodology

- git: `git status --short` · `git log --format='%h %ad %cd %s'` · `git rev-list --count c08b0c2..33dbdd2` ·
  `git show --stat`(대상 커밋 전부) · `git diff --name-only 6352121..cfc7374 -- services/ frontend/` ·
  `git show <ver>:HANDOFF.md | grep -n 커밋`(마감메모 원문 대조)
- 구조 직독: [`tests/test_compose_backend_env.py`](../../../tests/test_compose_backend_env.py) 전문 ·
  [`docker-compose.yml:195-214`](../../../docker-compose.yml#L195) ·
  [`docker-compose.llama.yml`](../../../docker-compose.llama.yml) 전문 ·
  [`docker-compose.external.yml`](../../../docker-compose.external.yml) 전문 ·
  [`.env.example:47-115`](../../../.env.example) ·
  [`llm_gateway/main.py:43-69`](../../../services/llm_gateway/app/main.py#L43)
- 실측 재현: `grep -cE '\$\{[A-Z_]+-' docker-compose.yml` 등 · `docker compose … config`(rc·`--services`) ·
  `docker images --format` · `ls .env`
- 뮤테이션 2종 재실행(M-A′·M-B′ — 대상 검증 기록의 M-A/M-B 와 문자 그대로 같은 diff).
  트리 clean → `git checkout --` 분기, 뮤테이션 전후로 `git status --short` 공백 확인, 복원 명령은
  저장소 루트 절대경로에서.
- 가드 스윕: `grep -rln 'docker-compose' tests/*.py` · `grep -rn 'LLAMA_BASE_URL' tests/`

## Findings

### 1. 트리·커밋 — 보고 그대로

clean, 오늘 커밋 정확히 2개(`33dbdd2` 18:50 · `cfc7374` 19:00). gitStatus 스냅샷과 불일치 없음.

### 2. B1/B2 — 실체·심각도·실증 전부 재확인(검증자의 발견은 참)

- **B1(구조)**: `_EXTERNALIZABLE`은 백엔드 3종뿐([test:44-48](../../../tests/test_compose_backend_env.py#L44)),
  `InStackLlamaOverrideTest`는 `llama.yml`만 읽고([:206-208](../../../tests/test_compose_backend_env.py#L206)),
  `tests/` 전수에서 `LLAMA_BASE_URL`을 언급하는 파일은 `test_compose_backend_env.py` 하나다.
  base [`docker-compose.yml:202`](../../../docker-compose.yml#L202)의 표기를 잠그는 셀은 0건 — 확인.
- **B1(계약 스코프)**: "표기는 코드가 그 변수를 읽는 방식을 따른다"는 규칙은 **변수 스코프**로
  명문화돼 있다(2026-08-14 work_log §Issues "남는 일반 규칙" · HANDOFF 추적 부채 동일 문구 ·
  [`.env.example:89-91`](../../../.env.example#L89)). gateway 의 읽기가 기본값 *인자*(
  [`llm_gateway/main.py:58`](../../../services/llm_gateway/app/main.py#L58))인 한 콜론 형태는
  **그 변수를 선언하는 모든 자리**에서 요구된다 — base:202 포함. 계약 요구 분기에 셀 없음 →
  Blocking — `verification.md` "boundary matrix has no empty cells" 그대로.
- **B1(실증 재현)**:

  | 뮤테이션 | 자리 | 결과 |
  |---|---|---|
  | M-A′ `${LLAMA_BASE_URL:-…}` → `${LLAMA_BASE_URL-…}` | base:202 | **27 passed / 135 subtests 전원 green — 0셀** |
  | M-B′ 문자 그대로 같은 diff | [`llama.yml:76`](../../../docker-compose.llama.yml#L76) | **2 failed** — `test_an_empty_value_falls_back_to_the_in_stack_model` · `test_an_explicit_base_url_wins_over_the_in_stack_model` |

  대상 기록의 M-A/M-B 결과와 수치까지 동일하게 재현됐다. 복원 후 기준선 `17 passed / 55 subtests` 복귀.
- **B1(무결정 마감 판단)**: 제안(`_COLON_REQUIRED = {"LLAMA_BASE_URL": …}` 를 base·llama 두 파일에서
  함께 단정)은 기존 명문화 규칙의 *시행*이지 새 정책이 아니므로 오너 결정이 필요 없다는 판단에 동의한다.
- **B2(사실관계)**: [`.env.example:102-109`](../../../.env.example#L102)가 "값이 없으면 기동을 거부한다"를
  적고 주소 다섯을 나열, `EXTERNAL_CHROMA_PORT`만 107행에서 자기 예외("생략하면 8000")를 밝히며,
  `LLAMA_BASE_URL`은 external override 가 gateway 를 건드리지 않고(파일 전문 확인 — 주석뿐, 배선 없음)
  base 가 `:-` 폴백이라 실제로 거부하지 않는다. 문서↔동작 비대칭 = 내부 계약 모순 → Blocking +
  방향은 결정 사안 — 분류 정확.

### 3. 미검증 산정 — **틀렸다(본 감사의 주 발견, F1)**

- "마지막 검증 기록이 `docs/verifications/2026-08-13/`이고 그 뒤 커밋이 7개"는 git 산술과 안 맞는다.
  검증 디렉터리를 마지막으로 건든 커밋은 `c08b0c2`(08-13 11:40)이고, `33dbdd2` 직전까지 그 뒤
  커밋은 **10개**(d7e52c8·6352121·3b71eac + 08-14의 7개). 검증 세션 자기 반영 커밋 `d7e52c8`(11:49)을
  관례대로 제외해도 미검증은 **9커밋**이었다. "7"의 앵커는 실제로 검증 커버리지가 아니라
  **08-14 세션의 시작 경계**다.
- `6352121`(08-13 12:09, 베타 기준선 기록)·`3b71eac`(12:44, 배포 외부화 부채 등재)은 마지막 검증이
  닫힌 뒤에 쌓였고 어느 검증 기록의 Subject 에도 없다. 오늘 검증 기록이 자기 범위를 "2026-08-14의
  미검증 7커밋"으로 명시한 것 자체는 정직하지만, 그로써 **이 둘은 여전히 미검증**이다.
- 따라서 `cfc7374` 커밋 메시지·[HANDOFF 마감메모](../../../HANDOFF.md)의 *"오늘 기준 미검증 구간은
  0 이다"*는 **거짓**이다. 뿌리를 보면 08-13 마감의 "미검증 0"(11:49 시점 문장)이 뒤이은 두 커밋에
  이미 낡아 있었고, 어제 마감의 "오늘 2커밋"이 `8e57369` 뒤 낡았던 것과 **같은 병의 세 번째 변형**이다.
  "유도했다"고 하면서 앵커를 세션 경계에서 잡은 순간 규칙은 절반만 실행된 셈이다.
- **완화 사실**: 두 커밋 모두 docs-only(HANDOFF·work_log)다. `6352121`의 핵심 수치(베타 기준선)는
  오늘 예측→실측 체인이 교차 검증했고 `3b71eac`의 부채 등재 내용은 어제·오늘 검증이 소비했다.
  실효 리스크는 낮고 결함은 산정·기록 축이다 — 그러나 이 저장소는 인계 문구 정확성을 1급 규칙으로
  다루므로("5가 아니라 3" 함정으로 규칙이 생겼다) 정정 없이 넘기지 않는다.

### 4. 나머지 주장 — 전부 재현·확인

- 축 ③: 주소 없이 `config` → rc=1 · 서비스 10 → 7(`admin application frontend gateway
  generation_worker mongo worker`) 재현. `8e57369` diff 는 `.env.example`·`docker-compose.external.yml`·
  테스트 2개뿐이라 **base 무변은 파일 목록으로 증명**된다.
- "증분이 전부 compose 배선 가드이고 backend 프로덕션 0줄": `git diff --name-only 6352121..cfc7374 --
  services/ frontend/` 공백 — 참. (다만 subtest +49 중 +1은 검증 기록 242→243, "전부 가드"는 48/49의
  압축 — work_log 표는 정확히 분리해 두었다. F4.)
- 어제 예상값 "+6셀/+30"의 축 ① 귀속: `ExternalBackendEnvTest` 3서비스×3변수×3셀=27 + `CHROMA_PORT`
  3 = **30 subtests / 셀 4+2=6** — 산술적으로 정확. "낡은 것은 범위"라는 해석에 이견 없음.
- 재빌드: `ai_writte_system-app`·`-frontend`·`-gateway`·`-embedding` 오늘 18:19 생성 · 옛 태그
  `-application`(08-02)·`-worker`·`-generation_worker`(07-22) 잔존 · `-elasticsearch` 태그
  **07-12 무변(캐시 전량 히트 서술과 부합)** · `.env` 부재 — 전부 확인. "260커밍 뒤처짐"은
  실측 근사 **255커밋**(08-02 08:00 이미후 ~ `9e2f1ef`)로 사소한 과대(F5).
- AUTH_SESSION_TTL_HOURS: [2026-07-27 work_log:221](../../daily_logs/2026-07-27/work_log.md)에
  보안 근거("조용한 fallback 은 무한 세션") 계약 확인 · `grep tests/` 0건 ·
  [`main.py:390-396`](../../../services/application/app/main.py#L390) `ValueError` 확인 — "오너 결정
  없이 착수 가능" 판단 타당.
- 검증 인덱스·README 수치(243건)와 판정 어휘("조건부 합격" — 판정 줄에 조건 명시) 규칙 준수 확인,
  `test_docs_indexes` 13 passed / 253 subtests green.

## Issues / Risks

### Blocking

**F1. 미검증 산정 오류로 "미검증 구간 0"이 허위 상태로 기록됐다.** 실제 잔여 미검증 2커밋
(`6352121`·`3b71eac`, docs-only). 정정 경로 둘: (a) 별도 추기 검증으로 둘을 커버하거나 (b) HANDOFF·
work_log 해당 문장을 "미검증 2커밋 남음"으로 바로잡고 명시적으로 등재한다. 어느 쪽이든
"마지막 검증 기록 뒤 7커밋" 서술은 9커밋으로 정정되어야 한다. — 오너가 방향을 고른다(구현자가
골라도 되는 성질이지만, 이번 감사의 발견이므로 보고 후 진행).

### Hardening recommendations (비차단)

- **F2. B2 옵션 (a)의 비용 서술이 과대하다.** *"배포 서버가 호스트 llama 를 쓰는 선택지를 배제한다"* —
  `:?` 필수화 후에도 `LLAMA_BASE_URL=http://host.docker.internal:9080` 을 **명시적으로** 주면 호스트
  llama 는 여전히 쓸 수 있다. 사라지는 것은 선택지가 아니라 **미설정 시 암묵적 폴백**이며, (a)의 실제
  비용은 ".env 에 한 줄"이다. HANDOFF Owner Decisions 항목에 같은 문구가 들어가 있으므로 **오너가
  B2 를 결정하기 전에 정정**되어야 프레이밍이 기울지 않는다.
- **F3. "compose 를 읽는 가드 전부(3파일)" 열거가 부정확하다.** `grep -rln 'docker-compose' tests/` 는
  4파일이고 빠진 `test_core_sot_mongo.py`는 `docker-compose.test.yml`(URI 각주)만 언급해 base:202 를
  볼 수 없으므로 **결론은 불변**이다. "전부"를 주장할 때는 스윕을 근거로 열거한다.
- **F4. 커밋 메시지의 "subtest +49 는 전부 compose 배선 슬라이스의 신규 가드"** — +1은 검증 기록
  자리다(work_log 표는 정확). 보고 문구의 압축.
- **F5. "260커밋"은 실측 ≈255.** 근사치로는 맞지만 숫자를 적으면 측정값이어야 한다(이 저장소
  숫자 규범: 받아 적지 않고 잰다).
- **미재측정 목록(이 감사가 안 돌린 것)**: 알파 전수 원시값 `2281/4/2515`·192.76초(오너 지시로
  제외) · 프론트 빌드 지표 일치 주장(재빌드는 확인, 지표 미재측정).

## Verdict

**조건부 합격** — F1(미검증 산정: 실제 9커밋 중 7커밋만 검증했고 "오늘 기준 미검증 구간은 0"이
거짓 — `6352121`·`3b71eac` 잔여)을 정정할 것.

근거가 되는 사실들:

- 검증의 핵심 산출은 **전부 재현됐다** — B1/B2 는 구조·계약·실증(뮤테이션 수치까지) 어느 축에서도
  참이었고, M-A′↔M-B′ 대비는 이 감사가 독립적으로 다시 세웠다. 축 ① 짝 규칙·축 ③ 실측·"프로덕션
  0줄"·재빌드 실물 확인.
- 잔여 판단 3건(B1 무결정 마감 · B2 결정 필요 · AUTH_TTL 착수 가능)도 정본 대조로 타당하다.
- 그럼에도 **커버리지 주장 하나가 거짓으로 기록됐고** 그것이 HANDOFF 마감메모 — 다음 세션이
  입력으로 삼는 자리 — 에 등재돼 있다. "미검증 목록을 git 에서 유도" 규칙을 스스로 강조한 세션이
  세션 경계를 앵커로 삼아 같은 함정의 세 번째 변형을 만든 것이므로 조건 없이 넘기지 않는다.

## Outstanding items

- 오너 선택 대기: F1 정정 방향(추기 검증 vs 명시적 등재 + 문장 정정) · F2 를 B2 결정 전에 반영할지.
- 이 기록의 커밋으로 검증 기록은 243 → **244건** — 최상위 `README.md`·`docs/README.md`·본 인덱스
  판정 분포를 함께 갱신했다(`VerificationCountClaimsTest` 가 잠그는 자리).
- B1(B1 셀 추가)·B2(오너 결정)·AUTH_SESSION_TTL_HOURS 2셀은 이 감사 이전과 동일하게 열려 있다.

## Reproduction

```bash
git status --short                # 공백이어야 시작한다
git rev-list --count c08b0c2..33dbdd2        # 11 (오늘 33dbdd2 포함 → 세션 시작 기준 10)
git log --format='%h %ad %s' --date=format:'%m-%d %H:%M' -12

# B1 실증 — 같은 diff 를 두 파일에 (복원은 저장소 루트에서)
sed -i 's|${LLAMA_BASE_URL:-http://host.docker.internal:9080}|${LLAMA_BASE_URL-http://host.docker.internal:9080}|' docker-compose.yml
python3 -m pytest tests/test_compose_backend_env.py tests/test_compose_exposure.py \
                 tests/test_admin_surface_separation.py -q   # → 27 passed, 0셀
cd /mnt/f/devel/ai_writte_system && git checkout -- docker-compose.yml && git status --short

sed -i 's|${LLAMA_BASE_URL:-http://llama:9080}|${LLAMA_BASE_URL-http://llama:9080}|' docker-compose.llama.yml
python3 -m pytest tests/test_compose_backend_env.py -q       # → 2 failed
cd /mnt/f/devel/ai_writte_system && git checkout -- docker-compose.llama.yml && git status --short

# 미검증 산출 스윕
grep -rln 'docker-compose' tests/*.py     # 4파일 (test_core_sot_mongo 는 test.yml 만)
grep -rn 'LLAMA_BASE_URL' tests/          # test_compose_backend_env.py 만

# 축 ③ · 재빌드
docker compose -f docker-compose.yml -f docker-compose.external.yml config >/dev/null; echo rc=$?   # 1
docker images --format '{{.Repository}}:{{.Tag}} {{.CreatedAt}}' | grep ai_writte
git diff --name-only 6352121..cfc7374 -- services/ frontend/          # 공백
```
