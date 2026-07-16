# 독립 검증 — C0 Writing HTTP contract 구현 (SoT v1.7.1, D3=A)

## Subject metadata

- 날짜: 2026-07-16
- 요청자: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? C0 Writing HTTP contract 구현 완료 … SoT v1.7.1 … 브리프 D3=A와 v1.6.95 '안전망 먼저' 선례를 그대로 따랐습니다 … 커밋은 요청하지 않으셔서 하지 않았습니다")
- 검증자: 독립 검증 AI(Claude, 별도 세션 — 구현 미관여)
- 대상 슬라이스/산출물: C0 — Writing generate/gate/revise-and-gate/accept 4 endpoint 응답 타입화(성공 `response_model` + partial `responses={}` + exact-key 안전망). D3=A / D5=A. `ARCH-1` 첫 단계(발화→종결).
- 정본 계약 참조(canonical contract scope):
  - `docs/system-contract-sot.md` v1.7.1(버전 로그 행 + §~192 "타입 계약 동기화의 실제 범위(v1.6.94 → v1.6.95 척추 → v1.7.1 Writing)" + §~193 "response_model의 필드 필터링 위험(v1.6.95)")
  - `docs/plans/frontend-writing-workspace-decisions.md` — §D3(option 표·구현 lock 4조항), §D5(C0→C1→C2), §"선택 후 첫 구현 순서 / C0"(5단계), §"확인된 현재 계약과 선례"(endpoint 의미 + accept 502 partial save 계약)
  - `docs/system-contract-sot.md` v1.6.95 행("안전망 먼저" 절차의 선례) + v1.7.0 행(D3=A 잠금, ARCH-1 Ready 전환)
- 검증 대상 작업 출처: **working tree, uncommitted**(작업자가 "커밋은 요청하지 않으셔서 하지 않았습니다"라고 명시). 본 검증은 mutation을 위해 working tree를 일시 더렵히고 매번 백업 파일로 복원했다(최종 복원 완료, `grep`로 잔류 없음 확인).

## Scope

1. **계약 스코프·자기 모순** — 브리프 D3=A/D5=A lock + SoT v1.7.1 행/§~192-193이 요구하는 것. 브리프 ↔ SoT ↔ 코드 ↔ schema 간 수치/표현 일치.
2. **성공 모델 너비 = payload 너비(핵심)** — 4 성공 모델(+ 모든 중첩 component)이 `response_model`의 silent field-drop 위험 없이 builder 출력과 정확히 같은 너비인지.
3. **안전망-선-모델 순서 + exact-key 완전성** — `Writing*EnvelopeKeyTest` 9개가 **완전한 키 집합**(`set(body)` 동등, 부분 아님)을 잠그는지. 모델이 필드를 좁힐 때 안전망만 잡는지(mutation).
4. **partial envelope 계약** — revise-and-gate 4 partial(report/revision/retrieval/gate error) 각각 `6 COMMON + 정확히 1 discriminator`인지; **accept 502 partial의 load-bearing `502 + accepted=true + saved`**가 잠겼는지.
5. **`responses={}` 배선·OpenAPI 문서화** — 성공 200 = 성공 모델, partial-capable status = `partial | ErrorDetailResponse` union, plain-error status = detail-only가 실제 schema에 렌더링됐는지.
6. **D2=A 동형·ARCH-1 범위** — payload builder(`_writing_*_payload`) 무변경, route 추출 금지 준수, 프론트 소비 코드 무변경.
7. **독립 실행 재현** — 백엔드 1117/48/273 · Writing 4 suite 132/107 · 신규 9 · 프론트 47/build 90 · schema 재생성 IDENTICAL · mutation 2-bite.
8. **정적/구성·문서 일관성**.

## Methodology

계약 스코프를 먼저 확정한 뒤, 브리프 D3=A lock 4조항을 boundary matrix의 lock list로 전개하고 각 cell을 1차 소스에서 채웠다. 작업자의 claim(work_log Task 12·HANDOFF)은 "소스"로만 읽고, 정본(브리프·SoT)·코드·테스트·schema에서 독립 재도출했다.

- **계약 읽기**: 브리프 전문·SoT v1.7.1 행 + §~192-193 + v1.6.95/v1.7.0 행을 end-to-end 읽어 lock list 구축.
- **모델↔빌더 키 대조(수작업)**: `http_models.py` 각 모델 필드 ↔ `main.py` builder(`_writing_candidate_payload:2506`, `_writing_gate_payload:2533`, `_writing_loop_payload:2549`, `_writing_stages_payload:2557`, `_accepted_save_payload:2601`, `_analysis_job_payload:1340`) ↔ `pointer_wire`(`context_pointer.py:26 POINTER_KEYS`) 출력 키를 1:1 비교. 중첩(claim 4/pointer 4/hint 4/risk 3/finding 5/loop 4/stage 3/saved 4/analysis_job 6) 포함.
- **partial 경로 대조**: `main.py` revise-and-gate 4 partial 분기(`3019, 3053, 3095, 3126`)+성공(`3149`) 및 accept 502 partial(`3241-3247`)+성공(`3255-3264`)의 content 키 집합 ↔ 모델·테스트.
- **실행 재현**(아래 Reproduction의 정확한 명령):
  - Writing 4 suite → `132 passed, 107 subtests`
  - 신규 9 envelope-key 테스트 클래스 개별 실행 → `9 passed`
  - mutation A: `http_models.py`에서 `evaluated_by_model` 제거 → gate+accept envelope-key 실행(백업→복원) → `2 failed, 1 passed`
  - `npm run gen:api` → committed `schema.d.ts`와 `diff -q` → IDENTICAL
  - `npm test`(프론트) → `47 passed / 4 files`; `npm run build` → 90 modules
  - 풀 백엔드 → `1117 passed, 48 skipped, 273 subtests`
- **schema 직접 검사**: `schema.d.ts`의 Writing 4 endpoint operation 절에서 status→model 매핑을 직독(`2873` accept 502 union, `3128` revise 200, `3137/3164/3173/3182` revise partial union).
- **정적/구성**: `git diff --check`, `python3 -m py_compile`, `docker compose config --quiet`, `git status`로 builder/프론트 소비 코드 무변경 확인.

## Findings

### F1. 계약 스코프·자기 모순 — 정합. 충돌 없음.

브리프 D3=A lock 4조항("① exact-key 회귀를 모델보다 먼저 ② 재사용 HTTP 모델 분리 ③ generic detail과 partial의 OpenAPI union ④ main.py 전 router 추출 금지·Writing 모델만 분리")과 SoT v1.7.1 행·§~192-193("response_model은 미선언 필드를 조용히 삭제 → 모델 = payload 정확히 같은 너비, partial JSONResponse는 exact-key가 유일 runtime lock")은 서로 정합이며 코드와 일치한다. v1.6.95가 Writing 트랙을 Deferred로 넘긴 "partial-failure envelope"을 v1.7.1이 정확히 그 진술(성공 경로는 dict라 response_model 적용 가능, uncoverable은 partial envelope뿐)로 닫았다(브리프 §40 ↔ SoT §~192).

### F2. 성공 모델 너비 = payload 너비 — 14개 모델 전부 정확히 일치(too-narrow도 too-wide도 아님).

수작업 1:1 대조 결과:

| 모델 (`http_models.py`) | builder 출력 키 수 | 일치 |
|---|---|---|
| `WritingCandidatePayload` (79) 12키 | `_writing_candidate_payload` (2507-2531) 12키 | ✅ |
| `CandidateClaimPayload` (58) 4키 | builder claim dict (2516-2519) 4키 | ✅ |
| `ContextPointerPayload` (49) 4키 | `pointer_wire`/`POINTER_KEYS` (`context_pointer.py:26,90-91`) 4키 | ✅ |
| `MemoryHintPayload` (66) 4키 | builder hint dict (2522-2524) 4키 | ✅ |
| `RiskNotePayload` (73) 3키 | builder risk dict (2527-2528) 3키 | ✅ |
| `WritingGatePayload` (104) 6키 | `_writing_gate_payload` (2533-2547) 6키 | ✅ |
| `WritingGateFindingPayload` (96) 5키 | builder finding dict (2538-2543) 5키 | ✅ |
| `WritingLoopPayload` (113) 4키 | `_writing_loop_payload` (2549-2555) 4키 | ✅ |
| `WritingStagePayload` (120) 3키 | `_writing_stages_payload` (2557-2562) 3키 | ✅ |
| `WritingStageError` (126) 2키 | `*_error`/audit_error dict (`{type, detail}`) 2키 | ✅ |
| `AcceptedSavePayload` (134) 4키 | `_accepted_save_payload` (2601-2607) 4키 | ✅ |
| `AnalysisJobPayload` (141) 6키 | `_analysis_job_payload` (1340-1350) 6키 | ✅ |
| `WritingReviseGateResponse` (161) 6키 | revise-and-gate 성공 payload (`3149-3159`) 6키 | ✅ |
| `WritingAcceptResponse` (170) 5키 | accept 성공 payload (`3255-3264`) 5키 | ✅ |

Optional 표현(`gate`/`saved`/`analysis_job`/`candidate_id`/`audit_error` `| None`)은 builder가 `None`을 내는 분기와 정확히 대응한다. enum 9종(`writing/models.py:21-84`의 TaskType/OutputType/GateDecision/GateFindingType/GateSeverity/ClaimType/HintType/RiskType/RiskSeverity, `revise_gate.py:77-95`의 LoopStatus/StageName/StageStatus)은 실존하며 `http_models.py:29-44`에서 정확히 import된다. 빌더가 `.value`(문자열)를 내고 모델이 enum 타입을 선언 → pydantic이 유효 멤버값으로 수용.

### F3. 안전망 완전성 + mutation 실증 — exact-key는 **완전한 키 집합**을 잠근다(부분 아님), too-narrow 모델은 안전망만 잡는다.

신규 9 테스트는 전부 `self.assertEqual(set(body), {...})` 형태의 **완전 집합 동등** 검사다(`test_writing.py:513`, `test_writing_gate.py:406`, `test_writing_accept.py:391/421`, `test_writing_revise.py:1151/1169/1184/1198/1213`). subset containment가 아니므로, 모델이 한 필드를 빼면 response_model이 그 필드를 공개 응답에서 삭제하고 집합 비교가 fail한다.

**mutation A(독립 재현)**: `WritingGatePayload`에서 `evaluated_by_model` 제거 → gate·accept envelope-key가 **정확히 2개** bite(`test_gate_envelope_keys_are_complete`, `test_success_envelope_keys_are_complete`), accept partial(analysis 실패)은 JSONResponse라 model을 안 타서 **1 passed**로 유지. 작업자 claim("2 failed") 정확히 재현. 이는 (a) gate 모델이 gate·accept에 공유된다는 점, (b) partial이 response_model을 우회한다는 점을 동시에 실증한다. 백업 파일로 복원 후 `grep` 잔류 없음 확인.

### F4. partial envelope 계약 — 4 revise-and-gate partial + accept 502 load-bearing, 전부 잠김.

- **revise-and-gate 4 partial**(코드 `3019/3053/3095/3126`): 각각 `{candidate, gate, loop, stages, audit_id, audit_error}`(6 COMMON) + **정확히 1개** `*_error`(`{type, detail}`). 테스트 `_COMMON | {"<discriminator>"}`(`test_writing_revise.py:1150`)로 4종 각각 pin. partial이 emit 가능한 status(400/502/503/504)는 `REVISE_AND_GATE_RESPONSES`(`http_models.py:217`)의 union arm에 전부 포함.
- **accept 502 partial**(코드 `3241-3247`): `status_code=502`, `"accepted": True`(리터럴), `"saved": _accepted_save_payload(...)`, `"analysis_job": None`, `"analysis_error": str(exc)`. 브리프 §37/SoT v1.7.0의 load-bearing "502이지만 accepted=true이고 saved 존재"와 정확히 일치.
- **`accepted=true` 값 pin 위치**(적대적 확인): 신규 `WritingAcceptEnvelopeKeyTest`는 키 **집합**(accepted 키 존재)+status+saved shape만 잠그고 `accepted`의 **값**은 pin하지 않는다. 그러나 **기존** `WritingAcceptApiTest::test_partial_failure_is_502_and_retry_converges`(`test_writing_accept.py:296-312`)가 `assertEqual(failed.status_code, 502)`(:300) + `assertTrue(failed.json()["accepted"])`(:301)로 **값 true를 pin**하고, 멱등 재시도 수렴(:305-312)까지 잠근다. 두 테스트 합쳐 boundary cell이 빈 칸 없이 채워진다.

### F5. `responses={}` 배선·OpenAPI 문서화 — schema에 정확히 렌더링.

`gen:api` 재생성이 committed `schema.d.ts`와 **IDENTICAL**(diff -q) → 커밋 파일이 진짜 재생성물임이 입증됨. schema 직독 결과:

- **accept operation**: 200=`WritingAcceptResponse`, 400/404/409/503/504=`ErrorDetailResponse`, 502=`WritingAcceptAnalysisPartial | ErrorDetailResponse`(`schema.d.ts:2873`), 422=`HTTPValidationError`(자동).
- **revise-and-gate operation**: 200=`WritingReviseGateResponse`(`3128`), 400/502/503/504=`WritingReviseGatePartial | ErrorDetailResponse`(`3137/3164/3173/3182`), 404=`ErrorDetailResponse`, 422=`HTTPValidationError`.

즉 "같은 status가 generic detail과 partial envelope 둘 다 가질 수 있음 → union 표현"(브리프 D3=A lock ③)이 정확히 발현됐다.

### F6. D2=A 동형·ARCH-1 범위 — payload builder 무변경, route 미추출, 프론트 소비 코드 무변경.

`git diff HEAD -- services/application/app/main.py`는 **import block(8행) + 4 endpoint decorator(response_model/responses 부착)**만 변경한다. `_writing_*_payload`/`_accepted_save_payload`/`_analysis_job_payload`/`pointer_wire` 본체는 한 줄도 diff에 없다 → D2=A(동형) 준수. `git status`에서 프론트 변경은 `schema.d.ts` 단一件(자동 생성물), `client.ts` 등 소비 코드 무변경 → "손선언 없이 생성 타입 소비" 확인. `product-readiness-backlog.md:37` ARCH-1 = **Done**, "route는 추출하지 않음(의존성 전달이 아직 복잡)" 명시 → D3=A lock ④("main.py 전 router 추출 금지, Writing 모델만 분리") 준수.

### F7. 독립 실행 재현 — 정량 전부 일치.

- Writing 4 suite: `132 passed, 107 subtests`(claim 일치)
- 신규 9 envelope-key: `9 passed`
- 풀 백엔드(`--ignore=tests/test_memory_mongo.py`): `1117 passed, 48 skipped, 273 subtests`(claim 정확히 일치; ES 미설치 기준선 1108 + 9)
- 프론트 `npm test`: `47 passed / 4 files`; `npm run build`: 90 modules(소비 코드 무변경)
- mutation A: `2 failed, 1 passed`(후 복원)
- `git diff --check` clean · `py_compile` OK · `docker compose config --quiet` OK

### F8. 정적/구성·문서 일관성 — 정합.

`CHANGELOG.md:5`(v1.7.1 C0 행), SoT v1.7.1 행·§~192-193, `product-readiness-backlog.md:37`(ARCH-1 Done), 브리프 C0 "구현 완료" 표시, HANDOFF가 서로 정합. 링크 대상 전부 존재.

## Issues / Risks

### Blocking(계약 의무) — 없음.

boundary matrix의 contract-required cell은 빈 칸 없이 채워졌다:
- 성공 4 모델 너비: 4 envelope-key 테스트(완전 키 집합) + 행위 회귀.
- revise-and-gate 4 partial discriminator: 4 envelope-key 테스트(정확히 1 discriminator + COMMON + `{type,detail}`).
- accept 502 partial(`502 + accepted=true + saved`): 신규 envelope-key 테스트(키 집합 + saved shape) + 기존 `test_partial_failure_is_502_and_retry_converges`(:300-301, 502 + accepted=true **값** + 멱등 수렴).
- partial의 runtime lock(JSONResponse 우회): exact-key 회귀로 보장. mutation A로 too-narrow가 잡힘을 실증.
- `responses={}` 문서화: schema 재생성 IDENTICAL + 직독으로 검증.

### Hardening recommendations(비차단 — 현 spec이 요구하지 않는 보강 후보)

- **H1(정밀도) — "성공 4 + union 6 literal" 카운트 표기가 schema와 미세 불일치.** work_log Task 12·SoT v1.7.1 행·CHANGELOG:5에 "성공 4 + union 6 literal"이라 했으나, 실제 schema.d.ts의 응답-레벨 union arm은 **5개**(revise-and-gate 400/502/503/504 = 4 + accept 502 = 1). "6"은 discriminator error *필드*를 셀 때만 성립한다(audit_error + report/revision/retrieval/gate_error = 5 + analysis_error = 1 = 6). 기능적 OpenAPI 표면(성공 모델 + 정확한 status의 partial union)은 완전히 정확하므로 **계약 결함 아님**. 다음 독자가 카운트를 오독해 "union arm이 6개"로 착각하지 않도록, 기회 될 때 "성공 4 + union arm 5(discriminator 필드 6)"로 정정 권장.
- **H2(응집) — `accepted=true` 값-lock이 신규 C0 테스트가 아닌 기존 테스트에 있다.** `WritingAcceptEnvelopeKeyTest`는 accepted의 키 존재만 잠그고 값은 pin하지 않는다. 값 true는 `test_partial_failure_is_502_and_retry_converges:301`에 pin돼 있어 cell은 채워져 있지만(= blocking 아님), C0 envelope-key 테스트만 추적하는 독자가 값-lock 위치를 놓칠 수 있다. 향후 accept envelope 테스트를 정비할 때 `assertTrue(body["accepted"])` 한 줄을 신규 테스트에 옮기거나 추가하면 응집이 좋아진다.
- **H3(문서화 여유 — 결함 아님) — `WritingAcceptAnalysisPartial.analysis_job`이 runtime보다 넓다.** 모델은 `AnalysisJobPayload | None`이지만 runtime 502 partial은 항상 `analysis_job: None`(`main.py:3245`)을 낸다. documentation-only 모델(JSONResponse, runtime 검증 안 받음)의 의도된 여유 표현이므로 over-restrictive/under-restrictive 어느 쪽도 아니다. 조치 불필요.

## Verdict

**합격(조건 없음).**

이유(load-bearing):
1. 성공 4 모델(+14 중첩 component)이 payload builder와 **정확히 같은 너비**로, response_model의 silent field-drop 위험이 없다(F2 수작업 대조 + F3 mutation 2-bite로 실증).
2. partial envelope(4 revise-and-gate variant + accept 502)의 계약이 **완전히 잠겼다** — 특히 accept의 load-bearing `502 + accepted=true + saved`가 신규 envelope-key 테스트(키 집합·saved shape)와 기존 테스트(502·accepted=true **값**·멱등) 합쳐 빈 cell 없이 lock(F4).
3. "안전망 먼저(v1.6.95 절차 재사용)"가 실제로 값을 냈다 — exact-key는 완전 키 집합을 잠그고, too-narrow 모델은 안전망만 잡는다(mutation A).
4. `responses={}` union이 schema에 정확히 렌더링됐고, committed `schema.d.ts` == 재생성물(IDENTICAL)로 위조 불가(F5).
5. D2=A 동형(builder 무변경)·D3=A lock ④( route 미추출, Writing 모델만 분리)·ARCH-1 종결 범위 전부 준수(F6).
6. 정량 1117/48/273·132/107·9·47/90·mutation 전부 독립 재현(F7).

비차단 H1(카운트 표기)·H2(값-lock 위치 응집)·H3(문서화 여유)는 hardening 후보로, 합격 판정에 영향을 주지 않는다.

## Outstanding items

- **커밋 미수행**: 작업자가 "커밋은 요청하지 않으셨다"고 명시했으므로 본 변경 전체가 **working tree, uncommitted** 상태다(`http_models.py`는 untracked, 나머지는 modified). 오너의 커밋 승인 대기.
- **C0 다음 = C1 기본 Writing 작업공간 UI**(`frontend-writing-workspace-decisions.md` §C1): latest clean editor의 instruction+generate → candidate/Gate read-only panel → pass accept intent → saved detail 재조회. C0가 낸 성공/partial 타입을 손선언 없이 소비.
- 검증 중 일시 mutation으로 더럽힌 `http_models.py`는 백업 파일로 복원했고 `grep`으로 잔류 없음을 확인했다(working tree는 검증 착수 전 상태로 동일).

## Reproduction

```bash
# 1. Writing 4 suite + 신규 9
python3 -m pytest tests/test_writing.py tests/test_writing_gate.py \
  tests/test_writing_accept.py tests/test_writing_revise.py -q -p no:cacheprovider
# → 132 passed, 107 subtests

python3 -m pytest -q -p no:cacheprovider \
  "tests/test_writing.py::WritingGenerateEnvelopeKeyTest" \
  "tests/test_writing_gate.py::WritingGateEnvelopeKeyTest" \
  "tests/test_writing_accept.py::WritingAcceptEnvelopeKeyTest" \
  "tests/test_writing_revise.py::WritingReviseGateEnvelopeKeyTest"
# → 9 passed

# 2. mutation A (too-narrow 모델 → 안전망만 bite)
cp services/application/app/writing/http_models.py /tmp/bak
# (WritingGatePayload에서 "    evaluated_by_model: str" 제거)
python3 -m pytest -q -p no:cacheprovider \
  "tests/test_writing_gate.py::WritingGateEnvelopeKeyTest" \
  "tests/test_writing_accept.py::WritingAcceptEnvelopeKeyTest"
# → 2 failed, 1 passed   ← accept partial(analysis 실패)은 JSONResponse라 통과
cp /tmp/bak services/application/app/writing/http_models.py   # 복원

# 3. schema 재생성 IDENTICAL
cd frontend && cp src/api/schema.d.ts /tmp/committed.d.ts && npm run gen:api \
  && diff -q /tmp/committed.d.ts src/api/schema.d.ts   # → IDENTICAL

# 4. 프론트 회귀·빌드
npm test -- --run --reporter=dot    # → 47 passed / 4 files
npm run build                       # → 90 modules

# 5. 풀 백엔드
cd .. && python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# → 1117 passed, 48 skipped, 273 subtests

# 6. 정적/구성
git diff --check && python3 -m py_compile \
  services/application/app/main.py \
  services/application/app/writing/http_models.py \
  && docker compose config --quiet
```

## Post-verification disposition (구현자, 2026-07-16)

원 판정 **합격(조건 없음)**은 보존한다. 오너 승인으로 비차단 hardening을 반영했다:

- **H2 반영(코드)** — `WritingAcceptEnvelopeKeyTest.test_partial_analysis_failure_envelope_keys_are_complete`에 load-bearing 값-lock을 추가했다: `assertTrue(body["accepted"])` + `assertIsNotNone(body["saved"])`. 이로써 `502 + accepted=true + saved` 계약이 기존 accept 행위 테스트뿐 아니라 C0 envelope 테스트 자체에서도 잠겨 self-contained해졌다. focused 재실행 **2 passed**.
- **H1 반영(문서)** — "성공 4 + union 6 literal" 표기를 "성공 4 + union arm 5(revise-and-gate 4 status + accept 502; discriminator 필드 6)"로 정정했다(work_log Task 12·SoT v1.7.1 행·CHANGELOG·브리프). 기능 표면은 원래부터 정확했고 카운트 표기만 오독 방지용으로 명확화.
- **H3 코드 무변** — `WritingAcceptAnalysisPartial.analysis_job`의 documentation-only 여유는 검증자 판정대로 결함이 아니므로 유지.

hardening 반영 후 정량 재확인: accept envelope 테스트 2 passed, 전체 수치 무변(회귀 순증 0 — H2는 기존 테스트에 assertion 2줄 추가). 코드 변경은 테스트 1건뿐(프로덕션 무변).
