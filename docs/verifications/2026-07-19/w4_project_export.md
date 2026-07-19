# W4 프로젝트 전체 ordered-latest export — 독립 검증

## Subject metadata

- **날짜**: 2026-07-19
- **요청자**: 오너(“작업 AI의 작업 결과 확인해서 검증하고 의심하고 또 의심해줄래?”)
- **검증자**: 독립 검증 AI(Claude, max effort)
- **검증 대상 slice/artifact**: Writing Workspace V2 **W4 — 프로젝트 전체 ordered-latest export(D6=A, SoT v1.7.17)**
- **canonical spec reference**:
  - `docs/plans/writing-workspace-v2-w0-contract.md` §4 matrix(EX-01~12, 신규 12행) + §6(W4 export exact contract, 신규) + 상태/정본 버전 header
  - `docs/system-contract-sot.md` v1.7.17 changelog entry
- **작업 출처**: working tree, **uncommitted**(`git diff HEAD` — 커밋 미지시 상태). HEAD = `34ae4df`.

## Scope

본 검증은 아래 표면을 W4 slice에 한정해 whole-stack으로 감사한다. W1~W3(PB/OU/WI/SC)은 본 slice 밖이므로 재검증하지 않는다.

1. **정본 계약** — W0 contract §6(6.1~6.4) + §4 matrix EX-01~12 + SoT v1.7.17 changelog
2. **Core SOT 구현** — `services/application/app/core_sot/models.py`(`ProjectExport`/`ProjectExportUnit`), `service.py::export_project`
3. **HTTP layer** — `services/application/app/main.py::export_project` endpoint + `ProjectExportResponse/Manifest/UnitModel`
4. **회귀 테스트** — `tests/test_core_sot.py::ProjectExportContractTest`, `tests/test_application_api.py::ProjectExportApiTest`
5. **공개 envelope/schema** — OpenAPI introspection, `frontend/src/api/schema.d.ts`(gen:api 산출물)
6. **전체 suite 재현** — backend full + frontend test/build
7. **문서** — `work_log.md`, `HANDOFF.md`, `CHANGELOG.md`의 W4 항목 정합성

## Methodology

“코드를 먼저 보지 않고 계약을 먼저 스코핑해서 읽는다.”(CLAUDE.md) — 계약 diff(§6/§4/SoT)를 먼저 읽어 boundary matrix(lock list)를 세운 뒤, 구현·테스트가 그 cell을 채우는지 추적했다. 작업 AI의 주장은 일절 전제하지 않고 primary source에서 재도출했다.

모든 명령은 working tree(미커밋)에서 실행.

```bash
# boundary diff (canonical contract)
git diff HEAD -- docs/plans/writing-workspace-v2-w0-contract.md docs/system-contract-sot.md
# 구현/테스트 diff
git diff HEAD -- services/application/app/core_sot/models.py \
  services/application/app/core_sot/service.py services/application/app/main.py \
  tests/test_core_sot.py tests/test_application_api.py
# 신규 회귀 focused
python3 -m pytest tests/test_core_sot.py::ProjectExportContractTest \
  tests/test_application_api.py::ProjectExportApiTest -v -p no:cacheprovider
# backend full
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
# frontend test/build + gen:api 재현성
cd frontend && npm test -- --run && npm run build && npm run gen:api
# OpenAPI introspection (params/response_model/operationId)
python3 -c "from app.main import create_app; ..."   # 본문 Methodology에 인라인
# under-strict guard = mutation testing (M1~M5, 각각 원복 + git diff 0 확인)
```

mutation testing은 `Edit`로 의도적 결함을 넣고 → 관련 테스트만 실행 → bite 확인 → 정확히 반대 `Edit`로 원복 → `grep MUTATION`/`git diff`로 0 변경 확인하는 절차로 수행했다.

## Findings

### F1. 정본 계약 — boundary matrix와 self-consistency

W0 contract §6이 다음 lock list를 확정한다(재인용, paraphrase 아님):

- **6.1 API**: `GET /projects/{project_id}/export?format=txt|markdown&manifest=<bool>&include_archived=<bool>`; format 미지정 기본 `txt`; `_EXPORT_FORMATS`(txt=`text/plain; charset=utf-8`, markdown=`text/markdown; charset=utf-8`); 지원 밖 format → 400; missing/cross-project → 404; archived project → 200(read); 응답 exact top-level `{format,filename,content_type,body,project_id,include_archived,manifest}`; filename=`{project_id}.{txt|md}`.
- **6.2 선택/순서**: Draft를 `position` 오름차순; archived는 기본 제외 + `include_archived=true` 옵트인(같은 position 순); 각 unit은 **latest version**(최대 `version_number`); version이 하나도 없는 Draft는 body/manifest 양쪽 skip(순서 변형 없음).
- **6.3 body**: unit block = `{heading}\n\n{raw_text}`; block 간 `\n\n`; heading = Markdown `# {title}` / TXT 제목 줄(plain); unit_kind별 레벨 매핑 없음; `raw_text` verbatim(AI metadata 미삽입); 포함 unit 0개 → body = 빈 문자열.
- **6.4 manifest**: 요청 시에만(같은 endpoint `manifest=true`); 미요청 시 `null`; shape `{project_id,format,include_archived,units[]}`, 각 unit = `{draft_id,title,unit_kind,position,version_id,version_number,snapshot_id,content_hash}`; body unit과 같은 순서·집합.

§4 matrix EX-01~12가 이 lock list를 fire 6(EX-01/03/04/06/08/12) · not-fire 6(EX-02/05/07/09/10/11)로 양분하고, 각 cell을 named 회귀에 1:1로 매핑한다. SoT v1.7.17 changelog는 위 전부를 paraphrase 없이 반영한다. **§6 ↔ §4 matrix ↔ SoT changelog 삼자 간 모순 없음**. D6=A 브리프가 “heading separator·manifest 전달·archived 포함”을 W4로 이관했다는 §6 서두의 진술도 work_log의 User Decisions와 정합한다.

### F2. Core SOT 구현 — spec ↔ 코드 literal 일치

`service.py:561-612 export_project`:

- `_EXPORT_FORMATS`(service.py:74-78)는 txt/markdown content_type·extension이 정확히 계약 리터럴과 일치. 단일 version export(`export_draft_version`)와 **동일 dict 공유**.
- `_require_project`(852-856)는 `None`일 때만 `NotFound`; **archived project를 reject하지 않는다** → EX-11(archived project=200)의 핵심 경계. `_require_active_project_and_draft`(864-870)와 대비하면 export가 의도적으로 read 경로임이 명확.
- `list_drafts`(repo, in-memory 191-197 / mongo 218-223)는 position이 모두 있으면 `sorted(key=position)`. `_require_ordered_drafts`(872-885)는 unit_kind/position 검증 + `1..N` contiguous permutation 보장. export가 ordered invariant를 재사용(§6.2 “W0 §2 contiguous 보장 재사용”과 정합).
- archived 필터 `if draft.archived and not include_archived: continue`(579-580) — 기본 제외 + opt-in. drafts가 이미 position 순이므로 include 시에도 같은 순서 유지.
- latest 선택 `max(versions, key=lambda v: v.version_number)`(586) — 과거 version 아님.
- version 없는 unit `if not versions: continue`(582-585) — body/manifest 양쪽 skip, 순서 변형 없음.
- heading `f"# {draft.title}" if fmt == "markdown" else draft.title`(601); block `f"{heading}\n\n{snapshot.raw_text}"`(602); join `"\n\n".join(blocks)`(608). 0 unit → `""`.
- filename `f"{project_id}.{extension}"`(606).
- `ProjectExportUnit` 필드 8개(models.py)와 `ProjectExport` 필드 7개가 §6.4 unit shape + §6.1 top-level과 literal 1:1.

`body=snapshot.raw_text`는 단일 version export 선례(`export_draft_version` service.py:552)와 동일 verbatim. **AI metadata 주입 경로 없음** → EX-05 충족.

### F3. HTTP layer — response_model 절차(v1.6.95) 준수 + exact-key 회귀

`main.py` endpoint는 `response_model=ProjectExportResponse`를 붙였고, EX-12(`test_export_response_exact_keys`)가 top-level/manifest/unit 3단 exact-key를 `set(...)` 비교로 pin한다. v1.6.95 규칙(“모델 붙이기 전 exact-key 회귀를 먼저 깐다”)의 본질적 가치는 **key drop 잡기**다. EX-12의 `set(body) == {7 keys}` 비교는 response_model에서 필드 하나라도 빠지면 실패한다(extra-key leak은 response_model이 strip하므로 본 규칙의 알려진 한계이며, 동작상 계약 위반이 아님 — leak이 응답에 노출되지 않으므로).

예외 매핑: `UnsupportedExportFormat → 400`, `NotFound → 404`. archived project는 `_require_project` 통과 → 200. 이 매핑이 EX-10(400/404)·EX-11(200)을 산출한다.

### F4. 회귀 테스트 — boundary matrix 빈 셀 없음 + under-strict guard mutation 실증

12 cell 전부 named 회귀에 매핑됨(EX-01~12). 추가 방어 테스트 4종(`test_unsupported_format_is_rejected`, `test_missing_project_raises_not_found`, `test_archived_project_export_survives` core mirror, `test_include_archived_flag_over_http` HTTP mirror).

**under-strict guard(mutation testing)** — 각 테스트가 자기 clause를 정확히 pin하는지, 결함을 넣어 확인:

| mutation | 위치 | bite 결과 |
|---|---|---|
| M1 latest `max`→`min` | service.py:586 | **EX-04만** 실패(`v1 body` 잘못 선택) — 1 failed |
| M3 archived 필터 `continue`→`pass` | service.py:579-580 | **EX-02만** 실패(archived 누출) — 1 failed, 9 passed |
| M5 block join `\n\n`→`\n` | service.py:608 | **다중-unit body 비교 7개** 실패 — 7 failed, 9 passed |
| M4 `if manifest:`→`if True:` | main.py | **EX-09만** 실패(manifest 항상 populate) — 1 failed, 5 passed |

모든 mutation이 의도한 clause의 테스트만 정확히 bite했다. 각 mutation 후 `grep MUTATION`/`git diff`로 원복을 확인(0 residual).

**over-strict guard** 도 확인: EX-06(`test_txt_and_markdown_heading_shapes`)는 raw_text 자체가 `# already a heading\n\nbody`라, markdown이 raw 기존 `#`에 추가 변형을 가하거나 txt가 `#`을 붙이면 body가 달라져 실패한다. EX-12 exact-key는 extra 추가·key 누락 양방향 감지. EX-02 archived 제거 후 d2가 남아있는지도 단정(과잉 제거 감지).

### F5. 공개 envelope/schema — OpenAPI ↔ schema.d.ts 정합

OpenAPI introspection 결과 `/projects/{project_id}/export` GET, operationId `export_project_..._get`, 200 → `ProjectExportResponse`, params(`format` default `txt` / `manifest` default `False` / `include_archived` default `False` / `project_id` path required). 이는 `schema.d.ts`의 gen:api 산출물 diff(98줄 추가: `ProjectExportResponse/Manifest/UnitModel` + operation)과 literal 1:1.

`npm run gen:api` 재실행 결과 작업 AI가 남긴 `schema.d.ts`와 **byte-identical**(재생성 후 `git diff` 동일 98 insertions). 재현성 확정.

### F6. 정량 주장 독립 재현

| 주장(work_log/HANDOFF/CHANGELOG) | 재현 |
|---|---|
| backend **1197 passed / 73 skipped / 297 subtests** | ✅ 일치(24.25s) |
| frontend **146 passed / 10 files** | ✅ 일치 |
| build **96 modules, JS 287.30 kB** | ✅ 일치(SoT changelog “287.30 kB”) |
| gen:api byte-identical | ✅ 일치 |
| 신규 회귀 **16 passed** | ✅ 일치 |

직전 W3(v1.7.16)의 1181 passed + 신규 16 = 1197. 산술 정합.

### F7. 문서 정합성

CHANGELOG v1.7.17 항목·HANDOFF W4 Current Status/Next Tasks 업데이트·SoT changelog 모두 구현과 정합. 단, work_log “Regression (양방향)”에 **“ProjectExportContractTest 8종 + ProjectExportApiTest 8종”**이라 적었으나 실제는 **ContractTest 10종 + ApiTest 6종 = 16종**이다(총합 16은 맞음, 클래스별 분배만 부정확). 본 slice 동작·계약과 무관한 표기 오류.

## Issues / Risks

### Blocking(contract obligations)

**없음.** boundary matrix EX-01~12의 12 cell이 전부 named 회귀로 채워졌고, under-strict/over-strict guard가 mutation으로 검증됐으며, spec ↔ 코드 literal이 일치하고, 계약(self-consistency)에 모순이 없다. “빈 셀 = blocking” 기준을 만족한다.

### Hardening recommendations(non-blocking)

계약이 요구하지 않아 본 slice를 fail시키지 않지만, 경계를 더 단단하게 만드는 후보. 오너 판단으로 반영 여부 결정.

- **H1 — `InvalidDraftOrder` → 500 노출 가능**. `export_project`가 `_require_ordered_drafts`를 호출하는데, `main.py` endpoint는 `UnsupportedExportFormat`(400)·`NotFound`(404)만 잡고 `InvalidDraftOrder`(`CoreSotError`)를 매핑하지 않는다. ordered-unit migration이 W3에서 mandatory이고 새 project는 항상 ordered로 생성되므로 정상 상태에선 발생하지 않는다(§6.2 “W0 §2 contiguous 보장 재사용”이 ordered를 전제). corrupt/partial migration 시에만 500. 권고: 409(또는 400)로 매핑하거나 최소 log 남기기.
- **H2 — `assert snapshot is not None`(service.py:588)**. 선례 `get_draft_version`(service.py:514-525)는 snapshot 누락 시 `raise NotFound`로 **명시적** 처리한다. export_project는 `assert`라 `python -O`에서 제거되면 None 접근 → 500. referential integrity(version → snapshot)로 None는 불가능하지만, 선례와의 일관성·방어적 코딩 관점에서 `if snapshot is None: raise NotFound(...)`가 더 안전.
- **H3 — export 전용 Mongo end-to-end 회귀 부재**. `export_project` 자체의 Mongo 회귀가 없다. 단, `list_drafts`(mongo 218-223, in-memory와 동일 position 정렬)·`list_versions`·`get_snapshot`이 각각 Mongo 회귀로 검증되고(`test_core_sot_mongo.py:274`에서 position [1,2,3] 단정), export는 이들을 단순 조합하므로 간접 보증은 된다. 권고: `ProjectExportContractTest`를 Mongo repo로도 parametrize하면 latest 선택 + archived filter + skip versionless 조합 동작을 live로 직접 증명.
- **H4 — 빈 project(0 draft → body=`""`) 명시적 회귀 부재**. 코드로 보장(`_require_ordered_drafts(())` 통과, 빈 blocks join=`""`)이나 전용 테스트 없음.
- **H5 — content_type 전체 문자열 단정 부재**. EX-06은 `assertIn("text/plain", ...)` 부분 매치. `_EXPORT_FORMATS` 리터럴 전체(`text/plain; charset=utf-8`) 단정이 더 강함(단일 export 선례에 의존).
- **H6 — OpenAPI `responses`에 400/404 미문서화**. EX-10 동작(400/404)은 맞지만 OpenAPI엔 200/422만. 단일 version export 선례와 동일 패턴. 권고: `responses={400:..., 404:...}` 추가 시 API 소비자 친화적.

## Verdict

**PASS(조건 없음).**

근거(부하-bearing):
1. boundary matrix EX-01~12(fire 6/not-fire 6) 12 cell 전부 named 회귀로 채워짐 — 빈 셀 없음.
2. spec ↔ 코드 literal 일치(heading `# {title}`/제목 줄, separator `\n\n` block 내·간, filename `{id}.{txt|md}`, content_type, exact top-level/manifest/unit keys, manifest shape).
3. 계약 self-consistency(§6 ↔ §4 matrix ↔ SoT v1.7.17) 모순 없음.
4. under-strict guard를 mutation testing으로 실증(M1/M3/M4/M5 각각 정확한 clause만 bite). over-strict(EX-06 raw heading 충돌, EX-12 양방향, EX-02 과잉 제거)도 확인.
5. 작업 AI의 정량 주장(backend 1197/73/297, frontend 146/10, build 287.30 kB, gen:api byte-identical)을 전부 독립 재현.
6. response_model 절차(v1.6.95) 준수 — exact-key 회귀(EX-12)가 key drop을 잡는다.

“green bar ≠ 계약 검증” 구분을 명시: F4의 mutation testing이 단순 통과를 넘어 각 테스트가 clause를 pin함을 입증했다. Hardening H1~H6은 계약 요구가 아니므로 본 verdict에 영향 없다.

## Outstanding items

- **작업물 미커밋**: 본 slice는 working tree에만 있음(`git diff HEAD`, 커밋 미지시). 오너가 커밋을 지시하면 W1~W4 전체가 하나의 히스토리로 확정된다. 작업 AI가 “커밋해 드릴까요?”로 물은 상태.
- **프론트 소비 미배선**: W4는 backend 계약만 확정. 다운로드 UI 배선은 별도 소비 slice(오너 결정 사항 a).
- **다음 code slice는 오너 결정**: (a) 프론트 export UI 배선, (b) dogfood/OPS-1, (c) Deferred 항목.
- **H1~H6 반영 여부**: 오너 판단. 반영 시 production 코드 변경(H1/H2) 또는 테스트/문서만(H3~H6)으로 분리 가능.

## Reproduction

```bash
cd /mnt/f/devel/ai_writte_system

# 1. canonical contract diff
git diff HEAD -- docs/plans/writing-workspace-v2-w0-contract.md docs/system-contract-sot.md

# 2. 신규 회귀 focused (expect: 16 passed)
python3 -m pytest tests/test_core_sot.py::ProjectExportContractTest \
  tests/test_application_api.py::ProjectExportApiTest -v -p no:cacheprovider

# 3. backend full (expect: 1197 passed, 73 skipped, 297 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# 4. frontend (expect: 146 passed/10 files; build 96 modules 287.30 kB; gen:api byte-identical)
cd frontend && npm test -- --run && npm run build && npm run gen:api && git diff --stat src/api/schema.d.ts

# 5. under-strict guard(mutation) — 각 mutation을 Edit로 적용 후 focused 실행, bite 확인 후 원복
#    M1: service.py:586 max→min       → EX-04 실패
#    M3: service.py:579-580 continue→pass → EX-02 실패
#    M5: service.py:608 "\n\n"→"\n"   → 다중-unit 7개 실패
#    M4: main.py if manifest:→if True: → EX-09 실패
```
