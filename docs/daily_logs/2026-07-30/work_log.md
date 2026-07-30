# 2026-07-30 작업 로그

## Task — 컨텍스트 예산 트랙: R-e(K-6) 구현 — 포인터 렌더링 제거, 항목 번호 인용

### Goals

- HANDOFF Next Tasks 2번의 순서(**1b closure → R-e(K-6) → 가드(K-3) → 밀도(K-1)**)에서
  **1b closure는 어제 커밋 `c402012`로 이미 닫혔다**(재감사 B1~B5 전부 수정 + 회귀, backend
  1717 passed). HANDOFF의 "1b closure가 다음이다" 줄은 같은 커밋에서 갱신되지 않은 **stale
  서술**이었다. 따라서 오늘의 착수점은 **R-e**다.
- R-e는 오너 결정이다(2026-07-29, `plans/context-budget-korean-tokens-decisions.md` §2-1):
  report 프롬프트에서 **항목별 포인터 JSON을 없애고 번호 인용 + 서버측 매핑**으로 바꾼다.
  대응표를 프롬프트에 싣는 변형은 절감이 0이라 그 안이 아니다.
- 성공 기준: ① report 프롬프트 토큰이 실측으로 크게 줄고 ② 실 12B가 번호를 정확히 인용하며
  ③ 번호↔포인터 매핑의 경계가 뮤테이션에 물리는 회귀로 잠긴다.

### Completed work — 구현

**① 프롬프트 렌더링(`writing/prompt.py`)**

- `format_context_package(package, include_pointers=True)` → **`include_citation_numbers=True`**.
  이름을 바꾼 이유: 더 이상 포인터를 싣지 않으므로 옛 이름은 **적극적으로 거짓**이다.
- 항목 한 줄이 `- [label] {포인터 JSON} text` → **`- [N] [label] text`**.
- **번호는 macro → micro 순서로 1부터** 센다. `package_pointers`가 같은 순서로 allowlist를
  만들고 파서가 그 순서로 번호를 되돌리므로, **두 순서가 갈라지면 실패가 아니라 오귀속**이
  된다(claim의 근거가 조용히 다른 항목에 붙는다). 이 성질은 **세 셀**이 잠근다 — 렌더↔파서 왕복
  (H1 보강, 단독으로 양방향 발산을 잡는다) · service 경유 e2e · 섹션 번호 연속성.

**② 파서(`writing/report.py`)**

- `related_context_pointers`의 **wire가 정수 배열**이 됐다. `parse_report`가 번호를 그 요청의
  allowlist 위치로 되돌린다(**서버측 매핑**). 도메인 모델(`CandidateClaim.related_context_pointers`
  = `ContextPointer` tuple)·HTTP 출력·Gate 프롬프트·accept advisory는 **무변**이다 —
  바뀐 것은 모델이 쓰는 wire 하나뿐이다.
- `allowed`를 `frozenset` → **순서 있는 tuple**로 바꿨다(번호가 곧 위치다).
- **번호는 1-based**다. 그래서 `0`은 어떤 항목도 가리키지 않는다 — "없음"을 `0`으로 쓰는 모델은
  거부되고, 0-based였다면 **첫 항목이 조용히 근거로 붙었을 것이다**. 음수도 같은 이유로
  거부한다(tuple 끝으로 감싼다).
- `bool`은 `int`의 하위형이라 **명시적으로 먼저 막는다** — 안 막으면 `true`가 항목 1이 된다.
- 프롬프트 본문(`TEMPLATE`)의 인용 절을 함께 고쳤고 **버전을 `writing_candidate_report_v2`로
  올렸다**. report 템플릿은 **Mongo 영속이 아니라 조립 때마다 in-memory seed**이고 sha256 불변
  핀은 `analysis_extract` 전용이므로 기존 배포와 충돌하지 않는다(베타 Mongo `prompt_templates`
  실측: `analysis_extract` v1~v4 **4행뿐**). 그래도 버전을 올린 이유는 **v1이 두 형식을 뜻하면
  진단·감사가 거짓말을 하기 때문**이다.

**③ 예산 회계와 정본 렌더러 합치기 — 추적 부채 해소**

- HANDOFF 추적 부채 "★ 의도된 중복, 존치/제거 판단 필요"의 **판단 시점이 R-e 직후**로 기록돼
  있었다. R-e가 포인터 렌더링을 없애면서 그 중복의 존재 이유(순환 import)가 사라졌으므로
  **지금 합쳤다**.
- 신설 [`context_search/item_render.py::render_context_item`](../../../services/application/app/context_search/item_render.py)
  **한 정의**를 프롬프트와 회계가 함께 쓴다. 종전에 합칠 수 없던 이유는 정본 렌더러가
  `writing/context_pointer.py`(→ `context_search.service`를 import)에 의존했기 때문인데, 이제
  렌더러의 의존성은 `ContextItemStatus` 하나다.
- `estimate_rendered_item_tokens`에서 **`pointer` 인자가 사라졌다**(렌더링에 안 쓰이므로).
  호출부 3곳(source block · canonical memory · candidate memory)을 함께 고쳤다.
- **의도적 여유 하나를 새로 만들었고 그 크기를 회귀에 명시했다**: 회계는 항목을 만드는
  시점에 그 항목이 몇 번이 될지 모른다(번호는 조립 순서에서 나온다). 그래서 세 자리
  상한(`_BUDGET_CITATION_NUMBER=999`)으로 센다 — 999까지는 **회계 ≥ 렌더링**이고 여유는
  항목당 최대 2자 = **1토큰**이다. 브리프 §2-4의 "여유를 두기로 하면 회귀에 명시한다"에 따라
  세 회계 셀이 `0 ≤ 여유 ≤ 항목수`를 단정한다(종전 `assertEqual`을 대체).
- `context_search/service.py`의 `import json`이 이 변경으로 고아가 돼 제거했다(내 변경이
  만든 고아만).

**④ 진단이 옛 버전을 보고하고 있었다(실측으로 발견)**

- 실 12B 관통을 돌렸더니 헤더가 `report prompt_version: writing_candidate_report_v1`을 찍었다 —
  [`report_live_diag.py:233`](../../../services/application/app/writing/report_live_diag.py#L233)의
  기본값이 **리터럴 사본**이었기 때문이다. v2가 실제로 돌고 있는데 운영자는 v1을 읽는다.
  기본값을 `report.VERSION`에서 끌어오도록 고치고, 헤더가 **실제 버전**을 싣는지 단정하는
  회귀를 더했다(뮤테이션으로 물림 확인).

### Completed work — 실측 (베타, 외부 12B `n_ctx=16384`)

측정 대상은 어제 회계 수정 후 만들어진 **`heavy long AFTER accounting fix`** project
(`6a696057c3b652c072831ef3`, draft `…ef4`, version `…ef5`, source block **69개**). 같은
`ContextPackage`(items 69 · `budget_excluded` 0 · `degraded` False)를 세 형태로 렌더링해
외부 llama `/tokenize`로 실제 토큰을 셌다(작업 트리를 마운트한 application 컨테이너 안에서
`build_services()` 경유 — 배포 이미지 재빌드 없이 실 파이프라인을 그대로 쓴다).

| 렌더링 | 문자 | 컨텍스트 tok | user 메시지 tok | + system(465) |
|---|---:|---:|---:|---:|
| **new (번호 인용)** | 4,924 | **2,678** | 2,751 | **3,216** |
| old (포인터 JSON) | 18,586 | 11,165 | 11,376 | 11,841 |
| generation (인용 없음) | 4,588 | 2,411 | 2,484 | 2,949 |

- **절감 −72.8%**(11,841 → 3,216, **8,625 tok**). 포인터가 report 컨텍스트의 79%였다는 어제
  진단이 그대로 확인됐다.
- **old 11,841은 어제 배포 레코드의 실측(첫 호출 입력 11,837 · 직전 11,905)과 사실상 일치**한다 —
  즉 이 표의 "before"는 재구성이 아니라 **실제로 돌던 값**이다.
- **헤드룸이 부호를 바꿨다**: `3,216 + 출력 상한 6,144 = 9,360 ≤ 16,384` → **+7,024**
  (어제 같은 자리에서 **−1,665**였다).
- **창 8192(알파 기본)에서도 프롬프트 단독 초과는 사라진다**(3,216). 다만
  `3,216 + 6,144 = 9,360 > 8,192`이므로 **상한 기준으로는 여전히 넘는다** — K-3 가드가 필요한
  이유는 R-e 뒤에도 그대로 남는다(가드 식은 `입력 + 출력 ≤ 창`).
- **밀도(K-1)는 손대지 않았고 그대로 보인다**: 회계 1,232 vs 실제 2,678 = **2.17배**. 회계는
  자기 단위(`len/4`) 안에서 정확하고, 이 간극이 K-1의 오차원이다(의도된 분리).

**실 12B 스파이크 — 모델이 번호를 정확히 인용하는가**: `diagnose_writing_report.py`를
`--current-position`으로 돌려(그 모드는 HTTP 시드를 건너뛰므로 401 부채와 무관하다) **3회** 관통.

- **3/3 `Strict parse: OK`, repair 0회.** 모델은 범위 안의 번호만 썼고(`[6]`·`[2, 69]`·`[15, 69]`),
  근거가 없는 claim에는 `[]`를 냈다. provider 실측 `prompt_tokens=3,296`·`3,257`(위 표와 정합).
- 어제 관측된 report **repair 1/3**(64자 `content_hash`를 한 글자도 안 틀리고 베끼는 요구)이
  R-e로 줄어들 것이라는 브리프의 부수 기대는 **3/3 무-repair와 정합하지만 비율로 확인된 것은
  아니다** — 표본 3회는 가설을 반증하지 못했을 뿐이다.

### Issues found — HANDOFF Next Tasks 2번이 stale이었다

- HANDOFF는 "1b closure가 다음이다(B1~B5 수정 + 회귀 필요)"라고 적었는데, **그 항목들은 같은
  커밋(`c402012`)에서 이미 수정됐다**. 커밋 메시지·work_log·SoT v1.7.60은 전부 수정 완료를
  말하고 HANDOFF만 착수 전 서술로 남아 있었다.
- **왜 위험한가**: 다음 작업자가 이미 닫힌 것을 다시 열거나, 반대로 "여기가 막혀 있다"고 보고
  트랙 전체를 멈춘다. 오늘 HANDOFF에서 그 줄을 **교체**했다(추가가 아니라 교체).

### Issues found — 이중 방어가 한 겹으로 줄었다 (의도된 것, 기록해 둔다)

- 종전에는 **프롬프트 렌더러도** 항목마다 `context_pointer_of`를 호출해 cross-project·불변식
  위반 항목을 거부했고, 독립 검증(2026-07-15)이 그 "fails-closed 이중 방어"를 합격 근거로
  들었다. R-e 뒤 프롬프트는 identity를 아예 만지지 않으므로 **그 겹이 없다**.
- 계약은 그대로 유지된다: `enrich_metered`가 **요청을 만들기 전에** `package_pointers(package)`를
  호출하므로 위반 항목은 여전히 provider 호출 전에 거부된다. 그 사실을 단정하는 것은
  `provider.calls == 0` 두 셀이며, **이제 그 두 셀이 이 계약을 혼자 진다**는 점을 테스트 주석에
  명시했다.

### Issues found — repair 프롬프트는 컨텍스트를 다시 싣지 않는다 (기존 성질, 변화 없음)

- repair 호출은 `system=TEMPLATE` + `{invalid, error}`만 보낸다
  ([`report.py:120-124`](../../../services/application/app/writing/report.py#L120-L124)) — **ContextPackage가
  없다**. 그래서 인용이 틀렸을 때 모델이 볼 수 있는 것은 자기 출력과 에러 문구뿐이다.
- **R-e가 이걸 나쁘게 만들지는 않았다**: 종전에도 포인터를 다시 보여주지 않았으므로 잘못 베낀
  포인터는 사실상 `[]`로 후퇴하는 것 말고 고칠 길이 없었다. 번호 쪽이 오히려 고치기 쉽다
  (`"1"` → `1` 같은 타입 오류가 자기 출력 안에서 보인다). **어제 관측된 repair 입력이 첫 호출의
  1/4(3,119 tok)인 이유가 이것**이며, 그래서 repair는 헤드룸이 넉넉하다.
- 기록만 해 둔다 — 인용 정확도가 실제로 문제가 되면(오늘 3/3 무-repair) repair에 항목 목록을
  다시 싣는 것이 후보이고, 그때 비용은 첫 호출과 같아진다.

### Verification

- **뮤테이션 8종 전부 해당 셀에서 물었다**(각각 적용 → 집중 스위트 → 원복). H1 보강 셀에 대한
  단독 3종은 아래 "독립 검증 후속 보강" 절에 있다:

  | # | 뮤테이션 | 무는 셀 |
  |---|---|---|
  | M1 | 매핑을 0-based로(`allowed[v]`, 범위 `0..N-1`) | 번호↔항목 매핑 · 0/음수 거부 · e2e · fence |
  | M2 | `bool` 가드 제거 | `true`가 항목 1이 되는 셀 |
  | M3 | micro 번호를 1부터 다시 시작 | e2e · 섹션 연속성 |
  | M4 | `package_pointers` 순서를 micro→macro로 | allowlist 순서 · e2e |
  | M5 | 회계가 `text`만 센다(2026-07-29 장애 재현) | 회계 3셀 |
  | M6 | 회계가 항목을 두 번 센다(과잉 교정) | 회계 3셀 |
  | M7 | report가 번호를 안 싣는다(`include_citation_numbers` 누락) | e2e |
  | M8 | 진단이 버전 리터럴을 박는다 | 진단 헤더 셀 |

- backend 전량(test-mongo healthy 확인 후): **1720 passed / 1 skipped / 1477 subtests**(672s).
  직전 기준선 1717 / 1468 대비 **+3 테스트 · +9 subtest**다(구현분 +2 · H1 보강 셀 +1).
  H1 보강 전 실행은 1719 / 1474였다. **증가 폭이 신규 경계 수보다 작은 이유**:
  R-e로 성질이 바뀐 셀 6개는 **교체**(구 포인터 wire 거부 셀이 rogue-key 셀 자리를 대신하는 식)이고
  진단 버전은 **기존 셀에 단정을 더한 것**이라 테스트 수가 늘지 않는다. 실제로 수를 늘린 것은
  **0/음수 거부**·**섹션 번호 연속성**, 그리고 H1 보강의 **렌더↔파서 왕복** 셋이다. skip은 알려진 live Chroma 1건.
- 공개 계약 무변: `frontend/src/api/schema.d.ts` 재생성 diff **0**(도메인 모델·HTTP 응답이
  바뀌지 않았다).
- 실 배포 관통 3회(위 스파이크, 3/3 무-repair) + 토큰 실측 2회(동일 수치 재현). 마지막 관통으로 진단
  헤더가 `writing_candidate_report_v2`를 찍는 것도 실 경로에서 확인했다.

### Decisions

- **번호는 1-based로 정했다.** 0-based가 tuple 인덱스와 직결돼 코드가 짧지만, 모델이 `0`을
  "없음"으로 쓰는 흔한 실수가 **조용히 첫 항목을 근거로 만든다**. 1-based면 그 입력이 거부된다 —
  실패를 오귀속보다 위에 둔다.
- **wire 필드 이름 `related_context_pointers`를 그대로 뒀다.** 도메인 필드명이 같고, 이름을
  바꾸면 프롬프트·파서·advisory·프론트 타입까지 번지는데 얻는 것은 표현상 정확성뿐이다.
  구 wire(포인터 객체)는 타입 검사에서 **거부**되므로 두 형식이 섞여 통과할 일은 없다.
- **`R-a`(report 전용 예산)는 여전히 보류다.** R-e 뒤 헤드룸이 +7,024로 벌어졌으므로 지금
  당장의 필요는 사라졌다. 다음은 순서대로 **가드(K-3)**, 그 뒤 **밀도(K-1)**다.

### 독립 검증 후속 보강 (같은 슬라이스)

독립 검증 [`verifications/2026-07-30/r_e_citation_numbers_audit.md`](../../verifications/2026-07-30/r_e_citation_numbers_audit.md)
판정은 **합격(차단 0)**이고 비차단 후보 2건(H1·H2)이 남았다. 둘 다 처리했다.

- **먼저 워킹 트리 충실성을 내가 직접 대조했다.** 검증자가 뮤테이션 원복에 `git checkout --
  report.py`를 써서 **미커밋 R-e(v2)를 HEAD(v1)로 지웠다가** 복구한 사고가 있었다(검증 기록
  Outstanding items에 본인이 투명하게 남겼다). 복구 주장을 그대로 믿지 않고, 내가 뮤테이션
  실험 때 떠 둔 백업 5개와 `diff`로 대조해 **제품 코드 5파일이 바이트 단위로 동일**함을
  확인했다. **교훈**: 미커밋 작업이 있는 트리에서 `git checkout -- <file>`은 원복 수단이 아니다
  (HEAD로 되돌린다). 뮤테이션은 **역방향 Edit** 또는 **사전 백업 후 복사**로 원복한다 — 오늘
  내가 쓴 방식이 후자이고, 그 덕에 사고를 사후에 검증할 수 있었다.
- **H1 종결 — 매핑 셀을 자급자족으로 만들었다.** 지적은 정확했다: `test_each_number_maps_to_its_own_package_item`은
  allowlist만 보므로 **프롬프트 번호 부여**가 갈라지는 것을 혼자서는 못 본다(그 방향은 service
  경유 e2e 셀이 잡았다). 신규 셀 `test_rendered_number_resolves_to_the_item_it_labels`는
  **렌더링된 프롬프트에서 `- [N] …` 번호를 정규식으로 읽어** 그 번호가 그 줄의 항목으로
  되돌아오는지 본다 — provider·service 없이 **render↔parse 왕복만으로** 발산을 잡는다. 세 origin의
  본문을 서로 다르게 둔 것이 요점이다(같은 본문이면 어느 줄이 어느 항목인지 구분할 수 없다).
  **뮤테이션 3종을 이 셀 단독으로 재실증**: micro 번호 재시작(프롬프트 쪽 발산) · `package_pointers`
  순서 반전(파서 쪽 발산) · 0-based 매핑 — 전부 이 셀 하나에서 물었다.
- **H2 — 실측은 독립 재실측되지 않았다. 그 한계를 좁히지 말고 재현 경로를 repo 도구로 못박는다.**
  검증자는 외부 12B(`n_ctx=16384`)와 베타 Mongo의 69-항목 project가 없어 −72.8%·3/3 strict parse를
  재실측하지 못했다(결정론적 부분 — before 교차참조·회계 산술·렌더 형식·공개 계약 — 은 전부
  독립 검증됐다). **이 수치는 베타 머신-로컬 관측치이며 그렇게 읽어야 한다.** 다만 재현에 새
  스크립트가 필요하지는 않다 — **repo의 운영 진단 도구가 같은 수를 찍는다**:

  ```bash
  # 베타(또는 외부 12B가 도달 가능한 머신)에서, 스택이 떠 있는 상태로:
  docker compose run --rm --no-deps \
    -v "$PWD/services:/app/services" -v "$PWD/scripts:/app/scripts" -e PYTHONPATH=/app \
    application python scripts/diagnose_writing_report.py \
      --project-id 6a696057c3b652c072831ef3 \
      --current-position 6a696057c3b652c072831ef4 6a696058c3b652c072831ef5
  # → "Report usage: prompt_tokens=3257" (오늘 3회: 3,296 · 3,257)
  #   before 대응값은 2026-07-29 기록의 11,837 · 11,905 (audit 레코드 실측)
  #   헤더의 "report prompt_version: writing_candidate_report_v2"도 같은 출력에서 확인된다
  ```

  `--current-position`을 주면 HTTP 시드를 건너뛰므로 **401 부채와 무관하게** 돈다(그 사실 자체가
  추적 부채 목록의 "진단 도구가 막혀 있다"에 대한 우회이기도 하다). 항목별 렌더링 비교표
  (4,924자 vs 18,586자)는 일회용 측정 스크립트로 냈고 **repo에 넣지 않았다** — 같은 결론이 위
  진단 한 줄로 재현되므로 유지 비용을 만들 이유가 없다.

### Next steps

- **K-3 가드**: `입력 + 출력 ≤ 창`. 창은 이미 `/props`에서 읽어 감사에 남는다(1b). 남은 것은
  고정 오버헤드(system 프롬프트 465 tok · 후보 산문 · 구조적 래퍼)를 더해 판정하는 자리와,
  넘을 때의 동작이다. **베타에서 만드는 것이 낫다**(창을 상수로 박는 설계가 애초에 작동하지
  않는다).
- **K-1 밀도**: 회계 1,232 vs 실제 2,678(2.17배). 추천은 여전히 (c)+(a).
- R-e 전후 **report repair 비율**은 dogfood 관찰 항목으로 남긴다(오늘 3/3 무-repair).
