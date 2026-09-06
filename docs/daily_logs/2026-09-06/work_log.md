# 2026-09-06 작업 로그

## 목표

- HANDOFF Next Tasks 0 의 남은 축인 **Phase S-0(공개 저장소 문서 위생)** 을 닫는다.
- 착수 전에 오너 결정을 받는다 — 이 항목은 *무엇을 고치는가*가 아니라 *어디까지 고쳐 쓰는가*가 쟁점이고, 그 답이 이 저장소의 이력 보존 원칙과 충돌한다.
- 스윕은 1회성이므로 **재유입 방지 가드**를 실제 산출물로 남긴다.

---

## 세션 12 — Phase S-0 문서 위생 (브리프 → 시행 → 뮤테이션)

### 1. 착수 전 실측

감사 기록(`security_audit_dual_workflow.md` §B.1~B.4 · §A.17)이 "47+ 파일"이라 적은 것을 직접 쟀다.

| 축 | 실측 |
|---|---|
| 스윕 대상 실주소 | **3개** — 베타 머신 LLM 호스트(현행) · 구 검증 머신 LLM 호스트 · 배포 호스트 LAN IP |
| 총 노출 | **56 파일 / 134 히트**(치환 시점 136 — 브리프 자신이 대상에 들어와 늘었다) |
| ├ 살아 있는 문서·코드 | 10 파일 / 18 히트 — `CHANGELOG.md`(7) · `system-contract-sot.md`(2) · `docs/plans/` 5파일(6) · `scripts/` 3파일(3) |
| └ 이력 계열 | 46 파일 / 116 히트 — `verifications/` 21 · `daily_logs/` 20 · `benchmarks/` 3 · `verification_briefs/` 2 |
| 평문 비밀번호 | 3 히트 / 2 파일 (확인용 계정) |
| 재유입 가드 | **0건** |
| `HANDOFF.md` 자신 | 이미 깨끗했다(2026-09-05 자가 검수가 걷었다) |

**실측이 감사보다 컸다.** 감사의 개별 발견은 47·50·53 파일로 서로 다르게 적혀 있었는데, 세 발견이 같은 대상을 다른 시점·다른 패턴으로 센 것이었다. 하나로 합쳐 재보정한 값이 56이다.

**착수 전에 드러난 것 둘.**

- **`scripts/` 3종이 사설 주소를 *동작하는 기본값*으로 들고 있었다**(`DEFAULT_LLAMA_BASE_URL`). 문서가 아니라 코드라 치환이 곧 동작 변경이고, 그 기본값은 구 검증 머신이 현역이던 기간 이후로 **이미 틀려 있었다**.
- **감사 기록 자신이 최대 집중 지점**이다. 고쳐 쓰면 발견을 서술한 문서가 발견을 재현할 수 없게 된다.

### 2. 결정 브리프 — 저장소 안의 규칙 충돌을 오너에게 올렸다

브리프 [`docs/plans/security-phase-s0-docs-hygiene-decisions.md`](../../plans/security-phase-s0-docs-hygiene-decisions.md).

**막힌 지점은 취향이 아니라 문서 간 모순이었다.**

- `HANDOFF.md:4`(공개 저장소 보안 규칙, 2026-08-28) — *"…IP·호스트명…을 `HANDOFF.md`·`docs/daily_logs/`·`docs/verifications/`·`CHANGELOG.md` 등 저장소 문서에 기록하지 않는다"* → **이력 계열을 지목한다.**
- `HANDOFF.md` 표준 제약(제품명 D5) — *"★ 이력 문서는 대상이 아니다 … 그것이 그때의 사실이다"* → **같은 계열을 면제한다.**

두 규칙은 축이 다르지만(보안 / 표시명) **대상 파일 목록이 같다.** CLAUDE.md §1 이 요구하는 대로 임의로 한쪽을 고르지 않고 오너에게 올렸다.

### 3. 오너 결정 (2026-09-06)

| # | 결정 | 근거 |
|---|---|---|
| **D1** | **D — 전 계열 전건 + 감사 기록만 예외** | 두 규칙 중 **보안 규칙이 canonical**. 더 최근이고 더 구체적이며(파일 계열을 열거한다), 제품명 면제는 *표시명* 축의 판단이지 비밀값 축의 판단이 아니다. 감사 기록만 예외인 이유는 **발견의 근거**이기 때문 |
| **D2** | **A + D — 산문은 역할 별칭, 코드는 환경변수** | 두 자리의 성질이 다르다. 산문은 *어느 머신이었나*를 남겨야 하고, 코드의 하드코딩은 애초에 값이 아니라 환경변수여야 하는 자리다 |
| **D3** | **D — 정확 일치는 전건, 광의 정규식은 문서 경로만** | 픽스처 마찰(광의를 전건에 걸 때의 비용)과 `scripts/` 구멍(경로 한정만 할 때의 비용)이 **서로 다른 축**이라 한 규칙으로 둘 다 못 잡는다 |
| **D4** | **A — `scripts/` 3종 환경변수 필수(fail-fast)** | 전부 외부 LLM 이 있어야만 의미가 있는 live smoke 다. `localhost` 기본값은 *조용히 틀린 곳에 붙는* 실패라 이 저장소가 반복해 경계해 온 형태 |
| **D5** | **A — 평문 비밀번호를 걷는다(계정명은 남긴다)** | 계정명은 비밀값이 아니고, HANDOFF Next Tasks 7 의 정리 대상 지시가 그 이름으로 대상을 가리킨다 |

**트레이드오프(오너가 받아들인 것)**: D1=D 는 **이력 문서 45개를 사후 편집한다.** 그 비용을 치른 이유는 역할 별칭이 이미 이 저장소의 표준 표기라(HANDOFF 머신 표·S-6·S-7) 편집이 *사실을 지우는 것이 아니라 표기를 규칙에 맞추는 것*이 되기 때문이다 — 어느 머신이 무엇을 했는지는 별칭으로 그대로 읽힌다. 원문이 필요한 자리(감사 기록)만 예외로 남겼다.

### 4. 시행

**스윕 — 56 파일 / 136 히트** (커밋 `5aa7687`)

- 실주소 3종 → `<베타-LLM>` · `<구검증-LLM>` · `<알파-호스트-LAN>`. **포트는 남겼다**(`.env.example` 이 공개하는 저장소 고정값이다).
- 각괄호를 쓴 이유: CommonMark 의 raw HTML 태그명은 ASCII 로 시작해야 하므로 태그로 해석되지 않고, 각괄호가 있어야 **자리표시자임이 한눈에** 보인다.
- 벤치마크 JSON 2건은 스키마를 유지한 채 값만 바꿨다 — 키를 지우면 그때 무엇에 붙어 측정했는지가 사라진다.
- 평문 비밀번호 3히트 → `` `timeline_demo`(비밀번호는 저장소 밖) ``.
- 감사 기록 1파일은 원문 보존.

**코드 — live smoke 3종**(`phase2a_provider` · `phase2b3_compare_judge` · `phase4_context_search_planner`)

```python
default=os.environ.get("LLAMA_BASE_URL"),
required=not os.environ.get("LLAMA_BASE_URL"),
```

환경변수가 있으면 종전대로 선택 인자, 없으면 argparse 가 **exit 2 로 즉시 멈춘다**(실측). `DEFAULT_LLAMA_BASE_URL` 상수는 제거했고 그 자리에 남은 빈 줄도 정리했다.

**가드 — [`tests/test_repo_hygiene.py`](../../../tests/test_repo_hygiene.py) 신설. 이것이 실제 산출물이다.**

파일에서 지워도 git 이력에는 남으므로(이력 재작성은 2026-08-23 에 한 번 했고 비싸다) 이 조치의 값어치는 **소급 삭제가 아니라 앞으로의 커밋을 막는 것**에 있다.

시행에서 확정된 네 가지 — 전부 셀로 잠겼다.

1. **금지값을 조각으로 조립한다.** 가드 파일에 값을 그대로 적으면 **가드가 자기 자신을 문다.** 조립의 대가로 **가드 파일도 검사 대상에 남는다** — 예외로 빼면 그 자리가 다음 구멍이다(`test_the_guard_covers_its_own_file` 이 그 결정을 잠근다).
2. **옥텟 4개를 정확히 요구한다.** 3~4개를 허용하면 `npm 10.9.8` 같은 **버전 문자열이 사설 주소로 잡힌다** — 초안이 실제로 그랬고 실측 4파일이 걸렸다.
3. **CIDR 표기(`/prefix`)는 통과**시킨다. `172.16.0.0/12`·`127.0.0.0/8` 은 신뢰 대역 계약 literal 이지 호스트가 아니다.
4. **`git add` 전의 새 파일도 검사한다.** 추적 파일만 보면 유출이 들어오는 바로 그 순간이 검사 밖이다.

광의 규칙의 허용목록은 **3건이고 각 행에 이유가 붙는다** — 감사 기록(오너 결정) · S-3 검증 기록(픽스처 IP 분류표가 문서의 내용 자체) · 2026-07-23 로그(도커 브리지 컨테이너 IP 로 홈 LAN 호스트가 아니다). 이유 없는 행이 생기면 다음 스윕이 그것을 지워도 되는지 판단할 수 없다. 예외가 낡는 것도 가드가 본다(`test_every_allowlist_entry_still_exists`).

### 5. 뮤테이션 — 10종, 커밋 후 변형 (사전 `git status --short` 비어 있음 확인)

기준선: `5 passed, 4665 subtests passed`.

| # | 적용한 변형 | 자리 | 재실패한 셀 | 판정 |
|---|---|---|---|---|
| M1 | 문서 끝에 베타 LLM 실주소 한 줄 추가 | `docs/daily_logs/2026-09-05/work_log.md` | `test_no_swept_address_or_secret_returns` + `test_documents_carry_no_private_host_address` (2 failed) | ✅ under-strict |
| M2 | 문서 끝에 평문 비밀번호 한 줄 추가 | 같음 | `test_no_swept_address_or_secret_returns` (1 failed) — IP 규칙은 안 문다(정상) | ✅ under-strict |
| M3 | **`scripts/`** 에 구 검증 머신 실주소 추가 | `scripts/phase2a_provider_live_smoke.py` | `test_no_swept_address_or_secret_returns` (1 failed) | ✅ 정확 일치가 코드 경로를 덮는다 |
| M4 | 문서에 CIDR 계약 literal 3종 추가 | `docs/daily_logs/2026-09-05/work_log.md` | **없음(5 passed)** | ✅ over-strict — 계약 표기를 안 문다 |
| M5 | 문서에 `npm 10.9.8 / node v22.23.1` 추가 | 같음 | **없음(5 passed)** | ✅ over-strict — 버전 문자열을 안 문다 |
| M6 | 정규식 `10` 분기를 옥텟 `{3}` → `{2,3}` 로 완화 | `tests/test_repo_hygiene.py` | `test_documents_carry_no_private_host_address` (4 failed) | ✅ **옥텟 수가 load-bearing** |
| M7 | `_is_document` 를 `tests/` 까지 확장 | 같음 | `test_documents_carry_no_private_host_address` (2 failed) | ✅ **경로 한정이 load-bearing** — 픽스처가 문다 |
| M8 | `git add` 안 한 새 파일에 배포 호스트 실주소 | `docs/daily_logs/2026-09-06/_mut.md`(untracked) | 2 failed | ✅ 추적 전 창이 닫혀 있다 |
| M9 | 정확 일치 규칙에서 감사기록 예외 제거 | `tests/test_repo_hygiene.py` | `test_no_swept_address_or_secret_returns` (4 failed) | ✅ 예외가 load-bearing(보존 결정이 실재한다) |
| M10 | 이미 깨끗한 파일(`CHANGELOG.md`)을 허용목록에 등재 | 같음 | `test_every_allowlist_entry_still_exists` (1 failed) | ✅ 낡은 예외가 조용히 안 남는다 |

전건 원복 후 `git status --short` 비어 있음 확인. **뮤테이션 결과는 `grep FAILED` 가 아니라 요약줄의 failed 수로 읽었다**(`pytest-subtests` 는 `SUBFAIL` 로 낸다).

### 6. 검증

- `tests/test_repo_hygiene.py` · `tests/test_docs_indexes.py`: **20 passed / 4958 subtests**.
- `tests/test_typecheck.py`(scripts/ 를 `call-arg`+`misc` 로 본다): **8 passed / 3 subtests**.
- 잔여 실주소·비밀값(감사 기록 제외): **0**.
- 전수(test-mongo ON, writable PRIMARY 확인 후): **2879 passed / 4 skipped / 7881 subtests, 321s**.

**★ 전수 판정은 `passed` 가 아니라 `skip` 수를 먼저 본다 — 이번에 4다(기준선 1).** 추가 3건은 전부 `test_context_search_memory_lexical_retrieval.py` 이고 사유가 *"elasticsearch package not installed"* 다. **이번 변경과 무관한 알파 호스트의 도구 공백**이고(`requirements-dev.txt` 에 `elasticsearch` 항목 자체가 없다 — 그 파일은 `mypy` 한 줄뿐이다), 해당 파일의 마지막 변경은 `747f5e4` 로 이번 슬라이스가 아니다. 기준선 2803/1 은 베타에서 잰 값이라 **머신-로컬 차이**다. 아래 §7 에 부채로 남겼다.

subtest 수가 3189 → 7881 로 뛴 것은 새 가드가 추적 파일 전건을 subtest 로 도는 탓이다(가드 단독 4665).

---

## 발견 — 알파 호스트에 `elasticsearch` 파이썬 패키지가 없어 셀 3개가 조용히 skip 된다

- **문제**: 전수 요약줄은 초록인데 lexical retrieval 셀 3개가 skip 이다. HANDOFF 가 이미 경계해 온 형태 — *"요약줄은 초록이다"*.
- **원인**: `requirements-dev.txt` 는 `mypy` 한 줄뿐이고 `elasticsearch` 를 안 싣는다. 베타에는 어떤 경로로든 설치돼 있었고 알파에는 없다.
- **처리**: 이번 슬라이스 범위 밖이라 고치지 않았다. **HANDOFF 함정 절의 "호스트 도구 공백"에 한 절 더했다** — 다음 사람이 알파에서 전수를 돌릴 때 skip 4 를 회귀로 오독하지 않게.
- **결과**: 판정에 영향 없음(스윕·가드와 무관한 축).

---

## 결정 — SoT 버전을 올리지 않았다

S-3·S-1 은 서비스 동작을 바꿔 SoT 버전(v1.8.30·v1.8.32)을 받았다. S-0 은 **저장소 문서와 개발용 스크립트 CLI**만 바꾸므로 서비스 계약이 무변이다. 이 축의 정본은 `HANDOFF.md` 머리의 공개 저장소 보안 규칙이고, 이번에 처음으로 **그 규칙을 강제하는 가드**가 생겼다 — 규칙 문언은 그대로 두고 검사를 붙였다(문언을 줄이면 계약이 약해진 채 합의된다).

---

## 다음 단계

1. **정체성 그룹 Slice 5 독립 검증** — HANDOFF Next Tasks 1. Phase S 에서 남은 것은 트리거 대기 항목(S-2·S-5·S-6)과 원격 서버 설정(S-7)뿐이라 저장소 안의 다음 작업이 여기다.
2. **S-7(cloudflared 토큰 저장 방식)** — 저장소 작업이 아니라 배포 호스트 설정이다. 오너가 서버에서 `--token-file`(0600) 또는 systemd `EnvironmentFile=` 로 옮긴다. **`Environment=` 는 안 된다**(`systemctl show` 로 드러난다).
3. `elasticsearch` 를 `requirements-dev.txt` 에 실을지 — 별개 판단(그 파일은 프로덕션 이미지와의 분리를 의도적으로 지킨다).
