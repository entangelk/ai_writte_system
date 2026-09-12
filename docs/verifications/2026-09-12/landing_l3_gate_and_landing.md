# 랜딩 ③ 본문 · ④ 가입 동의 게이트 · S-2 nginx 헤더 — 독립 검증

**조건부 합격** — 동의 스탬프의 **Mongo 영속 축이 무셀**이다(쓰기면에서 스탬프가 통째로 사라져도 277셀 전건 초록 — MV-A 실측). 세부 조건 둘: ① `tests/test_auth_users_mongo.py` 에 동의 축 셀 둘(게이트 이전 행 None 판독 + 스탬프가 `insert`·`replace` 문서에 실리는 쓰기면 왕복 — 같은 파일의 C-6·탈퇴축 선례 그대로) ② 확인란 문구의 버전 표기·약관·방침 링크 새 탭(`target="_blank"`)의 단정 셀(HANDOFF 10 완료 문언이 계약으로 적은 축). 이 둘을 닫으면 합격이다.

- **일시**: 2026-09-12 · **검증자**: 독립 세션 — 구현(세션 68)·문서 폐쇄 어느 쪽도 아니다
- **대상 커밋 4개**: `58a8ac9`(백엔드 동의 게이트) · `86a4de7`(프런트 동의 게이트) · `f36c7bd`(랜딩) · `b6fd464`(S-2 nginx 헤더)
- **정본**: SoT [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.8.59** 행(랜딩 ② 의 v1.8.56~58 계약 — "AuthGate 는 보호 구간만"·"푸터는 공개 표면에만"·"버전 핀 두 곳" 포함) · 방침 [`docs/legal/privacy-policy-draft.md`](../../legal/privacy-policy-draft.md) **제3조 본문**(머리말 고지는 Slice 5 편집 중이므로 제외) · 브리프 [`plans/landing-page-scope-decisions.md`](../../plans/landing-page-scope-decisions.md) D1=ⓒ·착수 순서 ③④·"② 가 실제로 만든 것" · HANDOFF 10·12번 완료 문언
- **환경 경고(다른 작업 AI 와 트리 공유)**: 검증 중 Slice 5 세션이 커밋 둘(`0379fe3`·`bcd30b2`)을 만들었고 `WITHDRAWAL_GRACE_PERIOD` 30→60 미커밋 편집이 잠시 나타났다 사라졌다(그 창에 `test_a_naive_stored_stamp_reads_back_aware` 1실패 — Slice 5 소관, 원복 확인). **그 어느 것도 건드리지 않았다**: 백엔드 변이는 HEAD 탈치 워크트리(`/tmp/vv_worktree`, `bcd30b2`)에서, 프런트 변이는 cp 백업 + Edit 역방향 + `cmp` 바이트 확인으로. 감사 대상 파일은 `b6fd464..bcd30b2` 사이 무변(`test_auth_users.py` 12줄은 Slice 5 의 핀 docstring 갱신 — 동의 셀 무변, `frontend/src/legal/*.md` 사본 둘은 Slice 5 이동).

## Scope

1. **게이트 백엔드** — 상수·400 단일 얼굴·서버 전용 저장·거절 재요청 새 스탬프·관리자/게이트 이전 None·Mongo 매핑·핀 셀
2. **게이트 프런트** — 미체크 제출 잠금(강제 클릭 포함)·바디 청구·문구 버전·새 탭 링크
3. **랜딩** — 루트 익명 얼굴(한계 셋·푸터·버튼 둘)·딥링크 제외·만료 건너뜀·LB1 네 얼굴·h1·스키마
4. **nginx** — server 레벨 배치·`always`·가드의 측정 축
5. **문서 정확성** — SoT v1.8.59 행 수치의 기록 대조(전수 재실행 불가 — 트리 이동, 아래 Methodology)

## Methodology

- 스코프 문서 전문 독해(위 정본 넷) → 경계 행렬 수립 → 코드/셀 대조 → 뮤테이션 6종(구현자 8종과 각이 다른 새 변이) → 원복 `cmp` 바이트 확인.
- 초점 회귀(메인 트리, 코드는 `b6fd464` 와 동일): `python3 -m pytest tests/test_auth_users.py tests/test_signup_throttle.py tests/test_auth_api.py tests/test_service_policy_contract.py tests/test_frontend_nginx_headers.py -q` → **264 passed / 1285 subtests**. 프런트: `cd frontend && npx vitest run src/App.test.tsx src/legal src/typeScale.test.ts --reporter=basic` → **53 passed / 4 files · EXIT=0**(출력 파일 캡처 후 grep).
- **전수(3034/1/4166·482/41)는 재실행하지 않았다** — 기록 세션 68 인용 + 귀속 산술로 대체: 프런트 `58a8ac9^..b6fd464` 의 `App.test.tsx`·`LegalPage.test.tsx` 신규 `it(` **+4**(478+4=482 성립) · 백엔드 `58a8ac9` 신규 `def test_` **+6**(동의 5+HTTP-400 셀 1) + nginx **+2셀**. 현재 트리는 Slice 5 커밋이 셀·문서를 더해 전수 카운트 재검증이 원칙적으로 불가능하다 — 이 한계 자체를 기록으로 남긴다(지시에 따름).
- **뮤테이션 6종** — 각 변이 전 프리플라이트 `git status --short`(메인 트리) / 워크트리 `git status --short`, 변이 후 초점 재실행, 원복 후 `cmp <파일> <백업>` 바이트 동일 + 재실행 초록. `SUBFAILED` 포함해 읽었다(가이드 규칙). 실제 diff 는 아래 표에 그대로 적는다.

### 변이 표 (변이 → 기명 셀)

| 변이 | 방향 | 적용한 diff(그대로) | 실측 | 기명 셀 |
|---|---|---|---|---|
| MV-A | under(방어 제거) | `users_mongo.py` `_doc` 에서 `"terms_agreed_at": value.terms_agreed_at,`·`"terms_version_agreed": value.terms_version_agreed,` **두 줄 삭제** | **277 passed / 0실패** (auth 4종 파일) | **없음 — 조건 ①의 실증** |
| MV-B | under(방어 제거) | `_entry` 의 `doc.get("terms_agreed_at")`→`doc["terms_agreed_at"]`(버전 필드도 같이) | 4실패 | **전부 타축 legacy 셀**(C-6·승인 status·탈퇴×2)이 우발 포착 — **동의 이름 셀 0** |
| MV-C | under | `LegalFooter.tsx` `export const TERMS_VERSION = "1.0";`→`"1.1";` | 3실패 | `legalSource.test.ts` 문서 핀 1 + `App.test.tsx` 바디 리터럴 2(`requests an account…`·`keeps the signup request…`) |
| MV-D | under | `Landing.tsx` 한계 `<li><strong>개인 프로젝트입니다.</strong>…</li>` 블록 삭제 | 1실패 | `shows the landing face…`(App 랜딩 표면 셀) |
| MV-E | under | `nginx.conf` server 레벨 `add_header X-Frame-Options "DENY" always;` 삭제 + `location /api/ {` 첫 줄에 같은 줄 삽입 | 2 SUBFAILED(기명 `X-Frame-Options`) | nginx 가드 양 셀(server 레벨·`always`) |
| MV-F | over | `AuthGate.tsx` `location.pathname === "/" && !sessionExpired`→`location.pathname === "/"` | 3실패 | 만료 셋(`returns to login…`·`partial-envelope…`·`revise-and-gate…`) |

## Findings

### 게이트 백엔드 — 주장 전부 코드에서 성립

- `TERMS_VERSION = "1.0"` 단일 상수(`users.py:119`); `request_signup` 이 `agreed_terms_version != TERMS_VERSION` 이면 `InvalidUserInput`(`users.py:385`) — 해셔·스토어 앞(비밀번호 상한 검사와 같은 자리). 라우터가 이를 **400** 으로 매핑(`routers/auth.py:113`), 모델은 관대(`api/models.py:90` `str | None = None`) — 누락·옛 판본 모두 400 단일 얼굴. HTTP 셀 `test_the_consent_gate_answers_400_not_422`(`test_signup_throttle.py:520`)이 누락 400·"0.9" 400·정상 201 셋을 한 셀에.
- **저장은 서버만**: `agreed_at = self._clock()`(`users.py:390`)·`terms_version_agreed=TERMS_VERSION`(신규 `users.py:436`·재요청 갈래 `users.py:413`) — 클라이언트 청구는 저장되지 않는다. 서비스 셀 5개(`test_auth_users.py::SignupConsentGateTest`)가 스탬프·누락 거절(행 무잔여 포함)·"0.9" 거절·**재요청 새 스탬프**(첫 동의 승계 금지, `later` 시각 단정)·관리자 `create_user` None(`users.py:316` 생성자가 동의 필드를 안 넣는 것과 짝)을 각각 잠금.
- **핀**: `test_service_policy_contract.py:34,62` — `from …users import TERMS_VERSION` + `_ENFORCED_VERSION = TERMS_VERSION`(import 로 상수를 가리킨다 — 문서만 고쳐도, 상수만 고쳐도 문다). 프런트 핀 `legalSource.test.ts:29,46` `ENFORCED_VERSION = TERMS_VERSION`(LegalFooter 상수 import) — **버전 핀 두 곳** 계약(v1.8.56 예고) 이행. MV-C 로 문서 핀과 바디 리터럴 둘이 물리는 것을 실증.
- **스키마**: `schema.d.ts:2688` `agreed_terms_version?: string | null` — gen:api 재생성 반영 확인. tier 핀 초록으로 operation 105 무변도 간접 확인.

### 게이트 프런트 — 잠금 축과 무잠금 축

- 미체크: 제출 버튼 `disabled` + `submitSignup` 가드 이중(`AuthGate.tsx:539-541`·`372-375`), 셀 `keeps the signup request behind the terms consent checkbox` 가 **강제 클릭으로도 요청 미발송**(fetch 호출 수 1)까지 잰다. 체크 전환 시 `switchMode` 가 `termsAgreed` 리셋(`AuthGate.tsx:333`).
- **무잠금(조건 ②)**: 확인란 문구 `(버전 {TERMS_VERSION})을 확인했고 동의합니다`(`AuthGate.tsx:529`)와 링크 `target="_blank"`(`AuthGate.tsx:527-528`)는 **어떤 셀도 단정하지 않는다** — `grep -rn "_blank\|새 탭" frontend/src/App.test.tsx frontend/src/legal/LegalPage.test.tsx` 무출력. HANDOFF 10 완료 문언이 *"약관·방침 링크는 새 탭 — 폼 입력 보존"* 을 계약으로 적었다. 문구에서 버전이 빠지거나 링크가 같은 탭이 되어도 전수는 초록이다(값 자체는 MV-C 가 물었던 바디·문서 핀이 다른 층에서 잠금).

### 랜딩 — 경계 행렬 전 셀 성립

- 루트 익명 → 랜딩: `initialMode={location.pathname === "/" && !sessionExpired ? "landing" : "signin"}`(`AuthGate.tsx:124-126`) — **라우팅 무변**(보호 구간 `path="*"` 한 자리 그대로). h1·한계 셋(승인제·외부 전송·개인 프로젝트)·방침 제4조 링크·버튼 둘을 App 랜딩 셀이 잠금(MV-D 재실패). **벤더 이름 무표기** — "외부 추론 서비스" 로만(`Landing.tsx:80`), 방침 제4조 3항이 정본이라는 SoT 문언과 일치.
- 딥링크 제외(over 셀)·만료 건너뜀(만료 셋, MV-F 로 재실증 — 배너 상실 방지 계약)·로그인 폼 h1 "로그인"(`AuthGate.tsx:460`)·랜딩 버튼 "로그인"→폼·"새 계정 요청"→확인란 있는 가입 폼(셀 둘).
- **LB1 네 얼굴**: `LegalPage.test.tsx` 한 셀이 랜딩(401)·세션 확인(pending fetch)·오류(500)·가입 접수(201)를 `unmount()` 로 끊으며 전부 **진짜 `App`**(=진짜 `AuthGate`)을 렌더해 통과 — "계약이 사는 자리를 셀이 지나는가"(v1.8.57 교훈) 충족. 푸터는 넷 전부에, 앱 셸에는 없음(over 셀 존재 — Slice ② 유산).
- typeScale 이관 목록에 랜딩 규칙 넷 등재(`typeScale.test.ts` MIGRATED) — 초록으로 확인.

### nginx — 가드가 계약의 두 축을 정확히 잰다

`nginx.conf:29-31` 세 헤더가 server 레벨(`location` 밖)에 `always` 로. 가드는 괄호 깊이 파서로 중첩 블록을 걷어 낸 **server 레벨 문자열**에 단정(`test_frontend_nginx_headers.py:33-61`) — MV-E(location 안으로 이동)가 두 셀 모두 `SUBFAILED(header='X-Frame-Options')` 로 재실패. CSP 미포함은 SoT 문언(AdSense 관측 전·오너 결정 동반)과 일치 — 계약 위반 아님.

### 문서 정확성

SoT v1.8.59 행·HANDOFF 10·12·세션 68 기록의 셀 수·증가 귀속·변이 8종 서술은 상호 모순 없음(위 귀속 산술). 전수 수치 자체는 현재 트리에서 재검증 불가(기록됨).

## Issues / Risks

### Blocking (조건)

- **C1 — 동의 스탬프의 Mongo 영속 무셀**. 방침 제3조 *"운영자는 동의한 시각과 동의한 문서의 버전을 기록합니다"* 의 배포 체계에서 기록이 사는 곳은 `users_mongo.py` 다. **MV-A: `_doc`(`users_mongo.py:158-159`)에서 동의 필드 두 줄을 지워도 auth 초점 277셀 전건 초록** — 가입마다 스탬프가 몽고에 안 쓰이는 배포가 조용히 나간다. 읽기면(`_entry:199-200` `.get`)도 동의 이름 셀이 없고(MV-B 의 4실패는 전부 C-6·승인·탈퇴 legacy 셀의 우발 포착), 게이트 이전 행 전부(=현존 계정 전부)가 KeyError 로 로그인 500 에 죽는 방향 역시 동의 축 셀이 잡지 않는다. **같은 파일에 선례가 둘 있다** — C-6 빈 셀(2026-08-02 검증 실측, 이후 셀 추가)·탈퇴축 `test_the_write_face_carries_the_stamp_through_insert_and_replace`(2026-09-08 검증 H1). 동의 축(같은 파일의 최신 필드 쌍)만 아무 셀도 받지 않았다. 처방: 그 두 선례의 모양으로 셀 둘 — ① legacy 문서(필드 없음)가 `None` 판독 ② 스탬프가 `insert`·`replace` 문서에 실리는 왕복(저장면 `collection.docs[…]` 까지).
- **C2 — 확인란 문구 버전·새 탭 링크 무셀**(위 Findings). HANDOFF 10 완료 문언이 적은 축(링크 새 탭 = 폼 입력 보존)에 단정이 없다. 한 셀로 충분: 문구에 `버전 1.0` 포함 + 두 링크 `target="_blank"`·`href` 단정.

### Hardening recommendations (비차단)

- **H1 — 로그인 폼 h1 "로그인" 무핀**: SoT 문언이 이름 변경을 계약으로 기록했으나 셀은 `아이디` 라벨로만 폼을 찾는다. h1 이 다른 문구로 바뀌어도 무셀(화면 낭독 사용자의 탐색 축).
- **H2 — 랜딩 벤더 표기 금지의 부정 단정 무셀**: "벤더 교체 시 방침과 함께 안 움직이면 거짓이 된다"는 축인데 랜딩에 `Google`·`Gemini` 토큰이 없음을 기계가 안 본다(금지 어휘 가드는 법률 문서만 본다).
- **H3 — 생성 스키마 무가드**: `schema.d.ts` 에 필드가 있음을 수동 확인(grep)했으나 `gen:api` 미실행 드리프트를 재는 셀은 이 슬라이스 범위 밖 — 회귀 관례에 이미 의존.

## Verdict

**조건부 합격** — C1(동의 스탬프 Mongo 영속 셀 둘)·C2(확인란 버전 문구·새 탭 링크 셀) 를 닫아야 합격이다. 그 외 축(400 단일 얼굴·서버 전용 저장·재요청 새 스탬프·소급 동의 금지·핀 두 곳·랜딩 네 얼굴·만료 건너뜀·nginx server 레벨·`always`)은 코드·셀·변이 삼각 대조에서 전부 성립했다. 판정 승격은 조건을 닫는 슬라이스가 아니라 **다음 독립 검증 세션**이 한다(v1.8.57 선례 — 조건을 닫은 세션이 자기 판정을 올리면 독립성이 사라진다).

## Outstanding items

- 다른 작업 AI(Slice 5)가 같은 트리에서 계속 작업 중 — 검증 중 커밋 둘(`0379fe3`·`bcd30b2`) 추가·`users.py` 30→60 미커밋 편집 일과성 관측. 이 기록은 그 어느 쪽도 판정하지 않는다.
- **등재 시점 충돌 관측(2026-09-12)**: 같은 창에 Slice 5 검증자의 미커밋 기록(`account_withdrawal_slice5_promotion.md`)·인덱스 행·건수 버프가 있었고, 이 기록의 등재로 레코드 총수가 **303건**(조건부 **97**)이 되는 순간 두 검증자의 숫자 버프가 겹쳐 잠시 302로 합쳐졌다 — 검증 세션 도중 상대 세션이 같은 파일들의 숫자를 303/97 로 조정해 정합(`test_docs_indexes` 17 passed / 316 subtests 확인). **이 기록 파일만 이 세션이 커밋한다** — 인덱스·루트 README 는 상대의 미커밋 편집과 같은 파일이라 커밋하면 그 반쪽 작업까지 실리므로 남겨 둔다(상대의 등재 커밋이 함께 가져간다).
- 전수 수치(3034/1/4166·482/41)는 세션 68 기록 인용이고 현재 트리 재실측 불가 — 기준선 갱신은 다음 전수 세션 몫.
- AdSense 화면별 제어(방침 제6조 2항 수정 동반)는 오너 결정 대기 — SoT 문언 그대로.

## Reproduction

```bash
cd <repo> && git status --short        # 무출력(프리플라이트; 다른 AI 편집 있으면 변이 금지)
python3 -m pytest tests/test_auth_users.py tests/test_signup_throttle.py \
  tests/test_auth_api.py tests/test_service_policy_contract.py \
  tests/test_frontend_nginx_headers.py -q     # 264 passed / 1285 subtests
cd frontend && npx vitest run src/App.test.tsx src/legal src/typeScale.test.ts \
  --reporter=basic                              # 53 passed / 4 files · EXIT=0
# C1 실증(MV-A): services/application/app/auth/users_mongo.py _doc 에서
#   "terms_agreed_at": value.terms_agreed_at,  및
#   "terms_version_agreed": value.terms_version_agreed,  두 줄 삭제 후
# python3 -m pytest tests/test_auth_users_mongo.py tests/test_auth_users.py \
#   tests/test_signup_throttle.py tests/test_auth_api.py -q   # → 277 passed (0실패)
# 원복: 역방향 편집 + cmp 바이트 확인(워크트리에서 했음: git worktree add --detach /tmp/w HEAD)
# MV-C: frontend/src/legal/LegalFooter.tsx TERMS_VERSION "1.0"→"1.1"
#   → legalSource 핀 1 + App 바디 2 실패 · MV-F: AuthGate.tsx initialMode 에서
#   "!sessionExpired &&" 제거 → 만료 셋 3실패 · MV-E: nginx.conf X-Frame-Options 를
#   location /api/ 안으로 → SUBFAILED(header='X-Frame-Options') 2
```
