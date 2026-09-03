# identity group Slice 2(분석 runner 배선)— 독립 검증

**조건부 합격** — 러너 레벨 **judge 미구성 격리 셀 부재**(B1). 완료 기록·SoT v1.8.23 리터럴 ③이 "ProviderError·`InvalidIdentityJudgement`·**judge 미구성** 어느 것이 와도 job은 succeeded·후보는 `needs_review` 잔류"를 확정 리터럴로 주장하고 공통 작업 규칙도 LLM judge 도입 Slice에 "provider 미구성" 명시 검증을 요구하나, 러너 배선 셀은 앞 둘만 잠갔다(judge=None 서비스가 짝이 있을 때 `IdentityJudgeNotConfigured`를 내는 경로). 행동 자체는 계약대로다(검증자 probe 실측 — job SUCCEEDED·relation 0건). 셀 1개 추가로 폐쇄 가능하다(Slice 1 B1~B3와 같은 "빈 것은 잠금" 모양).

## Subject metadata

- 검증일: 2026-09-03
- 요청자: 오너 — "작업 ai가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? Slice 2(분석 runner 배선) 완료·마감."
- 검증자: 이 세션(구현 세션 6과 다른 세션). 구현자 보고(work_log 세션 6·SoT v1.8.23 행·커밋 메시지·HANDOFF)는 전부 **가설**로 취급해 원본에서 재유도했다.
- 대상: 커밋 4개 — `488b867`(구현: 어댑터+배선+감사 셀)·`e6a4c87`(adapter parse 축 셀)·`fd02e88`(위치 잠금+max_tokens 핀)·`3da4112`(기록). HEAD `3da4112`, 트리 clean. **코드 기준선은 `2d467b5`**(`488b867^` — e6a4c87·fd02e88은 테스트 전용).
- 정규 계약: `docs/plans/pending-candidate-identity-grouping-implementation-phases.md` §Slice 2(규칙·검증 문장 + 완료 기록 리터럴 ①~⑤) · §공통 작업 규칙(LLM judge Slice의 provider 미구성·parse error·ProviderError·audit row 수 명시 검증) · `docs/system-contract-sot.md` **v1.8.23**(변경이력 행 + §Phase 2A "identity group 판정이 runner에 붙었다" 조항 + §LLM 파이프라인 관측의 리터럴 9종·계측 목록·재분류 목록).

## Scope

1. 경계 행렬 — 계획 §Slice 2 규칙/검증 문장 + SoT v1.8.23 리터럴 ①~⑤ + 공통 규칙 4축을 should/should-NOT/리터럴로 전개해 셀 대응표를 만든다.
2. 구현 코드 감사 — 어댑터(compare judge 모양 주장: versioned 프롬프트·strict parse·repair 1회·terminal 거부)·runner 격리 구조(성공 경로·종결 뒤·전체 단위·첫 실패 종료·D4 재분류 위치)·조립(env 게이팅·max_tokens·`AnalysisService.repository`)·계측(site·scope·correlation_id).
3. 테스트 코드 감사 — 신규 18셀(16+2) 각각의 단정이 계약 조항을 잠그는지.
4. 뮤테이션 — 구현자 표의 핵심 4종(M2·M3·M4·M9) 재유도 + 검증자 신설 2종(구현자 표에 없는 축).
5. 전수 회귀 재실행 + OpenAPI 덤프 **코드 경계**(2d467b5 ↔ HEAD) 대조 + 문서 가드.

## Methodology

환경(측정의 일부): WSL2(GTX 1060), Python 3.12.3 / pytest 9.0.2, `.env` 없음(compose 기본값), test-mongo(127.0.0.1:27020, rs-test) `up -d` 후 `State.Health.Status=healthy` 게이트 후 개시(구현자는 내린 채 마감 — 검증자가 재기동). 이 머신 관례 skip 1(ES 패키지 탑재).

- 전수: `python3 -m pytest -q 2>&1 | tail -3`(백그라운드, test-mongo healthy 후).
- 수집 산술: `python3 -m pytest --collect-only -q | tail -1` → 2741(= 주장 2740 passed + 1 skipped).
- OpenAPI: `python3 scripts/dump_openapi.py`를 본 트리(HEAD `3da4112`)와 `git worktree add --detach /tmp/pre_slice_2d467b5 2d467b5`에서 각각 실행 → `cmp` 바이트 동일, md5 `10978d55571a90ccd52f65220fc354d3`·**384,414B**(선례 검증 기록들과 같은 지문 — 덤프 방법 동일성 교차).
- 집중: `python3 -m pytest tests/test_identity_judge_runner_wiring.py tests/test_llm_call_sites.py tests/test_identity_judging.py -q`.
- 뮤테이션: 매번 `git status --short` empty 확인(사전 게이트, clean-tree 분기) → 변이 → `pytest tests/test_identity_judge_runner_wiring.py[-q]`(필요시 `tests/test_analysis_runner.py`·`tests/test_llm_call_sites.py` 병합) → **요약줄+FAILED/SUBFAILED 함께 판독** → `git checkout -- <path>` → `git status --short` empty 재확인. 적용 diff는 아래 표에 축약 없이 기재. 변이 창은 전수 백그라운드 실행과 시간적으로 겹쳤다 — 변이는 깨뜨리기만 하므로 오염은 "실패"로만 나타날 수 있고, 전수가 기대치 그대로 green이면 간섭은 사후 배제된다(`main.py`·`runner.py`는 컬렉션 시점 변이 전에 import 완료; 런타임 `inspect.getsource(main)` 판독 셀 `test_analysis_extractor_schema.py:909`만 이론상 창에 걸릴 수 있었다).
- probe 2종(비커밋 축 검증): [`repro_judge_not_configured_isolation.py`](repro_judge_not_configured_isolation.py)·[`repro_reclassify_no_call_mislabel.py`](repro_reclassify_no_call_mislabel.py) — 기록 옆에 커밋(선례 `repro_outbox_retry.py`).

## Findings

### 1. 경계 행렬 — 셀 대응

| 계약 조항(계획§Slice 2 / SoT v1.8.23 / 공통 규칙) | 셀 | 비고 |
|---|---|---|
| 성공 경로에서 후보 저장 뒤 group 서비스 호출 | `test_success_path_judges_recorded_candidates_after_save` | judge가 pool을 저장소에서 읽으므로 pair 관측 자체가 "저장 뒤" 증명. relation·group·member·needs_review 잔류까지 |
| 저장 실패·job 실패 판정 미시도 | `test_candidate_save_failure_skips_judging` | 유령 앵커→preflight 실패→job FAILED, `judge.calls==[]` |
| 판정 실패 job 실패화 금지·needs_review 잔류 | `test_provider_error_does_not_fail_the_job` · `test_parse_error_does_not_fail_the_job` | 첫 실패로 단계 종료(`len(calls)==1`)까지 |
| **judge 미구성 격리(러너)** | **없음** | **B1** — 서비스 레벨 셀(`test_identity_judging.py:273`)은 `IdentityJudgeNotConfigured` *발생* 축만 잠그고 러너 격리는 별개 분기 |
| 후보 0개 no-op | `test_zero_candidates_is_noop` | relation·group 0건까지 |
| no shortlist no-op | `test_no_shortlist_is_noop` | character 이름 불일치 2+event retriever 미주입 2 혼합(Slice 1 B1의 runner 면) |
| 미배선(judging 서비스 부재) no-op | `test_missing_judging_wiring_is_noop` | B1과 다른 축 — 서비스 자체가 없으면 짝이 생기지 않는다 |
| 종결 뒤 판정(리터럴 ②, 격리의 구조화) | `test_judging_runs_after_the_job_reaches_success` | judge 호출 시점 job 상태 SUCCEEDED 단정 |
| focal=이번 job 기록 후보(리터럴 ④) | `test_only_this_jobs_candidates_are_focal` | 옛 2·신규 1에서 calls 2쌍, 옛-옛 pair 무판정 |
| audit 행 수(공통 규칙) | 감사 4셀 — 3 pair→3행·repair 2행·terminal `[parse_error, success]`·provider taxonomy 유지 | 실 `ObservedProvider`+`llm_call_scope`(seam C)로 site·correlation_id=job_id·error_type까지 |
| parse error 축(공통 규칙) | adapter 3셀 — verdict 축 밖·정확키·repair 1회 회수 | `TerminalJsonIdentityJudge` 직접 |
| site 리터럴 `identity_judge`+조립 감싸기 | `test_identity_judge_assembly_is_wrapped` + site 집합 셀(8→9) | 집합 셀은 추가·삭제 어느 쪽이든 실패 |
| `ANALYSIS_IDENTITY_JUDGE_MAX_TOKENS` 기본 512 | `test_identity_judge_max_tokens_default_and_env_override` | 기본값+env override 축 |

### 2. 구현 코드

- **어댑터**(`analysis/identity_judge.py`) — compare judge(`compare_judge.py`)와의 "같은 모양" 주장을 대조해 확인: versioned 프롬프트(`analysis_identity_v1`:39-40)·strict parse(정확키:175)·repair 1회(:111-124)·terminal 거부 `InvalidIdentityJudgement`(:122)·판정 축 세 값 전부 허용(compare의 `create` 배제에 대응하는 도메인측 배제 없음 — 모듈 주석이 근거 제시). **template 미사용 예외도 compare처럼 `InvalidIdentityJudgement`로 감싼다**(:96-99 ≡ `compare_judge.py:100-102`) — H1 참조.
- **runner 격리**(`runner.py:176-231`) — `mark_job_succeeded` **뒤**에 호출(실패 try의 재발산이 구조적으로 앞을 막는다 — 성공 경로만 리터럴 ①). 격리는 `except InvalidIdentityJudgement`(D4 재분류) → `except Exception: pass`(전체 단위) 순. `reclassify_last_as_parse_error`는 순수 인메모리 연산(`llm_call_scope.py:97-119`)이라 핸들러 탈출 경로 없음 — "판정 실패 job 응답을 깰 수 없다"는 구조 확인.
- **계측** — run endpoint가 기존 scope(`correlation_id=job_id`, `routers/analysis.py:229-231`)를 열고 판정이 그 안에서 도니 `identity_judge` 행이 extractor 행과 같은 correlation_id로 나란히 남는다(SoT §관측 조항과 일치). 조립 감싸기는 `main.py:798-824`(compare:847-860과 동일 모양 — 자체 in-memory 템플릿 서비스+시드 포함).
- **조립 게이팅** — `_default_analysis_runner`는 `LLM_GATEWAY_BASE_URL` 없으면 None(→ endpoint 503, `main.py:774-776`). `AnalysisService.repository` 읽기 전용 프로퍼티로 같은 저장소 인스턴스 조립 확인.

### 3. 테스트 코드

- 18셀 전부 단정이 public 표면(job 상태·후보 상태·relation/group·감사 행)을 겨냥하고, under/over 방향이 셀 독스트링에 명시돼 있다. 감사 셀은 `_observed`(실 `ObservedProvider`+가짜 inner)로 seam C를 실제로 통과한다 — "실 adapter+seam C" 주장 성립.
- 구현자 뮤테이션 표 11종의 배치·판정을 읽어 대조 — M4(None-가드 제거)의 "관측 동등" 판정을 아래 5번에서 독립 재현해 흡수층 규명까지 확인.

### 4. 뮤테이션(검증자 실측 — 구현자 표 재유도 4 + 신설 2)

| 변이 | 적용 diff | 실측 |
|---|---|---|
| **V-A focal 확대(신설·과잉)** | `runner.py` `for result in recorded:` → `for candidate in self._analysis_service.list_needs_review_candidates(project_id=project_id):`(candidate_id도 `candidate.id`) | **1 failed** — `test_only_this_jobs_candidates_are_focal` |
| **V-B max_tokens 기본 변조(신설)** | `main.py:817` `"ANALYSIS_IDENTITY_JUDGE_MAX_TOKENS", "512"` → `"511"` | **1 failed** — `test_identity_judge_max_tokens_default_and_env_override` |
| M3 재유도(위치 이동) | `runner.py` `mark_job_succeeded` 블록과 `_judge_candidate_identities` 호출의 **순서 교환**(이동이지 삽입 아님 — "작성 정확히 1회"류 단정이 없어 이동 변이가 순수하게 위치 셀에만 걸린다) | **1 failed** — `test_judging_runs_after_the_job_reaches_success` |
| M2 재유도(격리 제거) | `except Exception:  # noqa…` 본체 `pass` → `raise` | **2 failed** — `test_provider_error_does_not_fail_the_job` + `test_provider_failure_row_keeps_its_taxonomy`(구현자 표와 동일 짝) |
| M4 재확인(None-가드 제거) | `if self._identity_judging is None: return` 2줄 삭제 | **38 passed**(wiring 16+analysis_runner 22) — 관측 동등. 흡수층 = `except Exception`이 `AttributeError`를 삼키는 이중 보호(구현자 판정 그대로) |
| M9 재유도(D4 재분류 분기 제거) | `except InvalidIdentityJudgement:` 핸들러 블록 전체 삭제(`except Exception: pass`만 남김) | **1 failed** — `test_terminal_rejection_is_reclassified_and_isolated`(구현자 표와 동일 짝) |

V-A·V-B는 **구현자 표에 없던 축**이다(focal 과잉 방향·max_tokens 핀) — 둘 다 기명 셀이 물었다. 매 변이 후 `git checkout --` 원복·`git status --short`에서 코드 파일 소실 확인.

### 5. probe 실측(비커밋 축)

- **judge 미구성 러너 격리(B1의 행동 확인)** — [`repro_judge_not_configured_isolation.py`]: `CandidateIdentityJudgingService(judge=None)`을 runner에 주입하고 같은 이름 옛 후보로 짝을 만들면 `IdentityJudgeNotConfigured`가 루프 안에서 발생하며 격리 경계가 삼킨다 — **job SUCCEEDED·relation 0건**. 행동은 계약대로다. 빈 것은 잠금뿐.
- **호출 없는 재분류 오염(H1 실증)** — [`repro_reclassify_no_call_mislabel.py`]: scope에 `analysis_extractor` success 행 1건이 있는 상태에서 시드 안 된 템플릿의 `TerminalJsonIdentityJudge`가 provider 호출 **없이** `InvalidIdentityJudgement`를 내고 러너와 같은 재분류를 돌리면 — `site=analysis_extractor outcome=parse_error error_type=InvalidIdentityJudgement`로 **관계 없는 extractor 행이 오염**된다.

### 6. 전수·산술·OpenAPI·기록

- 수집: **2741 tests collected** = 주장 2740 passed + 1 skipped. 기준선 산술(2722+18=2740) 성립.
- OpenAPI: **2d467b5 ↔ HEAD 바이트 동일**(md5 `10978d55…`, 384,414B — 선례 기록 지문과 동일). 구현자 기록의 "HEAD~1 worktree 대조"는 커밋 시각 대비상 테스트 커밋 전후였을 개연성이 높아 그 측정만으로는 무변 주장이 성립하지 않는다(H3) — 검증자가 올바른 경계에서 재측정해 참임을 확정.
- SoT v1.8.23: 변경이력 행·`call_site` 리터럴 9종·계측 목록 `identity_judge` 조항·재분류 목록 갱신·§Phase 2A 조항 전부 diff로 확인(리터럴 ↔ 코드 대조 무불일치). HANDOFF 착수점·README 핀(v1.8.23)·portfolio/product-overview(8→9곳) 갱신 확인. work_log 세션 6의 수치·셀 목록은 재유도한 범위에서 전부 일치.

## Issues / Risks

### Blocking(계약 의무)

- **B1 — 러너 레벨 judge 미구성 격리 무셀.** 완료 기록(계획 §Slice 2)·SoT v1.8.23(변경이력 행 리터럴 ③·§Phase 2A 조항)·HANDOFF가 "ProviderError·`InvalidIdentityJudgement`·judge 미구성 어느 것이 와도 job은 succeeded"를 확정 리터럴로 주장한다. 셀은 앞 둘만 있다. 공통 작업 규칙이 LLM judge 도입 Slice(1·2·5)에 "provider 미구성" 명시 검증을 요구하고, 이번이 실 provider 호출이 생기는 첫 Slice다. 서비스 레벨 셀(`test_identity_judging.py:273`)은 오류 *발생*을 잠글 뿐 러너의 *격리*는 별개 분기다. 폐쇄: `test_missing_judge_is_isolated_in_the_runner`류 셀 1개(서비스 주입·judge=None·같은 이름 짝 → job SUCCEEDED·`needs_review` 잔류·relation 0건). 다음 전수 기대값 2741/1/3133. 대안: 기록 문구에서 "judge 미구성"을 삼축 주장에서 빼고 서비스 레벨 잠금으로만 인용(오너 선택).

### Hardening(비차단)

- **H1 — provider 호출 없는 `InvalidIdentityJudgement`의 재분류 오염.** probe 실측(위 5번): 템플릿 미시드 조립 등 provider 호출 전 예외가 나면 `reclassify_last_as_parse_error`가 같은 scope의 **관계 없는 마지막 행**(예: extractor success)을 `parse_error`로 바꾼다. SoT/계획의 "`InvalidIdentityJudgement` 시점의 마지막 호출이 곧 실패한 repair 호출이다"는 **기본 조립에서만 성립하는 가정이지 불변식이 아니다**(기본 조립은 시드를 조립점에서 하므로 도달 불가 — 손조립 runner·smoke에서만 노출). compare judge가 같은 모양(`compare_judge.py:100-102`)이라 이 Slice의 이식은 선례 충실하다. 권고: ① 문구를 "provider가 실제로 답한 뒤에만"으로 한정하거나 ② 러너 핸들러가 마지막 호출의 site가 `identity_judge`인지 확인한 뒤 재분류.
- **H2 — HANDOFF KPI 문단의 사이트 열거가 여전히 8개.** 리터럴 수는 각주로 9로 정정했으나(`일치했다(둘 다 8…; …리터럴은 9)`) 바로 뒤 사이트 나열에 `identity_judge`가 없다. 다음 갱신 때 나열에 추가하면 된다.
- **H3 — 구현자의 OpenAPI 대조는 무의미한 경계였을 개연성이 높다(결론은 참).** 커밋 시각이 순서대로 `488b867` 15:47(코드)→`e6a4c87` 15:51·`fd02e88` 15:53(테스트 전용)→`3da4112` 19:02(기록)인데, stash 서술("커밋 후 stash가 빈 트리에서 자기 비교")가 속한 기록 작성 시창의 HEAD는 `fd02e88`이었고 HEAD~1은 `e6a4c87` — 즉 "HEAD~1 worktree 대조"는 **코드 커밋을 낀 경계가 아니라 테스트 커밋 전후**를 비교했을 가능성이 지배적이다(양쪽 다 Slice 2 코드 포함 — 그 경계에서 바이트 동일인 건 자명하다). OpenAPI 무변 결론 자체는 본 검증이 올바른 경계(2d467b5↔HEAD)에서 참으로 확정했으므로 차단은 아니나, "실측"으로서는 실효가 없었다. 향후 기록은 "코드 기준선 커밋 ↔ 측정 커밋"을 명시하는 게 좋다(Slice 1 기록이 그렇게 썼다).

## Verdict

**조건부 합격** — B1(러너 레벨 judge 미구성 격리 셀 부재)를 닫으면 합격.

근거: ① 경계 행렬의 나머지 전 축이 기명 셀로 잠겼고 검증자 신설 변이 2종(V-A focal 과잉·V-B max_tokens)까지 물렸다 ② 구현자 뮤테이션 표의 재유도 4종(M2·M3·M4·M9)이 셀 짝까지 일치 재현됐다 ③ OpenAPI 무변이 올바른 경계에서 바이트 수준으로 확인됐다 ④ 전수 산술(수집 2741=2740+1)이 독립 성립했다. B1은 Slice 1 B1~B3와 같은 "행동은 계약대로, 빈 것은 잠금"이며 셀 1개로 닫힌다.

## Outstanding items

- test-mongo는 검증자가 전수용으로 기동했다(구현자는 내린 채 마감) — 전수 확인 후 내린다.
- 트리 clean. 본 검증의 커밋은 기록+repro 스크립트 2종+인덱스 갱신뿐(코드 무접촉).
- Slice 3(Review Inbox 읽기면) 착수는 B1 폐쇄 후가 권장 순서다(오너 판단).

## Reproduction

```bash
# 환경: Python 3.12.3 / pytest 9.0.2, .env 없음
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect --format '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done
python3 -m pytest --collect-only -q | tail -1        # 2741 tests collected
python3 -m pytest tests/test_identity_judge_runner_wiring.py tests/test_llm_call_sites.py tests/test_identity_judging.py -q
python3 -m pytest -q                                  # 전수(아래 결과)
python3 scripts/dump_openapi.py | md5sum              # 10978d55… (384,414B)
git worktree add --detach /tmp/pre 2d467b5 && (cd /tmp/pre && python3 scripts/dump_openapi.py | md5sum)
python3 docs/verifications/2026-09-03/repro_judge_not_configured_isolation.py      # PROBE-OK
python3 docs/verifications/2026-09-03/repro_reclassify_no_call_mislabel.py         # CONFIRMED: …corrupted to parse_error
# 뮤테이션: git status --short empty 확인 후 위 표 diff 적용 →
#   pytest tests/test_identity_judge_runner_wiring.py -q (또는 표의 파일 조합) → git checkout -- <path>
```

- 전수: **2740 passed / 1 skipped / exit 0, 1998.05초**(3134 subtests). 구현자 주장 2740/1/**3133**과 셀 수는 정확히 일치한다. subtest +1의 잔차는 **검증자 자신의 미커밋 검증 기록이 디스크에 있는 채로 돌았기 때문**이다 — 문서 가드는 기록마다 subTest로 행 구조를 검사하므로 이 기록 1건이 subtest를 1 올린다(가드 단독 실측 287→288과 같은 축). 제3자 재현 시 이 기록을 커밋한 뒤면 3134, 스태시하면 3133이다.
