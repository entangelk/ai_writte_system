# 독립 검증 — D8-6 잔여 purge reconciler (commit 20847eb + 66f884e + 10ff8d6)

## Subject metadata

- **날짜**: 2026-08-02
- **요청자**: 오너("다음작업 검증해줘. 개발로 돌아와 D8-6 잔여 중 결정이 필요 없는 쪽을 끝냈습니다… 결함이 기록보다 나빴습니다")
- **검증자**: Claude(독립 세션, max 노력) — 시행자 세션이 아님.
- **대상 슬라이스**: D8-6 잔여 — `scripts/purge_reconciler.py`(고아 project_id 잔류 데이터 정리, dry-run 기본, `--apply`만 삭제, 컬렉션 DB 발견, 삭제 후 enqueue) + `tests/test_purge_reconciler.py`(6셀). 그리고 시행자가 보고한 **기존 결함 진단**: `POST /admin/projects/{id}/purge`의 derived 단계 mongo 장애 → 503 → 재시도 불가(core_sot 비어 404).
- **정규 스펙**: `docs/system-contract-sot.md` v1.7.74(D8-6d — "부분 실패 시 멱등 재시도" *거짓 단언*, 본 검증이 확증) · D5(부분 삭제 금지, v1.7.49 "부분 삭제는 조용한 고아") · `docs/verifications/2026-08-01/d8_6d_purge_endpoint.md`(line 77 — partial-failure 503→404 시나리오를 "ghost"로 분류, 시행자가 정정).
- **검증 대상 출처**: `20847eb`(reconciler + 테스트) · `66f884e`(거짓 가드 정정 — setUp에 outbox entry 추가) · `10ff8d6`(문서). HEAD = `10ff8d6`. push 안 됨.

## Scope

1. **★ 시행자의 결함 진단이 사실인가** — (a) derived 503→재시도 시 core_sot NotFound→404 (b) 잔류가 D5 위반(llm_call_audits 프롬프트·writing_drafts_scratch 원고 후보). 코드로 반증 시도.
2. **★ 08-01 검증과의 정합** — 종전 검증이 이 시나리오를 놓쳤는지, "ghost" 판단을 시행자가 정정한 것이 옳은지.
3. **거짓 가드 자기 고백의 진실성** — 66f884e(setUp outbox entry)가 없으면 순서 뮤테이션이 통과하는가(거짓 가드), 있으면 잡히는가.
4. **양방향 뮤테이션 3종 재현** — 순서 뒤집기 / live 판정 제거 / 컬렉션 발견 하드코딩.
5. **reconciler의 4가지 잠금** — under-strict(고아 삭제)·over-strict(live 보존)·dry-run 기본·로스터 안 믿음.
6. **회귀 전량** — 1848 passed 독립 재현.
7. **★ 권위 소스 정정 누락** — 시행자가 발견한 결함의 거짓 단언 원천(SoT/docstring)이 정정됐는지.

## Methodology

- 결함 진단: endpoint 핸들러(`main.py:2807-2819`) + `CoreSotService.purge_project`(`service.py:933-938`, `_require_project`→NotFound `service.py:956`) + mongo `_purge_project`(`mongo_repository.py:189-202`) + derived purge 예외 처리(`analysis/mongo_repository.py:237-241`) + 전역 503 handler(`main.py:1228-1230`) 교차 독해.
- D5: SoT v1.7.49/71/74 changelog + llm_call_audit(v1.7.41 "프롬프트 감사")·writing_drafts_scratch(scratch_mongo "candidate drafts") 컬렉션 내용 확인.
- 08-01 정합: `docs/verifications/2026-08-01/d8_6d_purge_endpoint.md` line 77/94 직독.
- 뮤테이션(작업 트리 일시 변이 → re-fail → `git checkout`, CLAUDE.md §6): Edit로 변이 → `git diff` 의도 확인 → `pytest tests/test_purge_reconciler.py -v` → `git checkout --` 복구 → `git status --short` clean 확인. 거짓 가드 재현은 66f884e(setUp entry)를 되돌리는 2파일 변이로.
- 회귀: `docker compose -f docker-compose.test.yml up -d test-mongo`(127.0.0.1:27020) → `python3 -m pytest -q`.
- 권위 소스: `git show 10ff8d6 --stat`(SoT/main.py 미건드림 확인) + docstring/SoT grep.
- boundary matrix: [should fire] 고아 발견·고아 삭제·"모르는 컬렉션" 발견·삭제 후 enqueue 순서 · [should NOT fire] live 삭제·dry-run 기본 위반.

## Findings

### 1. ★ 시행자의 결함 진단 — 둘 다 사실 (코드 확증)

**(a) derived 503 → 재시도 불가(404).** `CoreSotService.purge_project`(`service.py:933-938`)는 `_require_project`를 먼저 부르고, 이것은 project 행이 없으면 `raise NotFound`(`service.py:956`)한다. endpoint 핸들러(`main.py:2807-2810`)는 `try`가 core_sot만 감싸고 derived 8종은 try **밖**이다. 시나리오: ①첫 호출 `_require_project` 통과 → `_repo.purge_project`(8컬렉션+project 행) 성공 → derived 단계 mongo 장애 → PyMongoError 전파(derived purge는 `analysis/mongo_repository.py:237-241`가 `delete_many`만, 삼키지 않음) → 전역 handler(`main.py:1228-1230`) → **503**. ②재시도 `_require_project` → project 행 이미 삭제 → **NotFound → 404**. endpoint docstring(`main.py:2806`)·SoT v1.7.74 changelog의 "재시도(멱등)"는 **derived 단계 실패에는 성립하지 않는다**. 시행자 진단 정확.

**(b) 잔류 = D5 위반.** `llm_call_audit`·`writing_scratch`는 derived 8종(`main.py:2816-2818`)에 포함. core_sot(선행) 성공 후 derived 실패 시 이들이 남는다. `llm_call_audits`는 LLM 호출의 감사 레코드(프롬프트 포함, v1.7.41), `writing_drafts_scratch`는 원고 후보(scratch_mongo). **파기 요청받은 데이터가 남음** = SoT v1.7.49 "부분 삭제는 조용한 고아" 금지 위반. 시행자 진단 정확.

### 2. ★ 08-01 검증은 이 시나리오를 놓치지 않았다 — "ghost" 판단을 시행자가 정정

`d8_6d_purge_endpoint.md` line 77이 이 시나리오를 정확히 기술: "partial-failure 503→재시도→404… core_sot 커밋 후 derived 완료 전 mongo 다운… 잔류 derived는 대부분 **query-도달 불가 ghost**". 08-01은 이것을 "완전 멱등 재시구/reconciler" hardening #2로 남겼고, **본 슬라이스가 그 예견된 hardening의 실행**이다. 시행자가 "08-01 기록은 잔류물을 ghost로 판단했는데 동의하지 않았다"고 한 것도 정확 — 08-01의 "query-도달 불가 ghost"가 `llm_call_audits`(감사 조회 도달)·`writing_drafts_scratch`(복구 도달)에는 성립하지 않으므로 D5 위반으로 정정한 것이 옳다. 08-01은 또한 "D5 완성" 과대 표현(line 66/78)과 derived wiring 회귀 부재(조건부 합격 사유, line 72)도 이미 지적했다.

### 3. ★ 거짓 가드 자기 고백 — 진실 (뮤테이션으로 재현)

시행자의 "처음 쓴 순서 셀에 뮤테이션(enqueue 먼저)이 통과했다"는 고백을 독립 재현:
- **66f884e 되돌림**(setUp의 outbox entry 제거) + 순서 뒤집기 → 순서 셀이 **PASSED**(거짓 가드). 원인: `_collections_scoped_by_project`가 apply 루프 *전*에 발견하는데, outbox가 비어 있으면 발견 대상에서 빠져 삭제 대상이 아니므로 순서가 무의미.
- **66f884e 적용**(현재 HEAD) + 순서 뒤집기 → 순서 셀 **FAILED**(잠김, 뮤테이션 1).

즉 66f884e가 진짜로 셀을 살렸음이 증명됐다. 시행자의 "테스트가 통과한다로는 그 테스트가 무엇을 잡는지 알 수 없다" 자기 반성은 정확하고, 그 교훈을 work_log에 남긴 것은 모범적이다.

### 4. 양방향 뮤테이션 3종 — 전부 잡힘 (독립 재현)

| 변이 | re-fail한 셀 | 비고 |
|---|---|---|
| 순서 뒤집기(enqueue 먼저) | `test_the_enqueued_purge_event_survives_the_sweep` (stdout: `_purge`가 outbox project_purged까지 삭제, deleted 2) | under-strict ✓ |
| live 판정 제거(`_orphan_project_ids`) | `test_the_orphan...`(고아 판정) + 순서 셀의 live 보존 보조 단정(line 219). stdout: `purged: {..., "live": {"llm_call_audits": 1}}` | over-strict ✓ — 멀쩡한 원고 삭제 방향 잡힘 |
| 컬렉션 발견 하드코딩 | `test_a_collection_the_script_never_heard_of`(모르는 컬렉션) **+ 순서 셀**(로스터가 outbox 빠져 기존 entry 잔류) | 로스터 안 믿음 ✓ |

세 변이 모두 가드가 의도 결함을 잡는다. **뮤테이션 3의 정정**: 시행자 보고는 "'모르는 컬렉션' 셀만"이라 했으나 실제로는 순서 셀도 같이 잡힌다(하드코딩이 `index_sync_outbox`를 빼 기존 stale entry가 안 지워지기 때문). 보고보다 가드가 **더 넓게** 잠근다(과소 진술이지 결함 아님).

### 5. reconciler 4잠금 + 회귀 — 합격

under-strict(고아 삭제)·over-strict(live 보존, 뮤테이션 2로 확증)·dry-run 기본(`test_the_default_run_changes_nothing`·`test_without_apply_nothing_is_written`)·로스터 안 믿음(`_collections_scoped_by_project`가 `find_one`로 DB 발견, 하드코딩 뮤테이션으로 확증). 회귀 **1848 passed / 4 skipped / 1559 subtests / 108.10s**, exit 0 — 시행자 보고 그대로, 회귀 0건. CLI 통과(`PurgeReconcilerCommandTest`). endpoint 순서 미변경(`git diff 6380b4c..HEAD -- main.py` purge 블록 무변). HANDOFF에 3지선다(ⓐ현행유지+reconciler / ⓑderived먼저-"살아있는데 기억만 없는 project"위험 / ⓒcore_sot 멱등화-404계약변경) 등재 확인.

## Issues / Risks

### Blocking (계약 의무)

1. **★ 권위 소스의 거짓 단언이 정정되지 않았다.** 시행자가 결함을 발견·코드 확증·reconciler로 수습·HANDOFF에 정정 기록·오너 결정 3지선다로 올렸으나 — **SoT v1.7.74 changelog(`system-contract-sot.md:37`, "부분 실패… 멱등 재시도")와 endpoint docstring(`main.py:2806`, "클라이언트 재시도(멱등)")의 거짓 단언 자체는 남아 있다.** 이번 슬라이스 3커밋은 SoT/main.py를 전혀 안 건드렸다. 미래 독자가 SoT/docstring을 읽으면 "derived 실패해도 재시도하면 된다"고 오독한다(verification 가이드 "Spec ↔ implementation consistency" 위반). 시행자가 오너 결정(ⓐⓑⓒ) 이후로 정정을 미룬 것은 합리적(어느 쪽이 결정되냐에 따라 정정 내용이 달라지므로)이나, **현재 권위 소스는 코드와 어긋나는 거짓 상태**다. 최소한 "재시도(멱등)"에 취소선/주의를 달거나, 결정 시 본문/docstring을 그 결정에 맞게 개정해야 한다. → 조건부 합격 사유.

### Hardening recommendations (비차단)

2. **뮤테이션 3 보고의 미세 과소 진술** — 시행자는 "컬렉션 발견 하드코딩 → 모르는 컬렉션 셀만"이라 했으나, 실제로는 순서 셀도 같이 잡힌다. 가드가 보고보다 강하므로 결함이 아니나, work_log의 뮤테이션 표가 실제 re-fail 셀보다 좁게 적혀 있다. 표의 정확도 보강 권장.
3. **dry-run 출력에 live project 카운트 미포함** — summary JSON이 `orphan_project_ids`·`orphans`는 보고하나, "조사 대상 live project 수"는 없다. 운영자가 reconciler를 돌릴 때 "내 live 데이터가 N개 있고 그건 안 건드린다"는 확인이 summary만으로는 안 된다. 보강 후보(현재 요구사항 아님).

## Verdict

**조건부 합격.** reconciler 자체는 견고하다 — 시행자의 결함 진단(503→404 재시도 불가, D5 위반)은 코드로 확증됐고, 거짓 가드 자기 고백은 뮤테이션으로 재현됐으며 정정(66f884e)이 진짜로 셀을 살렸음이 증명됐고, 양방향 뮤테이션 3종이 전부 잡히며, 회귀 1848이 재현됐다. 08-01 검증과의 정합도 완전하다(이 슬라이스가 예견된 hardening #2의 실행).

**조건(Blocking #1)**: 오너 결정 3지선다(ⓐⓑⓒ) 중 하나가 확정되면, 그 결정에 맞춰 **SoT v1.7.74 changelog의 "멱등 재시도"와 endpoint docstring의 "재시도(멱등)" 거짓 단언을 정정**해야 한다. 현재 권위 소스가 코드와 어긋나 있다. 결정 전이라면 최소한 "재시도 불가(수습은 reconciler)"로 주의를 다는 즉시 정정이 바람직하다.

## Outstanding items

1. **오너 결정 3지선다 대기** — purge endpoint 재시도 가능성(ⓐ 현행유지+reconciler / ⓑ derived 먼저 / ⓒ core_sot 멱등화=404 계약 변경). HANDOFF line 171. ⓑ·ⓒ는 데이터 안전성·공개 계약 트레이드오프. "급하지 않다"(발생 조건 드물고 수습 수단 생김).
2. **Blocking #1의 정정** — 위 결정에 따라 SoT/docstring 개정.
3. **D8-6 마지막 잔여**: purge 감사 로그(저장 위치·필드·조회 표면이 사실상 결정 사항 → 작은 브리프 선행 권장).
4. **08-01 조건부 합격 조건(derived purge wiring 회귀)**은 `_PurgeSpy`로 이미 해소됐다(HANDOFF line 44) — 본 슬라이스와 무관, 확인만.
5. push 안 됨(커밋 3개 로컬 main).

## Reproduction

```bash
# 1. 결함 진단 (코드 경로)
grep -n "_require_project\|raise NotFound" services/application/app/core_sot/service.py  # 937, 956
sed -n '2807,2819p' services/application/app/main.py   # try = core_sot만

# 2. 거짓 가드 재현 (66f884e 되돌림 + 순서 뒤집기 → 순서 셀 PASSED)
#    Edit test setUp: index_sync_outbox insert 제거
#    Edit script: enqueue를 _purge 전으로
#    pytest tests/test_purge_reconciler.py::PurgeReconcilerCommandTest::test_the_enqueued_purge_event_survives_the_sweep → PASSED (거짓)
#    git checkout -- scripts/purge_reconciler.py tests/test_purge_reconciler.py

# 3. 뮤테이션 3종 (현재 HEAD에서 각각 → re-fail → checkout)

# 4. 회귀
docker compose -f docker-compose.test.yml up -d test-mongo
python3 -m pytest -q      # 1848 passed / 4 skipped / 1559 subtests
```
