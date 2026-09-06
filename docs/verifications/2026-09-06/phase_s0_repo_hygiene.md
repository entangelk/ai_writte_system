# Phase S-0(공개 저장소 문서 위생) 독립 검증

## Subject metadata

- 일자: 2026-09-06 · 요청자: 오너("검증하고 의심하고 또 의심") · 검증자: Claude Code(구현자와 다른 세션)
- 대상: Phase S-0 슬라이스 — 커밋 `0b64a73`(브리프) → `5aa7687`(시행) → `13ad728`(기록). 트리 clean.
- 정규 스펙: 브리프 [`docs/plans/security-phase-s0-docs-hygiene-decisions.md`](../../plans/security-phase-s0-docs-hygiene-decisions.md)(Resolved — D1=D · D2=A+D · D3=D · D4=A · D5=A) · [`HANDOFF.md`](../../../HANDOFF.md) 머리 "공개 저장소 보안 규칙" · 구현 기록 [`../../daily_logs/2026-09-06/work_log.md`](../../daily_logs/2026-09-06/work_log.md) 세션 12
- 환경(측정 문맥): WSL2 `DESKTOP-27QM1FP` · mypy 2.3.1 설치 · `elasticsearch` 파이썬 패키지 **부재** · `docker-compose.test.yml` test-mongo Up(healthy)

## Scope

1. 스윕 완결성 — 실주소 3종·평문 비밀값 잔존(감사 기록 예외 외 0인가)과 치환 리터럴(D2)
2. D4 코드 변경 — `scripts/` 3종 환경변수 필수화·exit 2
3. 가드(`tests/test_repo_hygiene.py`) — 규칙 둘·예외·조각 조립·옥텟 4·untracked 커버
4. ★ 뮤테이션 — 구현자 10종 표 대조 + **검증자 독립 설계 5종**(특히 "가드가 자기 예외를 추가한다"는 방향 — 구현자 표에 없는 축)
5. 기록 4종 — work_log 세션 12 · CHANGELOG · HANDOFF · README/plans README 기준선
6. 전수 재실행 — 2879 passed / 4 skipped 클레임

## Methodology

- **잔존 측정**: 금지값(값 자체는 가드 `_FORBIDDEN_VALUES` 조각에서 조립해 사용 — 이 기록에는 적지 않는다)을 `git grep -lE`/`-oE`로 HEAD·`1f72cc5`·`0b64a73`·`5aa7687` diff 4지점에서 계산. **라인 수**(`git grep -E | wc -l`)와 **발생 수**(`-oE`)를 구분해 재었다.
- **우회 탐색**: `_PRIVATE_HOST_RE`을 직접 import 해 14개 경계 입력(후행 `.`·`,`·`)` · CIDR · 3옥텟 · 5옥텟 · 선행 숫자 · `10.x` 변형)을 투입. 완화 정규식(후행 `.` 허용)으로 `docs/`+루트 `*.md` 전수 재스캔해 가드가 놓치는 실제 발생 수를 셈.
- **뮤테이션**(검증자 5종 — 매번 커밋 후 `git status --short` empty 게이트 → 변형 → `python3 -m pytest tests/test_repo_hygiene.py -q` → `git checkout --`/`rm` 복원 → clean 재확인. 판정은 요약줄 failed 수로):
  - V-M1 브리프 문서 끝에 배포 호스트 주소 삽입(under-strict)
  - V-M2 untracked 신규 파일에 베타 주소 삽입(under-strict)
  - V-M3b 정확일치 루프에 `tests/test_repo_hygiene.py` 자기 예외 추가 + 금지값 1종을 **통째로** 가드 파일에 주석 삽입(예외-확장 축)
  - V-M3c 자기 예외 없이 통값만 삽입(커버리지 실재 확인)
  - V-M4 후행 금지 클래스에서 `/` 제거(CIDR 통과 축이 load-bearing인가)
- **exit 2 실측**: `env -u LLAMA_BASE_URL python3 scripts/phase4_context_search_planner_live_smoke.py`(스크립트가 dotenv를 읽지 않음을 grep 확인한 뒤 — `.env` 소유 머신에서도 측정 유효).
- **전수**: `python3 -m pytest -q`(test-mongo healthy 확인 후).

## Findings

### 1. 스윕 완결성 — 일치(독립 재측정)

- HEAD에서 실주소 3종·평문 비밀번호는 **감사 기록 1파일에만** 잔존(주소 29발생/13라인 — D1=D 예외 범위와 정확히 일치). 계정명 `timeline_demo`는 D5 약속대로 보존.
- 치환 산술이 전부 닫힌다: `0b64a73` 시점 주소 보유 **57파일/165발생** − 감사기록 29발생 = **56파일/136발생 제거**. `5aa7687` diff의 `-`라인 136발생·`+`라인 0발생(재유입 없음) 실측. 브리프의 "56파일/134히트"는 **라인 수** 기준(134 재현), "136히트"는 **발생 수** 기준(재현) — 아래 H2 참조.
- 포트 보존(`:9080`), 벤치마크 JSON 2건 키 유지·값만 별칭(`"base_url": "http://<베타-LLM>:9080"`), 재현 `.sh`는 env 전달 확인용이라 값이 별칭이어도 기능 무변 — D2 약속 이행.
- `.env`는 `.gitignore:24-25`로 무시돼 가드 스캔 밖 — 실주소의 정당한 자리라는 설계와 일치.

### 2. D4 — 일치

- `scripts/` 3종에서 `DEFAULT_LLAMA_BASE_URL` 0건. `env -u LLAMA_BASE_URL …` → **rc=2 실측**(argparse required). 설정 시 `--llama-base-url`는 `[...]` 선택 인자·`--help` rc=0.
- 잔존 `DEFAULT_LLAMA_BASE_URL` 언급 12건은 문서 산문(CHANGELOG·work_log·브리프·감사기록 원문 보존)과 `services/llm_gateway/app/main.py`의 동명 상수(`host.docker.internal:9080` — 사설 주소 아님, 2026-08-15 검증이 정상이라 확인한 값)로, 클레임 범위(3종 live smoke)와 정확히 일치.

### 3. 가드 코드 — 동작 일치, 한 축에서 자물쇠가 죽어 있음(→ B1)

- 조각 조립(`"192.168." + "1.22"` 꼴)로 가드 파일 자체가 스캔 대상 — V-M3c 확인(통값 삽입 시 정확일치 셀이 가드 파일을 잡는다).
- 옥텟 4개 정확 요구: 정규식 구조 + `npm 10.9.8` 통과 + 5옥텟 통과 확인. CIDR 통과는 **2층 방어**(단위 셀 + `docs/system-contract-sot.md` 등 실콘텐츠): V-M4(`/` 제거)에서 6재실패.
- untracked 창: V-M2 확인. 비-UTF-8 추적 파일 10건은 전부 `docs/img/*.png` — 가드 계약("바이너리는 대상이 아니다")·감사 범위(텍스트)와 일치.
- 광의 규칙 허용목록 3행(감사기록·S-3 검증기록·2026-07-23 로그) 각각 사유 기술, 대상 파일이 실제 주소 보유(낡음 감지 셀의 전제가 참).

### 4. 뮤테이션 — 구현자 10종 표는 정직. 검증자 5종 중 1종이 **죽은 자물쇠**를 발견

| 변이 | 내용 | 결과 |
|---|---|---|
| V-M1 | 추적 문서에 실주소 재유입 | **2 failed**(정확일치+광의) ✓ |
| V-M2 | untracked 파일에 실주소 | **2 failed** ✓ |
| V-M3c | 가드 파일에 금지값 통째로(예외 없이) | **1 failed** — 스캔이 가드 파일을 덮음 ✓ |
| V-M4 | `/`를 후행 클래스에서 제거(CIDR를 잡게) | **6 failed** — CIDR 축 load-bearing ✓ |
| **V-M3b** | **자기 예외 추가 + 금지값 통째로** | **5 passed — 아무 셀도 안 물었다** |

V-M3b에서 서브테스트 4670→4666(가드 파일의 4값 subtest가 스캔에서 소실)으로 예외가 실제 효력을 냈는데도 초록이었다. work_log §4-1 "`test_the_guard_covers_its_own_file` 이 그 결정을 잠근다"는 주장과 상충 — 그 셀([`tests/test_repo_hygiene.py:136-142`](../../../tests/test_repo_hygiene.py))은 `_tracked_files()` **목록 멤버십**만 단정할 뿐 스캔 루프의 skip은 보지 않는다. 구현자 표의 M4·M5(물지 않음)는 NOT-fire 분기 확인(계약 표기·버전 문자열 통과)으로 정상 기록이며, 옥텟·경로 축(M6·M7)의 재현 가능성도 확인했다.

### 5. 기록 4종 — 일치(정정 권고 1건 → H2)

- work_log 세션 12(뮤테이션 10종 표 포함) · CHANGELOG 2026-09-06 행(skip 4 내역 명기) · HANDOFF 4곳(S-0 폐쇄 · Next Tasks 머리 · "새 것을 더할 때" 가드 한 줄 · 함정 절 "알파 skip 4 정상") · README 기준선 2803/3189→2879/7881 · plans/README 122/102→123/103(Resolved) — 전부 확인.
- SoT 무변 확인: `docs/system-contract-sot.md` 계약 버전 v1.8.33, `1f72cc5`→HEAD 버전행 0 변경 — 변경은 이력 2행(v1.6.89·90)의 주소 표기 치환뿐.

### 6. 전수 — 재현

- 본 머신: **2879 passed / 4 skipped / 7886 subtests, 324s** — 구현자 보고(2879/4/7881, 321s)와 passed/skipped 정확히 일치. subtest +5는 구현자 측정이 기록 커밋(13ad728, work_log 신규 1파일 = subtest +5) 이전이었음으로 설명된다(가드 단독 4665→4670도 동일 원인). skip 4 = lexical retrieval 3(`elasticsearch package not installed` — 사유 문구까지 재현) + 기존 기준선 1.

## Issues / Risks

### Blocking (계약 의무)

- **B1 — `test_the_guard_covers_its_own_file` 은 제 이름이 주장하는 계약을 잠그지 않는다(죽은 자물쇠, V-M3b 입증).** 브리프 D3 시행 확정 #1("예외로 빼면 그 자리가 다음 구멍")과 work_log §4-1("그 셀이 그 결정을 잠근다")이 요구하는 분기 — *정확일치 스캔에서 가드 파일(및 임의의 파일)이 예외로 확장되지 않는다* — 를 잡는 셀이 없다. 셀은 `assertIn(..., _tracked_files())`만 하므로, 스캔 루프에 `or relative == "tests/test_repo_hygiene.py"`를 더하고 금지값을 통째로 심어도 전수가 초록이다(실측: 5 passed, subtest 4개 소실). 브리프가 정확히 경고한 실패 경로(값을 통째로 쓰고 → 가드가 물고 → 예외로 "해결")를 아무 셀도 잡지 않는다. 검증 가이드 기준 "계약 요구 분기 무추적 = green bar 와 무관하게 blocking".

### Hardening (비차단)

- **H1 — 광의 규칙의 후행 마침표 우회(잠재, HEAD 피해 0).** `_PRIVATE_HOST_RE`의 `(?![0-9./])`가 `.`을 포함해, 문장 끝에 온 새 사설 주소(예: `192.168.`+`100.50`+`.`)는 3개 대역 모두에서 잡히지 않는다(직접 투입 확인). 완화 정규식으로 `docs/` 전수 재스캔 결과 **현재 놓치는 발생 0** — 잠재 결함. 처방 후보: 후행 클래스를 `(?![0-9/])(?!\.\d)`로 바꾸면 문장 끝 마침표는 잡고 5옥텟 문자열(`192.168.1.2.3`)은 여전히 통과한다(단, 점-접미 형태(`192.168.x.y.example.com`)는 새로 잡히므로 짝 셀 추가와 버전 문자열 4파일 재실측이 동반돼야 한다).
- **H2 — 측정 단위 혼란 정정(기록 정확성).** 브리프 착수 표 "134히트"는 라인 수, 시행 기록 "136히트"는 발생 수다. "브리프 자신이 포함돼 +2"라는 설명은 산술이 성립하지 않는다(브리프 초안은 4라인/9발생을 더했고, 정확한 관계는 57파일−감사기록=56파일, 165발생−29발생=136발생). 최종 수치(56/136)는 참이므로 치환 자체는 무결하나, 재검증자가 모순으로 오독할 수 있어 work_log/브리프 한 줄 정정을 권고.
- **H3 — 정확일치 예외 집합의 구조적 노출.** B1과 동일 근원: 예외가 인라인 `if relative == _AUDIT_RECORD`라 집합 자체가 단정 불가. `_EXACT_RULE_EXCEPTIONS = frozenset({_AUDIT_RECORD})`을 모듈 상수로 내고 셀이 그 구성을 단정하면 자기예외·제3의 파일 추가가 모두 잡힌다. 광의 허용목록 확장은 낡음 감지 션이 1차 방어(깨끗한 파일 등재 시 실패 — 구현자 M10 확인)라 완화 상태.
- **H4 — RFC1918 밖 클래스.** IPv6 ULA(`fd00::` 계열)·선행 0 변형·호스트명 형태는 광의 규칙 밖(정확일치는 문자열이라 변형에 무감각). 브리프가 "일반 시크릿 스캐닝은 별개 사안"으로 유예한 축과 같은 성격 — 계약 확장 여부는 오너 판단.

## Verdict

**조건부 합격** — 조건: 정확일치 스캔의 예외 집합 확장(가드 파일 자기예외 포함)을 실제로 잡는 회귀 셀을 추가할 것(V-M3b 변이가 재실패해야 한다).

근거: 스윕·치환·D4·가드 동작·기록은 전부 독립 재측정과 일치한다(잔여 0, 산술 폐쇄, exit 2 실측, 전수 2879/4 재현). 그러나 브리프·work_log가 "잠겼다"고 명명한 over-strict 축 하나가 실제로는 무셀 상태로, 이 저장소 검증 규범(계약 요구 분기 무추적 = blocking)상 그대로 합격할 수 없다. 조건은 상수 노출 한 곳+셀 하나 규모로 닫힌다.

## Outstanding items

- B1 조건 미결 — 오너가 다음 슬라이스(또는 별도 마이크로 슬라이스)에서 보강할지 정한다. 검증자는 규범상 조용히 고치지 않았다.
- 알파 호스트 `elasticsearch` 미설치로 인한 skip 3 — 사전존재 공백(work_log §발견). `requirements-dev.txt`에 실을지는 별개 오너 판단.
- 저장소 다음 작업은 Slice 5 독립 검증(HANDOFF Next Tasks 1).
- git 이력·커밋 메시지의 주소 잔존은 오너 결정으로 out of scope(D1 서술 확인).
- (사전존재, 본 슬라이스 무관) `docs/verifications/README.md` "전체 목록"이 **최신순**을 선언했는데 `### 2026-09-05` 절이 09-02 뒤에 끼어 있다 — 유래는 감사 등록 커밋 `a1f2033`.

## Reproduction

```bash
# 게이트: git status --short 가 빈 뒤에만 변형한다(verification.md §Mutation).
# 금지값은 이 기록에 적지 않는다 — 가드에서 조립한다:
VAL=$(python3 -c "import sys; sys.path.insert(0,'tests'); from test_repo_hygiene import _FORBIDDEN_VALUES as F; print(F[0][1])")

# V-M1: 문서 재유입 → 2 failed 기대
printf '\n_MUT %s_\n' "$VAL" >> docs/plans/security-phase-s0-docs-hygiene-decisions.md
python3 -m pytest tests/test_repo_hygiene.py -q | tail -1   # 2 failed
git checkout -- docs/plans/security-phase-s0-docs-hygiene-decisions.md

# V-M3b: 자기예외 + 통값 → 5 passed(=죽은 자물쇠) / V-M3c: 통값만 → 1 failed
#   tests/test_repo_hygiene.py 스캔 루프의
#   `if relative == _AUDIT_RECORD:` 를
#   `if relative == _AUDIT_RECORD or relative == "tests/test_repo_hygiene.py":` 로
#   바꾸고 모듈 주석에 "$VAL" 을 한 줄 넣는다. 각각 실행 후 git checkout -- tests/test_repo_hygiene.py

# H1 우회 실증(파일 수정 없음):
python3 - <<'EOF'
import sys; sys.path.insert(0,'tests')
from test_repo_hygiene import _PRIVATE_HOST_RE as RE
t = '192.168.' + '100.50' + '.'          # 문장 끝 마침표
print('후행 마침표:', bool(RE.search(t))) # False = 우회
EOF

# 잔여·D4·전수
git grep -lF "$VAL" -- .                    # 감사기록 1파일만
env -u LLAMA_BASE_URL python3 scripts/phase4_context_search_planner_live_smoke.py; echo "rc=$?"  # rc=2
python3 -m pytest -q | tail -1               # 2879 passed / 4 skipped
```
