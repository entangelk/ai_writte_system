# 독립 검증 — Writing stable context pointer (SoT v1.6.92)

> **Post-verification note (2026-07-15, 작업 AI가 추가)**: 본 기록은 **28-test pre-hardening** working tree(1093/48/257)를 검증했다. 평결 PASS(조건 없음)는 그대로이며, 이후 비차단 hardening 2건이 **반영**돼 테스트가 **28→31**(subtests 17→20), 베이스라인이 **1093→1096/48/260**이 됐다. **H2 closed** — `test_generation_service_sends_no_pointer`·`test_revise_service_sends_no_pointer`(`tests/test_writing_context_pointer.py`)가 실 `WritingService.generate`/`WritingRevisionService.revise`의 provider request 본문에 pointer가 없음을 assert; 두 call site(`prompt.py:147`·`revise.py:119`)에 `include_pointers=True` mutation 시 **정확히 이 2개만 실패**(나머지 29 통과)해 본 기록이 지적한 "formatter 단위 테스트가 못 잡는 call-site 변경" 갭이 실제로 닫힘을 실증. **H1 closed** — `test_non_array_pointer_field_is_rejected`(str/dict/int 매개변수화), `_claim`의 `_list` 우회 mutation에서 3 subtest 전부 bite. **H3은 open(설계상)** — 실 12B pointer 복사 준수율은 sandbox 검증 불가한 본질적 한계이며 오너 풀스택 후속(Outstanding items 참조). hardening 턴은 **프로덕션 코드 무변**(테스트만 추가, mutation 복원 exact 확인). 반영 상세는 `docs/daily_logs/2026-07-15/work_log.md`.

## Subject metadata

- **날짜**: 2026-07-15
- **요청자**: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 의심해줄래?" — CLAUDE.md §5 검증 트리거)
- **검증자**: 독립 AI(Claude Code, max effort)
- **대상 slice/artifact**: Writing stable context pointer 구현 — self-report `D2=A first→B`의 B 종결. 신규 `ContextPointer` + `writing/context_pointer.py`(projection·allowlist·wire), `CandidateClaim.related_context_pointers` additive, report parser membership 검증, 4 소비 표면 직렬화.
- **정본 계약 참조**:
  - `docs/system-contract-sot.md` **v1.6.92**(및 v1.6.91 계약 승인 row)
  - `docs/plans/05-writing-stable-context-pointer-decisions.md`(잠김 구현 계약 1~6, 양방향 회귀 매트릭스, sub-decision **P-i** origin 불변식 테이블)
  - `docs/plans/05-writing-self-report-decisions.md`(D2=A first→B, D5=B)
- **작업 소스**: working tree, **uncommitted**(commit되지 않음 — `git status`로 확인). 변경 15파일 + 신규 2파일(`context_pointer.py`, `tests/test_writing_context_pointer.py`).

## Scope

정본 계약이 요구하는 다음 표면을 1차 소스에서 재도출해 검증한다.

1. **계약 자체**(브리프 잠김 계약 1~6 + P-i sub-decision + 양방향 매트릭스 + SoT v1.6.91→92 row) — 계약 내부 모순, spec↔코드 literal 불일치, spec-silent-but-code-enforced gap 탐색.
2. **구현 코드** — `context_pointer.py`(projection·invariant·allowlist·wire), `models.py`(`ContextPointer`/`CandidateClaim`), `prompt.py`(노출 경계 opt-in), `report.py`(parser membership + service guard + template), `accept.py`·`gate_prompt.py`·`main.py`(소비 직렬화), `report_live_diag.py`(진단 allowlist).
3. **회귀 테스트** — `tests/test_writing_context_pointer.py`(신규 28) + 수정된 `test_writing.py`·`test_writing_report.py`·`test_writing_report_live_diag.py`. 각 테스트가 계약을 실제로 고정하는지(under-strict/over-strict 양방향, 경계값 매개변수화) 감사.
4. **불변 표면**(계약 6) — `loop_audit.py`·`audit_hash.py`·`gate.py`(Gate decision schema)가 미변경이며 pointer 누출이 없는지.
5. **스모ke/envelope** — worker가 보고한 1093/48/257·focused 28/17·`provider.calls==0`을 독립 재실행.

## Methodology

정본 스코프를 먼저 읽고(브리프 전문 + SoT v1.6.91/92 row), 그로부터 **경계 매트릭스**(should-fire / should-NOT-fire 분기 + 리터럴)를 구축한 뒤, 코드·테스트가 각 셀을 채우는지 추적. "코드를 먼저 보고 맞추는" 접근이 아니라 "계약이 요구하는 분기를 먼저 나열하고 빈 셀을 찾는" 접근.

재현에 쓴 정확한 명령:

```bash
# focused 신규 테스트
python3 -m pytest -q -p no:cacheprovider tests/test_writing_context_pointer.py

# 전체 스위트(envelope claim 재계산)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# 정적/구성 검증
python3 -m py_compile services/application/app/writing/context_pointer.py \
  services/application/app/writing/models.py services/application/app/writing/report.py \
  services/application/app/writing/prompt.py services/application/app/writing/accept.py \
  services/application/app/writing/gate_prompt.py services/application/app/writing/report_live_diag.py \
  services/application/app/main.py tests/test_writing_context_pointer.py
git diff --check
docker compose config --quiet
python3 -c "import services.application.app.main; from services.application.app.writing.context_pointer import context_pointer_of, package_pointers, pointer_wire, pointer_json; print('OK')"

# 호출처/직렬화지점/불변표면 grep
grep -rn "format_context_package(" --include=*.py services/
grep -rn "parse_report(" --include=*.py services/ tests/
grep -rn "candidate_claims\|related_context_pointers\|pointer_ids" --include=*.py services/application/app/writing/
```

모든 계약 주장은 1차 소스(코드 file:line, 테스트 file:line, smoke 출력)에서 재도출. worker의 요약은 신뢰하지 않고 재확인.

## Findings

### 1. 계약 — 착수 전 모순 포착·P-i 개정의 정당성

브리프 follow-up("세 origin non-empty 불변식을 구현 전 재확인, 빈값 가능하면 owner 승인 없이 허용 금지")이 실제로 모순을 잡았는지 독립 확인.

- **모순은 실재한다**(1차 소스 재확인): `context_search/service.py`의 memory projection은 `content_hash`를, candidate projection은 `version_id`·`content_hash`를 하드코딩 빈값으로 둔다(브리프 §"관측된 사실" 표가 `service.py:775-802`/`:885-912`/`:1057-1080`을 인용). `MemoryEntry`/`AnalysisCandidate` store에는 해당 필드가 없다 → 잠김 계약 1("네 non-empty string")은 memory/candidate를 pointable하게 만들 수 없다. 동시에 회귀 매트릭스 under-strict 행은 세 origin round-trip을 요구한다. **두 조건은 동시 만족 불가** — worker의 모순 주장은 사실이다.
- **개정 절차가 올바르다**: worker는 코드 작성 전 멈추고 4선택지 브리프(P-i~P-iv)를 만들어 owner 확인을 받았고(`work_log.md` User Decisions P-i, `05-writing-stable-context-pointer-decisions.md:87-123`), P-i(origin별 테이블)로 계약 1을 개정한 뒤 SoT v1.6.92 row·브리프 잠김 계약 1·CHANGELOG·self-report 결정문에 반영했다. CLAUDE.md §1(Think Before Coding) + "계약 내 모순은 silently 선택하지 않는다"를 정확히 이행.
- **각하 옵션의 근거도 타당**: P-iv(서버가 결측 필드 mint)가 D1=A "기존 authority 재사용"과 정면 충돌, P-iii(source-block 전용)이 매트릭스 under-strict 행 폐기를 요구, P-ii(균일 완화)가 source-block 실결함(빈 hash)을 조용히 통과시킨다는 각하 사유가 코드 관점에서 성립.

**계약 자기모순 탐색 결과**: 잔존 모순 없음. P-i 개정 후 (a) 계약 1 origin별 테이블 ↔ (b) 매트릭스 "세 origin 인용" ↔ (c) 실경로 빈값 구조 — 세 조건이 모두 양립한다.

### 2. 구현 — P-i origin 불변식 테이블 (계약 1)

`context_pointer.py:36-40` `_NON_EMPTY_FIELDS`:
- `SOURCE_BLOCK_COLLECTION → {document_id, version_id, content_hash}`
- `MEMORIES_COLLECTION → {document_id, version_id}`
- `CANDIDATES_COLLECTION → {document_id}`

`context_pointer.py:58-73` 검사 로직: 미지 collection → `_NON_EMPTY_FIELDS.get()`이 `None` → "not a pointable context origin" 거부(`:59-62`); 각 key에 대해 non-empty 집합이면 `value.strip()` 검사, 아니면 `value != ""` 검사(`:63-73`).

- **브리프 P-i 테이블과 정확히 일치**: source_blocks=4필드 non-empty / memory=hash만 `""` / candidate=version·hash `""`. collection 리터럴은 `indexing/service.py`·`context_search/service.py`에서 import해 2차 정의 없음(`:17-22`). literal 불일치 없음.
- **collection non-empty는 묵시적으로 강제**: collection이 `""`이면 dict lookup miss → 거부. 별도 분기 불필요, 정합.

### 3. 구현 — project_id 제외 + 사전 거부 (계약 2)

- `context_pointer.py:53-57`: `pointer.project_id != project_id`면 `InvalidContextPointer`. `package_pointers`(`:82-87`)가 `package.project_id`를 주입. macro+micro 전체 순회(`:86`).
- `report.py:94-97`: `enrich_metered`가 provider 호출 **전**에 `package_pointers(package)`를 만들고 `InvalidContextPointer`를 `InvalidCandidateReport`로 래핑. → cross-project·P-i 위반 item이 모델에 도달하지 않는다.
- `pointer_wire`(`:90-91`)는 `POINTER_KEYS` 4개만 출력 → `project_id`는 wire에 실리지 않는다.

### 4. 구현 — 노출 경계 opt-in (계약 3)

- `prompt.py:51-58`: `format_context_package(package, *, include_pointers=False)`. `:107-111` `_format_item`이 `include_pointers=True`일 때만 `- [label] {pointer_json} text`로 prefix.
- **호출처 grep(독립)**: `format_context_package(` 호출 4곳 — `gate_prompt.py:67`·`prompt.py:147`(generation)·`revise.py:119`은 **기본값**(pointer 미노출), `report.py:122-123`만 `include_pointers=True`. → generation/revise/Gate 평문 prompt는 무변. worker 주장("정확히 report 한 turn") 확인.

### 5. 구현 — parser exact membership (계약 5)

`report.py:155-169`:
- `_claim`(`:155-161`): `_exact(v, ("text","type","requires_gate_check","related_context_pointers"))` → required 4-key. `requires_gate_check` bool 검사. `_list(v["related_context_pointers"])`로 배열성 강제. claim 내 중복 `len(set(pointers)) != len(pointers)` 거부(`:159`).
- `_pointer`(`:162-169`): `_exact(v, POINTER_KEYS)`(exact 4-key) → 전 필드 string 검사(`:164-165`) → `ContextPointer` 구성 → `pointer not in allowed` membership(`:167-168`).
- `parse_report`(`:129-145`): `allowed = frozenset(allowed_pointers)`, 기본 `()` → fails-closed(`[]`만 통과). first·repair 양쪽 모두 동일 `allowed_pointers` 사용(`:103`, `:114`).
- `_list`(`:147-148`)·`_string`(`:150-152`)·`_exact`(`:153-154`): 비-배열·비-문자열·키 불일치를 모두 거부.

**이중 방어 확인**: P-i 위반 pointer(예: 빈 hash source-block)는 allowlist 구성 단계에서 이미 거부되므로 allowlist에 존재하지 않고, 따라서 parser membership에서도 결코 통과할 수 없다. projection(invariant)과 parse(membership)가 독립적으로 동일 경계를 닫는다.

### 6. 구현 — 소비 표면 4곳 동일 literal (계약 4)

- `main.py:2364-2367`(HTTP response), `accept.py:136-139`(advisory copy), `gate_prompt.py:54-60`(Gate 입력 candidate_claims) — 전부 `pointer_wire(p)`로 동일 직렬화.
- **Gate decision schema 무변 확인**: `gate.py:107-126` `parse_writing_gate_result`는 `{decision, findings, checked_constraints}`를 파싱하고 `_finding`(`:128-152`)은 `{type,severity,message,evidence,recommended_decision}`. claim/pointer와 완전 분리. `gate.py`는 diff에 없음(미변경). Gate가 candidate_claims에서 pointer를 **입력으로만** 받고 decision schema는 무변.

### 7. 불변 표면 — loop audit / audit_hash bodyless (계약 6)

- `loop_audit.py`: `pointer_ids`(`:42`, `:170`)는 run/stage-level package 요약이며 candidate_claims 미접촉. 미변경(diff에 없음).
- `audit_hash.py`: `package_pointer_ids`(`:33-41`)는 `source_ref_ids`·`snapshot_id`·`pointer.document_id`·`pointer.version_id`를 쓰는 package-level fingerprint. `finding_fingerprint`(`:23-30`)는 gate findings만 해시. **candidate_claims / related_context_pointers를 해시하는 경로 없음**. 미변경. → claim에 pointer가 추가돼도 audit hash 무변(bodyless 설계 정합).
- Mongo/Core SOT/Analysis candidate mint 쓰기 코드를 전혀 건드리지 않음(diff에 해당 서비스 없음). 쓰기 수 무변 확인.

### 8. 회귀 테스트 감사 (테스트 코드 = audit subject)

`tests/test_writing_context_pointer.py`(28 test / 17 subtest). 각 테스트가 계약 분기를 실제로 고정하는지, under-strict/over-strict 양방향이 있는지 확인:

| 계약 분기 | 테스트(file:line) | under | over | 비고 |
|---|---|---|---|---|
| 세 origin projection round-trip | `:103-114` | ✓ | — | 3 origin subTest |
| source-block 빈 version/hash/doc 거부 | `:116-126` | — | ✓ | 3 field subTest, fails-closed |
| memory/candidate 채워진 결측필드 거부 | `:128-139` | — | ✓ | P-iv(발명) 거부 |
| memory 빈 doc/version 거부 | `:141-148` | — | ✓ | 2 field subTest |
| 미지 collection 거부 | `:150-153` | — | ✓ | |
| cross-project projection 거부 | `:155-161` | — | ✓ | |
| allowlist macro+micro 커버 | `:163-168` | ✓ | — | |
| claim pointer round-trip(3 origin) | `:177-188` | ✓ | — | |
| 다중 pointer claim | `:190-196` | ✓ | — | |
| 근거 없는 claim `[]` 유효 | `:198-204` | — | ✓ | D3=A over-strict |
| missing pointer field 거부 | `:206-210` | — | ✓ | required≠empty |
| hallucinated 4필드 각각 거부 | `:212-219` | — | ✓ | 4 field subTest |
| 다른 package valid-looking 거부 | `:221-226` | — | ✓ | membership |
| rogue/missing key 거부 | `:228-237` | — | ✓ | exact-key |
| non-string field 거부 | `:239-243` | — | ✓ | type |
| claim 내 중복 거부 | `:245-249` | — | ✓ | |
| 두 claim 같은 item 허용 | `:251-259` | — | ✓ | per-claim dedup |
| 기본 빈 allowlist `[]`만 + pointer 거부 | `:261-267` | ✓ | ✓ | fails-closed 양방향 |
| fence 안 unknown pointer 거부 | `:269-280` | ✓ | ✓ | |
| service: extractor pointer 노출 + claim 보존 | `:284-296` | ✓ | — | prompt JSON + enriched |
| service: template pointer 지시문 | `:298-303` | ✓ | — | literal 확인 |
| service: cross-project provider 호출 0 | `:305-310` | — | ✓ | `provider.calls==0` 실측 |
| service: P-i 위반 provider 호출 0 | `:312-317` | — | ✓ | `provider.calls==0` 실측 |
| formatter 기본값 pointer 미노출 | `:323-330` | — | ✓ | D2=B 축 lock |
| report formatter pointer prefix | `:332-336` | ✓ | — | |
| label/section 무변 | `:338-343` | — | ✓ | |
| Gate prompt claim pointer | `:359-367` | ✓ | — | |
| accept advisory claim pointer + 4-key | `:369-374` | ✓ | — | project_id 제외 확인 |

**테스트 품질 평가**: (a) assertion이 계약을 고정(부산물 아님), (b) under-strict(버그 재도입 시 재실패) + over-strict(정상 case 거짓 거부 방지) 양방향 명시, (c) 경계값 매개변수화(4필드·3origin subTest), (d) public envelope/membership 대상. `provider.calls == 0`로 "provider 호출 전 거부"를 실측하는 점이 특히 견고. mutation-bite 재실증은 worker가 work_log에 기록(본 검증은 green 재현으로 실측, 코드 수정 없이 통과).

**추가 fixture 정정 확인(D3=A 귀결)**: `test_writing_report.py:21-25` `_payload` claim에 `related_context_pointers: []` 추가, `test_writing_report_live_diag.py:197-198` fixture 동일. pointer 없는 report JSON이 신 parser에서 invalid가 되는 것은 D3=A가 명시 수용한 계약 변경(report 비영속)이라 회귀가 아님 — 정당한 정정.

### 9. smoke / envelope 독립 재실행

- **focused**: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_context_pointer.py` → **28 passed, 17 subtests passed**. worker 주장과 정확히 일치.
- **full**: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1093 passed, 48 skipped, 257 subtests passed**(3건 TestClient collection warning은 pre-existing cosmetic). worker 주장(1093/48/257)과 정확히 일치.
- **baseline 산술 검증**: 본 환경 ES 미설치(48 skip). v1.6.90 ES-설치 baseline 1068/45/240에서 ES 3개를 빼면 1065/48/240 → +28 test / +17 subtest = **1093/48/257**. 산술 정합.
- `py_compile`(8 모듈+테스트) PASS, `git diff --check` clean, `docker compose config --quiet` PASS, `import services.application.app.main` + context_pointer import → 순환 없음 실측 PASS.

### 10. 패턴 스윕 (§4)

- **claim 직렬화 지점**: `related_context_pointers`를 wire에 싣는 곳은 정확히 4곳 — report parser(template/`_exact`)·HTTP(`main.py`)·Gate(`gate_prompt.py`)·accept(`accept.py`). 5번째 누출 지점 없음.
- **formatter opt-in**: `include_pointers=True`는 report 1곳만. generation/revise/Gate는 기본값.
- **loop audit claim 미접촉**: `loop_audit.py`/`loop_audit_mongo.py`는 `pointer_ids`(run/stage 요약)만, candidate_claims 미참조.

## Issues / Risks

### Blocking (계약 의무)

**없음.** 경계 매트릭스의 계약-요구 분기(should-fire / should-NOT-fire 전부)가 named regression test에 매핑되며, 빈 셀이 없다. spec↔코드 literal 불일치·계약 내부 모순·spec-silent-but-code-enforced gap 모두 발견되지 않았다. green bar와 별개로 매트릭스를 독립 추적한 결과다.

- "exact 4-key/string 검사"(SoT v1.6.92) → `_exact`+`_list`+string 검사로 코드에 존재, 테스트로 lock.
- "중복·rogue·cross-project·hallucinated 거부" → 각각 named test.
- "provider 호출 전 거부"(계약 2/P-i) → `provider.calls==0` 실측 테스트 2건.
- "Gate decision schema·loop audit bodyless 무변" → gate.py·loop_audit.py·audit_hash.py 미변경을 독립 확인.

### Hardening recommendations (비차단, 계약이 요구하지 않는 보강)

- **H1 — `related_context_pointers` 비-배열 전용 테스트 부재**: `_list`(`report.py:147-148`)가 `related_context_pointers`가 배열이 아닐 때(문자열/dict/숫자) "report field must be an array"로 거부하지만, 신규 필드에 대한 전용 회귀가 없다. 단 `_list`는 공유 헬퍼이며 `test_writing_report.py:205-209`(`test_fence_does_not_weaken_array_field_check`, `candidate_claims: "not-an-array"`)가 이미 이 메커니즘을 lock한다. 즉 slice 고유의 새 분기가 아니라 공유 메커니즘을 재사용한 것이므로 비차단. 보강 가치는 낮으나, pointer 특화 회귀 클래스에 `related_context_pointers: "x"` 케이스 1건을 추가하면 동일 클래스 내 자체 완결성이 올라간다.
- **H2 — generation/revise service-level no-pointer 테스트 부재**: D2=B 축(평문 prompt에 pointer 미노출)은 `test_default_formatter_shows_no_pointer`(`:323-330`)가 **formatter 경계**에서 lock하고, 호출처 grep이 3 service call site의 기본값 사용을 증명한다. 그러나 "generation service가 보낸 request의 context_package에 pointer JSON이 없다"는 end-to-end service-seam assertion은 없어서, 향후 누군가 generation 경로에 `include_pointers=True`를 끼워넣으면 formatter 단위 테스트는 잡지 못한다. formatter lock + grep으로 계약(계약 3 = formatter opt-in)은 충족되므로 비차단이나, service-seam lock을 추가하면 D2=B 축을 call-site 변경에도 견고하게 만든다.
- **H3 — 실 12B pointer 준수율 미검증( worker가 이미 명시한 honest caveat)**: 새 지시문("package item pointer를 정확히 복사, 없으면 `[]`")에 대한 12B의 실제 복사 정확도·`[]` 남용/hallucination 빈도는 sandbox에서 검증 불가하다(결정적 회귀는 fake provider 기반). 이는 slice 결함이 아니라 본질적 한계이며, worker가 work_log·HANDOFF에 owner 풀스택 후속으로 명시하고 실패 시 `scripts/diagnose_writing_report.py`가 exact 절을 보여줌을 확인. Gate quality baseline(21/21) 선례와 동일하게, 실패 재현 전까지는 prompt 미건드림이 올바른 태도.

## Verdict

**PASS(조건 없음).**

이유(load-bearing):
1. **경계 매트릭스에 빈 셀 없음** — 계약 1~6이 요구하는 should-fire/should-NOT-fire 분기 전부가 named regression test에 매핑되며, under-strict·over-strict 양방향과 경계값 매개변수화가 갖춰져 있다.
2. **착수 전 모순 포착·P-i 개정이 정당** — 잠김 계약 1("4 non-empty")과 실경로(memory/candidate 구조적 빈값)·매트릭스(세 origin 인용)의 3충 모순을 코드 전에 발견하고 owner 결정으로 계약을 개정한 절차가 CLAUDE.md §1에 정합. 개정 후 계약 자기모순 잔존 없음.
3. **spec↔코드 literal 일치 + 불변 표면 무변** — P-i 테이블·4-key wire·repair 1회·Gate decision schema `{decision,findings,checked_constraints}`·loop audit bodyless·쓰기 수 0이 모두 코드·diff에서 독립 확인.
4. **smoke/envelope 독립 재현** — 1093/48/257·focused 28/17·`provider.calls==0`·`py_compile`/`git diff --check`/`compose config`/import-cycle 없음을 직접 실행으로 실측(모두 worker 주장과 일치).
5. **fails-closed 이중 방어** — P-i invariant(projection)와 membership(parse)이 독립적으로 동일 경계를 닫아, 모델이 보지 못한/invariant 위반 pointer는 결코 통과할 수 없다.

3건 hardening(H1/H2/H3)은 모두 계약이 요구하지 않는 보강이거나 본질적 한계로, verdict에 영향을 주지 않는다.

## Outstanding items

- **미커밋 상태**: 본 slice는 working tree에 uncommitted로 존재(`git status` 확인). 오너가 커밋을 승인하면 별도 커밋 필요. 검증은 uncommitted 트리 기준.
- **실 12B pointer 준수 관측(오너 풀스택 후속)**: sandbox 검증 불가. 오너가 실 gateway로 `/writing/report` 또는 `/writing/revise-and-gate`를 돌려 `invalid_candidate_report` 502 증가 여부를 확인하고, 실패 시 `scripts/diagnose_writing_report.py`로 first+repair raw의 exact 절을 확인해야 한다. 재현 전 prompt 미건드림 권장(Gate quality 21/21 baseline 선례). — 이 검증이 PASS인 것과 무관하게, live 준수율은 별도 후속 과제.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# 1. 정본 계약 스코프 읽기(매트릭스 구축용)
#    docs/plans/05-writing-stable-context-pointer-decisions.md (잠김 계약 1~6 + P-i + 매트릭스)
#    docs/system-contract-sot.md v1.6.92 row

# 2. focused 신규 회귀 (28 test / 17 subtest 기대)
python3 -m pytest -q -p no:cacheprovider tests/test_writing_context_pointer.py

# 3. 전체 스위트 (1093 passed / 48 skipped / 257 subtests 기대)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# 4. 정적/구성/import 검증
python3 -m py_compile services/application/app/writing/{context_pointer,models,report,prompt,accept,gate_prompt,report_live_diag}.py services/application/app/main.py tests/test_writing_context_pointer.py
git diff --check
docker compose config --quiet
python3 -c "import services.application.app.main; from services.application.app.writing.context_pointer import context_pointer_of, package_pointers, pointer_wire, pointer_json"

# 5. 경계 추적 (호출처·직렬화지점·불변표면)
grep -rn "format_context_package(" --include="*.py" services/        # report만 include_pointers=True
grep -rn '"candidate_claims"\|related_context_pointers' --include="*.py" services/application/app/writing/  # 직렬화 4곳
grep -n "candidate_claims\|related_context_pointers\|pointer_ids" services/application/app/writing/loop_audit.py services/application/app/writing/audit_hash.py  # bodyless 확인
```
