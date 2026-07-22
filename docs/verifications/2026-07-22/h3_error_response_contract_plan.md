# 검증 기록 — H3 에러 응답 계약 착수 결정 브리프 + work_log (오너 결정 D1~D4=A)

## Subject metadata

- **날짜**: 2026-07-22
- **요청자**: 오너 (entangelk) — "작업 AI가 작업한 내용 확인해서 검증하고 의심하고 또 의심해줄래? API 계약 세분화"
- **검증자**: Claude (독립 검증, 작업 AI의 산출물을 1차 소스에서 재도출)
- **검증 대상**:
  - `docs/plans/api-error-response-contract-decisions.md` (신규, untracked) — H3 착수 결정 브리프, 상태 Resolved (D1=A·D2=A·D3=A·D4=A)
  - `docs/daily_logs/2026-07-22/work_log.md` (modified) — H3 페이즈 착수 Task + H-2 노트 갱신
- **작업 소스**: working tree, uncommitted (`git status`: `?? docs/plans/api-error-response-contract-decisions.md`, ` M docs/daily_logs/2026-07-22/work_log.md`)
- **정본 참조**: `docs/system-contract-sot.md` (현재 v1.7.28; v1.6.94/v1.6.95가 H1/H2 계보), `docs/plans/frontend-api-contract-decisions.md` (H1/H2 Resolved 2026-07-16), `docs/verifications/2026-07-22/legacy_drafts_500_503_integrity_mapping.md` (500→503 fix의 H-2 발단)

## Scope

이 검증은 **계획/결정 문서**의 건전성을 다룬다 (아직 코드 슬라이스 아님 — S1~S5는 착수 전). 검증 표면:

1. **브리프의 실측 숫자 주장** (1차 소스) — endpoint 수, responses= 선언 수, HTTPException 상태코드 분포, ErrorDetailResponse 모델, gen:api 생성기 종류.
2. **S2 spine lock 리스트** (lines 99-119) — 각 endpoint의 선언 대상 에러 코드가 실제 코드와 일치하는가. 이것이 슬라이스의 실제 잠금 목표이므로 가장 load-bearing.
3. **선례 기반 주장** — H1(spinet-first·exact-key·silent-field-loss)이 실재하고 H3가 올바로 상속하는가; SoT 버전(v1.6.94/v1.6.95)과 "타입 계약 동기화" 절이 주장대로 존재하는가.
4. **결정의 전제 타당성** — D1=A(reason 코드 지연)의 전제인 "프론트는 status 분기"가 프론트 코드로 참인가.
5. **work_log 정확성** — D1~D4=A 기록, H-2 "skip→페이즈" 갱신의 정확성.

## Methodology

정량·코드 클레임은 전부 작업 AI의 숫자를 믿지 않고 1차 소스에서 재도출:

- **endpoint/분포 카운트**: `services/application/app/main.py`·`app/**/*.py`를 python 스크립트로 AST 근접 파싱 — `@app.<method>` 데코레이터(멀티라인 path 포함) 추출, 각 raise/JSONResponse 블록에서 `status_code=` 값 추출. 멀티라인 데코레이터·멀티라인 raise 모두 처리. (스크립트는 Reproduction 절에全文.)
- **responses= 선언**: `grep -nE 'responses=' main.py` + `http_models.py:257-289` 직독로 3개 dict(REVISE_AND_GATE_RESPONSES·ACCEPT_RESPONSES·GENERATE_ASYNC_RESPONSES)의 키 확인.
- **spine lock 리스트 교차**: 각 spine route의 decorator 줄 → 다음 decorator 직전까지 함수 본문에서 status_code 추출, 브리프 표와 1:1 대조. path-param 이름 불일치로 첫 패스에서 누락된 version/export 엔드포인트는 경로 전체 재추출로 보완.
- **202/동적 카테고리 확인**: `main.py:3230-3240`·`3693-3700` 직독로 `return JSONResponse(status_code=...)` vs `raise HTTPException` 구분.
- **선례**: H1 브리프(`frontend-api-contract-decisions.md`) 전문 + SoT changelog v1.6.94/v1.6.95 행 + "타입 계약 동기화" 절(line 219) 직독.
- **D1=A 전제**: `frontend/src/api/client.ts`의 `ApiError` 정의 + status 분기 지점(`=== 502/503/504`, `>= 500`) + detail 사용처 grep로 "문자열 파싱 분기 없음" 확인.

## Findings

### 1. 실측 숫자 — 대부분 정확, 동기부여 절에 정밀도 문제 3건

| 클레임 (브리프 line 27) | 재도출 결과 | 판정 |
|---|---|---|
| endpoint 61개 | 61 | ✓ 정확 |
| responses= 선언 3개 | 3 (generate=202, revise-and-gate, accept) | ✓ |
| `ErrorDetailResponse{detail:str}` 단일 (`_DETAIL_ONLY`) | `http_models.py:158-162`에 정확히 존재 | ✓ |
| gen:api = openapi-typescript 타입 전용 | `frontend/package.json:11` 정확 | ✓ |
| HTTPException 분포 404×62 | 62 | ✓ 정확 |
| 400×30 / 503×18 / 409×16 / 504×7 | 30 / 18 / 16 / 7 | ✓ 전부 정확 |
| **502×20** | **19** | △ 1 차이 |
| **동적 status_code=status ×9** | 9줄(`status_code=status` 9회)이나 **raise HTTPException + return JSONResponse 혼합** | △ 카테고리 불분확 |
| **202×1** | **0** (raise HTTPException 기준) | ✗ 카테고리 오류 |

- **`202×1`는 카테고리 오류** (`main.py:3235`는 `return JSONResponse(status_code=202, content={"job":...})` — async-generate의 **success arm**이지 `raise HTTPException` 에러가 아님). "raise HTTPException 상태코드 분포"에 success 상태를 넣음.
- **동적×9**: grep은 `status_code=status` 9회를 잡지만, 예컨대 `main.py:3695`는 `return JSONResponse(status_code=status, ...)`(partial-envelope 반환)로 raise가 아님. 9는 줄 수로는 맞으나 "(ProviderError 매핑) raise"로 특성화하면 loose.
- 이 셋은 **동기부여(motivation) 절**의 정밀도 문제. 정성 클레임("에러는 대부분 미선언")은 404×62 등 실제 raise가 뒷받침하므로 D1~D4 결정을 뒤집지 않음. 단 브리프가 "1차 소스 실측"이라고 명시한 만큼 정밀도가 credibility에 영향.

### 2. "에러 선언 3개 endpoint" — 정밀도 문제 (비차단)

브리프는 generate·revise-and-gate·accept 3개를 "이미 에러 응답을 선언한 endpoint"로 묶고(line 14, 25), D1=A를 "기존 3 writing endpoint와 동형"이라 서술(line 50). 그러나:
- `generate`의 `GENERATE_ASYNC_RESPONSES`는 **202 success arm만** 선언(`http_models.py:283-289`), 에러 모델 없음.
- `_DETAIL_ONLY` 에러 본문 선례는 **revise-and-gate + accept = 2개**.
- 결론 불변이나, D1=A의 "기존 3 endpoint와 동형"은 에러 본문 기준으로 **2**가 정확. 동기부여 과대 서술.

### 3. S2 spine lock 리스트 (lines 99-119) — **전부 정확 ✓ (가장 중요)**

각 endpoint의 선언 대상 코드를 실제 함수 본문의 raise/JSONResponse status와 1:1 대조:

| endpoint | 브리프 | 실측 | |
|---|---|---|---|
| POST /projects | (422 자동) | none | ✓ |
| GET /projects | — | none | ✓ |
| GET /projects/{id} | 404 | 404 | ✓ |
| PATCH /projects/{id} | 404,409 | 404,409 | ✓ |
| DELETE /projects/{id} | 404 | 404 | ✓ |
| GET/PUT /brief, brief/versions, brief/versions/{v} | 404 / 404,409 / 404 / 404 | 일치 | ✓ |
| POST /drafts (create) | 404,409,503 | 404,503,409 | ✓ (순서만 상이) |
| GET /drafts (list) | 404,503 | 404,503 | ✓ |
| GET /drafts/{id} | 404 | 404 | ✓ |
| PATCH /drafts/{id} | 404,409 | 404,409 | ✓ |
| DELETE /drafts/{id} | 404 | 404 | ✓ |
| GET drafts/versions, /{v} | 404 | 404 | ✓ |
| GET versions/{v}/export | 400,404 | 400,404 | ✓ |
| GET project/export | 400,404,503 | 400,404,503 | ✓ |
| PUT draft-order (reorder) | 404,409 | 404,409 | ✓ |
| POST versions (save) | 404,409,400 | 404,409,400 | ✓ |

20개 엔드포인트 전부 일치. spine 영역(1803-2185)의 에러 보유 엔드포인트 18개가 lock 리스트에 누락 없이 정확한 코드로 매핑됨. 503(list/create/export)은 commit `1f526fe`의 `DraftOrderIntegrityError → 503`과 일치. 이 표가 S2 구현의 실제 잠금 목표이므로, **정확성이 확인된 상태에서 S2는 코드 진실에 부합하게 선언 가능**.

### 4. S2 범위 자기모순 — "spine 14" vs lock 리스트 20 (S2 착수 전 해소 권장)

- **D2=A 및 S2 행(line 92)**: "spine 14 = projects 5 + drafts 5 + versions 4"(= H1의 정확한 14)를 명시. H1 브리프(line 27)와 SoT v1.6.95가 같은 14로 확정.
- **lock 리스트 표(lines 99-119)**: 14에 **brief 4 + draft-order 1 + project-export 1 = 6개**를 더해 **20개** 열거. 이 6개는 H1 spine 14에 **포함되지 않았음**을 H1 브리프·SoT v1.6.95로 확인.
- 확장 자체는 오너의 H-2 의도("CRUD 패밀리 전체 + reorder + export", work_log line 241)와 부합하나, **문서가 "14"라고 쓰면서 "20"을 나열**하는 자기모순. S2 착수 시 범위 혼란 유발.
- 해소: (a) lock 리스트를 H1 14로 줄이고 6개를 별도 슬라이스로, 또는 (b) 라벨을 "spine 14 + CRUD-family 6"으로 정정. 둘 다 acceptable.

### 5. 선례 기반 — 타당 ✓

- H1(spinet-first D1=A·D2=A, exact-key 안전망 먼저, silent-field-loss 리스크) 실재 (`frontend-api-contract-decisions.md` 전문).
- H3의 "silent-field-loss 리스크 거의 없음" 주장(line 33) 타당 — 성공 모델과 달리 에러는 단일 `ErrorDetailResponse` 재사용이라 "모델이 payload보다 좁아 필드 소실" 구조가 없음.
- SoT v1.6.94(v1.6.93 계약의 code slice, 갭 기록)·v1.6.95(H1 spine + H2 확정) 존재. **SoT line 219 "타입 계약 동기화" 절이 이미 `responses={}` 패턴을 partial envelope에 대해 문서화 중** — H3는 이 패턴을 plain error로 확장. 즉 H3는 신규 패턴이 아니라 기존 선례의 확장이며, D3=A 근거가 더 강함(브리프는 이를 명시하지 않으나 비차단 보강 후보).

### 6. D1=A 전제 (프론트 status 분기) — **참으로 확인 ✓**

`frontend/src/api/client.ts`: `ApiError(status, detail)`는 둘 다 보존(8, 27, 315)하되 분기는 전부 숫자 status — `err.status === 502`(348, partial 처리), `=== 503`(620), `=== 504`(626), `>= 500` retryable(312, 632). `detail`은 표시 전용(`${err.status}: ${err.detail}`). **detail 문자열 파싱 분기 0건**(`readDetail` 32-38은 display 추출, `typeof partial.detail === "string"` 361은 타입 가드). 따라서 D1=B(reason 코드) 지연은 합리적 — reason을 쓰는 기존 프론트 코드가 없으므로 지금 도입은 Simplicity First 위반 소지.

### 7. work_log 정확성 — **정확 ✓**

- D1~D4=A 기록(work_log "User Decisions and Rationale")이 브리프와 1:1.
- H-2 노트 갱신(line 241): "최초 skip 권고 → 오너 재검토로 뒤집힘 → 부채가 아니라 다음 페이즈(H3)" — 오너 의도·근거를 정확히 보존. "세 endpoint만 503 넣는 부분 패치는 최악(불완전+불일치)" 논리도 타당.
- Next steps의 `start_next_unit` 부채 "→ H3 S5로 흡수" 표기 정확(브리프 line 142와 일치).

## Issues / Risks

### Blocking (계약 의무)
없음. 이 검증 대상은 계획/결정 문서이며 코드 계약·회귀 잠금은 아직 착수 전(S1~S5). D1~D4 결정은 정본·선례·실측에 기반해 건전하고, S2 lock 리스트(구현 시 실제 잠금 목표)는 코드 진실과 전부 일치. boundary matrix의 빈 cell·미선언 분기 문제는 슬라이스 구현 시점에 적용될 사안.

### Hardening recommendations (비차단, 현 spec을 넘는 보강)
- **H-1 (권장, 커밋 전 정리)**: 브리프 동기부여 절의 분포 숫자 정정 — `202×1` 삭제(success JSONResponse 오분류), `502×20`→`19`, 동적×9를 "raise + JSONResponse partial 혼합"으로 명시. 1차 소스 실측을 표방한 만큼 정밀도 유지 권장.
- **H-2 (권장, 커밋 전 정리)**: "에러 선언 3개 endpoint"·D1=A "기존 3 endpoint와 동형"을 "2개(revise-and-gate·accept); generate는 202 success arm만"으로 정정.
- **H-3 (S2 착수 전 필수 해소, 비차단)**: §4 자기모순 — "spine 14" 라벨 vs lock 리스트 20. 라벨을 "spine 14 + CRUD-family 6(brief/draft-order/project-export)"로 정정하거나, lock 리스트를 14로 줄이고 6개를 별도 슬라이스로. H1 선례(D2=A가 "H1과 동일 spine 14"를 명시)와의 정합을 위함.
- **H-4 (문서 보강)**: 브리프에 SoT line 219가 이미 `responses={}` 패턴을 문서화 중임을 명시 — H3가 기존 선례 확장임을 드러내 D3=A 근거 강화.
- **H-5 (S5 착수 시 확인)**: `start_next_unit` 503 방어 — commit `1f526fe`가 고친 것은 create/export/list이고 accept/start_next_unit은 별개. S5에서 `writing_accept_endpoint`가 `DraftOrderIntegrityError`를 이미 잡는지 우선 확인(이중 방어 회피).

## Verdict

**조건부 합격 (conditional pass)**.

- **합격 근거**: D1~D4=A 결정은 정본(v1.6.94/v1.6.95)·H1 선례·1차 소스 실측에 기반해 건전. 가장 load-bearing한 산물인 **S2 spine lock 리스트 20개 엔드포인트 전부 실제 코드와 정확히 일치**. D1=A의 전제(프론트 status 분기) 프론트 코드로 검증 완료. work_log의 오너 결정·H-2 갱신 정확.
- **조건**: 
  - H-3(S2 범위 "14 vs 20" 자기모순)은 **S2 착수 전** 해소 필요.
  - H-1/H-2(분포 숫자·"3 endpoint" 정밀도)는 커밋 전 정리 권장이나, 결정·lock 리스트 정확성에는 무영향이므로 커밋을 차단하진 않음.
- **S1(SoT 전역 에러 계약 섹션)은 조건 없이 진행 가능** — spine 카운트와 무관.

## Outstanding items

- 작업 AI가 **오너 greenlight 대기 중**: (1) 계획 문서 + work_log 커밋, (2) S1 착수.
- 본 검증의 권고: 커밋 전 H-1/H-2 정리(빠른 문서 편집)를 같이 넣으면 깔끔. H-3은 S2 직전에 해소. S1은 즉시 진행 무방.
- 코드 변경 없음(전부 문서). 검증도 코드 무변경.

## Reproduction

```bash
# 1. endpoint / responses= 카운트
grep -rnE '@app\.(get|post|put|patch|delete)\(' services/application/app/main.py | wc -l   # = 61
grep -nE 'responses=' services/application/app/main.py                                     # = 3 lines

# 2. HTTPException 분포 (멀티라인 인식 python 카운트; 아래 스크립트)
python3 - <<'PY'
import re, glob
c={}
for f in glob.glob('services/application/app/**/*.py', recursive=True):
    for m in re.finditer(r'raise\s+HTTPException\s*\((.*?)\)\s*(?:from\s+\w+)?', open(f,encoding='utf-8').read(), re.S):
        sm=re.search(r'status_code\s*=\s*([^,)\n]+)', m.group(1))
        if sm:
            v=sm.group(1).strip(); k='DYN' if not v.isdigit() else v; c[k]=c.get(k,0)+1
print(sorted(c.items(), key=lambda x:(not x[0].isdigit(), x[0])))
PY
# 404=62, 400=30, 503=18, 409=16, 502=19, 504=7, DYN=5(raise만; JSONResponse 동적 포함 시 grep status_code=status = 9)

# 3. 202가 raise인지 확인 (JSONResponse success arm)
sed -n '3230,3240p' services/application/app/main.py

# 4. spine lock 리스트 교차 (각 route 함수 본문의 status_code 추출)
python3 - <<'PY'
import re
lines=open('services/application/app/main.py',encoding='utf-8').read().splitlines()
N=len(lines); deco=[]; i=0; pat=re.compile(r'@app\.(get|post|put|patch|delete)\(')
while i<N:
    m=pat.search(lines[i])
    if m:
        s=i; buf=lines[i]; j=i
        while buf.count('(')>buf.count(')'): j+=1; buf+='\n'+lines[j]
        pm=re.search(r'@app\.\w+\(\s*["\']([^"\']+)["\']', buf)
        deco.append((s+1,m.group(1).upper(),pm.group(1) if pm else '???',s,j)); i=j+1
    else: i+=1
for k in range(len(deco)):
    ln,method,path,s,e=deco[k]; end=deco[k+1][3] if k+1<len(deco) else N
    if not(1800<=ln<=2200 or 'export' in path): continue
    body='\n'.join(lines[s:end]); r=[]
    for m in re.finditer(r'(?:raise\s+HTTPException|return\s+JSONResponse)\s*\((.*?)\)\s*(?:from\s+\w+)?', body, re.S):
        sm=re.search(r'status_code\s*=\s*([^,)\n]+)', m.group(1))
        if sm: v=sm.group(1).strip(); r.append('DYN' if not v.isdigit() else v)
    print(f"L{ln:5} {method:6} {path} -> {r if r else '(none)'}")
PY

# 5. ErrorDetailResponse / _DETAIL_ONLY
grep -nE 'class ErrorDetailResponse|_DETAIL_ONLY' services/application/app/writing/http_models.py

# 6. gen:api 생성기
grep -nE 'gen:api|openapi-typescript' frontend/package.json

# 7. D1=A 전제: 프론트 status 분기 / detail 파싱 부재
grep -nE 'class ApiError|err\.status ===|\.status >= 5|readDetail' frontend/src/api/client.ts

# 8. 선례·SoT 버전
grep -nE 'v1\.6\.9[45]|척추 14|타입 계약 동기화' docs/system-contract-sot.md docs/plans/frontend-api-contract-decisions.md
```
