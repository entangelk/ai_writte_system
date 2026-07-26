# 독립 검증 — 다중 사용자 단계 전환 (D0=A, SoT v1.7.49)

## Subject metadata

- **날짜**: 2026-07-26
- **요청자**: 오너 ("작업 AI가 계획을 세웠는데 제대로 했는지 검증하고 의심하고 또 의심해줄래? … 정본 개정하고 커밋했습니다 — 6c144a8, SoT v1.7.49")
- **검증자**: 독립 검증자 (Claude, 별개 세션)
- **대상 슬라이스**: 오너 요청(로그인·인증·아이디별 관리·CMS 삭제·관리자 기능)에 대한 **계약 단계 전환** — SoT §"제품과 프로젔트 경계"·§"Product Shell"·frontend CORS 조항·보관/삭제 조항 개정. **코드·회귀 무변**(계약 문서 전용 슬라이스).
- **정본 계약 참조**: SoT **v1.7.49**(개정 후) 및 v1.7.48(직전) §"제품과 프로젝트 경계"(250–253줄), §"Product Shell"(541·544줄), frontend CORS 조항(238줄), §Core SOT 보관 정책(274–282줄), 변경이력(36줄). 결정 브리프 `docs/plans/multi-user-auth-cms-decisions.md`(D0=A 확정, D1~D8 승인 대기).
- **작업 소스**: 커밋 `6c144a8` (HEAD). 작업 트리 clean. 파일: `docs/system-contract-sot.md`(+16/−14 본문 4곳 + 변경이력 1행)·`docs/plans/multi-user-auth-cms-decisions.md`(브리프 §0·D0 갱신)·`HANDOFF.md`(상태·결정 항목 rewrite)·`docs/daily_logs/2026-07-26/work_log.md`(D0 결정 섹션 +30).

## Scope

이 슬라이스는 **코드를 건드리지 않는 계약 전용 전환**이다. 따라서 boundary matrix의 셀은 "회귀 테스트"가 아니라 **개정이 지켜야 하는 계약 일관성 조건**들이다. CLAUDE.md §5 "계약 자체와의 교차 확인"·"리터럴 일관성"·"Smoke run vs envelope claim"을 이 슬라이스의 검증 축으로 쓴다.

1. **시점 한정어 잔존 여부** — "MVP는 단일 사용자"·"인증 없는"·"`user_id`를 지금 억지로 넣지 않는다" 같은 시점 한정어가 현행 계약 **본문**(변경이력 행이 아닌)에 잔존하지 않는지 전수.
2. **개정 4곳의 사실성** — 작업 AI가 본문에 적은 주장(보관 정책 "확정"·`project_id` 강제 "살아남는다"·v1.6.53 G3=A 참조·main.py:2242·2254 archive)이 정본 다른 곳·실제 코드와 일치하는지.
3. **내부 모순** — 개정 전/후 정본이 단일 진술 집합인지(같은 정본 안에서 충돌하는 진술이 없는지).
4. **"아직 구현되지 않았으니 배포 스택은 여전히 무인증" 경계** — 이게 정본 어디에, 어떤 강도로 못박혀 있는지. 이 슬라이스에서 가장 위험한 오독("계약에 적혀 있으니 있겠지")을 방어하는 문장인지.
5. **실측 숫자 재측정** — 브리프·정본 변경이력·HANDOFF가 "공개 operation 62개 / 52 path"라고 주장; 이 숫자를 코드에서 독립 재측정.
6. **브리프 ↔ 정본 ↔ HANDOFF 일관성** — D0=A, D1~D8 목록, v1.7.49 참조가 세 문서에서 같은 뜻인지.
7. **CSRF/CORS 기술 서술** — "쿠키 인증에서 CORS를 여는 것은 CSRF 표면을 넓히는 일"이라는 정본 238줄 서술의 정확성.
8. **코드·회귀 무변 확인** — 커밋이 docs/HANDOFF/work_log만 건드렸는지.

## Methodology

스코프된 계약 읽기(개정 4곳 + 그것이 의존하는 §Core SOT 보관 정책 + v1.6.53 이력) → 일관성 boundary matrix → grep/코드 재측정으로 셀 채우기. 작업 AI 보고를 **독립 재측정**으로 실증; 숫자·file:line 참조는 전부 재확인.

**정확한 명령**:

- 커밋 구조: `git show 6c144a8 --stat` (4개 파일, docs 한정).
- 정본 diff: `git show 6c144a8 -- docs/system-contract-sot.md`.
- 브리프 diff: `git show 6c144a8 -- docs/plans/multi-user-auth-cms-decisions.md`.
- 시점 한정어 전수: `grep -nE "(단일 사용자|MVP는|계정/인증이 없는|인증 없는|무인증|user_id를.*억지로)" docs/system-contract-sot.md`.
- 보관 정책 본문: `grep -nE "(archive|soft.?delete|보존|source_ref|snapshot.*version)" docs/system-contract-sot.md`(이력 행 제외).
- 직전 정본 비교: `git show 6c144a8^:docs/system-contract-sot.md | grep -nE "(archive로 처리|보관/삭제 정책|단일 사용자 제품 표면)"`.
- `project_id` 강제 코드: `grep -rnE "project_id" services/application/app/core_sot/service.py | grep -E "(None|!= project_id)"`.
- main.py archive 참조: `sed -n '2238,2260p' services/application/app/main.py`.
- operation/path 재측정(2기준):
  - FastAPI app: `python3 -c "from app.main import create_app; ..."` — 비즈니스 경로 한정.
  - OpenAPI 덤프: `python3 scripts/dump_openapi.py > /tmp/sot_openapi.json` 후 `paths`/operation 집계.
- v1.6.53 G3 참조: `git show 6c144a8^:docs/system-contract-sot.md | grep -n "v1.6.53"`(132줄).
- D1~D8 교차: `grep -nE "^## D[0-9]" docs/plans/multi-user-auth-cms-decisions.md` vs 정본 변경이력 설명.

## Findings

### 1. 시점 한정어 잔존 — 없음 (본문 4곳이 전부)

현행 정본 **본문**(변경이력 테이블 행 제외)에서 "MVP는 단일 사용자"·"인증 없는"을 현행 사실처럼 기술하는 곳은 없다. grep 결과:

- 238줄(frontend CORS): "당시 근거는 '인증 없는 단일 사용자 API'… **다중 사용자 전환 후에는 근거가 사라지는 게 아니라 강해진다**" — 과거형 근거 + 현재 강화. ✅
- 250–253줄(§제품과 프로젝트 경계): "다중 사용자로 확장한다… 종전 조항 … MVP 단계의 제약이었고 그 단계가 끝나 해제됐다" — 명시적 해제. ✅
- 541·544줄(§Product Shell): "다중 사용자 제품 표면으로 확장한다(v1.7.49)… 구현 전까지 실제 표면은 여전히 단일 사용자다" — 의도 vs 현 구현 상태를 구분. ✅

이력 행(92·132줄)에 "단일 사용자"·"인증 없는" 표현이 있으나 이는 **과거 결정의 역사 기록**이지 현행 계약 진술이 아니므로 모순이 아니다. 작업 AI의 "본문 4곳 개정" 주장은 정확하다.

### 2. 개정 4곳의 사실성 — 전부 사실

**(a) 보관 정책 "확정" 주장 (544줄)** — 정본 276줄이 "project/draft 삭제는 MVP에서 archive로 처리한다. `source_snapshots`·`draft_versions`·`source_blocks`·`source_refs`는 보존한다"로 이미 확정 계약이며, 277–282줄이 archive의 읽기전용·쓰기차단(409)·상태전이를 상세 규정한다. 작업 AI가 544줄에 적은 "보관 정책은 확정돼 있다(project/draft는 archive = soft delete, snapshot/version/source_ref는 보존)"는 이 276줄과 정확히 일치 — **사실**.

**(b) `project_id` 강제 "살아남는다" (252줄)** — `services/application/app/core_sot/service.py`에서 cross-project 접근이 실제로 거부된다(414·639·804·833·841·881줄의 `if x is None or x.project_id != project_id` 패턴, 885줄 `_require_active_project_and_draft`). "소유권은 그 위에 얹히는 두 번째 경계"라는 서술이 현재 코드 구조와 정합 — **사실**.

**(c) v1.6.53 G3=A 참조 (253줄)** — 정본 132줄 이력에 "G3=A(`xpack.security.enabled=false`; 코드가 무인증 plaintext·MVP 단일 사용자, **보안 ON은 인증 slice 선행 필요라 범위 밖**)"로 정확히 기록돼 있다. 작업 AI의 "그 결정이 '인증 slice 선행 필요라 범위 밖'이라고 스스로 적었던 항목" 서술은 인용 정확 — **사실**.

**(d) main.py:2242·2254 archive 참조 (브리프 56줄)** — `services/application/app/main.py:2242`가 `@app.delete("/projects/{project_id}")` → `archive_project`, 2254줄 인근이 `@app.delete("/projects/{project_id}/drafts/{draft_id}")` → `archive_draft`. 두 줄 참조 정확. `archive_project` 본문 주석 "MVP: delete is archive (soft delete); SOT data is preserved"는 정본 276줄과 일치 — **사실**.

### 3. 내부 모순 — 개정 **해소**, 신규 모순 **없음**

**직전 정본(v1.7.48)은 진짜 내부 모순을 가지고 있었다**:

- §Core SOT 274줄: "project/draft 삭제는 MVP에서 archive로 처리한다 … 보존한다" → **보관 확정**
- §Product Shell 542줄: "보관/삭제 정책, draft/chapter/scene 계층은 미확정이다" → **보관·삭제 미확정**

같은 정본 안에서 §Core SOT는 보관을 확정 계약으로, §Product Shell은 "보관/삭제 미확정"으로 동시에 서술했다. v1.7.49의 544줄 개정("보관 정책은 확정 … 영구 삭제 정책은 여전히 미확정(D5)")은 이 모순을 **§Core SOT 쪽으로 정렬하며 해소**한다. 이는 CLAUDE.md §5 "계약 자체와의 교차 확인 — 내부 계약 불일치는 blocking" 원칙에 정확히 부합하는 수정이며, 작업 AI가 단계 전환 외에 발견한 기존 부채까지 같이 닫은 것이다. 개정 후 현행 정본에서 보관 정책 진술은 단일(확정)로 수렴.

281줄 "unarchive는 MVP 범위가 아니므로 … 영구 불변을 규정하지 않는다"는 archive 영구성의 일부를 미확정으로 두지만, 이는 544줄의 큰 틀("보관 정책 확정")과 충돌하지 않는다 — "archive 처리 자체는 확정"이고 "archive의 영구 취소 가능성"이 별도 미확정 칸이다.

### 4. "배포 스택은 여전히 무인증" 경계 — 적절한 강도로 3곳에 못박힘

이 슬라이스에서 가장 위험한 오독("정본에 '다중 사용자'라고 적혀 있으니 인증이 서 있겠지")에 대한 방어가 세 곳에 일관되게 나타난다:

- 정본 251줄: "**그 슬라이스가 끝나기 전까지 배포된 스택은 여전히 무인증**이므로, 이 조항을 근거로 외부에 노출하면 안 된다. 인증이 실제로 서는 시점은 각 슬라이스가 정본에 계약을 적을 때다."
- 정본 541줄: "구현 전까지 실제 표면은 여전히 단일 사용자다."
- HANDOFF "Owner Decisions Needed": "정본은 방향을 적었지만 **코드는 아직 없다**: 배포 스택은 여전히 무인증이므로 이 조항을 근거로 외부에 노출하면 안 된다."

"의도(정본) vs 현 구현(코드)"의 분리가 명시적이고, 다음 작업자가 오독할 여지가 없다. 이 경계 못박기는 이 슬라이스의 가장 중요한 설계 결정이며 정확하다.

### 5. 실측 숫자 "62 operation / 52 path" — OpenAPI 전체 기준으로 재현됨 (미세 자기모순)

재측정 결과 두 기준이 다른 숫자를 낸다:

| 기준 | paths | operations |
|---|---|---|
| OpenAPI 덤프 **전체** (`/health` 포함) | **52** | **62** |
| OpenAPI 덤프 비즈니스 (`/health`·`/docs`·`/redoc`·`/openapi.json` 제외) | 51 | 61 |
| FastAPI app 비즈니스 (위와 동일) | 51 | 61 |

작업 AI의 "62개 / 52 path"는 **OpenAPI 전체 기준(`/health` 포함)**과 정확히 일치한다. 작업 AI가 `dump_openapi.py` 출력에서 정직하게 쟀음이 확인됨.

다만 **브리프 54줄이 "`/health` 외 전부가 인가 대상"이라고 서술**하는데, 이 문장은 `/health`를 제외한다는 뜻이므로 — 그 제외 기준을 쓰면 61/51이다. 즉 숫자(62/52, `/health` 포함)와 한정어("`/health` 외", 제외)가 미세하게 안 맞는다. `/health`가 비즈니스 경로가 아니라 인가 대상이 아니라는 점에서 두 표현의 **의도는 같고**(≈62개 비즈니스 operation 전부가 인가 대상), 1개 차이는 D7 전수 가드의 대상 규모나 인가 정책의 의미를 바꾸지 않는다.

### 6. 브리프 ↔ 정본 ↔ HANDOFF 일관성 — 일치

- **D0=A**: 브리프 3줄(상태)·30–34줄(D0 헤더+오너 인용)·42–44줄(결정), 정본 36줄(변경이력)·250줄(본문), HANDOFF "Owner Decisions Needed" — 전부 "D0=A, 오너 2026-07-26"으로 동일.
- **D1~D8 목록**: 정본 36줄 "별도 서버 여부·인증 방식·소유권 모델·기존 데이터 귀속·삭제 의미·관리자 범위·인가 시행 지점·슬라이스 순서"(8개) ↔ 브리프 `## D1`…`## D8` 헤더(8개, 69·84·98·112·127·146·159·173줄) — 항목 수·순서 일치.
- **v1.7.49 참조**: 브리프 3·5·9·34·43줄, 정본 1·36·238·250·541줄 — 전부 v1.7.49.

### 7. CSRF/CORS 서술 (정본 238줄) — 방어적 권고는 맞으나, 비유가 느슨함

"쿠키 인증에서 CORS를 여는 것은 **CSRF 표면을 넓히는 일**이다"라는 서술은 방어적 권고(단일 origin 유지)라는 **결론은 정확**하나, 기술적으로 엄밀하지 않다. CSRF(cross-site 요청에 쿠키가 자동 첨부; SameSite 쿠키 속성·폼 방어 대상)와 CORS credentials(`Access-Control-Allow-Credentials` + 특정 origin; fetch 응답 읽기 허용)는 **관련되지만 다른 메커니즘**이다. "CORS를 넓히면 인증된 크로스사이트 공격 표면이 커진다"가 정확한 표현이다.

다만 **브리프 본문 D2=A(88줄)는 이 부분을 정확히 기술**한다 — "CSRF 대비 필요(SameSite=Lax + 상태변경은 POST/PUT/DELETE라 대부분 자동 방어)". 즉 느슨한 비유는 정본 238줄 한 곳뿐이고, 브리프의 실제 설계 권고는 정확하다. Follow-up(194–195줄)의 "CORS는 계속 닫아둔다… 쿠키 인증에서는 여는 순간 CSRF 표면이 커진다"도 같은 느슨한 비유를 반복한다.

### 8. 코드·회귀 무변 — 확인

`git show 6c144a8 --stat`: 변경 파일 4개(`system-contract-sot.md`·`multi-user-auth-cms-decisions.md`·`HANDOFF.md`·`work_log.md`). `services/`·`tests/`·`frontend/`·`schemas/` 부재. **코드·회귀 무변 주장 사실.** 따라서 이 검증은 회귀 스위트 실행을 포함하지 않는다(실행 대상이 없음).

## Issues / Risks

### Blocking (계약 의무)

**없음.** 이 슬라이스는 boundary literal(401/403 등)을 새로 도입하지 않고, 기존 내부 모순을 해소하며, 코드를 건드리지 않는다. 개정 4곳 모두 정본 다른 곳·코드와 일치한다.

### Hardening recommendations (비차단)

- **H1 — 62/52 숫자의 `/health` 포함/제외 일관성** (브리프 54줄·정본 36줄·HANDOFF "Owner Decisions Needed"). 숫자는 `/health` 포함 OpenAPI 전체 기준(62/52), 한정어는 "`/health` 외"(제외 → 61/51)이다. 규모 감각용 숫자라 인가 정책의 의미는 바뀌지 않으나, 둘 중 하나로 통일하면 더 정확하다 — 예: "`/health`를 제외한 61 operation / 51 path" 또는 "62 operation(`/health` 포함) 전부". 어느 쪽이든 D7 전수 가드가 담아야 할 범위는 `/health` 제외이므로, 61/51 쪽이 실제 구현 계약과 더 가깝다.
- **H2 — 정본 238줄·브리프 194–195줄의 "CSRF 표면" 비유 정정**. "CSRF 표면을 넓히는 일"을 "인증된 크로스사이트 요청 공격 표면(CORS credentials)을 넓히는 일 — CSRF는 SameSite=Lax로 별도 방어(D2=A)" 정도로 정정하면, 브리프 D2=A(88줄)의 정확한 서술과 정본이 같은 정밀도를 갖는다. 결론(단일 origin 유지·CORS 닫기)은 변함없이 유효하다.

두 건 모두 후속 슬라이스(D7 인가 시행 또는 문서 정정 증분)에서 자연스럽게 닫을 수 있다. 이 슬라이스의 합격을 막지 않는다.

## Verdict

**합격 (조건 없음).**

이유(하중을 지는 근거):

1. **개정 4곳이 전부 사실** — 보관 정책 "확정"(276줄과 일치)·`project_id` 강제 "살아남는다"(코드 시행)·v1.6.53 G3=A 참조(정확)·main.py:2242·2254(정확).
2. **시점 한정어 잔존 없음** — 현행 본문에서 "MVP는 단일 사용자"를 현행 사실로 기술하는 곳이 없다. 작업 AI의 "본문 4곳 개정" 주장 정확.
3. **기존 내부 모순 해소** — 직전 정본이 가진 §Core SOT(보관 확정) vs §Product Shell(보관/삭제 미확정) 충돌을 v1.7.49가 단일 진술로 수렴. CLAUDE.md §5 "계약 자체 교차 확인" 원칙에 부합.
4. **"배포 스택은 여전히 무인증" 경계가 3곳에 일관** — 이 슬라이스의 핵심 위험("계약에 있으니 있겠지")을 정본·HANDOFF가 명시적으로 방어. 다음 작업자의 오독 여지 차단.
5. **숫자 62/52가 OpenAPI 전체 기준으로 재현됨** — 작업 AI가 정직하게 쟀음이 실증(`/health` 포함/제외 한정어 불일치 H1은 비차단).
6. **코드·회귀 무변 확인** — 커밋이 docs/HANDOFF/work_log만 건드림.

비차단 H1·H2는 후속에서 닫을 수 있는 정확성 다듬기이며, 합격 조건이 아니다.

## Outstanding items

- **D1~D8 승인 대기** — 오너가 설계 결정 8건(별도 서버 여부·인증 방식·소유권 모델·기존 데이터 귀속·삭제 의미·관리자 범위·인가 시행 지점·슬라이스 순서)을 정해야 다음 슬라이스가 착수 가능. 브리프 각 항목에 추천안(A 계열)이 붙어 있으나 미승인.
- **dogfood(★) vs 인증 선후** — 여전히 실질 갈림길(HANDOFF "Owner Decisions Needed"에 ★★ D1~D8과 별도 ★ dogfood로 병존).
- **배포 노출 금지 유지** — 정본 251·541줄·HANDOFF가 못박은 대로, 인증 슬라이스가 끝나기 전까지 현재 무인증 스택을 외부에 노출하면 안 된다. 이것은 이 검증이 확인한 경계이자 운영 지시다.
- **작업 트리 clean, 커밋 `6c144a8` = HEAD**. 검증자는 슬라이스를 수정하지 않았다(H1·H2는 권고만, 미적용).

## Reproduction

```bash
# 커밋 구조 (docs-only)
git show 6c144a8 --stat

# 정본·브리프 diff
git show 6c144a8 -- docs/system-contract-sot.md
git show 6c144a8 -- docs/plans/multi-user-auth-cms-decisions.md

# 시점 한정어 잔존 여부 (현행 본문 = 이력 행 36·92·132 제외하고 238·250–253·541·544만 남아야 함)
grep -nE "(단일 사용자|MVP는|계정/인증이 없는|인증 없는|무인증|user_id를.*억지로)" docs/system-contract-sot.md

# 직전 정본의 내부 모순 (§Core SOT 보관 확정 vs §Product Shell 미확정)
git show 6c144a8^:docs/system-contract-sot.md | grep -nE "(archive로 처리|보관/삭제 정책)"

# project_id 강제 코드
grep -nE "project_id != project_id|is None" services/application/app/core_sot/service.py

# main.py archive DELETE (브리프 56줄 참조)
sed -n '2242,2260p' services/application/app/main.py

# 숫자 재측정 — OpenAPI 전체(62/52) vs 비즈니스(61/51)
python3 scripts/dump_openapi.py > /tmp/sot_openapi.json
python3 -c "import json;d=json.load(open('/tmp/sot_openapi.json'));p=d['paths'];print('all',len(p),sum(1 for v in p.values() for m in v if m in('get','post','put','patch','delete')));s={'/health','/docs','/redoc','/openapi.json'};print('biz',sum(1 for k in p if k not in s),sum(1 for k,v in p.items() if k not in s for m in v if m in('get','post','put','patch','delete')))"
```
