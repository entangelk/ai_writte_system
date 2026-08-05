# Slice 8.2c 브리프 확정(N1~N6) + Phase 9(서비스 활동 로그) 신설 — 독립 검증

- **날짜**: 2026-08-05
- **의뢰자**: 오너("작업 AI가 작업한 거 확인 검증하고 의심하고 또 의심해줄래 … 문서 작업 완료, 커밋했다(c884151)")
- **검증자**: Claude Code (독립 세션 — 구현에 관여하지 않음)
- **검증 대상**: 커밋 `c884151` 단건. **코드 0줄, 문서 전용 슬라이스** — `docs/plans/08-2c-…`(Resolved + §N2-a) · `docs/plans/09-service-activity-log.md`(신설) · `docs/plans/README.md` · `README.md` · `HANDOFF.md` · `docs/daily_logs/2026-08-05/work_log.md`. HEAD `c884151`, 작업 트리 clean.
- **정본 참조**: `docs/system-contract-sot.md` v1.7.89 · `docs/plans/08-2c-project-name-history-decisions.md` · `docs/mongo_collections.md` §43/§43B · SoT 변경이력 v1.7.78(D8-5f)·v1.7.82(D8-6)
- **작업 출처**: 커밋 `c884151`(부모 `1f8b99c`). 실측 라벨은 `c956fa3`이며 `git merge-base --is-ancestor c956fa3 c884151` = true(도달 가능). 커밋됨(working tree 미사용).

---

## Scope

문서 슬라이스이므로 뮤테이션은 대상이 아니다(고친 코드가 없으니 물릴 가드도 없다). 대신 **문서가 코드·정본·가드와 일치하는가**를 잡는다.

1. **결정 기록 정합** — "오너 결정(2026-08-05)" 표의 N1~N6=A 와 각 항목 제목의 확정 표기가 충돌 없이 들어갔는가.
2. **§N2-a 실측 주장의 코드 부합** — 개명/제목 변경이 덮어쓰기라는 것, `system_events`가 코드 0줄이라는 것, `draft_versions`에 `created_at`/`user_id`가 없다는 것, purge 생존자가 `admin_audit_events`·`request_usage_ledger` 둘이라는 것.
3. **코드 인용(file:line) 정확성** — `service.py:450/458` · `models.py:78` · `purge_reconciler.py:49` · `main.py:3419` · N1=A "피회" 설계의 생명줄인 `_PROJECT_ID_FIELD`.
4. **A4 정반대 선례** — `llm_call_audits` 격리 / `access_grant_uses` fail-closed 특성화가 코드와 일치하는가.
5. **정본 일관** — D8-6(이름 미보존)·D8-5f v1.7.78(오염 금지)·현행 v1.7.89 인용, 그리고 "I2를 뒤집으면 D8-6이 무너진다"는 논리의 진위.
6. **인덱스·가드** — 계획 문서 수 99 · 브리프 81 무변 · operation 76 무변 · `test_docs_indexes.py` 12/10.
7. **분석 논리 정합** — "두 축이 직교한다(purge 생존 여부)" · "두 함정이 정반대 방향" 프레임.
8. **연기 항목의 의도적 미실시** — §43B 예외 포인터·SoT v1.7.90·L6 Resolved·CHANGELOG 가 구현 시점으로 올바르게 미뤄졌는가.
9. **부실 참조 스윕** — 다른 문서에 옛 상태("98개"·"8.2c 결정 대기"·v1.7.90)가 남지 않았는가.

## Methodology

검증자는 구현에 관여하지 않았고, 작업자의 주장을 1차 소스(코드·SoT·가드·디스크 카운트)에서 재도출했다. 뮤테이션 없음(코드 무변). 숫자 주장은 직접 grep/카운트로 재현.

```bash
git rev-parse --short HEAD          # c884151
git status --short                  # (비어있음)

# 코드 인용 재현
sed -n '445,470p' services/application/app/core_sot/service.py   # :450 rename_project, :458 rename_draft
sed -n '74,90p'  services/application/app/core_sot/models.py     # :78 DraftVersion (created_at/user_id 부재)
grep -rn "system_events" services/ scripts/ tests/ | grep -v "\.md:" | wc -l   # 0
sed -n '45,62p'  scripts/purge_reconciler.py                     # :49 _collections_scoped_by_project
grep -n  "_PROJECT_ID_FIELD =" scripts/purge_reconciler.py       # = "project_id"
grep -n  "llm_call_audit\|except Exception" services/application/app/observability/llm_call_scope.py  # :247 isolation boundary
sed -n '131,156p' services/application/app/auth/access_grants.py # record_use fail-closed 독스트링
sed -n '7,13p'    services/application/app/quota/ledger.py       # target_project_id (생존자)

# 인덱스·가드 재현
ls docs/plans/*.md | wc -l                                        # 100 (README.md 제외 = 99)
ls docs/plans/*-decisions.md | wc -l                              # 81
grep -cE "@app\.(get|post|patch|put|delete)\(" services/application/app/main.py  # 76
python3 -m pytest -q tests/test_docs_indexes.py                  # 12 passed / 10 subtests

# 부실 참조 스윕
grep -rn "98개" docs/ HANDOFF.md README.md
grep -rn "v1\.7\.90" docs/system-contract-sot.md
```

## Findings

### 1. 결정 기록 정합 — 합격
`08-2c-…` 상태가 `Awaiting owner decision` → `Resolved — N1~N6 전부 A로 확정(오너 2026-08-05)`로 바뀌었고, §"오너 결정" 표 6행(N1~N6)이 모두 A이며 각 N 제목에 `*(오너 확정: A)*`가 일관되게 붙었다. 본문 `### Decision needed` 소제목은 브리프 템플릿 잔향이나 Resolved 선례(08-3 등)와 같은 양식이라 충돌 아니다.

### 2. §N2-a 실측 — 코드와 정확히 일치 (하중받는 주장 전부)
| 실측 주장 | 재도출 | 결과 |
|---|---|---|
| 개명 = `replace(project,name=…)`→`put_project` 덮어쓰기 | `service.py:450-456` | ✓ |
| draft 제목 변경 = 같은 덮어쓰기 | `service.py:458-467` | ✓ |
| `system_events` = 코드 0줄 | grep 0건 (services/scripts/tests, .md 제외) | ✓ |
| `draft_versions`에 `created_at`/`user_id` 부재 | `models.py:78` DraftVersion 필드 = id·project_id·draft_id·version_number·snapshot_id·idempotency_key | ✓ |
| purge 생존자 = `admin_audit_events`·`request_usage_ledger` | SoT v1.7.82(tombstone, `target_project_id`, 이름·owner·본문 미보존) · `ledger.py:9-12`(행은 `target_project_id`, "이름이 project_id가 아닌 것이 핵심") | ✓ |
| reconciler가 `project_id` 보유 컬렉션을 DB에서 발견·sweep | `purge_reconciler.py:49-58` `_collections_scoped_by_project`, 하드코딩 없음 | ✓ |

### 3. 코드 인용(file:line) — 현행 코드 기준 정확
- `service.py:450`=`rename_project`, `:458`=`rename_draft` ✓
- `models.py:78`=`DraftVersion` ✓
- `purge_reconciler.py:49`=`_collections_scoped_by_project` ✓
- `main.py:3419` = **현행(c884151)에서 `async def rename_project(`** ✓ (독자가 보는 코드에 맞음)
- **N1=A 설계의 생명줄 확인**: `_PROJECT_ID_FIELD = "project_id"`(`purge_reconciler.py:43`). reconciler는 `project_id` **필드**를 찾지 `_id`를 보지 않으므로, `_id`=project id 만 있고 `project_id` 필드가 없는 컬렉션은 발견되지 않아 생존한다 — "구조적으로 피한다" 설계가 성립. 회귀#4("누군가 `project_id`를 더하면 실패한다")도 이 메커니즘과 정확히 부합.

### 4. A4 정반대 선례 — 코드 독스트링이 한 글자로 확인
- `llm_call_audits` 격리: `llm_call_scope.py:247` `except Exception: # noqa: BLE001 — deliberate isolation boundary` ✓
- `access_grant_uses` fail-closed: `access_grants.py:136-143` `record_use` 독스트링이 *"The caller does **not** swallow failures… This is the opposite of the LLM-call audit, which is isolated precisely because **it** is not load-bearing for a security boundary"* — 문서의 "llm_call_audits 격리(보안 하중 없음) / access_grant_uses fail-closed(하중 있음)"과 한 글자 단위 일치 ✓

### 5. 정본 일관 + 분석 논리 — 합격
- D8-6 "purge는 이름을 남기지 않는다": SoT v1.7.82가 명시(tombstone, 이름·owner·본문 미보존, TTL 없음) ✓
- "I2(활동 로그는 삭제 계약의 예외가 아니다)를 뒤집으면 D8-6이 무너진다": 논리 성립 — 활동 로그를 purge 생존으로 만들면 개명·제목·저장 이벤트 전체가 삭제 예외로 승격돼 D8-6의 "이름 미보존"을 사실상 폐기.
- "두 축 직교(축1=project 자식→sweep됨 / 축2=purge 생존→최소면적)"와 "두 함정 정반대(name_history는 `project_id` **없어야**, 활동 로그는 **있어야**)": `_PROJECT_ID_FIELD="project_id"` 메커니즘과 `ledger.py`·`access_grants.py` 독스트링으로 입증 ✓

### 6. 인덱스·가드 — 합격
- 계획 문서 수 99(디스크 100 − `README.md`)·브리프 81 무변(신규 파일이 `*-decisions.md` 아님)·operation 76(`@app.{verb}` 카운트=76) ✓
- `test_docs_indexes.py` = **12 passed / 10 subtests** (실재실행, 주장과 오차 없음) ✓

### 7. 연기 항목 의도적 미실시 — 합격
`mongo_collections.md` §43B 예외 포인터(신규 `project_name_history` 분) 부재 · SoT v1.7.90 부재(현행 89) · `08-2-…` L6 미갱신 · CHANGELOG 미갱신 — 전부 "구현과 함께 간다"는 작업자 주장과 일치. 지금 쓰면 정본이 코드가 아직 하지 않는 동작을 서술하게 된다는 근거도 타당.

### 8. 부실 참조 스윕 — 클린
"98개" 계획문서수 잔재 없음(매칭은 무관한 옛 로그의 "398개" 1건) · v1.7.90 부재 · §43B `project_name_history` 포인터 부재 · "8.2c 오너 결정 대기" 잔재 없음(HANDOFF "Owner Decisions Needed"에서 제거 → "결정 완료"로 이동, 중복 없음) ✓

## Issues / Risks

### Blocking (계약 의무 위반)
**없음.** 결정 기록·코드 인용·정본 일관·인덱스 가드·분석 논리 어느 것도 계약 위반이 없다.

### Hardening recommendations (비차단)
1. **`main.py` 줄 수 "6,074"가 71줄 부실** — 실측 라벨 `c956fa3`에서는 6,074가 맞았으나, `c956fa3..c884151` 사이 `4cfd950`(GET /me/quota)가 `main.py`에 71줄을 더해 현행은 **6,145**. `09-service-activity-log.md` §1이 "HEAD c956fa3"으로 범위를 명시해 방어되나, §6의 "지금…6,074줄"은 현재시제라 71줄 어긋난다. → 권고: c956fa3 참조를 빼고 현행 줄 수로 적거나 "측정 시점 6,074(현행 6,145)" 둘 다 기재.
2. **`main.py:3419` 인용은 현행에 정확하나 라벨과 미세 불일치** — 현행 3419 = `rename_project`(정확)이나 c956fa3 시점 3419 = `issue_access_grant`. 독자가 보는 코드에는 맞으므로 기능 영향 없고, 라벨 정리만으로 닫힘.

둘 다 `c956fa3` 실측 라벨을 건드려 둔 채 그 사이 `main.py`가 바뀐 데서 온 표면적 기준-불일치. 결론·구현에 영향 없음.

## Verdict — 합격

문서 슬라이스의 하중받는 주장(N1~N6 결정 기록 · §N2-a 실측 · A4 정반대 선례 · "I2 뒤집으면 D8-6 붕괴" 논리 · 인덱스/가드 정합)이 **코드·SoT·독스트링에서 한 건 빠짐없이 재도출**됐다. 특히 §N2-a의 축1/축2 분석이 `ledger.py:9-12`·`access_grants.py:136-143`이 이미 서술하는 메커니즘 위에 서 있고, N1=A "피회" 설계가 `_PROJECT_ID_FIELD="project_id"`로 입증되는 점은 다음 작업자(Phase 9 착수자)가 틀리기 어렵게 한다. Blocking 0, hardening 2건(모두 표면적 부실). **8.2c 구현 착수 가능.**

## Outstanding items

- **작업 트리 clean, 커밋됨(`c884151`)**. 본 검증은 읽기 전용(뮤테이션 없음).
- Hardening 2건은 다음 8.2c 구현 커밋에서 `main.py` 관련 숫자를 한 번 더듬으면 닫힌다 (이 검증 기록과 함께 반영 권장).
- 본 검증 기록 추가로 `docs/verifications/README.md`(42일치·218건, 판정 분포 08-05 기준·합격 146)·`README.md`(218건/42일치)·`docs/README.md`(218건)의 숫자 주장을 같이 올렸고 `test_docs_indexes.py`가 green임을 확인했다.

## Reproduction

```bash
git rev-parse --short HEAD                                      # c884151
# 위 Methodology 의 명령 시퀀스가 곧 재현이다.
python3 -m pytest -q tests/test_docs_indexes.py                 # 12 passed / 10 subtests
```
