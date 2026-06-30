# Slice 1 draft version export 독립 검증

## Subject metadata

- 검증일: 2026-06-30
- 요청자: entangelk(사용자, "작업 AI가 작업한 분에 대해서 검증하고 의심하고 또 의심해줄래?")
- 검증자: Claude(독립 검증 — 작업자 주장을 그대로 신뢰하지 않고 1차 소스에서 재도출)
- 검증 대상 slice/artifact: Slice 1 draft version export — `DraftVersionExport` model, `CoreSotService.export_draft_version()`, `GET /projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export?format=txt|markdown` endpoint, 신규 회귀 11개(도메인 6 + HTTP 5)
- 정본 계약 참조:
  - `docs/system-contract-sot.md` v1.6.14(changelog `docs/system-contract-sot.md:36`, Phase 0 `:293-294`, Phase 1 `:303`, 문서 역할 `:63`)
  - archive read-allowed 정책: `:136-141`(특히 `:137` "읽기...허용") + changelog v1.5 `:52`
- 검증 대상 작업 출처: working tree, **uncommitted**(사용자가 커밋을 요청하지 않았음). `HEAD = b2a530c`.

## Scope

1. **계약 자체 일관성**: Phase 0 ↔ Phase 1 export clause ↔ changelog v1.6.14 간 모순·literal 불일치 탐지.
2. **boundary matrix**: 계약에 명시된 모든 should-fire / should-NOT-fire 분기와 literal(content_type, 확장자, 상태코드, 추적 필드명)을 매핑하고 빈 칸을 찾는다.
3. **구현 코드**: `export_draft_version()`(service) → `get_draft_version()`(service) 의존 경로, `_EXPORT_FORMATS` 화이트리스트, endpoint 예외 매핑.
4. **회귀 테스트**: 신규 11개가 boundary matrix의 어느 분기를 pin하는지 추적; under-strict/over-strict guard 존재; 공개 surface(envelope/body) 단정 여부.
5. **envelope 카운트 재도출**: 실제 HTTP 응답 필드를 직접 호출해 work log의 "325 통과(35 skip)"와 envelope claim을 독립 재계산.

## Methodology

1. `git diff services/application/app/core_sot/{models,service}.py services/application/app/main.py tests/test_{core_sot,application_api}.py docs/system-contract-sot.md`로 전체 변경분 독해.
2. SoT에서 export clause(`:303`)와 archive read-allowed(`:136-141`, `:52`)를 end-to-end 정독하고, `grep "§113\|§115"`로 테스트 docstring이 인용한 조항 번호의 존재를 독립 확인.
3. `export_draft_version`이 의존하는 `get_draft_version`(`service.py:232-249`)과 `_require_project`/`_require_draft`(`service.py:419-429`)를 읽어 archive/cross-project/missing 동작의 실제 구현 위치를 추적.
4. `TestClient(create_app())`로 실제 endpoint를 호출해 txt/markdown 양쪽 envelope 전체 필드·body 일치·filename 패턴·unsupported(missing/cross 포함 6종 변형) 상태코드를 독립 재도출.
5. archive 경로 독립 실행: `DELETE /projects/{id}`(project archive)와 `DELETE /projects/{id}/drafts/{draft_id}`(draft archive) 이후 export가 실제로 200인지 확인.
6. 재실행: `python3 -m unittest tests.test_core_sot tests.test_application_api -v`(66), `python3 -m unittest discover tests`(325, skip 35).

## Findings

### F0. 재실행 — 작업자 주장과 일치

- `python3 -m unittest tests.test_core_sot tests.test_application_api -v` → **Ran 66 tests OK**. 신규 11개(`CoreSotExportTest` 6 + `ApplicationApiTest` export 5) 모두 green.
- `python3 -m unittest discover tests` → **Ran 325 tests, OK (skipped=35)**. 작업자 주장(314→325, skip 35)과 정확히 일치. 이전 v1.6.13 검증 시 314 → +11 = 325로 정합.
- 35 skip은 Mongo 미연결(`CORE_SOT_MONGO_URI` 없음)로 일관.

### F1. 계약 자체 일관성 — 무모순

세 곳(Phase 0 `:293-294`, Phase 1 `:303`, changelog `:36`)의 export 서술을 교차 대조:

| 주장 | Phase 0 | Phase 1 | changelog | 코드 |
|---|---|---|---|---|
| 형식 = plain text + Markdown | `:293` | `:303` | `:36` | service.py:58-59 |
| DOCX/PDF/EPUB 후속 | `:294` | (미언급, 모순 아님) | (미언급) | — |
| body = raw_text verbatim | — | `:303` | `:36` | service.py:270 |
| AI metadata 미주입 | — | `:303` | `:36` | service.py:270 |
| 두 형식 body 동일 | — | `:303` | `:36` | service.py:270 (format 무관) |
| format은 content_type/확장자만 | — | `:303` | `:36` | service.py:264-269 |
| 추적 필드 version_id/number/snapshot_id/content_hash | — | `:303` | `:36`("version 추적 필드") | service.py:273-276 |
| unsupported 400 | — | `:303` | `:36` | service.py:259-260, main.py:336 |
| missing/cross-project 404 | — | `:303` | `:36` | service.py:240-243, main.py:338 |
| archive 허용 | — | `:303`("archive는 read를 막지 않으므로") | `:36` | get_draft_version archived 미검사 |

내부 모순 없음. Phase 0의 "첫 export 형식은 ... 확정(`:293`)"과 이전 "export 형식 ... 미확정" 삭제(`:294`)도 정합. 계약은 blocking inconsistency 없이 자체 정합.

### F2. body verbatim + AI metadata 미주입 — 코드·실행 양쪽으로 확인

- `service.py:270` `body=detail.snapshot.raw_text` — snapshot의 raw_text를 그대로 대입. 변환·strip·metadata 주입 경로가 코드에 존재하지 않는다.
- 독립 실행(raw_text에 마크다운 헤더 `#` + `---` 분리자 포함): txt/markdown 양쪽 `body`가 입력 raw_text와 **문자열 동일**(`body equality across formats === True`).
- AI metadata 미주입은 HTTP 회귀 `assertNotIn("---\nanalysis", body["body"])`(`tests/test_application_api.py`)로 표현되지만, 사실상 F3(body == raw_text verbatim) 단정이 더 강하게 흡수한다 — body가 raw_text와 정확히 같으면 metadata가 들어갈 틈이 없다.

### F3. 두 형식 body 동일 — format 무관 raw_text

- `service.py:264-270`: `content_type, extension = _EXPORT_FORMATS[fmt]`만 fmt에서 오고, `body=detail.snapshot.raw_text`는 fmt에 무관. 마크다운 합성/제거 분기가 없다.
- 독립 실행: txt.body == md.body == raw_text(**True**). filename(`draft-1-v1.txt` / `draft-1-v1.md`)·content_type만 차이.

### F4. format은 content_type/확장자만 — 화이트리스트 엄격

- `service.py:56-60` `_EXPORT_FORMATS = {"txt": (...,"txt"), "markdown": (...,"md")}`. 딕셔너리 키 외에는 `service.py:259-260` `UnsupportedExportFormat`.
- 독립 실행으로 **6종 변형** 탐색: `pdf` 400, `html` 400, `md`(alias 시도) 400, `MARKDOWN`(대소문자) 400, `TXT`(대소문자) 400. alias 허용 없음, 대소문자 구분 — 정확한 화이트리스트. 매핑은 `txt→.txt`/`markdown→.md`로 계약과 일치.

### F5. 추적 필드 — envelope·model 양쪽에 4개 전부

- model `models.py:111-120` `DraftVersionExport`는 `version_id`/`version_number`/`snapshot_id`/`content_hash`를 모두 필드로 가짐.
- service `service.py:273-276`가 각각 `version.id`/`version.version_number`/`detail.snapshot.id`/`detail.snapshot.content_hash`로 채운다.
- endpoint `main.py:347-350` envelope에 4개를 전부 노출. 독립 실행 응답에 4개 전부 확인.

### F6. unsupported 400 / missing·cross-project 404

- unsupported: `service.py:259-260` → `main.py:336` `HTTPException(400)`.
- missing version: `get_draft_version` `service.py:237-243`(`get_version` None 또는 `version.project_id != project_id or version.draft_id != draft_id` → `NotFound`) → `main.py:338` `HTTPException(404)`.
- cross-project: 동일 `service.py:240` 검사. 독립 실행 project_b 컨텍스트에서 project_a version → 404 확인.

### F7. requested version not latest — get_draft_version 재사용으로 보장

- `export_draft_version`는 `service.py:261-263`에서 `get_draft_version(version_id=...)`에 요청 version_id를 그대로 전달. "latest 조회" 분기가 없다. 따라서 v1 요청 시 v2 body가 나올 경로가 없다. 회귀 `test_export_picks_the_requested_version_not_the_latest`가 under-strict(latest 반환)를 잠근다.

### F8. archive survives — get_draft_version이 archived를 검사하지 않는다

- `get_draft_version`(`service.py:232-249`)은 `_require_project`/`_require_draft`만 호출하고, 둘 다(`service.py:419-429`) archived 플래그를 검사하지 않는다. archived 차단은 `save_draft`→`_require_active_project_and_draft`(`service.py:431-437`)에만 있다. export는 read이므로 archive read-allowed 정책(SoT `:137`, v1.5 `:52`)과 정합.
- 독립 실행: `DELETE /projects/{id}` 후 export **200**(body 보존), `DELETE /projects/{id}/drafts/{draft_id}`(draft archive) 후 export **200**(body 보존). project·draft 양쪽 archive 모두 확인.

### F9. 회귀 테스트 — boundary matrix 분기 추적

신규 11개 테스트를 boundary matrix에 매핑:

| boundary 분기 | pin하는 회귀 | under-strict guard |
|---|---|---|
| body verbatim | `CoreSotExportTest.test_export_body_matches_selected_version_verbatim` + HTTP | body를 raw_text 외 것에서 도달하면 실패 |
| AI metadata 미주입 | HTTP `assertNotIn` + F3 흡수 | metadata 주입 시 F3에서 실패 |
| 두 형식 body 동일 | `test_txt_and_markdown_differ_only_in_content_type_and_extension` | 마크다운 합성/제거 시 body 비교 실패 |
| txt/markdown content_type·확장자 | 동일 + `test_export_markdown_format_query` | — |
| requested not latest | `test_export_picks_the_requested_version_not_the_latest` | latest 반환 시 version_number==1 실패 |
| unsupported 거절 | `test_unsupported_format_is_rejected` + HTTP 400 | 모든 format 허용 시 예외 미발생 실패 |
| missing version 404/NotFound | `test_export_missing_version_raises_not_found` + HTTP 404 | 존재하지 않는 version 반환 시 NotFound 미발생 실패 |
| cross-project 404 | HTTP `test_export_cross_project_returns_404` | 타 project version 노출 시 200 실패 |
| archive survives | `test_export_survives_archive` | archive 차단 시 409/예외 실패 |
| 추적 필드 4개 | 도메인 + HTTP | — |
| 기본 format = txt(쿼리 생략) | HTTP `test_export_returns_selected_version_body_and_traceability` | — |

cross-draft 격리는 export 직접 회귀가 없으나, `export_draft_version`이 재사용하는 `get_draft_version`의 `version.draft_id != draft_id` 검사(`service.py:241`)를 **기존** `test_get_version_cross_draft_returns_404`가 이미 pin한다(동일 코드 경로).

각 테스트는 공개 surface(body, envelope 필드, 상태코드)에 단정하며 내부 헬퍼가 아니다. under-strict guard는 위 표와 같이 존재한다.

## Issues / Risks

> 차단 이슈는 없다. 아래 4건은 모두 비차단 note(정확성·방어적 관찰).

### N1. 테스트 docstring·문서의 "§113/§115 read-allowed" 인용이 존재하지 않는 조항을 가리킨다(정확성)

- `tests/test_core_sot.py` `test_export_survives_archive` docstring이 "SoT §113/§115 read-allowed"를 인용하고, 같은 문구가 `docs/daily_logs/2026-06-30/work_log.md`·`HANDOFF.md` "잠근 범위"에도 반복된다.
- `grep "§113\|§115\|§ 113\|§ 115" docs/system-contract-sot.md` → **히트 없음**. 이 SoT는 번호 조항(§N)이 아니라 마크다운 섹션으로 구성된다.
- 실제 archive read-allowed 근거는 SoT `:137`("읽기...허용")와 changelog v1.5(`:52`)다. 주장 자체는 유효하지만, 인용 번호가 부정확해 미래 독자(및 다음 검증자)가 해당 clause를 찾지 못한다. CLAUDE.md "Trace each test function back to the clause it protects" 관점에서 추적성 정확성 약화.
- **영향**: boundary lock은 실재하고 동작하지만, 인용 링크가 끊겨 있다. **권고**: docstring·문구의 "§113/§115"를 "SoT §archive read-allowed(`:137`)" 식으로 실제 위치로 수정.

### N2. content_type 실제값이 계약 literal에 charset suffix를 붙인다

- 계약 Phase 1 `:303`은 content_type을 `text/plain`/`text/markdown`으로 서술. 코드 `service.py:58-59`는 `text/plain; charset=utf-8`/`text/markdown; charset=utf-8`이다.
- 회귀는 `assertIn("text/plain", ...)`(`tests/test_core_sot.py`) substring 매칭이므로 계약 literal은 보존된 채 통과. `; charset=utf-8`은 MIME 표준 합리적 상세라 계약 위반은 아니나, "every literal must appear unchanged" 엄격 해석에서는 suffix 추가에 해당. **영향 없음**(literal 보존 + UTF-8 명시는 이로움). note로만 기록.

### N3. filename prefix 패턴이 계약에 명시되지 않았고 테스트도 prefix를 검증하지 않는다

- 코드 `service.py:268` filename = `f"{draft_id}-v{version.version_number}.{extension}"`(예 `draft-1-v1.txt`). 계약은 확장자(`.txt`/`.md`)만 명시하고 전체 패턴은 미확정.
- 회귀는 `.endswith(".txt")`/`.endswith(".md")`만 검사 → prefix(`{draft_id}-v{n}`) 변경을 잡지 못한다. pin할 조항이 계약에 없으므로 차단은 아니나, filename 포맷이 향후 계약에 편입될 경우 regression 보강이 필요.

### N4. archived-draft·missing-project export에 명시적 HTTP regression이 없다

- archive survives 회귀는 project archive만 다룬다. draft 자체 archive 후 export는 명시 regression이 없다(독립 실행으로는 200 확인, 동일 `_require_*` 경로이므로 project archive와 동일 동작).
- missing-project(존재하지 않는 project_id) export도 명시 regression이 없다(기존 `test_get_missing_project_returns_404`가 다른 endpoint로 project 누락을 커버).
- 둘 다 동일한 `get_draft_version` → `_require_project`/`_require_draft` → `NotFound` 경로이므로 N2/cross-project/missing-version 회귀가 경로를 커버한다. 독립 실행으로 200/404 동작을 확인했으나, export endpoint 자체의 직접 regression이 없어 회귀 보강 후보.

## Verdict

**합격(Pass).**

Load-bearing 이유:
1. 사용자가 명시한 5개 수용 기준(body verbatim·AI 미주입·두 형식 body 동일, format은 content_type/확장자만, 추적 필드, unsupported 400·missing/cross-project 404, archive 허용)이 **모두 회귀 테스트로 pin**돼 있고, 코드는 계약과 일치하며, 독립 실행으로 재확인했다.
2. 계약(Phase 0/Phase 1/changelog v1.6.14)은 자체 정합(F1, blocking inconsistency 없음).
3. boundary matrix에서 계약에 명시된 모든 분기가 named regression에 매핑된다(F9). 빈 칸으로 보이는 cross-draft는 기존 `test_get_version_cross_draft_returns_404`가 동일 service 메서드를 통해 pin한다.
4. 스위트 325 통과(35 skip)를 독립 재현했다(F0).

N1(§113/§115 허위 인용)은 추적성 정확성 약점이지만 boundary lock 자체는 실재·동작하므로 차단 조건(빈 칸)은 아니다. N2~N4는 계약 미명시 분기이거나 동일 경로를 기존 회귀가 커버하는 방어적 관찰이다. 어느 것도 "계약 분기가 테스트에 매핑되지 않았거나 코드-계약이 불일치"하는 차단 기준에 해당하지 않는다.

## Outstanding items

- **커밋 미수행**: 작업자가 커밋을 요청받지 않아 export slice는 working tree에 uncommitted 상태. 소유자의 커밋/publish 결정 대기.
- **Next Tasks 2~6 블로킹 유지**: export는 Slice 1 잔여 백엔드 작업으로 Next Tasks(Gateway/model tool-call wire, source_ref boundary, Phase 4/5 payload schema)와 별개. 상류 결정 미확정으로 해당 작업들은 여전히 막혀 있다.
- **비차단 권고 4건**(N1~N4)은 소유자 재량. N1(인용 수정)은 문서 정확성 관점에서 권장.

## Reproduction

```bash
# 1. 전체 변경분 확인
git diff services/application/app/core_sot/models.py \
       services/application/app/core_sot/service.py \
       services/application/app/main.py \
       tests/test_core_sot.py tests/test_application_api.py \
       docs/system-contract-sot.md

# 2. §113/§115 인용 실존 확인(빈 결과 = 허위 인용)
grep -nE "§ ?11[35]" docs/system-contract-sot.md   # → no match

# 3. 신규 회귀 + 전체 스위트
python3 -m unittest tests.test_core_sot tests.test_application_api -v   # 기대: Ran 66 OK
python3 -m unittest discover tests                                      # 기대: 325, skipped=35

# 4. envelope + 경계값 독립 재도출
python3 -c "
from fastapi.testclient import TestClient
from services.application.app.main import create_app
c = TestClient(create_app())
p = c.post('/projects', json={'name':'N'}).json()
d = c.post(f\"/projects/{p['id']}/drafts\", json={'title':'D'}).json()
base = f\"/projects/{p['id']}/drafts/{d['id']}/versions\"
raw = '# Chapter 1\n\nOpening line.\n\n---\n\nNext scene.'
v = c.post(base, json={'raw_text':raw,'idempotency_key':'k'}).json()['draft_version']['id']
txt = c.get(f'{base}/{v}/export').json()
md  = c.get(f'{base}/{v}/export?format=markdown').json()
assert txt['body']==md['body']==raw
assert txt['content_type'].startswith('text/plain') and md['content_type'].startswith('text/markdown')
assert txt['filename'].endswith('.txt') and md['filename'].endswith('.md')
for f in ('version_id','version_number','snapshot_id','content_hash'): assert f in txt
assert c.get(f'{base}/{v}/export?format=pdf').status_code==400
assert c.get(f'{base}/nope/export').status_code==404
c.delete(f\"/projects/{p['id']}\")
assert c.get(f'{base}/{v}/export').status_code==200
print('all envelope/boundary claims reproduced')
"
```
