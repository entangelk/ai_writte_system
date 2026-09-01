# 독립 검증 기록

이 디렉터리는 **구현자가 아닌 검증자가** 각 슬라이스를 다시 뜯어본 기록이다. 2026-06-24부터
**61일치 · 268건**이 쌓여 있다.

## 이 저장소의 검증이 무엇인가

일반적인 코드 리뷰가 아니라 **반증 시도**다. 검증자는 구현자의 보고를 사실로 받지 않고,
그것이 **틀렸다는 가설**로 접근한다. 각 기록은 같은 골격을 가진다.

| 절 | 무엇을 담는가 |
|---|---|
| Subject metadata | 대상 커밋·정규 스펙(SoT 조항)·검증자가 구현자와 다른 세션임을 명시 |
| Scope | 무엇을 볼 것인가 — 특히 **★로 표시된 것이 가장 의심스러운 축** |
| Methodology | 재현 절차. 명령과 실측값을 그대로 적어 제3자가 다시 돌릴 수 있게 한다 |
| Findings | 재현 결과. 구현자 보고와 **일치/불일치**를 항목별로 |
| Issues / Risks | **Blocking**(계약 의무 위반)과 **Hardening**(비차단)을 분리 |
| Verdict | 합격 · 조건부 합격 · 불합격 |
| Outstanding items | 남은 것. 오너 결정이 필요한 것은 여기로 올라간다 |

**핵심 기법 = 뮤테이션(mutation) 검증.** "테스트가 통과한다"로는 그 테스트가 *무엇을 잡는지*
알 수 없다. 그래서 고친 코드를 **일부러 되돌리거나 변형해** 회귀가 **다시 실패하는지**를 확인한다.
실패하지 않으면 그 테스트는 아무것도 잠그지 않고 있던 것이다. 회귀는 **양방향**을 요구한다 —
원래 결함을 재현하면 실패해야 하고(under-strict), 과잉 교정으로 정상 경로를 깨도 실패해야 한다
(over-strict).

## 판정 분포 (2026-09-01 기준)

> **판정 열은 그 기록의 *최종* 판정이다**(오너 2026-08-06: *"테스트의 목적은 조건이 닫히는
> 거니까"*). 조건부로 나갔다가 조건이 닫혀 승격된 기록은 **그 기록 자신의 최종 문구**를 따른다.
> 종전에는 발행 시점 판정이 섞여 있었고 판정 절이 있는데도 `—`인 행이 14건 있었다 — 2026-08-06에
> 17건을 기록 본문과 대조해 정렬했다. **판정은 이 셋뿐이다** — 종전의 `서술형`은 걷어냈다.
> *"판정 문구가 정형화되기 전 초기 기록"* 이라 정의돼 있었으나 **222건 전수 확인 결과 해당하는
> 기록이 0건**이었고(모든 기록이 `## Verdict` 절과 판정 문구를 갖는다) 가이드에 정의된 적도 없다.

| 판정 | 건수 | 뜻 |
|---|---|---|
| 합격 | 185 | blocking 결함 없음 |
| **조건부 합격** | **79** | 합격이되 닫아야 할 조건이 있었다 |
| **불합격** | **4** | 핵심 계약 위반으로 다음 슬라이스 진행이 차단됐다 |

**조건부 합격이 29%**라는 것이 이 절차가 형식이 아니라는 증거다. 검증이 실제로 지적을 냈고,
그 지적은 후속 커밋으로 닫혔다(각 기록의 Outstanding items → 이후 work_log의 hardening 절).

## 읽어 볼 만한 것 (처음 오는 사람)

절차가 실제로 무엇을 잡아내는지 보여 주는 기록들이다.

- [`2026-08-02/d8_7_g1c_loopback_exposure.md`](2026-08-02/d8_7_g1c_loopback_exposure.md) —
  **"시행 완료"가 파일 수준에서만 참이었다.** compose 포트 매핑을 고쳤지만 이미 만들어진
  컨테이너는 옛 매핑을 그대로 들고 있었다. 파일을 읽어 내린 결론을 `docker ps`가 뒤집은 사례.
- [`2026-07-31/k4_front_counter_budget.md`](2026-07-31/k4_front_counter_budget.md) —
  검증 도중 **재현율 ~1/9의 프론트 플레이크**를 관측하고, 원인을 단정하지 않은 채
  "내 변경 탓이 아닐 수 있다"는 판별 기준을 남겼다.
- [`2026-07-30/r_e_citation_numbers_audit.md`](2026-07-30/r_e_citation_numbers_audit.md) —
  검증 중 `git checkout --`으로 **미커밋 구현을 날린 사고**와 그 복구가 기록돼 있다.
  이후 이 저장소의 원복 절차가 바뀌었다.
- [`2026-07-28/auth_d8_5a_admin_boundary.md`](2026-07-28/auth_d8_5a_admin_boundary.md) —
  비차단 지적 하나(`관리자가 사용자 초기 비밀번호를 안다`)가 **오너 결정 항목으로 승격**돼
  아직 열려 있다(D8-5 C-6).

## 전체 목록

최신순. 같은 날 여러 건이면 슬라이스별로 나뉜 것이다.

### 2026-09-01

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`scene_note_slice_2.md`](2026-09-01/scene_note_slice_2.md) | 장면 메모 Slice 2(저장 API·활동 기록, `edec884`·`a0257d9`) 독립 검증. v1.8.13 경계 행렬(페이즈 §Slice 2 16항 포함) 전량 ↔ 셀 대응 확인, 구현자 변이 9종 중 7종 재실행 **전부 기록과 동일하게 재실패**(M9는 "삽입" 구성이 6 failed로 재현 — work_log의 "이동" 표기와 달리 두 독법 모두 물림) + **검증자 독자 변이 5종**(읽기 순서 이동 7셀·모델 경계·소유권 deps 제거 2파일 6fail·행위자 출처·**창 리터럴 5초→6초**). **차단 1건: 연타 창 "5초" 리터럴 무핀** — 변이로 6초로 바꿔도 46셀 green(테스트가 상수를 상징적으로 참조). 같은 계열 12000·200 무핀은 하드닝. 하드닝: SoT v1.8.13 행 "27→46" 오기(실측 23→46)·행위자 셀 docstring 과잉 주장(소유자==행위자 구조적 동일, 소유자 조회 변이가 46셀 통과). 집중 4파일 191/1116·collect 2666 재현. 전수 2663/9/1/3082+7 — 9 failed 전부 검증자 미등록 기록을 잡은 `test_docs_indexes`(등재 후 단독 green). | **조건부 합격** |
| [`final_save_conditions_closure.md`](2026-09-01/final_save_conditions_closure.md) | final-save 재검증 조건 폐쇄(`67e8609`) 3차 재검증. **R1·B4 실측 폐쇄**(semantic 토큰 정의+사용·designTokens 5/5, 변이 재실패 · S1~S13 프로브의 pytest 편입 `tests/test_final_save_analysis.py` 1 passed, H1 변이로 셀 재실패 — 전수 green bar가 이제 finalize 계약을 안다). **R2 계약 시나리오 폐쇄**(변이 잠금, 실패 경로 reload 없음·저장 후 stale 필드로도 "필요" 전환 확인)이지만 **잔여 조건 3**: R3 reloadLatest의 getDraft 추가로 채택 흐름 3셀 red(목 미갱신 — 목 갱신 또는 호출 국한), R4 `--status-danger`가 브리프 semantic 표에 미등재(`PaletteProvenanceTest` red 단독 재현 — 위성 표 계열), D5(200 vs 502) 미확정(502 선언은 의도적 유지 확인). 프런트 전수 3 failed 전부 R3, 백엔드 9 failed = docs 가드 7(미등재) + R4 1 + live-mongo 부하 플레이크 1(단독 green). | **조건부 합격** |
| [`final_save_hardening_recheck.md`](2026-09-01/final_save_hardening_recheck.md) | final-save 보강(`66ece84`·`30a9194`) 재검증. **백엔드 차단 7건·H1 실측 폐쇄** — dedupe 행·B2 수정·조립 호환·라벨·키 핀·tier 74/100·봉투 재조회 전부 suite+요청 실행으로 확인(변이 M-A~M-D 전부 재실패, 역배선은 wiring 가드가 구현자 스스로 잡은 흐름과 일치). 프로브 전환본(패치 없음) **41단정 전부 통과** — D4=A 실행 경로가 끝까지 돈다. **잔여 조건 4**: R1 `--danger-600` 프리미티브 직접 사용(designTokens semantic 라우팅 red — 선행 하드닝 권고의 방향 정정), R2 수동 분석 성공 후 상태 바 "분석 필요" 고정(**실앱 회귀** — 라벨 우선순위가 갱신되지 않는 draft.* 필드로 이동, AnalysisTrigger는 onStatusChange만 보고), B4 finalize 셀의 suite 부재(잠금은 프로브가 홀로, M-B는 크래시 잠금), D5(200 vs 502) 오너 미확정. 백엔드 전수 7 failed 전부 검증자 미등재 기록(제품 셀 0 — 선행 11 failed 소멸), 프런트 슬라이스 귀속 red 2셀+부하 플레이크 1(단독 green). | **조건부 합격** |
| [`final_save_analysis_checkpoint.md`](2026-09-01/final_save_analysis_checkpoint.md) | 최종 저장·분석 연동 D4=A 체크포인트(`832089b`·`0922a24`) 독립 검증. 작업자 주장(컴파일·분류 가드 18/193·tsc·schema.d.ts 재생성)은 **전부 정확히 재현** — 그러나 엔드포인트로 요청 1건을 보낸 적이 없어 **기능 전체가 동작하지 않는 채 커밋**된 것을 프로브가 포착: ①과금 dedupe 표 무매핑 → 전 finalize 요청 503 fail-closed ②`_require_active_project_and_draft`(→None) 반환값 사용 → 성공 경로 전무(500; 커밋 시점의 mypy 가드가 이미 지목) ③유료 402/429 미선언 ④final API 회귀 셀 0개 ⑤프런트 vitest red 3셀(상태 바 "분석 미실행" pin 파열 + 디자인 토큰 2 — 미정의 `--status-danger`·raw 색) ⑥`register_drafts` 시그니처 변경에 조립 지점 5곳 미갱신 ⑦활동 라벨표 미추가(화면 리터럴 폴백) ⑧DraftPayload 키 핀 미갱신 ⑨tier 행렬 미배치(확정 계약 갱신 의무). **백엔드 전수 11 failed·프런트 3 failed 전부 이 슬라이스 유래로 main red.** B1·B2 런타임 패치 아래 경계 행렬 14행은 **13행 준수**(잔여 H1: runner 실패 시 응답 job 상태 낡음). 변이 3종 전부 재실패. 분석 실패 200 vs accept 502 선례 긴장은 오너 판단으로 올림. | **불합격** |

### 2026-08-31

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`scene_note_slice_1.md`](2026-08-31/scene_note_slice_1.md) | 장면 메모 Slice 1(읽기 API·검색, `c861bc0`~`aafab21`) 독립 검증. v1.8.12 경계 행렬에서 **`/notes` 평면 legacy 503 face 무셀 발견**(변이 W5 — 핸들러 제거에 0셀, 실제 동작은 500) → 조건부. 독자 변이 5종: casefold 상실·**라우터 strip 비대칭(0셀, 보강)**·윈도우 off-by-one·인가 deps 제거(tier 행렬 6셀 — "이미 전수 가드 안" 주장 실증)·503 제거(차단). 구현자 S1(순서 가드 결함) 재적용으로 보고대로 2셀 재실패 확인. 전수 backend 2638/1/3065·frontend 385(단독)·schema +228·tier 72/98 실측 일치. 기록 정합성 3건: 미존재 해시 `6c05e73`(**ae2fc9d 재발**), Session 3 Next steps 낡음, HANDOFF "96 operation" 낡음. | **조건부 합격** |
| [`scene_note_slice_0.md`](2026-08-31/scene_note_slice_0.md) | 장면 메모 Slice 0(저장·파기 수명, `cab1a7d`~`1458894`) 독립 검증. SoT v1.8.11 경계 행렬 전 분기 ↔ 셀 대응 확인(빈 칸 없음), **검증자 독자 변이 5종**(과잉 파기 V1·V5 / 교체→보존 V2 / 타임존 V3 / 유일성 플래그 V4) 전부 물림 — 구현자 10종이 안 덮은 방향 보완. 구현자가 보고한 가드 결함(M1, service 조회가 파기 고아를 가림)을 동일 변이 재적용으로 **사후 실증**(동일 2셀 재실패). reconciler 자동 포함(동적 발견)·`scene_notes` 참조 지점 전수(core_sot 외 0접촉)·신규 33셀 collect-only 실측·전수 **2610/1/3024** 재현. 비차단: work_log의 `ae2fc9d` 미존재 해시 인용, SoT 행 "양 경로"(실제 3경로) 과소 기술, Slice 2 선결과(검사 순서·미리보기 바이트 산정). | **합격** |

### 2026-08-29

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`n3_n4_closure.md`](2026-08-29/n3_n4_closure.md) | 2차 재검증 조건 N3·N4의 폐쇄 보강(`717ed5e`+`fe7bc4e`) 독립 재검증. **N3 폐쇄 실증**: 혼합 versions 3경로 200 셀 추가, 검증자가 2차 재검증과 동일한 V6b mutation(혼합일 때만 방어)을 재적용해 **정확히 신규 셀만 물림** 확인(1 failed — 평면 versions 셀 green, 중간 설계와 전면 방어가 셀 단위로 구분). 셀 주석의 조립 전제("drafts가 없어 create_chapter가 막지 않는다")도 `create_chapter` 가드 코드와 정합. **N4 폐쇄 실증**: 교체 인용의 출처가 SoT v1.5 행 원문(2026-06-28 확정 archive 정책·unarchive 범위 밖)과 정합, 정정 마커·버전 무상승 근거(work_log 세션 2 Decisions)·세션 1 로그 무결성 방침 확인, 결함 문구 잔여는 증거 파일뿐. 전수 **2571/4/3023**·집중 23/271·변동 귀속(+1 passed 신규 셀·+1 subtest 검증 기록 등재분)까지 주장과 정확히 일치. | **합격** |
| [`flat_legacy_escape_path_closure.md`](2026-08-29/flat_legacy_escape_path_closure.md) | 재검증 조건 N1·비차단 H1·N2의 폐쇄 보강(`9dead9e`+`0fb24cd`) 독립 재검증. **N1 폐쇄 실증**: SoT v1.8.10 대피 경로 명시·라우터 주석 정정·셀 3종 계약 고정, mutation M1·M2 재검증 모두 정확히 대상 셀만 물림, 혼합 상태 라이브 재현(versions 200·export 503) 삼자 일치. **subtest 기준선 정밀화 주장 재현**: 기준선(작업 전 `2c77a70`) 전수 2567/4/**3022**·HEAD 2570/4/3022(+3 passed, subtest ±0) — 1차 재검증의 3021은 동일 트리에서 재현 안 되는 측정 변동이었음을 검증자 스스로의 재측으로 확인. **신규 조건 2**: ① SoT가 명시한 "versions는 혼합 상태에서도 200" 분기 무셀(V6b mutation — 혼합만 방어하는 변형이 어떤 셀도 안 물림) ② "project unarchive(v1.5 MVP 범위 밖)" 인용의 출처가 저장소에 0건(실제 근거는 2026-06-28 §115 unarchive 여지 보존). 셀 1개·문구 1줄 수준. | **조건부 합격** |
| [`chapter_scene_hierarchy_b1_b5_closure.md`](2026-08-29/chapter_scene_hierarchy_b1_b5_closure.md) | 1차 검증(불합격) Blocking 5건의 세션 11 보강(`c911f03..aafd337` 7커밋) 독립 재검증. **B1~B5 전부 폐쇄 실증**: 평면 legacy 4경로 라이브 재현으로 500→**503**(서비스+라우터 2층, mutation으로 각층 분리 잠금 확인 — 목록 subtest는 서비스층이 흡수)·TXT/무손실/partial fail-closed 축 mutation 3종 신규 탐침 전부 물림(1차 무셀 V3 재검증 포함)·B5 uncertain 잠금 셀 양방향+mutation 재검증·SoT v1.8.9 본문·운용 수 실측 일치(96 op·활동 25/29)·전수 수치 주장과 정확히 일치(backend 2567/4/3021 test-mongo ON 직접 기동·mongo 85/85·프론트 383/383·build 442.34 kB·schema 0줄 차). 1차 H5(TestClient 대기 주장)도 본 환경에서 재현 안 됨. **신규 조건(N1)**: 순수 평면 legacy 상태의 `GET /export`·versions가 **200**으로 동작하는 것이 SoT 계층 조항("공개 CRUD·Writing accept… 503")에 정의돼 있지 않고 export 라우터 주석("unmigrated legacy data blocks it")과도 어긋남 — 목록은 503인데 내보내기는 되는 비대칭의 계약 결정이 필요(오너 판단: 대피 경로 명시 or 503 정합). | **조건부 합격** |

### 2026-08-28

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`chapter_scene_hierarchy.md`](2026-08-28/chapter_scene_hierarchy.md) | 장→장면 계층화 슬라이스(`65348ab..258c719` 구현 4커밋, SoT v1.8.9) — 정본 모델·Chapter API·순서 불변식·cascade purge 가드·UI 제목 확인·404 단계 구분·schema 파생물은 계약 대로임을 코드 직독·재실행·V1 mutation(구현자 주장 셀 재물림)으로 확인. **라이브 재현으로 Blocking 5**: ① migration 전 평면 상태(현 운영 데이터 형상)에서 `GET /drafts`·draft payload 경로·writing accept가 **500** — 엔드포인트가 선언한 503 "migration" 얼굴 위반(assert `drafts.py:70`·`AcceptedSavePayload.chapter_id` 필수 str). ② 계약 요구 셀 부재 — TXT 계층 export(V3 무셀 실증)·migration 무손실 축(version/snapshot/본문·archived·partial fail-closed, 브리프가 "양방향 회귀로 잠근다" 명시). ③ **`test_writing_accept.py` 6셀 red**(e735caa 회귀 — 이전 커밋 53 passed 실증)·프론트 전수 4셀 red(mock 미갱신): 수정한 파일을 실행하지 않은 채 "집중 60 passed"(묶음이 writing_accept 제외 선택 조합)로 마감. ④ SoT 본문 자기모순 — "draft/chapter/scene 계층은 미확정이다" 잔존·운용 수 91(실측 96)·"(구현 진행)". ⑤ "503 uncertain 잠금"(v1.8.8 정의=재시도 금지·오너 ⓐ) 대비 장 purge UI "다시 시도하세요"+재시도 버튼 활성 — **오너 판단**. Hardening: 장 unarchive 부재(D8=A 근거 도달 불가)·mongo chapter 경로 무셀·`report_budget_measure` legacy 생성. | **불합격** |
| [`deletion_slice.md`](2026-08-28/deletion_slice.md) | 삭제 기능 슬라이스(`070f0b9..adf93d0` 8커밋) — 원고 purge·소유자 프로젝트 purge(`execute_project_purge` 공유)·관리자 아카이브·프론트 4표면. 파괴 그래프·권한·409 조건·D3 리터럴·인메모리↔mongo 6축 대칭·운용 스윝(88→91, 활동 20→21) 코드 직독으로 정합 확인. 전수 전부 재현: 백엔드(test-mongo ON) **2544/4/2894**·mongo 단독 **79**·프론트 **386+tsc clean+build OK**. **뮤테이션 9종 — 6종 재실패(구현자 클레임 가드 3종 포함), 3종 무셀 통과가 곧 발견**: B3/B5 receipts 소거 제거(인메모리·mongo 양쪽)에 어떤 셀도 안 물고, B4 잡 가드를 종료 상태까지 확장해도 안 물음 — "6컬렉션"·D1의 should-NOT-fire 면이 잠기지 않았다. **Blocking 6**: SoT 미등재(신규 API 3종·운용 수, v1.8.0 선례)·앞의 무셀 3종·Crud 에러 선언 잠금 미등재(20핀 그대로, 관리자 트랙은 17로 등록한 비대칭)·소유자 purge 면 503 재시도 제공(관리자 면은 uncertain 잠금 — D4=A·HANDOFF:223와 충돌, archive/purge 단계 구분이 필요해 **오너 결정**)·기록 의무(CHANGELOG·HANDOFF 미갱신, mutation 표 미준수). | **조건부 합격** |

### 2026-08-27

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`d7_closure_d5_2_raw_text_limit.md`](2026-08-27/d7_closure_d5_2_raw_text_limit.md) | 08-27 세션 1~3 부채 처리 — D7 lock-list 등재(`04e0b7b`)·D5 실측 정정(`40c4524`)·D5-2 본문 4000자 전 경로(`3a8fa28`·`5085e42`·`7dae1b3`, SoT v1.8.7). 경계 매트릭스 전 셀 대조(경계/초과/env 양방향/무효 env 기동/프로바이더 0회/NotFound 순서/짧은 본문 과잉방지/no-maxLength). **"전 경로"를 쓰기 경로 전수 스윙으로 실증** — save_draft 호출 전수 `drafts.py:319`+`accept.py:159`·start_next_unit `accept.py:135` 유일, 세 경로 모두 상한 안쪽. **검증자 뮤테이션 6종(V1~V6) 전부 표적 셀 재실패** — V1 lock-list "503" 제거는 작업 AI 보고와 동일 SUBFAILED 좌표, V3(accept 시행 제거)는 7dae1b3 수선 셀(메시지 단정 포함)이 상한 이유로 물리는 것까지 재현. 수치 전부 재현: `test_application_api` **124/498** · 백엔드 전수(test-mongo ON) **2526/4/2841** · 프론트 **373+tsc clean**. 실DB mongosh 직접 재조사 — 초과 **1건=24,070자**·버전 멱등키 `report-budget-measure-v1`(씨드 확정)·영수증 0건·브리프 초과 0/2. 검색 조각 정정(40c4524)의 코드 정합도 확인(`DEFAULT_RECENT_SCENE_BLOCK_LIMIT=5`·`DEFAULT_CONTEXT_BUDGET_TOKENS=8192`·표식 없으면 유닛 전체). **후속 구현 `873ff84`**: Blocking 1 폐쇄(CHANGELOG 세션 2·3+세션 1 정정), H1 replay 순서 셀·H3 strip 시점 문서·H4 설명창 4필드 카운터/저장 차단을 보강했다. H2(서버 env↔프론트 4000 런타임 미러)는 새 public 설정 계약이 필요해 비차단 유지. 구현 세션 자기 검증(frontend **377+tsc**, accept **5/5**) 단계이므로 독립 재검 전까지 발행 판정을 유지한다. | **조건부 합격** |

### 2026-08-24

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`phase_8_5_quota_console.md`](2026-08-24/phase_8_5_quota_console.md) | 8.5 프론트 — 관리자 콘솔 "회원 사용량 한도" 화면+"서비스로 이동" 링크(`09946e2`·`36d5778`·`713b68d`·`2cea291`, SoT v1.8.4). 계약 4종의 **백엔드 전제를 정본에서 역방향 확인**(쌍 대체 `admin.py:241-248`·감사 후적용 `249-254`·StrictInt 422 `models.py:186-196`·자기 정지 400 `286-289`) — 가드 방향 전부 정당, detail이 payload를 상속해 행 교체 전제도 유효. schema.d.ts 재생성 **바이트 멱등**(손편집 없음, diff는 quota 5경로·6스키마뿐 — 이물 0건). 전수 **338/29**·build **705/425.90/14.76/387.43/31.36**·문서 가드 **13/265** 전부 재현. **검증자 뮤테이션 5종(작업자 2종과 다른 4종+M1 재검증)이 정확히 예상 셀 1개씩만 재실패** — 과잉 방향(소수 클라이언트 차단=계약 ③ 위반) 포함, 7셀이 각자 다른 조항을 잠금. 링크 "되돌아오지 않는다" 주장은 `AuthGate.tsx:112-128` 코드 실증(로그인 콜백 1회성, `/admin` 네비게이션 전수 grep 유일). 루트 실행 함정(jsdom 미부착 → 전 셀 1ms 실패)을 작업자 기록과 동일하게 밟아 재현. Hardening 2(P6 힌트 문구 미고정·링크 위치 미고정). | **합격** |

### 2026-08-23

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`llm_key_fallback_slice.md`](2026-08-23/llm_key_fallback_slice.md) | 키 폴백 슬라이스 8단계(`d8ba6e7…7bf07c9`, 브리프 `external-api-fallback-decisions.md`) + HANDOFF 지정 반증 축의 스모크 슬라이스 축(`21b1f1c`·`a330eff`). 브리프 §0·§1 경계 행렬 대조 — 리터럴 전항 일치(600/60·a1→b1→c1→a2→b2→c2·라운드로빈·502 표면·대시/콜론 표기·무설정 무변·key_index 로그). **검증자 자체 뮤테이션 12종 — 지정 축 4개 전부 잠금 확인**(M3 retryable=False 회전·M4a 502 정방향+M4b 분기는 기본 502가 흡수하는 문서용·M5 미종결 빈 답·M2 쿨다운 장>단 관계). **Blocking B1: 브리프 §1 "timeout/5xx는 쿨다운 없이" 조항과 동기 축(임베딩·리랭커) 구현 모순** — 동기 축은 네트워크·408·5xx에도 60s 쿨다운을 걸고 docstring이 그것을 "게이트웨이 형제와 같은 정책"으로 서술했으나 게이트웨이는 그렇지 않다. M9a(게이트웨이에 5xx 쿨다운 추가)는 3셀에 걸려 게이트웨이 축은 잠겨 있으나, **M9c(동기 축 5xx 쿨다운만 고립 제거)는 0셀** — 이탈 행동이 무가드임을 입증. Hardening 2(H1 리터럴 무가드·H2 파싱 규칙 미기재). 포커스 171/204, 전수 2489/4/2718 재현. **[B1·H1·H2 전부 닫힘 2026-08-23 — 오너 ⓑ 코드 정렬 `d71294a`·리터럴 핀+브리프 기재 `b2be4ad`; 원 검증자 사후 재검(뮤테이션 R1~R4 전부 재실패·전수 2493/4/2720 재현)으로 승격 확정 — 기록 "사후 재검" 절]** | **합격** |
| [`extractor_stabilization.md`](2026-08-23/extractor_stabilization.md) | extractor 안정화(`bb1ac41`+`6567286` — 검증 단위는 둘의 합, SoT v1.7.99). ★ 핀 sha 재계산 일치(v4 `b946a7…` 무변·v5 `bc2a0b…`) + v4↔v5 본문 diff가 명시된 2줄뿐임을 확인. 공유 파서 6호출부 grep 확인(gate·report·compare·extractor·planner·retrieval). 뮤테이션 5종 전부 표적 셀 재실패(X1 회복 무력화·X2 온전성 검사 삭제→over-strict 2셀·X3 기본 8192→2048 원복·X4 v5 펜스 금지 문장 삭제→immutable 핀 SUBFAILED·**X5 6567286의 1행 거꾸로 적용 → bb1ac41 단독 red 2셀 경위 재현**). 전수 **2489/4/2718 (229.8s)** — 기준선 주장과 일치, skip 4 구성(Chroma 1+ES 3)도 실측. 라이브 관통(알파 phase2a 3회 연속 성공)은 구현자 기록 수용(재실측 범위 밖 명시). | **합격** |
| [`phase_8_5_quota_admin.md`](2026-08-23/phase_8_5_quota_admin.md) | Phase 8.5(`d20cb67`·`5d89484`·`0a75c5e`·`44ffb47`, 브리프 `08-5-usage-admin-cms-decisions.md` D1ⓒ·D2ⓐ·D3ⓑ) + docs 비공개(`14e9904`) + SoT v1.8.0 등재(`e0b9995`·D-g 보충 확인). 브리프 §5 경계 행렬 대조 — 나머지 전 항 일치(tier **87·ADMIN 16 실측**·P6 재사용·status 유지·set_status 즉시·H2 분리·감사 fail-closed·읽기 미기록·`/me/quota` 동일 산식·정책 없는 회원 포함). **검증자 뮤테이션 8종(V1~V6·V9·W1) 전부 표적 셀 재실패. ★ Blocking B1: 브리프 §5 "비정수 → 400" 미시행** — 실측 탐침에서 `"77"`·`true`는 pydantic lax 강제 변환으로 **적용**(200, `true`→1 축소 예약 생성), `2.5`는 422, 400은 부재 + 이 축 셀 부재 + **브리프↔SoT v1.8.2↔work_log 삼자 불일치**(비정수를 결정 없이 삭제). Hardening 2(자기 정지 가드 부재·감사 실패 시 변경 잔존). 전수 2504/4/**2806**(기록 등재분 subtest +1 — 첫 측정은 기록 파일을 인덱스 갱신 전에 둔 검증자 순서 실수로 8실패 오염, 정합 후 재측 정리). | **조건부 합격** |

### 2026-08-22

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`signup_approval_slice.md`](2026-08-22/signup_approval_slice.md) | 자기 가입(승인제) 슬라이스 + 보안 점검(`bee4867`…`b6cee5d` 9커밋, SoT v1.7.97) — 브리프 P-1~P-7 경계 행렬 전 셀 대조. 정량 전부 재현(백엔드 **2480/0/skip4** — 단 환경 조건 기록: test-mongo 없으면 2365/119skip · 프론트 **331** · build **425.35kB** 소수점 일치 · tier 82·ADMIN 11). ★ **검증자 자체 뮤테이션 10종(작업자 8종과 독립) — 9종 표적 셀 물림, M9(stale 리셋 제거)만 미물림을 규명**: 흡수층은 설계가 아니라 **제2 결함**(잠금 중 `register_failure`가 잠금 레코드를 덮어 지운다 — 순수 프로브로 실증). 현재 단일 워커 배포에선 도달 불가·P-6이 지향하는 다중 인스턴스에서 현실화 → H-1. ★ 라이브 관통(nginx 5520): 가입 201→대기 403→active→로그인 200(Secure 쿠키 실측)→거절 403→재요청 201(같은 `_id`)→5회 실패 후 정답 401·Mongo 잠금 행 `{failures:0,+5분}`. 관리자 자격증명 없어 승인 API 라이브 재현은 Mongo flip 으로 대체(스위트 셀로 계약 잠금 확인). ★ **`/docs`·`/openapi.json` 이 공개 nginx 포트(5520)에서도 200** — 작업자 발견 ③보다 노출 확대. **Blocking B1**: `b6cee5d` 가 SoT 헤더+변경이력만 고쳐 **본문이 자기모순** — §상태코드 403 행(412)"생산자는 정확히 둘…이 둘 외의 403 선언은 거짓"·H3 3층(401)"detail 매칭 분기 금지"·C-6 절(326) 재인용이 v1.7.97 셋 생산자·등재 예외와 충돌(v1.7.56 선례는 본문을 갱신했다). 비차단 6(H-1 잠금 소거·H-2 login_failures 증가·H-3 노출 범위·H-4 SoT 셀 수 산수 47→49·8→5·H-5 브리프 operation 추정·H-6 서식). 검증 잔여 `verif_0822` 시드 정리 목록 등재. | **조건부 합격** |

### 2026-08-21

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`product_name_and_hardening.md`](2026-08-21/product_name_and_hardening.md) | 제품명 스윕(`29299e5` 세 `title=`+백엔드 스윕 가드) + 비차단 3건 보강(`cfcb182`) 합동 재검. ★ **은퇴명 잔존 전수 조사에서 README H1·LICENSE 제목줄이 모든 스윕 밖에 있는 살아있는 잔존임을 발견** → 오너 결정 요청 H-P1(이 슬라이스 계약 밖 미결 표면 — 조건 아님). 29299e5: `info.title` 실측·`schema.d.ts` 양쪽 0건·스캔 범위(compose 주입 M6 로 발화 확인)·M1~M5 같은 diff 전부 일치. 자체 축 — 변형 표기 M7 침묵(잔존 0실측·의도 문언화)·서비스 구분자 M8 침묵(D-2026-08-21-a 정확 글자 미단정 → H-P2). cfcb182: 프로덕션 0줄(stat)·개명 셀 두 서브테스트(갈리는 입력 `[2,0,1]`)·로그 셀 원인 단정 — N1~N4·R6b(페어링 1→2) 전부 일치, N3 에서 기존 비순열 5서브테스트 green 실증. 재검 기록 폐쇄 주석도 정확(정정된 "미검증 0" 원 오류는 검증자 자신). 전수 `2358/1/2592` 일치. **[Hardening 3건 전부 닫힘 2026-08-21]** H-P1 = **오너 결정 D-2026-08-21-d 로 교체**(`c1fed21` — README H1 `# 에-라잇` · LICENSE 제목줄, **스윕을 정문 두 파일까지 확장** + 존재 트립와이어) · H-P2·M7 = `924b0ab`(정확 글자 표 + 표 자체를 검사하는 둘째 셀 · 변형 표기 정규식, 식별자 형태는 over-strict P4 로 침묵 확인). 폐쇄 뮤테이션 P1~P7 전부 발화. | **합격** |
| [`reranker_c1_h1_h2_closure.md`](2026-08-21/reranker_c1_h1_h2_closure.md) | 폐쇄 커밋 `92b9b24`(조건 C1 + H1·H2) 독립 재검 — §조건 폐쇄가 **구현 세션 자작**이라 전항 재유도. ★ C1: 구조(투영·호출·순열·재조립이 한 `try`·`except Exception`+`noqa: BLE001`)·`FailOpenScopeTest` 4셀 감사·런타임(repro Part 1 "새어나감"→"정상 반환" 뒤집힘) 전층 일치 · C1-M1~M3 같은 diff 재유도 전부 일치(M1 5failed — 투영 3서브테스트+비예상 셀+로그 셀 · M2 1 · M3 "Unexpected logs"). H1: RV-B1/B2 뒤집힘 재실증·임베딩 `_constructor_names` 처방과 동형(잔여 차이는 이름 재결합 계열로 문언 바깥)·할당 별칭 침묵 확인(**문언 과대 없음**). H2: 원문 정정 확인, 단 셀 이름 `test_ties_keep_the_request_order` 에 정정된 문언 잔여(비차단 H2-a)·동률이 요청 순서가 아닌 응답 셀 부재(H2-b). **[Hardening 3건 전부 닫힘 2026-08-21 `cfcb182` — 오너 취사 채택, 프로덕션 0줄]** 셀 개명 + 갈리는 입력 subtest + 비순열 경로 로그 셀. **지적이 실재를 가리켰다**: 새 뮤테이션 N1(동률을 오름차순 인덱스로 tie-break)은 종전 셀이 원리적으로 못 보고, N3(순열 검사를 `return items` 로)에서 기존 비순열 5 subtest 는 전부 green 이고 새 로그 셀만 문다. R6b 페어링 1 → 2. 인계 "볼 만한 축 셋" 판정 — ① 프로그래밍 오류 삼킴: 투영 고장은 `ReorderingTest`(순서 실제 변경 단정)가 잡고 삼키는 길의 초록은 `FailOpenScopeTest` 계약 자체 ② `assertNoLogs` 로거 한 곳만(오탐 없음) ③ **R3b 낡은 리터럴 갱신 이행**(`33461cc`) — 새 리터럴로 11failed 물림 확인. 전수 `2357/1/2589` 일치. | **합격** |

### 2026-08-20

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`reranker_slice.md`](2026-08-20/reranker_slice.md) | 리랭커 슬라이스(`7a88ac1` seam+어댑터+데코레이터 · `f14917b` 하네스+external) + **임베딩 조건 B1 폐쇄(`a9bca6d`) 독립 재검**. ★ 구현자 자문 축 실증 — **fail-open 은 "모든 실패"를 안 덮는다**: `text_of`(투영) 예외가 `except RerankProviderError` 밖으로 새어나가 **검색 경로가 죽는다**(런타임 직접 실증) → **조건 C1**(폐쇄: 단계 전체 fail-open 권장 / 문언 스코프). R1~R7 같은 diff 전부 재현(R6b 재유도서 검증자도 들여쓰기 실수 — `count==1` 단정이 잡음). 산출물 4건 일치(no-op 기본 None·데코레이터 도메인 0줄·하네스 무정답·경계셀 `.jsonl` 투입 실패 실증) · D2=A "OpenAI 호환" 글자를 Cohere generic `POST /v1/rerank` 로 바로잡은 계약 수정이 브리프에 기록됨 · env 3종 대시+`:?` 아님 · 표기 3분할. **B1 폐쇄는 검증자 재현 스크립트 재실행(V1 뒤집힘)으로 승격 확정** — 폐쇄 세션이 못 고른 인덱스 행·Verdict 줄을 같이 정리. 비차단: 유일-생성자 셀의 속성·별칭 우회(B1 학습 미적용) · 동률 문언 정밀도. 전수 `2350/1/2582` 일치. **[→ C1·H1·H2 폐쇄 `92b9b24` · 독립 재검으로 승격 — [`reranker_c1_h1_h2_closure.md`](2026-08-21/reranker_c1_h1_h2_closure.md)]** | **합격** |
| [`embedding_adapter_slice.md`](2026-08-20/embedding_adapter_slice.md) | 임베딩 어댑터 슬라이스(`0bb73ee` 헬퍼+가드 · `c3f75c0` OpenAIEmbeddingProvider · `e49d458` README·external) — 지목 축 넷 판정: **① 별칭 import 우회 실존**(`import … as REP` 후 호출 → 가드 16 passed 침묵; 모듈 속성·원이름은 잡음 — 원인은 피호출자를 원이름 집합과만 비교하는 `tests/test_embedding_assembly.py:63`) · ② 헬퍼 env→provider 만(본문 전수 — required/base_url 는 호출자 정책 파라미터) · ③ E5 재유도로 접미 `/v1` 2서브테스트만 실패·`/v1/proxy` 통과 · ④ 기본값 native 무영향을 코드(6자리 기본값 동일)·셀·compose 렌더(native/빈둘, rc=0) 세 층에서 확인. E1~E6 같은 diff 전부 재현(페어링 노트: E1 은 import 잔류 여부로 1~2셀) · 산출물 4건·`--help` rc=0·전수 `2319/1/2544`(셀·subtest +22 예고 일치). → **조건 B1 = 별칭 우회 폐쇄(가드 asname 맵 강화 권장 / 또는 문언 축소)**. 비차단: 새 env 표기-셀 부재 · 스캔 범위 경로 하드코딩. **[→ B1·H1·H2 폐쇄 `a9bca6d` · 독립 재검으로 승격 — 판정 합격, [`reranker_slice.md`](2026-08-20/reranker_slice.md) Findings 7]** | **합격** |
| [`deploy_llama_required_b1_b2.md`](2026-08-20/deploy_llama_required_b1_b2.md) | cd1d82d(배포 override `LLAMA_BASE_URL` 필수화 = B2 시행 · over-strict 셀 = B1 폐쇄) — 오너 지목 축 셋 전부 실증. ① `:?` 국소성: 선언 3곳 전수(`:?` 는 external:117 뿐 · `docker-compose.test.yml` 미선언)·병합이 변수 단위임을 렌더로 확인(base env 4키·`extra_hosts` 생존)·M4(알파에 `:?` 유출)는 기존 InStack 셀이 물음. ② 뮤테이션 6종 페어링 — M1 under-strict 1셀 · M2/M3(base 대시화·`:?` 통일) over-strict 1셀 · M4b llama 대시화 2셀 · **M2′ 구(舊) 테스트 파일(`cd1d82d~1`) × base 대시화 = 0셀** 로 B1 "종전 0셀 → 이제 1셀" 을 양단 실증. ③ 오너 규칙 ①②③·기동 표 ↔ `docker compose config` 10종 정확 일치(rc=1 한국어 사유 전문 · 호스트 llama 명시 통과 · **빈 값도 거부** · 세 방식 폴백 주소 · `depends_on` 머지). **★ H1(비차단) — 구현자 실측 표의 "주소 없음 rc=1" 은 `.env` 중립화 없이 재현 불가**(이 머신 `.env` 가 LLAMA 를 제공 — 무통제면 LLAMA 아닌 다른 필수부터 rc=1) — repro 스크립트가 표준 절차(`--env-file /dev/null`)로 고정. H2 = 네 번째 compose 파일 비추적(기존 열린 항목·트리거 유지). | **합격** |
| [`mypy_guard_closure.md`](2026-08-20/mypy_guard_closure.md) | 조건 폐쇄(`5182cad` 코드 + `0741a45`·`d3cc557` 기록) 재검 — **재검 10종(M4~M13) 전부 의도대로**: 폐쇄 벡터 M8~M11 은 물고, 원 잠금 M4~M7 은 무뎌지지 않았으며(**M5·M6 은 이제 셀 둘씩** — 방어 심화), M12(에러 코드 제거=강화)는 **설정 셀이 통과**해 확장 트리거가 안 막힘을 재확인, M13(평범한 주석) 오탐 0. **★ 오너 지목 축 "허용 키 집합 과소" 를 실증** — `warn_unused_ignores = True`(가드 강화 키, 저장소 초록 셀 통과=불령)가 설정 셀에 걸리며 메시지 *"이 키들 밖은 전부 조용해지는 길이다"* 가 **거짓 보편문**임을 확인(`python_version`·`cache_dir`·`plugins` 도 무해). `files` 확대도 등가 단정이 거부(메시지는 "줄이지 않는다"). 화이트리스트 설계 자체는 정당(다섯째 벡터 원천 차단)·정본 문언은 정확 — **결함은 셀 안 세 문언으로 한정** → H4(트립와이어 정직 문언+키 추가 절차) · H5(범위 확대 서술). 전수 `2297/1/2520`(HANDOFF 예고값 일치). **첫 검증 기록을 조건부→합격으로 승격.** | **합격** |
| [`mypy_guard_slice.md`](2026-08-20/mypy_guard_slice.md) | 축 ② mypy 가드(`3610fc3` 확정 · `0b1c6f3` 구현 · `f09097e` 기록) — 착수 조건 1~5 전부 셀 매핑 확인, **구현자 뮤테이션 7종(M1~M7)을 같은 diff 로 전부 재현**(페어링 포함 — M4 비대칭 · M5 "가드만 사라지는 초록" · M7 "mypy 자체는 통과"), 정정 ①(88→111)은 **구현 직전 커밋 스냅샷에서 111/40/193 으로 정확 재현**, 정정 ②·전수 `2296/1/2519`(예열 후)·미설치 시 3셀 실패+설치법 메시지(venv 실증)까지 전부 일치. **★ 검증자 자체 공격 4종(M8~M11)이 새 구멍** — 무공백 `#type:ignore` · `# mypy: ignore-errors` 프라그마 · ini 퍼모듈 `ignore_errors` · `files` 범위 축소는 **넷 전부 "7셀 초록 + 표적 결함 생존"** 을 만들고, 억제 잠금 셀은 문자열 `"type: ignore"` 매칭이라 앞의 셋을 못 본다(산출물 문언 "억제 주석 0건이며 그것을 잠그는 셀" 이 실제 잠금 범위보다 넓다). 구현자가 남긴 "볼 만한 축" 셋(accept 호출자 계약 · lock RuntimeError 정책 · kpi 호출자 전수)은 위반 없음으로 판정. **→ 조건 폐쇄 재검(같은 날, [`mypy_guard_closure.md`](2026-08-20/mypy_guard_closure.md))으로 승격.** | **합격** |

### 2026-08-15

| 기록 | 무엇을 봤나 | 판정 |
|---|---|---|
| [`deploy_externalization_axes_1_2.md`](2026-08-15/deploy_externalization_axes_1_2.md) | 배포 외부화 축 ①(env 배선 `b6b1269`·`3ff94a3`) · ②(외부 전용 override `8e57369`) — **프로덕션 코드 0줄**, compose + 가드만. 축 ① 짝 규칙(`if not …` → dash / `os.environ.get(name, DEFAULT)` → 콜론)을 **코드 5자리 직접 읽기**로 확인하고 **콜론 42곳 전수 대조 → 추가 위반 0건**. 축 ② `CHROMA_PORT` 이름 충돌 판단 타당하며 셀이 **예외의 전제**(host publish 가 같은 이름을 쓴다)까지 잠근 드문 설계. 축 ③ 실측 전부 재현 — rc=1 + 한국어 사유 · 서비스 **10 → 7** · base diff 무변 · `:?` 셀 **3 SUBFAILED**(`grep FAILED` 사각지대 실제 재현). **★ M-A ↔ M-B 대비가 핵심** — 같은 변수·같은 서비스·**문자 그대로 같은 diff** 가 `llama.yml` 에서는 2셀을 물고 base 에서는 **0셀**(compose 가드 27 passed 전원 green). **Blocking 2**: B1 base [`docker-compose.yml:202`](../../docker-compose.yml#L202) 의 `LLAMA_BASE_URL` 표기를 잠그는 셀 0건(work_log 의 *"두 방향 다 셀로 잠갔다"* 는 override 한 자리에서만 참이고, **안 잠긴 쪽이 실제 기본 기동 경로**다) · B2 [`.env.example`](../../.env.example) 의 *"값이 없으면 기동을 거부한다"* 가 나열한 주소 다섯 중 `LLAMA_BASE_URL` 에는 거짓이며(`EXTERNAL_CHROMA_PORT` 는 같은 목록에서 예외를 명시했다) 미설정 시 파일 자신이 배격한 실패 형태가 된다 — 해소 방향 둘 다 타당해 **결정 사안**. 비차단: `_env_bool` 의 `""`→`True` · 새 override 파일 사각지대(M11 한계 재확인). **★ §추기(같은 날 감사 반영)** — 초판 대상 "7커밋"의 앵커가 **세션 경계**였음이 드러나(진짜 앵커는 마지막 검증 기록 커밋 `c08b0c2`) **`6352121`·`3b71eac` 를 추기 검증해 미검증을 실제로 0 으로 만들었다**(둘 다 Blocking 0). `6352121` 은 오늘 실측에서 **역산으로 검산**(2284−11=2273 · 2515−49=2466), `3b71eac` 은 **코드로 확인** — `/props`·`/tokenize`·`/apply-template` 셋 다 예외를 삼켜 `None` 이고 [`client.py:262`](../../services/llm_gateway/app/client.py#L262) 주석이 **`# 셀 수 없으면 판정하지 않는다(통과)`**, 대체 추정은 [`:237-238`](../../services/llm_gateway/app/client.py#L237) 이 **과소평가 방향**이라 명시 = **축 ③ 의 위험은 "안 뜨는 것"이 아니라 "조용히 통과하는 것"**. 서술 정정 넷: B2 옵션 (a)의 *"호스트 llama 선택지 배제"* 는 **과대**(`:?` 후에도 명시하면 사용 가능 — 사라지는 것은 암묵적 폴백뿐, **오너 결정 전 필독**) · "compose 읽는 가드 전부"는 **base 를 읽는 3파일** · "subtest +49 전부 가드"는 **+48/+1** · "260커밋"은 **215커밋**(앵커 명시). | **조건부 합격** |
| [`alpha_day_slice_audit.md`](2026-08-15/alpha_day_slice_audit.md) | 같은 날 작업 세션 산출물(재빌드 · 미검증 검증 `33dbdd2` · 새 기준선 기록 `cfc7374`)의 독립 재감사. **B1/B2 전 축 재현** — M-A′(base:202 dash 화) 0셀 ↔ M-B′(같은 diff 를 `llama.yml:76` 에) 2셀 을 다른 손으로 다시 세웠고 표기 계약의 스코프가 파일이 아니라 변수임을 정본 3곳에서 확인. 축 ③(rc=1·10→7·base 무변) · 재빌드 실물(app 태그 오늘 생성·옛 태그 3종 잔존·ES 태그 07-12 무변) · "프로덕션 0줄"(services/frontend diff 공백) · AUTH_TTL 계약(2026-07-27 보안 근거) 전부 확인. **Blocking F1**: *"마지막 검증 기록 뒤 7커밋"* 의 앵커는 검증 커버리지가 아니라 **08-14 세션 시작 경계** — 실제 미검증 9커밋 중 7커밋만 검증했고 `6352121`·`3b71eac`(08-13 검증 종료 뒤 커밋, docs-only)이 잔여라 **"오늘 기준 미검증 0"은 거짓**. 비차단: B2 옵션 (a) *"선택지 배제"* 서술 과대(명시 세팅으로 호스트 llama 여전히 가능) · "가드 전부"는 4파일 중 3파일 · "260커밋" 실측 ≈255. | **조건부 합격** |

### 2026-08-13

| [`debt_buttons_typescale_m5.md`](2026-08-13/debt_buttons_typescale_m5.md) | 부채 ①② 폐쇄(`db9f9c0` 기본 버튼 겉모습 다섯 벌→한 자리 · `f022088` typeScale 넷째 셀 · `08aed1b` 기록, Phase 10) — 기준선 전부 HEAD 에서 재측정(frontend **323/27**(423s) · build **704·진입 421.78·관측 lazy 387.43·AdminConsole 8.50 무변** · **CSS 31.42→30.79(-0.63)** 직접 빌드 · `tsc` OK). **★ 원문 전제 정정이 사실** — `b97307d` HANDOFF 가 *"관측된 피해 0건 · 시각 무변(transition 포함)"* 이라 **스스로 모순** 적었는데, 다섯 블록을 직접 재어 `.editor-actions button` 만 transition 없음·hover lift **2:3** 갈림을 잡아 "피해 0건이 아니라 아무도 안 본 것" 으로 정정(오너 **D-10.5-b** "다섯 곳 전부 뜨게"). **★ 캐스케이드 건전** — 7 선택자를 건드리는 규칙 9자리 전수 추출, 겉모집 속성은 통일 자리(328·345·357)에만, padding 은 자리별(446·1140·1290·1513·1810), `.row-actions button.ghost`(0,2,1)>(0,1,1) 로 정체성 유지 · CSS 파일 1개·`!important` 는 reduced-motion 전역(변경 전부터)만. **★ 뮤테이션 6종 전부 단독 물림**(구현자 N1-N4·M-a/b 와 독립): buttonAppearance M1→cell1·M2→cell2·M3→cell3·M4→cell4(over-strict padding) · typeScale **M5(MIGRATED 행 삭제)→cell4 가 종전 M5 한계를 닫는 핵심 증명**·M6(미등재 규칙)→cell4. **★ CSS-pre 31.42 를 cp-swap 빌드로 디스크에서 직접 측정**(믿지 않고 잼). 패턴 스윕: `background:…primary` 3곳 중 2곳(배지·날짜 점)은 cursor 없어 identity 의도 제외 — 놓친 사본 0. **Blocking 0**. 비차단: H1 `:disabled` 불투명도 네 값 갈림(363·579·1205·1352, cursor 는 동일) — ★최초엔 *cursor/input-link* 라 적었으나 틀려 정정(`ffa5848` 재측정 + 검증자 독립 재확인, 부채④). | **합격** |
| [`chart_h1_h2_hardening.md`](2026-08-13/chart_h1_h2_hardening.md) | 차트 검증(`e124879`) 비차단 H1·H2 보강(`444ab1b`·`f724fce`) — H1(셀 "still holds the exact palette")은 ΔE 재구현 대신 **출처 연결**(계열색↔주석 팔레트·검산 표면↔`--surface-raised`·그 토큰↔`.chart-frame` 배경)을 잠그고, H2(`tooltipStyle(color)` 적용 + 셀 "dresses every overlay" 전수)는 recharts 기본 스타일 회귀를 막는다. **★ 뮤테이션 H1-a(계열색 변경)·H1-c(프레임 배경)→H1 셀 단독 FAIL**(연결 ①·③ 양쪽), **H2-a(Tooltip contentStyle 제거)→H2 단독 FAIL**. chartColors 3→5 cells · 회귀 323/27 무변 · 관측 lazy 387.03→387.43(HEAD 빌드 재확인). **Blocking 0**. 비차단: H1 잔여(CVD 통과 자체는 여전히 자동 가드 아님 — palette 변경 시 재실행 리뷰 필수). | **합격** |
| [`login_button_false_finding_correction.md`](2026-08-13/login_button_false_finding_correction.md) | 10.4 검증(`33e8783`) 뒤 `2c6eb9e` — "정문 버튼이 브라우저 기본값(회색)"이 **하네스(`10_layout_probe.html`) 마크업이 `auth-submit` 클래스를 빠뜨린 가짜 입력**이었음을 정정, 거짓 발견 위에 쓴 `.login-form button` 규칙(base·hover·disabled)을 전부 되돌림. **★ 제거 깨끗함**(잔존·참조 0건) · **정문 버튼은 `AuthGate.tsx` 의 `className="auth-submit"`→`.auth-submit`(항상 `--action-primary`=rgb(0,110,190))로 여전히 스타일** — "회색이었다"는 입력 오류. 특이도 (0,1,1)>(0,1,0) 이 조용한 restyle 피해를 설명. **★ 구멍 구조적 폐쇄**: 거짓 규칙 재도입 시 오늘 `buttonAppearance` 가 cell 1·2 로 잡음(2c6eb9e 가 손으로 닫은 패턴을 가드가 대체). CSS 31.76→31.42(-0.34, f022088 빌드로 post 재확인). **Blocking 0**. | **합격** |

### 2026-08-12

| [`slice_10_4_layout.md`](2026-08-12/slice_10_4_layout.md) | Slice 10.4 페이지 배치 통일(`4db744c`·`e749873`·`822bf10`, Phase 10 §10.4) — 기준선 재현(frontend **318/26** · 백엔드 prod **0줄** · 번들 **CSS 31.76 · 진입 421.78 무변** 직접 빌드). **★ "실측으로 시작" = 작업자가 커밋한 headless-chromium 하네스를 내가 직접 돌려 픽셀 수치 PRE·POST 양쪽 열을 한 픽셀 안 틀림 없이 재현** — POST workspace 244·39·38%·1225 / admin 138·39·25%·1225 / editor 247·39·38%·1225 · PRE workspace 380·83·55%·1033 / admin 274·83·42%·1193 / editor 240·31·37%·1225(header 1257). 세 규칙 코드로 확인: ① 폭 `min(100%,68rem)` 한 곳(`.workspace-page,.admin-page`) == `main` max-width 68rem ② 블록 자기제한(`.page-heading` 42rem·p 34rem, 컨테이너로 좁히지 않음) ③ 제목 한 계단 + 로그인 `--type-display`=`round(1.125**9,3)`=2.887 **램프 안** 예외. 렌더로 찾은 둘 재현: `.login-form button` 규칙이 부모엔 **0줄**(회색 기본값) · `.overview-page { width:62rem }` override 가 부모엔 잔존(가드가 잡은 누락). **★ 뮤테이션 LM1·LM2·LM3 단독 물림**(스크립트 커밋) — 가드가 값이 아니라 **"평을 정하는 자리가 하나"** 임을 증명. **★ 가드 뿌리 분류 건전**(작업자가 두 번 틀린 자리): `access-log-page`는 `<ul>`(안쪽 블록)로 올바르게 제외 · **모든 라우트가 workspace-page/admin-page/auth-shell 안** (가드 밖 폭 0건). **Blocking 0**. 비차단: H1 기본 버튼 규칙 4곳 흩어짐(추적 부채) · T1 68rem 확장의 목록 행 간격(육안 확인). | **합격** |
| [`slice_10_3_observation_chart.md`](2026-08-12/slice_10_3_observation_chart.md) | Slice 10.3 관측 차트(`0aa787f`·`b7c6453`·`b60e90d`, Phase 10 §Follow-up L450–462) — 기준선 재현(frontend **313/25** · 백엔드 prod **0줄** · provenance **5/90** · 번들 **CSS 31.70 · 관측 lazy 387.03 · 진입 421.78 무변** 직접 빌드). **★ 슬라이스 핵심 = "재보고 뒤 예상과 달라진 결론"인 CVD/ΔE 4종을 작업자가 쓴 같은 dataviz 검증기로 전부 재계산, 정확 일치** — 채택안 `#006ebe,#8c1f4a,#9a6a24` PASS(최악 CVD **15.4**·정상 **19.7**) · 종전 `#1a6d99`안 PASS(CVD **12.6**) → 성공만 blue-600 로 옮긴 개선 **12.6→15.4** 재현 · 상태색 통일안 F1(blue·danger-600·warn-700) 정상 **13.9**·protan **4.5** FAIL · F2(blue·danger-700·warn-700) 정상 **12.2**·deutan **3.3** FAIL. "계열 팔레트는 UI 상태색과 다른 물건, 통일하면 색각 이상에 한 덩어리" 핵심 논리 성립. chrome 결함(막대 stroke `#f4f0e7` 크림 테두리) 종전 커밋에서 실존·현재 0 리터럴·간격 `--surface-raised`. **★ 뮤테이션 C1–C5 전부 재현(스크립트 커밋), C3·C4·C5 단독 물림을 두 가드 동시실행으로 증명, C5=이 슬라이스가 고친 결함의 재발**. designTokens TS 리터럴 가드 신설(0건). 이전 검증 폐쇄도 확인 — `e5c0fac`(내 H1) M6 재탐침 cell1 FAIL 로 맹점 닫힘 · `11f8bb6`(내 니트 0.78rem 17→11·19→18 정정 + 인덱스 가드) `test_docs_indexes` 13/247 green. **Blocking 0**. 비차단 2: **H1 — ΔE/CVD 자체는 자동 가드 아님**(cell3는 충돌만, palette 바꾸면 재실행이 리뷰 필수) · H2 Tooltip/Legend recharts 기본 스타일(육안 확인 대상). | **합격** |
| [`slice_10_3_typography_scale.md`](2026-08-12/slice_10_3_typography_scale.md) | Slice 10.3 타이포 축 + DraftEditor 적용(`d4bf832`·`a4ec45c`, Phase 10 §10.3) — 기준선 재현(frontend **309/24** · 백엔드 prod **0줄** · CSS-읽기 가드 provenance **5/89**). **★ 스케일 8계단 전부 `round(1.125**n,3)` 수기 계산과 정확 일치**, 정본 표(L397–406)↔`styles.css:140–147` 무결점. **★ 이관 충실: `var(--type-*)` 사용처 42곳 == `MIGRATED` 42행, 단계별 정확**(숨은 사용처 0). 위계 편집 3곳(`.editor-heading h1`→`var(--type-title)`·`.editor-page` padding-top·`.editor-heading` margin) 코드에 존재, "3.7배"(4.2/1.12=3.75) 성립. **★ 뮤테이션 M1–M5 전부 독립 재현**(스크립트 커밋): M1·M2→cell1 양방향 · M3→cell3 단독 · M4→cell2 죽은계단 · **M5→안 물음(공식 한계, 정본 L420–422 가 이미 못 박음)**. **Blocking 0**. **★측정 정밀도 니트(비차단, 서술 정정 권고)**: 패턴스윕 "0.78rem 17곳"→실측 **11곳**(총합 45 는 맞음, 17 이면 51) · "19종"→흡수열 distinct **18종**. 비차단 보강 1: **H1 — cell 1 정규식이 `1.125^n` 주석 있는 줄만 잡아 주석 없는 토큰은 램프 검사를 안 함**(M6 탐침 3 passed 로 실존, 현재 8 토큰은 전부 주석 있어 즉시 위험 0). | **합격** |

### 2026-08-11

| [`slice_10_2_activity_date_groups.md`](2026-08-11/slice_10_2_activity_date_groups.md) | Slice 10.2 활동 날짜 그룹(`34ed87f`·`c45506d`, Phase 10 §D3 ⓓ, backend 0줄) — 기준선 재현(frontend **305/23** · build **703/421.78·CSS 30.66** · 백엔드 가드 3종 **24/364** · prod 0줄로 기준선 2271/1/2430 유효). **★ 오너 "접힘" 의문 해소** — 모듈·두 화면·셀·**배포 이미지**(15:46 빌드·서빙 CSS `activity-day`) 전부에서 같은 날 행이 머리글 하나로 접힘 확인. 안 접혀 보인 건 같은 날 5건이라 머리글 하나(정상) + 눈에 덜 띄는 머리글 스타일. **M22(UTC 그룹) 4 failed 독립 재현**(모듈 3 + 화면 1) — local-boundary 불변식 양쪽 잠금. no-resort·미버림·now주입·clock-pitfall(2024 날짜) 셀 양호. D3=ⓓ 상한 유지. **Blocking 0**. 비차단 1(머리글 시각 강조 = 10.3~ 과제). | **합격** |
| [`slice_10_1_palette.md`](2026-08-11/slice_10_1_palette.md) | Slice 10.1 잉크블루 토큰 체계(`dcd2ad5`·`3465192`·`4dd2046`, Phase 10 §D2·§D6) — 기준선 재현(frontend **294/22** · build **702/420.81 무변·CSS 30.47** · provenance **3/62**). **★ WCAG 30짝 독립 재계산 전부 통과**(slate-400 #7f8994=3.32·slate-450 #636c77=4.98 위험짝 직접 계산, 스크립트와 소수 3째짜리 일치). 옛 팔레트 토큰·#a4452f 0(#f4f0e7 은 관측 차트만=예상 중간상태). 새 가드 designTokens(3)·provenance(3)·productName(2) 뮤테이션으로 물림 확인(provenance CSS-hex 변형→cell1·designTokens 미정의토큰→cell1). 8.4 `.writing-confirm` 결함 fix·작업자 자결함(body) fix. 타이포 29종 무변·유예사유 :root 기록. **★C1·H1(브리프 §D2 표·prose 짝 수 정정)은 후속 커밋 `259c7a4`에서 작업자 폐쇄** — 브리프 원시테이블 정정(slate-400 취소선→#7f8994·slate-450 신설) + 대비표 "착수 스냅샷" 명시·정본을 script/guard 지정(주석이 "독립 검증 C1·H1" 인용) + styles.css/work_log 짝 수 30 통일 + **검증자 권고대로 prose 를 len(PAIRS) 에 묶는 셀 추가**(provenance 3→4 cells, M16·M17). 검증자 실측·완전 → **합격 승격**. | **합격** |
| [`slice_10_0_account_menu.md`](2026-08-11/slice_10_0_account_menu.md) | Slice 10.0 계정 메뉴 + 제품명 "에-라잇"(`387bfe7`·`5965c9b`·`db223ee`, Phase 10 §D4 ⓐ+ⓒ·§D5) — 기준선 전부 독립 재현(frontend **289/20** · build **702 modules · 420.81 kB** · 백엔드 가드 **6/30** · `tsc` clean). **★ M2 헤드라인 내러티브 양방향 재현** — 강화 전 테스트(387bfe7)+변형 = **24 passed(안 물음)**, 강화 후+변형 = **1 failed(물음)**. M1→3·M4→2 failed 도 일치. 두 일탈 모두 건강 — disclosure vs `role="menu"`(ARIA menu 약속 불필요·`<a>` link 역할 보존) · 로그아웃 패널 유지(진행 신호 보존, M4 2겹). **★발견: 브라우저 탭 `<title>` 이 "AI Writing System" 잔존**(`index.html:6`) — D5 "이름 통일" 의도가 탭에서 미달성, `queryByText` 가 `<head>` 를 안 봐 가드 밖. 오너 결정: 수정은 작업 AI. **Blocking 0**. 비차단 3(★H1 탭 타이틀 통일+`document.title` 가드 · H2 openapi API title=범위 밖 · H3 work_log M1 셀 라벨 정정). | **조건부 합격** |

### 2026-08-10

| [`slice_9_2_personal_hub_activity.md`](2026-08-10/slice_9_2_personal_hub_activity.md) | Slice 9.2 개인 허브 `/me` + 통합 활동(`20be3c0`·`8b5a30d`·`7a1fb5e`·`6d7dd9a`, SoT v1.7.96) — 기준선 수치 전부 정확히 재현(backend **2265/1/2364** · frontend **285/20** · 진입 **420.08 kB** · 관측 lazy **386.70 kB**; 모듈 702↔주장 704 비부하 차이). **★ 빈 집합 이중 방어**(작업자가 뮤테이션으로 연 자리)를 경로별 3층으로 해체해 실측 — mongo 직접 셀이 `$in:[]` 성질의 **유일한 고정점**(서비스/HTTP 셀은 인메모리를 써 안 닿음)임을 확인, 작업자 "두 층이 서로를 가린다" 서술이 본질에서 맞음. P8 소유 기준 뮤테이션(전체→샘)·`?next=` over 뮤테이션(위치조건 제거→딥링크 삼킴) 양쪽 물림. `?next=` 미도입은 사운·SoT v1.7.96 에 해소 기록됨. **Blocking 0**. 비차단 2(★허브 표시 상한↔`list_for_projects` 서빙 상한 연결 가드 누락 — 9.1 `ActivityCeilingClaimTest` 선례 미연장 · 브리프 본문 P5/S-2 옛 `?next=` 문구 정리). | **합격** |
| [`slice_9_1_activity_timeline.md`](2026-08-10/slice_9_1_activity_timeline.md) | Slice 9.1 활동 타임라인 화면(`86ca173`·`f220abd`, SoT v1.7.94) — 두 정본(백엔드 분류표·프론트 라벨표)을 잇는 **연결 가드**가 뮤테이션 양방향으로 증명됐다(under: 백엔드 21번째 action → 라벨 셀 · over: 프론트 유령 라벨 → 같은 셀). **M3 형태**(라벨 칸에 리터럴을 복사하면 1차 셀은 못 잡고 폴백이 조용한 통과를 만드는 형태)를 **2차 셀**이 잠근다. target_type 링크 분류도 같은 형태로 연결. **F7 사실 확인** — payload 에 `draft_id` 없음·`target_id`=version id·편집 route 는 `draftId` 필수 → `draft_version` 비링크가 맞고 **계약 영향 0** 유지, 비링크는 프론트 셀에 잠김(M7). 기준선 재현(backend delta 직접 green·frontend **272/272 재실행 green** — 1차 run 의 DraftEditor emoji flake 1건은 과부하·단독 합격·재실행 합격·슬라이스 무관 · build 701/417.19 kB · op **77** 무변). **Blocking 0**. 비차단 2(표시 상한 100 ↔ 서빙 상한 100 이 비연결 — S4 라벨표와 달리 가드 없음 · DraftEditor emoji `selectionStart` 과부하 flake). | **합격** |
| [`accept_activity_cell_reinforcement.md`](2026-08-10/accept_activity_cell_reinforcement.md) | accept 활동 로그 **보강분**(`66f2845`·`33fe4b2`) — 어제 조건부 합격의 조건을 검증 세션 자신이 닫아 미검증으로 남았던 구간. 새 셀이 **네 방향**으로 문다(삭제·이중 기록 + **검증자 추가 축** 리터럴 변조·`target_id` 변조 → 공허한 단정 아님)·502 분기를 지워도 전수 가드는 통과하므로 **유일 방어**임을 재현·**계약의 3분기 열거가 완전함을 코드로 확인**(저장 뒤 예외는 `_finalize` 의 `WritingAcceptAnalysisError` 하나뿐, replay 도 그 경로를 지나 기록됨)·**정정된 N10 페어링 재현**(2 cells, 정정 전 표기가 틀렸음까지 확인)·주석 수(20 경로·지점 21) 코드 실측 일치. 기준선 `2250/1/2325` 를 **베타에서 원시값으로** 재현(알파 보정이 옳았다는 독립 증거, 939s). **Blocking 0** → 어제 기록을 **합격으로 승격**. 비차단 1(§6-b·work_log 의 "73 → 74 cells" 는 3-파일 세트 수인데 파일 하나 행에 붙었다 — 그 파일은 50 → 51). | **합격** |

### 2026-08-09

| [`service_activity_log_accept_extension.md`](2026-08-09/service_activity_log_accept_extension.md) | Phase 9 A2 추가 확정(`170ea3a`·`ca97f2b`) — 활동 로그가 `writing/accept` 를 포함(19 → **20**). 분류표 20/20/40·정본 11·`ai_request` 13·리터럴 `draft_version_accepted` 를 코드에서 재측정해 정본 3종과 문자 일치 확인, 기준선 `2246/4/2324`(보정 `2249/1`) skip 사유까지 재현. 구현자 N9 일치, **N10 은 재실패 셀 하나가 불일치**(신설 saved 셀이 아니라 기존 `test_non_pass_is_200_without_saved_artifacts`). **★ Blocking 1 — SoT v1.7.93 이 "남긴다"고 명시한 502 partial 분기를 잠그는 셀이 0건**: 그 `activity.record(...)` 6줄을 지워도 **전수 회귀 2246/4/2324 전부 green**(전수 가드는 같은 handler 의 성공 분기로 만족된다). 비차단 3건(뮤테이션 페어링 정정 · replay 가 이벤트를 매번 추가 — **9.0 본체 `save_draft` 와 동일 성질이라 이 슬라이스 편차 아님** · 주석 "19 개 호출부"). **조건은 같은 날 닫혔고 2026-08-10 독립 세션이 폐쇄를 재현해 합격으로 승격**([`accept_activity_cell_reinforcement.md`](2026-08-10/accept_activity_cell_reinforcement.md)). | **합격** |
| [`service_activity_log.md`](2026-08-09/service_activity_log.md) | Phase 9 Slice 9.0(`65507d9`·`c5b5af4`, A1~A8) — 서비스 활동 로그. 정본 10+검토 9=**19 경로** → `activity_events` + `GET …/activity`(op **77**). **★ N5 I1 방향**(`log_mongo` `project_id`→`target_project_id` 7셀, 8.2c `project_name_history` 와 정반대를 나란히 잠금)·**분류표 40 전수**(미등재·stale 0)·19 배선·A4 격리·A7 409 순서·A8 을 검증자가 1차 소스에서 재현. 뮤테이션 8종(7 완전일치, N2 핵심 409 일치). 회귀 `2244/4/2322`(보정 `2247/1`)·op 76→77·`schema.d.ts` +118. **Blocking 0**. `writing/accept` 정본 저장이나 오너 승인 B=19 존중→excluded+주석(오너 결정 대기, 행 하나). | **합격** |
| [`admin_surface_separation.md`](2026-08-09/admin_surface_separation.md) | 라우터 정리 Slice 2(`5bdaf15`·`878f24d`·`bb26d6e`, A1=ⓑ) — `/admin` 8 operation 을 별도 compose 서비스로 분리 + H-2(shim drift) 폐쇄. **표면 분할(76=68∪9·교집합 `/health`)**·**openapi sha `f8b42ef1…` worktree diff IDENTICAL**·소켓 라이브(LAN 게시 포트에서 `/admin` 은 **라우터 404**)를 검증자가 1차 소스에서 재현. **★ H-2 drift 뮤테이션(M6) 재현 + 추가 M8 로 operation별 route_class 가드(A6) 생존 입증**; 뮤테이션 7종 전부 구현자 보고 셀과 일치. 회귀 `2208/4/2247`(보정 `2211/1`) 재현(172s). 컨테이너 진입점 기동 트리 마운트로 입증. **Blocking 0**. 남은 nginx→admin 컨테이너 한 홉은 재빌드 후 오너 판정. | **합격** |

### 2026-08-08

| 기록 | 대상 | 판정 |
|---|---|---|
| [`main_unused_import_cleanup.md`](2026-08-08/main_unused_import_cleanup.md) | 라우터 분해 Slice 1 뒷정리(`3ff4274`·`7d4bc8d`) — `main.py` 미사용 import **21개 제거**(1,860→1,840줄, 변경 파일 1). 정적 축을 **1차 소스에서 재현**(OLD `d65a1c9` pyflakes 정확히 21 · NEW 0, 21 심볼이 작업자 표와 한 치 없이 일치) + pyflakes 와 무관한 **독립 잔류 grep**(20/21 잔류 0, 유일 히트는 모듈명 `datetime`). 구조적 축 `main` 경유 참조 **0건**(다중줄 import 오탐 1회를 파일 읽어 해소). 행위 무변 repro 지문 pre(`d65a1c9`) vs post **바이트 동일**(route 76·order-pairs 0·openapi sha `f8b42ef1…`). 뮤테이션 M4(`LlmCallSite` 제거) **8 failed 셀 이름까지 일치**·M1(`timedelta`) 안 뭄 재현. **★ `AUTH_SESSION_TTL_HOURS` 계약을 라이브로 적극 증명** — `-1`/`0`/`abc` 전부 `ValueError`(계약 살아 있음)인데 `grep tests/` **0건**(커버리지 없음). 회귀 `2197/4/2168` 0실패 재현(172s), ES 보정 `2200/1` = 셀 증감 0. **비차단: 작업자가 인용한 지문 해시 `47d78b68…` 재현 불가**(8종 시도) — 원인은 repro 가 JSON 을 stdout·요약표를 stderr 로 내는데 작업자가 `2>&1` 로 합쳐 받은 것(`2f5b253`로 폐쇄). | **합격** |

### 2026-08-07

| 기록 | 대상 | 판정 |
|---|---|---|
| [`router_split_slice1_remainder_1st.md`](2026-08-07/router_split_slice1_remainder_1st.md) | 라우터 분해 Slice 1 잔여 1차(`b6eec79`·`925a321`) — health·memory·observability·context-search(5 operation)를 `main.py` 밖으로 + 공유 직렬화기 3종 `api/payloads.py` + `_require_project_exists` factory 통합 + 라우터 로드 가드 글롭 전수화(2→6). 행위 무변 repro 지문 pre(`9bc06e3`) vs post(HEAD) **IDENTICAL**(route 76·order-pairs 0·openapi sha·dependency 트리). **이동 정의 12/12 AST-동일**(repro 가 못 보는 `dict` 응답 직렬화기 본문을 이게 닫음)·패치 타깃 3곳 갱신 누락 0. 뮤테이션 5종 전부 주장 셀에 물림(순환 복귀 `SUBFAILED(module=routers.memory)` 로 가드 보강이 범인 지목·register 누락 tier 가드·scope_id 제거→analysis 셀로 공유 증명·storage 503·billable 순서 1개만). 기준선 `2197/1/2159` 재현(1010s). **비차단: `GET …/memory` 응답 `scope.scope_id` 단정 셀 부재**(이동 전부터, hardening). 재현은 [`repro_byte_identical.py`](2026-08-07/repro_byte_identical.py)·[`repro_mutations.py`](2026-08-07/repro_mutations.py) | **합격** |
| [`router_split_slice1_remainder_2nd.md`](2026-08-07/router_split_slice1_remainder_2nd.md) | 라우터 분해 Slice 1 잔여 2차(`131bc2a`) — projects·drafts·source-refs(25 operation·정의 30)를 `main.py` 밖으로(in-routers 17→42, 잔여 34). 행위 무변 repro 지문 pre(`9bc06e3`=세션 착수 전) vs post(HEAD) **IDENTICAL**(route 76·order-pairs 0·openapi sha `f8b42ef1…`·dependency 트리) — 하루치(1차+hardening+2차)가 한 diff 로 증명. **이동 정의 30/30 AST-동일**(검증자 직접 재현 — 1차 repro 가 안 덮는 축). orphan 제거 **F821 undefined name 0건**(PEP 563 포함). 회귀 `2200/1/2163` 재현(test-mongo 사용, skip=1). 뮤테이션 N1(순환 복귀)이 글롭 가드로 `SUBFAILED(module=routers.projects)` — 1차 글롭 처방이 신규 모듈 3종을 자동 범위화한 것을 재확인. **비차단: 2차 byte-동일·뮤테이션 N1-N5 의 커밋된 repro 스크립트 부재**(부하 증명은 커밋된 지문 repro 로 덮임)·미사용 import 22(작업자) vs 21(실측). | **합격** |
| [`router_split_slice1_remainder_3rd.md`](2026-08-07/router_split_slice1_remainder_3rd.md) | 라우터 분해 Slice 1 잔여 3차(`70584c2`) — analysis 도메인(21 operation·정의 36)을 `main.py` 밖으로(in-routers 42→63, 잔여 13=writing). 공유 직렬화기 `_analysis_job_payload` 1종만 `api/payloads.py` 로 내림(writing 잔류가 import). 행위 무변 repro 지문 **두 기준** pre(`5aaf202`=3차 직전)·pre(`9bc06e3`=분해 이전) vs HEAD **모두 IDENTICAL**(route 76·order-pairs 0·openapi sha `f8b42ef1…`·dependency 트리) — **1·2·3차 전체가 한 diff 로 증명**. **이동 정의 36/36 AST-동일**(작업자 repro + 검증자 전수 추출). **결합도 독립 입증**: main.py(writing)가 이동 직렬화기 중 오직 `_analysis_job_payload`만 참조 → "유일 공유" 확인. orphan **F821 0건**(PEP 563). 회귀 `2200/1/2165` 재현(test-mongo 사용). 뮤테이션 N1-N5 전부 가드 작동(N1 `SUBFAILED(module=routers.analysis)` 글롭 자동 범위화·N3 analysis·writing 양쪽 시위·N4 BILLABLE 9개 전수). **★ 2차 hardening 2건(repro 미커밋·카운트 22→21)이 `13b673e`로 폐쇄**, 3차는 repro 처음부터 커밋. 재현은 [`repro_byte_identical_3rd.py`](2026-08-07/repro_byte_identical_3rd.py)·[`repro_mutations_3rd.py`](2026-08-07/repro_mutations_3rd.py). | **합격** |
| [`router_split_slice1_remainder_4th.md`](2026-08-07/router_split_slice1_remainder_4th.md) | 라우터 분해 Slice 1 잔여 4차·**완료**(`c289bce`) — writing 도메인(13 operation·정의 25)을 `main.py` 밖으로. **76 op 전부 routers/ 11모듈로**(in-routers 63→76, main.py 인라인 라우트 0). `_require_project_exists` 정의 **삭제**(writing이 마지막 사용) — 순수 이동이 아닌 실제 제거, AST 자동 생성 import 로 이동. 행위 무변 repro 지문 **HEAD ≡ `9bc06e3`(Slice 1 착수 전)** IDENTICAL(route 76·order-pairs 0·openapi sha `f8b42ef1…`·dependency 트리) — **모놀리스→11모듈 4-슬라이스 전체가 한 diff 로 증명**. 이동 정의 **25/25 AST-동일**(작업자 repro 24 + 검증자 전수 추출 25 — 작업자 TARGETS 가 헬퍼 `_derive` 1개 누락, 이동은 완전). `_require_project_exists` 삭제 잔류 참조 0·F821 0. AST import writing.py pyflakes 완전 clean. 회귀 `2200/1/2167` 재현(test-mongo 사용). 뮤테이션 N1-N5 전부 가드 작동(N1 `SUBFAILED(module=routers.writing)` 글롭 자동 범위화·**N3 accept partial envelope 502→500**(3차 예고축)·N4 BILLABLE 9개 전수). **★ 3차 hardening 2건이 `f9b5e45`로 폐쇄**(지금까지 hardening 4건 전부 폐쇄). 재현은 [`repro_byte_identical_4th.py`](2026-08-07/repro_byte_identical_4th.py)·[`repro_mutations_4th.py`](2026-08-07/repro_mutations_4th.py). | **합격** |

### 2026-08-06

| 기록 | 대상 | 판정 |
|---|---|---|
| [`shared_prelude_extraction.md`](2026-08-06/shared_prelude_extraction.md) | 공유 prelude 추출 3커밋(`2f20fbb`~`635d84b`) — `main.py` prelude 134 이름을 `app/env.py`·`app/api/{models,errors,dependencies}.py` 로 본문 byte-동일 추출해 **`main↔routers` 순환을 폐쇄**(H-3-A). 행위 무변 repro 지문 pre(10502a6) vs post(HEAD) **IDENTICAL**(route 76·order-pairs 0·openapi sha `f8b42ef1…`). 죽던 로드 경로 3종 부활(FQ 80 routes·라우터 먼저·`python -m` exit 0). AST 로 이름 해석 양방향 무결(이동 코드 미해결 전역 0·main 누락 import 0)·본문 byte-동일(샘플 14). 뮤테이션 3종 재실패(순환 재도입 5 cell·상대→절대 1 cell·별칭 제거 9 subtest). 기준선 `2196/1/1933/0` 재현(1131s). 사소 보고 오차 2건(main.py 4806→실측 4808·cell 수 라벨링)은 hardening. | **합격** |
| [`h3_closure_and_record_bundle.md`](2026-08-06/h3_closure_and_record_bundle.md) | 미검증 구간 5커밋(`da35489`~`9caa76c`) — H-3 폐쇄(`59fe1a1`, 유일 코드) + 기록·README 건수·기준선. 신규 가드 [`test_app_import_paths.py`](../../tests/test_app_import_paths.py)를 **양방향** 뮤테이션으로 물림 확정(작업 세션은 under-strict 1종만 쟀다 — over-strict를 본 검증이 채웠다). 행위 무변 repro 지문 IDENTICAL(route 76·order-pairs 0·openapi sha `1e275ab8…`), README 220/합격 148 디스크 정확 일치, 기준선 `2193/1/1931` 재현(974s). **비차단 H-3-A: `python -m services.application.app.main`이 분해로 회귀**(분해 전 exit 0 → circular import) — 배포 uvicorn 무관, H-3의 1줄 처방으로는 안 닫힌다. 집계 재현은 [`tally_verification_ledger.py`](2026-08-06/tally_verification_ledger.py) | **합격** |

### 2026-08-05

| 기록 | 대상 | 판정 |
|---|---|---|
| [`router_split_slice1_auth_admin.md`](2026-08-05/router_split_slice1_auth_admin.md) | 라우터 분해 Slice 1(auth·admin, `539171f`~`e8b9908`) — `main.py`의 route를 `register_auth`/`register_admin` 모듈로 이동. 행위 무변을 **독립 4경로 교차 확인**(route 집합 IDENTICAL 76=64+12 · 데코레이터 배선 IDENTICAL 12/12 보안 배선 포함 · handler 본문 byte-동일 · billable 표 무변). modernization 가드를 뮤테이션으로 증명 — **이동한 파일**(`routers/auth.py` /me/quota)에 `llm_call_scope(` 삽입 시 B6 양방향 셀+free-route 셀이 재실패. 전수 suite `2191/1/1931` 기준선 무변. 결정 전제 D8-7 G1=C(loopback 바인딩·코드 0줄) 1차 소스 FAITHFUL. **보강 패스**: OpenAPI 스키마 바이트 동일(sha `1e275ab8…`, 프런트 TS 코드젠 파급 0)·해석된 dependant 트리 76/76 동일·등록 순서민감 쌍 0·재현 스크립트를 [`repro_router_split.py`](2026-08-05/repro_router_split.py)로 커밋. 비차단: 작업자 "전수 suite 못 돌림"은 낡은 test-mongo 가정(실제는 기동 중), **H-3 분해가 `app.main` 짧은 import 경로를 하드 ImportError로 바꿈**(전 진입점 FQ라 미발현, 1줄×2로 닫힘) | **합격** |
| [`slice_8_2c_project_name_history.md`](2026-08-05/slice_8_2c_project_name_history.md) | Slice 8.2c 구현(`507be95`~`d1f736c`) — 파기가 프로젝트 이름 한 값을 남긴다. 뮤테이션 #3(`_doc()`에 `project_id` 주입)이 **fake key-set 셀과 실 Mongo reconciler 셀 양쪽**을 깨뜨려 2중 방어를 실증했고, #4(rename 핸들러에 이력 쓰기)가 보강 뒤 물리는 것까지 재확인 | **합격** |
| [`slice_8_2c_brief_and_phase9.md`](2026-08-05/slice_8_2c_brief_and_phase9.md) | Slice 8.2c 브리프 N1~N6=A 확정 + Phase 9(서비스 활동 로그) 신설(문서 전용, 코드 0줄) — §N2-a 실측(system_events=0·draft_versions 필드 부재·purge 생존자 2건)·A4 정반대 선례(llm_call_audits 격리/access_grant_uses fail-closed)·"I2 뒤집으면 D8-6 붕괴" 논리·N1=A 피회 설계(`_PROJECT_ID_FIELD`)를 코드·독스트링에서 재도출 | **합격** |

### 2026-08-04

| 기록 | 대상 | 판정 |
|---|---|---|
| [`slice_8_2b_duplicate_request_lock_recheck.md`](2026-08-04/slice_8_2b_duplicate_request_lock_recheck.md) | Phase 8 Slice 8.2b 재검증 — 독립 검증 FAIL(`c0e9ba9`)의 B1·B2 폐쇄 + H1~H3 보강(`2969a09`)을 뮤테이션·실 Mongo로 확인 | **합격** |
| [`slice_8_3_quota_enforcement.md`](2026-08-04/slice_8_3_quota_enforcement.md) | Phase 8 Slice 8.3 quota 시행(Q1=C·Q1-a=A·Q1-b=A·Q3=E·Q3-a=A·Q4~Q9) — 정산 wrapper·입장 뮤텍스·auth_support 우회를 반증 시도, 2145/1/1921 + 뮤테이션 재실패로 확인 | **합격** |
| [`slice_8_4_product_wiring.md`](2026-08-04/slice_8_4_product_wiring.md) | Phase 8 Slice 8.4 제품 경로 배선(W1~W7) — 잔여 단일 출처·확인 통로(사용자 행동만)·부트스트랩 면제(정책 행)·Q5=B↔H3 충돌 해소(status로 정지 판정 이동)를 반증 시도, 2170/4/1931 + 262/18 + 뮤테이션 5종 재실패 + detail 가드 결함→수정 서사 코드 확인 | **합격** |

### 2026-08-03

| 기록 | 대상 | 판정 |
|---|---|---|
| [`slice_8_2b_duplicate_request_lock.md`](2026-08-03/slice_8_2b_duplicate_request_lock.md) | Phase 8 Slice 8.2b 실수 중복 요청 DB 잠금(G1=C·G2~G6=A, 충돌 후 release/TTL race) | **불합격** |
| [`slice_8_2_usage_ledger.md`](2026-08-03/slice_8_2_usage_ledger.md) | Phase 8 Slice 8.2 사용량 원장(L1=B·L2~L5=A, target_project_id·부분 인덱스·시행 없음) | 합격 |
| [`slice_8_1_quota_policy.md`](2026-08-03/slice_8_1_quota_policy.md) | Phase 8 Slice 8.1 요청 한도 정책 저장 계약(P1~P8, 이중 창·KST·파생·시행 없음) | 합격 |
| [`slice_8_0_billable_boundary.md`](2026-08-03/slice_8_0_billable_boundary.md) | Phase 8 Slice 8.0 billable request 경계(B1~B6=A, 분류만·시행 없음) | 합격 |

### 2026-08-02

| 기록 | 대상 | 판정 |
|---|---|---|
| [`d8_6_purge_ui.md`](2026-08-02/d8_6_purge_ui.md) | D8-6 archive-only purge + 삭제 감사(tombstone) + purge UI | 합격 |
| [`d8_5d_admin_console.md`](2026-08-02/d8_5d_admin_console.md) | D8-5d 관리자 화면(첫 프론트 슬라이스) | 합격 |
| [`d8_5_c6_forced_password_change.md`](2026-08-02/d8_5_c6_forced_password_change.md) | D8-5 C-6 1회용 초기 비밀번호(최초 로그인 교체 강제 + 정책) | 합격 |
| [`d8_5b_admin_project_list.md`](2026-08-02/d8_5b_admin_project_list.md) | D8-5b 전 프로젝트 메타데이터 목록(GET /admin/projects) | 합격 |
| [`d8_5f_access_grant_audit.md`](2026-08-02/d8_5f_access_grant_audit.md) | D8-5f 승격 아래 요청 감사(access_grant_uses) + C-4 소유자 사후 조회 | 합격 |
| [`d8_5e_access_grants.md`](2026-08-02/d8_5e_access_grants.md) | D8-5e 관리자 승격(access grant) | 조건부 합격 |
| [`d8_7_g1c_loopback_exposure.md`](2026-08-02/d8_7_g1c_loopback_exposure.md) | D8-7 G1=C 저장소 노출면 축소(loopback 바인드) | 합격 |
| [`purge_reconciler.md`](2026-08-02/purge_reconciler.md) | D8-6 잔여 purge reconciler | 조건부 합격 |
| [`product_overview.md`](2026-08-02/product_overview.md) | 기획 축 제품 한 장 요약 + 낡은 단언 5건 정정 | 조건부 합격 |

### 2026-08-01

| 기록 | 대상 | 판정 |
|---|---|---|
| [`d8_6c2_worker_drain.md`](2026-08-01/d8_6c2_worker_drain.md) | D8-6c-2 worker PROJECT_PURGED drain 연결 | 합격 |
| [`d8_6c_purge_vector_lexical.md`](2026-08-01/d8_6c_purge_vector_lexical.md) | D8-6c-1·6c-1b vector/lexical 백엔드 파기 purge_project | 합격 |
| [`d8_6d_purge_endpoint.md`](2026-08-01/d8_6d_purge_endpoint.md) | D8-6d admin project purge endpoint | 조건부 합격 |

### 2026-07-31

| 기록 | 대상 | 판정 |
|---|---|---|
| [`alpha_rc_observation.md`](2026-07-31/alpha_rc_observation.md) | 알파 R-c 관측(창 32768), 컨텍스트 예산 트랙 종료 | 합격 |
| [`d8_6a_purge_core_sot.md`](2026-07-31/d8_6a_purge_core_sot.md) | D8-6a project 영구 파기 인터페이스(core_sot) | 합격 |
| [`d8_6b_purge_derived.md`](2026-07-31/d8_6b_purge_derived.md) | D8-6b derived 10컬렉션 파기 | 합격 |
| [`k4_front_counter_budget.md`](2026-07-31/k4_front_counter_budget.md) | K-4 프론트 글자수 카운터 + 소프트 경고 + `/writing/budget` 노출 — 독립 검증 | 합격 |
| [`r_a_budget_measure_league.md`](2026-07-31/r_a_budget_measure_league.md) | R-a/R-c 측정 리그 + 베타 실측 (989a1fc · b657f1b) | 합격 |
| [`r_a_implementation.md`](2026-07-31/r_a_implementation.md) | R-a 구현 (02feebb): report 예산을 창에서 유도한다 | 합격 |
| [`r_a_loop_accept.md`](2026-07-31/r_a_loop_accept.md) | R-a 유도를 revise-and-gate 루프·/writing/accept로 확장 (작업 트리, uncommitted) | 합격 |
| [`session_close_state.md`](2026-07-31/session_close_state.md) | 2026-07-31 세션 종료 상태 (HEAD = 337807b) | 조건부 합격 |

### 2026-07-30

| 기록 | 대상 | 판정 |
|---|---|---|
| [`k1_density_audit.md`](2026-07-30/k1_density_audit.md) | K-1 한글 토큰 밀도 환산 + 입력 예산 기본 8192 | 합격 |
| [`k3_context_window_guard_audit.md`](2026-07-30/k3_context_window_guard_audit.md) | K-3 컨텍스트 창 가드(거부 + 경고) | 합격 |
| [`r_e_citation_numbers_audit.md`](2026-07-30/r_e_citation_numbers_audit.md) | R-e(K-6) 항목 번호 인용 구현 | 합격 |

### 2026-07-29

| 기록 | 대상 | 판정 |
|---|---|---|
| [`beta_long_report_pointer_root_cause.md`](2026-07-29/beta_long_report_pointer_root_cause.md) | 베타 `long` report 실패 / 포인터 루트원인 실측 (코드 변경 0) | 합격 |
| [`slice1_context_budget_accounting_fix.md`](2026-07-29/slice1_context_budget_accounting_fix.md) | 슬라이스 1 / 컨텍스트 예산 회계 수정 (포인터 렌더링 회계 반영) | 합격 |
| [`slice1a_io_token_breakdown_audit.md`](2026-07-29/slice1a_io_token_breakdown_audit.md) | 슬라이스 1a / 감사에 입력·출력 토큰 분해 남기기 (K-3 관측 1a) | 합격 |
| [`slice1b_context_window_output_cap_reaudit.md`](2026-07-29/slice1b_context_window_output_cap_reaudit.md) | 독립 재검증 — K-3 관측 1b 컨텍스트 창·출력 상한 | **불합격** |

### 2026-07-28

| 기록 | 대상 | 판정 |
|---|---|---|
| [`auth_d8_3b_project_ownership.md`](2026-07-28/auth_d8_3b_project_ownership.md) | 인증 D8-3b 프로젝트 소유권 시행 (SoT v1.7.53) | 조건부 합격 |
| [`auth_d8_3c_combined_boundary_matrix.md`](2026-07-28/auth_d8_3c_combined_boundary_matrix.md) | 인증 D8-3c 401·403 최종 결합 boundary matrix 감사 (SoT v1.7.55) | 합격 |
| [`auth_d8_5a_admin_boundary.md`](2026-07-28/auth_d8_5a_admin_boundary.md) | 인증 D8-5a 관리자 경계 + 사용자 관리 (SoT v1.7.56) | 합격 |
| [`auth_d8_5c_global_kpi.md`](2026-07-28/auth_d8_5c_global_kpi.md) | 인증 D8-5c 전역 관측 KPI (SoT v1.7.57) | 합격 |
| [`c1_ctx16384_alpha_verification.md`](2026-07-28/c1_ctx16384_alpha_verification.md) | 컨텍스트 예산 C-1 (알파 `LLAMA_CTX_SIZE=16384` 기동 확인 슬라이스) | 합격 |

### 2026-07-27

| 기록 | 대상 | 판정 |
|---|---|---|
| [`auth_d8_3a_enforcement.md`](2026-07-27/auth_d8_3a_enforcement.md) | 인증 D8-3a 시행 (SoT v1.7.52) | 합격 |
| [`auth_d8_4_frontend_login.md`](2026-07-27/auth_d8_4_frontend_login.md) | D8-4 프론트 로그인 선행 독립 검증 | 합격 |
| [`auth_d8_slice1.md`](2026-07-27/auth_d8_slice1.md) | 인증 D8 슬라이스 1 (User·세션·로그인 API) 2026-07-27 | **조건부 합격** |
| [`auth_d8_slice2_owner_id.md`](2026-07-27/auth_d8_slice2_owner_id.md) | 인증 D8-2 (Project.owner_id) 슬라이스 2a·2b 2026-07-27 | 합격 |
| [`stack_bringup_handoff_machine_section.md`](2026-07-27/stack_bringup_handoff_machine_section.md) | 스택 기동 + HANDOFF 머신 구분 절 (2026-07-27) | **조건부 합격** |

### 2026-07-26

| 기록 | 대상 | 판정 |
|---|---|---|
| [`increment_5_kpi_readout.md`](2026-07-26/increment_5_kpi_readout.md) | 관측 KPI 증분 5 (집계 read-out `GET /observability/kpi`) | 합격 |
| [`increment_c_site_mapping_reclassify.md`](2026-07-26/increment_c_site_mapping_reclassify.md) | 관측 KPI 증분 C (site 매핑 · scope 개방 · 최종 거부 재분류) | 합격 |
| [`increment_dashboard_first_screen.md`](2026-07-26/increment_dashboard_first_screen.md) | 관측 KPI 대시보드 첫 화면 | 합격 |
| [`multi_user_d0_contract_transition.md`](2026-07-26/multi_user_d0_contract_transition.md) | 다중 사용자 단계 전환 (D0=A, SoT v1.7.49) | 합격 |

### 2026-07-25

| 기록 | 대상 | 판정 |
|---|---|---|
| [`observability_kpi_gate_migration.md`](2026-07-25/observability_kpi_gate_migration.md) | 관측 KPI 증분 B: writing_gate를 seam C로 이행 (SoT v1.7.45) | 합격 |
| [`observability_kpi_increment4_writing_gate.md`](2026-07-25/observability_kpi_increment4_writing_gate.md) | 관측 KPI 증분 4: `writing_gate` 첫 호출부 계측 + 와이어링 (SoT v1.7.42) | 합격 |
| [`observability_kpi_seam_extractor.md`](2026-07-25/observability_kpi_seam_extractor.md) | 관측 KPI seam(provider 데코레이터) 도입 + analysis_extractor 계측 (SoT v1.7.43) | 조건부 합격 |

### 2026-07-24

| 기록 | 대상 | 판정 |
|---|---|---|
| [`auto-promote-503-partial-envelope.md`](2026-07-24/auto-promote-503-partial-envelope.md) | `auto_promote_job` 503 partial envelope (SoT v1.7.35) | **조건부 합격** |
| [`observability-kpi-foundation-increments.md`](2026-07-24/observability-kpi-foundation-increments.md) | 관측 KPI 페이즈 기반 증분 1~3 (per-call 감사 레코드 + 게이트 파생점수) | 합격 |
| [`run_endpoint_storage_503_narrowing.md`](2026-07-24/run_endpoint_storage_503_narrowing.md) | `POST …/analysis/jobs/{id}/run` 저장소 장애 502→503 좁히기 (SoT v1.7.40, (B)) | 합격 |
| [`storage_503_global_handler.md`](2026-07-24/storage_503_global_handler.md) | 저장소 장애 매핑 전역화 (SoT v1.7.38, 전역 503 handler) | 합격 |

### 2026-07-23

| 기록 | 대상 | 판정 |
|---|---|---|
| [`h3_error_response_contract_s1_s2.md`](2026-07-23/h3_error_response_contract_s1_s2.md) | H3 에러 응답 계약 S1·S2 (SoT v1.7.29 / v1.7.30) | 합격 |
| [`h3_s3_analysis_error_responses.md`](2026-07-23/h3_s3_analysis_error_responses.md) | 독립 검증 기록 — H3 에러 응답 계약 S3: analysis 트랙 21 endpoint 에러 선언 | 합격 |
| [`h3_s4_memory_source_error_responses.md`](2026-07-23/h3_s4_memory_source_error_responses.md) | 독립 검증 기록 — H3 에러 응답 계약 S4: memory/source 트랙 7 endpoint 에러 선언 | 합격 |
| [`h3_s5_writing_error_responses.md`](2026-07-23/h3_s5_writing_error_responses.md) | 독립 검증 기록 — H3 S5: writing 트랙 12 endpoint 에러 선언 + `start_next_unit` 500 누수 폐쇄 | 합격 |
| [`rebuild_embedding_failure_502.md`](2026-07-23/rebuild_embedding_failure_502.md) | 독립 검증 기록 — 임베딩 실패 500 누수 폐쇄: source-block rebuild 502 매핑 (v1.7.34) | 합격 |

### 2026-07-22

| 기록 | 대상 | 판정 |
|---|---|---|
| [`accept_dirty_guard_unsaved_edits.md`](2026-07-22/accept_dirty_guard_unsaved_edits.md) | accept 후 미저장 편집 소실 결손 수정 (reloadLatest 덮어쓰기, 프론트 전용) | 합격 |
| [`h3_error_response_contract_plan.md`](2026-07-22/h3_error_response_contract_plan.md) | H3 에러 응답 계약 착수 결정 브리프 + work_log (오너 결정 D1~D4=A) | 조건부 합격 |
| [`increment3_d6_generation_pad_polling.md`](2026-07-22/increment3_d6_generation_pad_polling.md) | 비동기 생성 + 결과 패드 증분 3: 읽기 전용 패드 + 완료 배지 + 5초 폴링 (D6=A) | 합격 |
| [`legacy_drafts_500_503_integrity_mapping.md`](2026-07-22/legacy_drafts_500_503_integrity_mapping.md) | 레거시-데이터 `/drafts` 500 근본 수정 (DraftOrderIntegrityError 서브클래스 + 503 매핑) | 합격 |
| [`rail-tab-layering.md`](2026-07-22/rail-tab-layering.md) | 우측 레일 탭 레이어화 (dogfood 결손 수정) | 조건부 합격 |
| [`retry_slice_d4_generation_job.md`](2026-07-22/retry_slice_d4_generation_job.md) | 비동기 생성 job 재시도 endpoint + UI (async-pad D4=A, SoT v1.7.28) | 합격 |

### 2026-07-21

| 기록 | 대상 | 판정 |
|---|---|---|
| [`increment1_d2_d7_scratch_pad_prep.md`](2026-07-21/increment1_d2_d7_scratch_pad_prep.md) | 비동기 생성 + 결과 패드 슬라이스 증분 1 (D2=A + D7, scratch tier 패드 준비) | 합격 |
| [`increment2_d3_output_length_preset.md`](2026-07-21/increment2_d3_output_length_preset.md) | 검증 레코드 — 문체/분량 슬라이스 증분 2: 생성 분량 프리셋 (D3=A, SoT v1.7.22) | 합격 |
| [`increment2a_d4_generation_job_store.md`](2026-07-21/increment2a_d4_generation_job_store.md) | 비동기 생성 + 결과 패드 슬라이스 증분 2a (D4=A 데이터층, 생성 job 저장소) | 합격 |
| [`increment2b_d3_generation_worker.md`](2026-07-21/increment2b_d3_generation_worker.md) | 비동기 생성 + 결과 패드 슬라이스 증분 2b (D3=B, 생성 worker 실행 루프) + 2a hardening | 합격 |
| [`increment2c_d5_generate_endpoint_async_branch.md`](2026-07-21/increment2c_d5_generate_endpoint_async_branch.md) | Verification — 증분 2c: generate endpoint 동기/비동기 분기 (D5=A) | 합격 |
| [`increment3_d4_d5_d6_style_and_aspect.md`](2026-07-21/increment3_d4_d5_d6_style_and_aspect.md) | 문체/분량 슬라이스 증분 3 (D4+D5+D6): character aspect + Gate `style` finding + 문체 우선순위 | 합격 |

### 2026-07-20

| 기록 | 대상 | 판정 |
|---|---|---|
| [`async_generation_pad_brief.md`](2026-07-20/async_generation_pad_brief.md) | 비동기 생성 + 결과 패드 브리프 (D1~D7) | 합격 |
| [`project_brief_style_integration.md`](2026-07-20/project_brief_style_integration.md) | Verification — 문체/분량 슬라이스 증분 1: ProjectBrief 문체 정본 통합 (D1+D2) | 조건부 합격 |
| [`writing_scratch_recovery.md`](2026-07-20/writing_scratch_recovery.md) | Verification — 미채택 Writing candidate 복구 안전망 (scratch) | 조건부 합격 |

### 2026-07-19

| 기록 | 대상 | 판정 |
|---|---|---|
| [`w2_operational_closure.md`](2026-07-19/w2_operational_closure.md) | W2 테스트 머신 운영 closure — 독립 검증 | 합격 |
| [`w2_operational_closure_audit.md`](2026-07-19/w2_operational_closure_audit.md) | W2 테스트 머신 운영 closure — 독립 재감사 | 조건부 합격 |
| [`w2_project_brief_overview.md`](2026-07-19/w2_project_brief_overview.md) | W2 ProjectBrief onboarding + canonical overview — 독립 검증 | 합격 |
| [`w3_ordered_unit.md`](2026-07-19/w3_ordered_unit.md) | W3 증분 1 ordered unit 독립 검증 | 조건부 합격 |
| [`w3_writing_intent.md`](2026-07-19/w3_writing_intent.md) | W3 증분 2 Writing intent + W3 전체 closure 독립 검증 | 합격 |
| [`w4_export_frontend_zip.md`](2026-07-19/w4_export_frontend_zip.md) | W4 export UI + 회차별 개별 ZIP — 독립 검증 | 합격 |
| [`w4_export_ui_options.md`](2026-07-19/w4_export_ui_options.md) | W4 export UI 옵션화 (include_archived + manifest 토글) — 독립 검증 | 합격 |
| [`w4_project_export.md`](2026-07-19/w4_project_export.md) | W4 프로젝트 전체 ordered-latest export — 독립 검증 | 합격 |

### 2026-07-18

| 기록 | 대상 | 판정 |
|---|---|---|
| [`analysis_retry_v3_live.md`](2026-07-18/analysis_retry_v3_live.md) | Verification Record — 선택 C: analysis_extract_v3 + 명시 retry + 프론트 failed 판별 (독립 검증) | 합격 |
| [`d5a_live_deploy.md`](2026-07-18/d5a_live_deploy.md) | Verification Record — D5=A 재배포 + 라이브 closure (독립 검증) | 합격 |
| [`gate_finding_live_trigger.md`](2026-07-18/gate_finding_live_trigger.md) | Live Smoke Record — Context Gate finding 라이브 유발 + resolve/dismiss 관통 | 합격 |
| [`testbed_abc_slice.md`](2026-07-18/testbed_abc_slice.md) | Verification Record — 테스트베드 사용가능화 슬라이스 A+B+C (독립 검증) | 조건부 합격 |
| [`w0_contract_migration.md`](2026-07-18/w0_contract_migration.md) | Verification — Writing Workspace V2 W0 계약/migration | 조건부 합격 |
| [`w1_split_workspace.md`](2026-07-18/w1_split_workspace.md) | Verification — Writing Workspace V2 W1 split workspace | 조건부 합격 |

### 2026-07-17

| 기록 | 대상 | 판정 |
|---|---|---|
| [`b_review_inbox_second_slice.md`](2026-07-17/b_review_inbox_second_slice.md) | Verification Record — Frontend B Review Inbox 두 번째 슬라이스(candidate edit + conflict merge/split) | 합격 |
| [`b_review_inbox_ui.md`](2026-07-17/b_review_inbox_ui.md) | Verification Record — Frontend B Review Inbox 첫 슬라이스(목록 + 근거 detail + 이진 action) | 조건부 합격 |
| [`review_inbox_live_e2e.md`](2026-07-17/review_inbox_live_e2e.md) | Live Smoke Record — B Review Inbox 실 스택 관통 (v1.7.4 + v1.7.5) | 합격 |

### 2026-07-16

| 기록 | 대상 | 판정 |
|---|---|---|
| [`backend_contract_tightening.md`](2026-07-16/backend_contract_tightening.md) | 백엔드 공개 계약 조이기: 척추 응답 모델(H1) + 이름 검증(H2) (SoT v1.6.95) | 합격 |
| [`c0_writing_http_contract.md`](2026-07-16/c0_writing_http_contract.md) | C0 Writing HTTP contract 구현 (SoT v1.7.1, D3=A) | 합격 |
| [`c1_writing_basic_ui.md`](2026-07-16/c1_writing_basic_ui.md) | C1 기본 Writing 작업공간 UI 구현 (SoT v1.7.2, D1=A·D2=A·D4=A) | 합격 |
| [`c2_writing_loop_ui.md`](2026-07-16/c2_writing_loop_ui.md) | C2 자동 revise/retrieve loop UI | 합격 |
| [`frontend_editor_save.md`](2026-07-16/frontend_editor_save.md) | Frontend editor/save A1 슬라이스 (SoT v1.6.98) | **조건부 합격** |
| [`frontend_editor_save_a2.md`](2026-07-16/frontend_editor_save_a2.md) | Frontend editor/save A2 슬라이스 (SoT v1.6.99) | 합격 |
| [`frontend_first_slice.md`](2026-07-16/frontend_first_slice.md) | Frontend 첫 슬라이스 (SoT v1.6.94) | 합격 |
| [`frontend_project_navigation.md`](2026-07-16/frontend_project_navigation.md) | Frontend 프로젝트 상세 내비게이션 슬라이스 (SoT v1.6.96) | 합격 |

### 2026-07-15

| 기록 | 대상 | 판정 |
|---|---|---|
| [`writing_multi_finding_revise.md`](2026-07-15/writing_multi_finding_revise.md) | Verification — Phase 5.x Writing loop multi-finding revise (SoT v1.6.88) | 합격 |
| [`writing_per_stage_measure_mi.md`](2026-07-15/writing_per_stage_measure_mi.md) | Verification — Phase 5.10 Option A (M-i) per-stage 측정 도구 (SoT v1.6.87) | 합격 |
| [`writing_stable_context_pointer.md`](2026-07-15/writing_stable_context_pointer.md) | Writing stable context pointer (SoT v1.6.92) | 합격 |

### 2026-07-14

| 기록 | 대상 | 판정 |
|---|---|---|
| [`b2b_writing_loop_benchmark_harness.md`](2026-07-14/b2b_writing_loop_benchmark_harness.md) | Phase 5.10 B2b Writing loop full-stack benchmark harness | 합격 |
| [`residual_parser_fence_strip_sweep.md`](2026-07-14/residual_parser_fence_strip_sweep.md) | 잔존 4개 strict JSON parser fence-strip 스윕 (SoT v1.6.86) | 합격 |
| [`writing_gate_live_diag.md`](2026-07-14/writing_gate_live_diag.md) | Phase 5.10 D1=A Writing Gate live diagnostics CLI | 합격 |
| [`writing_loop_ceiling_and_fence_hardening.md`](2026-07-14/writing_loop_ceiling_and_fence_hardening.md) | Writing loop ceiling 합성 코어(Option A) + fence-sweep 검증기록 hardening 보강 | 합격 |

### 2026-07-13

| 기록 | 대상 | 판정 |
|---|---|---|
| [`writing_bounded_loop.md`](2026-07-13/writing_bounded_loop.md) | Verification — Phase 5.9 G8 bounded revise/retrieve loop | 합격 |
| [`writing_loop_aggregate_budget.md`](2026-07-13/writing_loop_aggregate_budget.md) | Verification — Phase 5.10 Writing loop aggregate token/wall-clock budget (B2 increment) | 조건부 합격 |
| [`writing_loop_audit_optin_reverification.md`](2026-07-13/writing_loop_audit_optin_reverification.md) | Verification — v1.6.79 Writing loop-audit opt-in delta (independent re-verification) | 조건부 합격 |
| [`writing_partial_revise.md`](2026-07-13/writing_partial_revise.md) | Phase 5.6 finding evidence 기반 부분 revise (SoT v1.6.73) | 조건부 합격 |
| [`writing_persisted_loop_audit.md`](2026-07-13/writing_persisted_loop_audit.md) | Verification — Writing persisted bounded-loop audit (Phase 5.9 L9 B, SoT v1.6.78) | 조건부 합격 |
| [`writing_report_api.md`](2026-07-13/writing_report_api.md) | Phase 5.5 Writing report 재평가 API (SoT v1.6.72) | 조건부 합격 |
| [`writing_retrieve_more.md`](2026-07-13/writing_retrieve_more.md) | Phase 5.8 Writing `retrieve_more` 1회 lifecycle (SoT v1.6.76) | 조건부 합격 |
| [`writing_revise_gate.md`](2026-07-13/writing_revise_gate.md) | Phase 5.7 partial revise→Gate 1회 합성 (SoT v1.6.74) | 조건부 합격 |
| [`writing_revise_report_gate.md`](2026-07-13/writing_revise_report_gate.md) | Phase 5.7 G3 B partial revise→report→Gate 합성 (SoT v1.6.75) | 조건부 합격 |

### 2026-07-12

| 기록 | 대상 | 판정 |
|---|---|---|
| [`candidate_edit_b1_closure.md`](2026-07-12/candidate_edit_b1_closure.md) | 독립 검증 후속 — candidate edit B1 closure (SoT v1.6.66, 6e15798) | 합격 |
| [`candidate_edit_backend.md`](2026-07-12/candidate_edit_backend.md) | Phase 6 candidate edit 백엔드 (SoT v1.6.66) | 조건부 합격 |
| [`character_alias_semantic.md`](2026-07-12/character_alias_semantic.md) | (c) character 별칭 semantic 보강 (SoT v1.6.62) | 합격 |
| [`character_homonym_reconciliation.md`](2026-07-12/character_homonym_reconciliation.md) | (c-2) 동명이인 semantic 반증 + merge/split reconciliation (SoT v1.6.63) | 합격 |
| [`gate_finding_persistence.md`](2026-07-12/gate_finding_persistence.md) | Phase 6 Context Gate finding 영속화 (SoT v1.6.65) | 조건부 합격 |
| [`indexing_live_smokes.md`](2026-07-12/indexing_live_smokes.md) | Verification — 인덱싱 파이프라인 live 관통 (full-stack, sandbox-external) | 합격 |
| [`indexing_live_smokes_independent_audit.md`](2026-07-12/indexing_live_smokes_independent_audit.md) | Verification — 인덱싱 live 관통 4종 독립 감사 (작업자 검증 기록의 적대적 재검증) | 합격 |
| [`llm_path_live_smokes.md`](2026-07-12/llm_path_live_smokes.md) | Verification — 실 LLM(12B) 경로 live 관통 4종 (full-stack, sandbox-external) | 합격 |
| [`llm_path_live_smokes_independent_audit.md`](2026-07-12/llm_path_live_smokes_independent_audit.md) | Verification — 실 LLM(12B) 경로 live 관통 4종 독립 감사 (작업자 검증 기록의 적대적 재검증) | 합격 |
| [`review_inbox_affordances.md`](2026-07-12/review_inbox_affordances.md) | Phase 6 Review Inbox 액션 어포던스 (SoT v1.6.67) | 합격 |
| [`review_inbox_backend.md`](2026-07-12/review_inbox_backend.md) | Phase 6 Review Inbox 백엔드 (SoT v1.6.64) | 합격 |
| [`writing_accept.md`](2026-07-12/writing_accept.md) | Phase 5.3 accept→save→analysis 재진입 (SoT v1.6.70) | 합격 |
| [`writing_gate.md`](2026-07-12/writing_gate.md) | Phase 5.2 Writing Gate (SoT v1.6.69) | 조건부 합격 |
| [`writing_generation.md`](2026-07-12/writing_generation.md) | Phase 5.1 Writing 생성 (SoT v1.6.68) | 합격 |
| [`writing_self_report.md`](2026-07-12/writing_self_report.md) | Phase 5.4 structured candidate report (SoT v1.6.71) | 조건부 합격 |

### 2026-07-11

| 기록 | 대상 | 판정 |
|---|---|---|
| [`candidate_state_transition.md`](2026-07-11/candidate_state_transition.md) | Verification — Phase 6 candidate 상태 전이 (백엔드 계약, SoT v1.6.61) | 합격 |
| [`canonical_candidate_dedup.md`](2026-07-11/canonical_candidate_dedup.md) | Verification — (e) canonical↔candidate 승격 dedup (SoT v1.6.60) | 합격 |

### 2026-07-10

| 기록 | 대상 | 판정 |
|---|---|---|
| [`connect_elasticsearch_skip_guard.md`](2026-07-10/connect_elasticsearch_skip_guard.md) | Verification — `ConnectElasticsearchTest` skip guard (b-5 후속, 테스트 전용) | 합격 |
| [`review_queue_persistence.md`](2026-07-10/review_queue_persistence.md) | Verification — (2B.4 후속) conflict review queue 영속화 (SoT v1.6.59) | 합격 |

### 2026-07-09

| 기록 | 대상 | 판정 |
|---|---|---|
| [`candidate_lexical_vector_retrieval_b2.md`](2026-07-09/candidate_lexical_vector_retrieval_b2.md) | (b-2) candidate lexical/vector retrieval (SoT v1.6.54 + v1.6.55) | 합격 |
| [`compose_elasticsearch_service_b5.md`](2026-07-09/compose_elasticsearch_service_b5.md) | (b-5) compose 전용 ES 서비스 (배포 lexical/hybrid 발화) | 합격 |
| [`es_lexical_backfill_v1_6_58.md`](2026-07-09/es_lexical_backfill_v1_6_58.md) | ES-lexical backfill 스크립트 (SoT v1.6.58) | 합격 |
| [`outbox_per_sink_bookkeeping_b6_increment2.md`](2026-07-09/outbox_per_sink_bookkeeping_b6_increment2.md) | (b-6) 증분2: outbox per-sink bookkeeping (SoT v1.6.57) | 합격 |
| [`worker_compose_increment1_b6.md`](2026-07-09/worker_compose_increment1_b6.md) | (b-6) 증분1 worker compose 서비스 (주장 v1.6.56) | **조건부 합격** |

### 2026-07-08

| 기록 | 대상 | 판정 |
|---|---|---|
| [`canonical_memory_lexical_hybrid_rrf.md`](2026-07-08/canonical_memory_lexical_hybrid_rrf.md) | 2026-07-08 SoT v1.6.52 독립 감사 (canonical memory retrieval ES lexical + hybrid RRF) | 합격 |
| [`canonical_memory_vector_retrieval.md`](2026-07-08/canonical_memory_vector_retrieval.md) | 2026-07-08 SoT v1.6.51 독립 감사 (canonical memory retrieval vector 확장) | 합격 |
| [`sot_v1_6_49_50_audit.md`](2026-07-08/sot_v1_6_49_50_audit.md) | 2026-07-08 세 커밋 독립 감사 (HANDOFF 정리 / SoT v1.6.49 / SoT v1.6.50) | 합격 |

### 2026-07-07

| 기록 | 대상 | 판정 |
|---|---|---|
| [`phase_2b_5_memory_vector_reindex_increment_1.md`](2026-07-07/phase_2b_5_memory_vector_reindex_increment_1.md) | Verification — Phase 2B.5 memory→vector 재색인 증분 1(계약+fake+회귀) | 조건부 합격 |
| [`phase_2b_5_memory_vector_reindex_increment_2.md`](2026-07-07/phase_2b_5_memory_vector_reindex_increment_2.md) | Verification — Phase 2B.5 memory→vector 재색인 증분 2(라이브 배선) | 합격 |
| [`phase_2b_6_semantic_identity_resolution.md`](2026-07-07/phase_2b_6_semantic_identity_resolution.md) | Verification — Phase 2B.6 event/open_question 의미적 identity resolution | 합격 |
| [`writing_canonical_memory_inclusion.md`](2026-07-07/writing_canonical_memory_inclusion.md) | Verification — Writing ContextPackage canonical memory 포함 (⑤ §5 B) | 조건부 합격 |

### 2026-07-06

| 기록 | 대상 | 판정 |
|---|---|---|
| [`phase_2b_2_prior_memory_context.md`](2026-07-06/phase_2b_2_prior_memory_context.md) | Verification — Phase 2B.2 prior-memory 검색 + Analysis 비교용 ContextPackage 구현 | 합격 |
| [`phase_2b_3_2_compare_judge.md`](2026-07-06/phase_2b_3_2_compare_judge.md) | Verification — Phase 2B.3.2 real Gateway terminal-JSON CompareJudge adapter | 합격 |
| [`phase_2b_3_compare_action.md`](2026-07-06/phase_2b_3_compare_action.md) | Verification — Phase 2B.3 candidate↔canonical compare + D3 scope key (proposals only) | 합격 |
| [`phase_2b_4_versioned_upsert.md`](2026-07-06/phase_2b_4_versioned_upsert.md) | Verification — Phase 2B.4 proposal→실제 memory versioned upsert | 조건부 합격 |

### 2026-07-05

| 기록 | 대상 | 판정 |
|---|---|---|
| [`b2_embedding_service_container.md`](2026-07-05/b2_embedding_service_container.md) | Verification — Phase 4 B.2 embedding 서비스 컨테이너 | 합격 |
| [`b3_chroma_persistent_adapter.md`](2026-07-05/b3_chroma_persistent_adapter.md) | Verification — Phase 4 B.3 Chroma persistent vector adapter | 조건부 합격 |
| [`b4_real_vector_backend_wiring.md`](2026-07-05/b4_real_vector_backend_wiring.md) | Verification — Phase 4 B.4 real vector backend wiring | 합격 |
| [`b5_deployed_live_smoke.md`](2026-07-05/b5_deployed_live_smoke.md) | Verification — Phase 4 real vector 백엔드 B.5 deployed live smoke | 합격 |
| [`deployed_smoke_rebuild_first.md`](2026-07-05/deployed_smoke_rebuild_first.md) | Verification — Phase 4 deployed context-search smoke 2-step 확장 | 합격 |
| [`phase2b1_memory_canonical_store.md`](2026-07-05/phase2b1_memory_canonical_store.md) | Verification — Phase 2B.1 canonical MemoryEntry store + candidate 승격 | 합격 |
| [`phase2b2_brief_spec_gate.md`](2026-07-05/phase2b2_brief_spec_gate.md) | Verification — Phase 2B.2 착수 브리프 스펙 게이트 검증 | 조건부 합격 |
| [`real_vector_backend_brief_b1_embedding_seam.md`](2026-07-05/real_vector_backend_brief_b1_embedding_seam.md) | Verification — Phase 4 real vector backend 브리프 + B.1 embedding seam | 합격 |
| [`shared_vector_index_slice.md`](2026-07-05/shared_vector_index_slice.md) | Verification — Phase 4 공유 in-process vector index slice (SoT v1.6.35) | 합격 |
| [`worker_real_chroma_archive_mutation.md`](2026-07-05/worker_real_chroma_archive_mutation.md) | Verification — worker→real Chroma archive mutation 배선 | 조건부 합격 |

### 2026-07-04

| 기록 | 대상 | 판정 |
|---|---|---|
| [`context_search_4_3_closure_and_smoke.md`](2026-07-04/context_search_4_3_closure_and_smoke.md) | Verification — Phase 4 Slice 4.3 follow-ups: empty-shell closure + deployed smoke | 합격 |
| [`context_search_slice_4_2.md`](2026-07-04/context_search_slice_4_2.md) | Verification — Phase 4 Slice 4.2 터미널 JSON LLM planner adapter | 조건부 합격 |
| [`context_search_slice_4_3.md`](2026-07-04/context_search_slice_4_3.md) | Verification — Phase 4 Slice 4.3 context search HTTP API + async wiring | 조건부 합격 |

### 2026-07-03

| 기록 | 대상 | 판정 |
|---|---|---|
| [`context_search_slice_4_1.md`](2026-07-03/context_search_slice_4_1.md) | Verification — Phase 4 Slice 4.1 context search | 조건부 합격 |
| [`phase3b_archive_outbox_slice.md`](2026-07-03/phase3b_archive_outbox_slice.md) | Phase 3B Archive Outbox 첫 code slice 독립 검증 | 합격 |
| [`phase3b_outbox_live_mongo_smoke.md`](2026-07-03/phase3b_outbox_live_mongo_smoke.md) | Phase 3B index_sync_outbox Live Mongo Smoke 독립 검증 | 합격 |
| [`phase3b_worker_retry_brief.md`](2026-07-03/phase3b_worker_retry_brief.md) | Phase 3B index worker/retry 결정 브리프 독립 검증 (pre-implementation) | 조건부 합격 |
| [`phase3b_worker_retry_slice.md`](2026-07-03/phase3b_worker_retry_slice.md) | Phase 3B index sync worker/retry 구현 slice 독립 검증 | 합격 |

### 2026-07-02

| 기록 | 대상 | 판정 |
|---|---|---|
| [`phase3a_deployed_rebuild_smoke.md`](2026-07-02/phase3a_deployed_rebuild_smoke.md) | Phase 3A Deployed Rebuild Smoke 독립 검증 | 조건부 합격 |
| [`phase3a_rebuild_http_api.md`](2026-07-02/phase3a_rebuild_http_api.md) | Phase 3A Explicit Rebuild HTTP API 독립 검증 | 합격 |
| [`phase3a_rebuild_script.md`](2026-07-02/phase3a_rebuild_script.md) | Phase 3A Explicit Rebuild CLI 독립 검증 | 합격 |
| [`phase3a_source_block_index.md`](2026-07-02/phase3a_source_block_index.md) | Phase 3A Source Block Indexing 첫 slice 독립 검증 | 조건부 합격 |
| [`phase3a_stale_validation.md`](2026-07-02/phase3a_stale_validation.md) | Phase 3A Source-Block Stale Validation 독립 검증 | 합격 |
| [`phase3b_sync_outbox_brief.md`](2026-07-02/phase3b_sync_outbox_brief.md) | Phase 3B Index Sync/Outbox Decision Brief 독립 검증 | 합격 |

### 2026-07-01

| 기록 | 대상 | 판정 |
|---|---|---|
| [`phase2a_provider_wiring.md`](2026-07-01/phase2a_provider_wiring.md) | Phase 2A Provider/Gateway Runner Factory Wiring 첫 구현 slice 독립 검증 | 조건부 합격 |
| [`source_ref_catalog_http_api.md`](2026-07-01/source_ref_catalog_http_api.md) | Phase 2A SourceRef Catalog HTTP API + Catalog Anchor Repair 독립 검증 | 조건부 합격 |

### 2026-06-30

| 기록 | 대상 | 판정 |
|---|---|---|
| [`gemma_benchmark_defaults.md`](2026-06-30/gemma_benchmark_defaults.md) | Gemma Q4 benchmark defaults 독립 검증 | 합격 |
| [`phase2a_analysis_http_api.md`](2026-06-30/phase2a_analysis_http_api.md) | Verification — Phase 2A analysis job/candidate HTTP read surface | 조건부 합격 |
| [`phase2a_analysis_http_api_i1_closure.md`](2026-06-30/phase2a_analysis_http_api_i1_closure.md) | Verification — Phase 2A analysis HTTP API I1/I2 closure | 조건부 합격 |
| [`phase2a_run_endpoint.md`](2026-06-30/phase2a_run_endpoint.md) | Phase 2A analysis run endpoint 독립 검증 | 조건부 합격 |
| [`phase2a_run_endpoint_closure.md`](2026-06-30/phase2a_run_endpoint_closure.md) | Phase 2A run endpoint — F4/F5/F6 폐쇄 재검증 | 합격 |
| [`phase2a_runner_execution_brief.md`](2026-06-30/phase2a_runner_execution_brief.md) | Verification — Phase 2A runner execution decisions brief | 조건부 합격 |
| [`slice1_draft_version_export.md`](2026-06-30/slice1_draft_version_export.md) | Slice 1 draft version export 독립 검증 | 합격 |

### 2026-06-29

| 기록 | 대상 | 판정 |
|---|---|---|
| [`analysis_job_state_runner_slice2.md`](2026-06-29/analysis_job_state_runner_slice2.md) | Phase 2A job-state runner integration verification | **조건부 합격** |
| [`analysis_mongo_persistence.md`](2026-06-29/analysis_mongo_persistence.md) | Phase 2A Analysis Mongo persistence 독립 검증 | 조건부 합격 |
| [`analysis_mongo_persistence_hardening.md`](2026-06-29/analysis_mongo_persistence_hardening.md) | Phase 2A Analysis Mongo persistence 보강 독립 재검증 | 합격 |
| [`analysis_phase2a_slice1.md`](2026-06-29/analysis_phase2a_slice1.md) | Phase 2A Slice 1 (analysis domain model + in-memory repository) 독립 검증 | **조건부 합격** |
| [`analysis_phase2a_slice2.md`](2026-06-29/analysis_phase2a_slice2.md) | Phase 2A Slice 2 (taxonomy extraction schema + logical_key derivation) 독립 검증 | **조건부 합격** |
| [`analysis_phase2a_slice3.md`](2026-06-29/analysis_phase2a_slice3.md) | Phase 2A Slice 3 (anchor order idempotency gap closure) 독립 검증 | 합격 |
| [`analysis_phase2a_slice4.md`](2026-06-29/analysis_phase2a_slice4.md) | Phase 2A Slice 4 (extraction runner + anchor-set identity closure) 독립 검증 | 합격 |
| [`analysis_write_error_and_job_state_commits.md`](2026-06-29/analysis_write_error_and_job_state_commits.md) | Analysis write-error and job-state commits verification | **조건부 합격** |

### 2026-06-28

| 기록 | 대상 | 판정 |
|---|---|---|
| [`archive_api_endpoint.md`](2026-06-28/archive_api_endpoint.md) | archive (DELETE) API endpoint 독립 검증 (CRUD API 완성) | 조건부 합격 |
| [`core_sot_fixture.md`](2026-06-28/core_sot_fixture.md) | Core SOT reusable fixture (plan 01 최소 산출물 #7) 검증 | 합격 |
| [`gateway_compose.md`](2026-06-28/gateway_compose.md) | gateway compose 편입 + gateway app shell 독립 검증 | 합격 |
| [`gemma_benchmark_harness.md`](2026-06-28/gemma_benchmark_harness.md) | Gemma benchmark harness (Slice 0 benchmark matrix) 검증 | 합격 |
| [`mongo_adapter.md`](2026-06-28/mongo_adapter.md) | Core SOT MongoDB Adapter 검증 기록 | 합격 |
| [`mongo_adapter_recheck.md`](2026-06-28/mongo_adapter_recheck.md) | Core SOT MongoDB Adapter 재검증 (독립 의심 검증) | 조건부 합격 |
| [`mongo_index_setup.md`](2026-06-28/mongo_index_setup.md) | Mongo index setup hardening (Slice 1 잔여 회귀) 검증 | 합격 |
| [`project_draft_list_get_api.md`](2026-06-28/project_draft_list_get_api.md) | project/draft list/get API 독립 검증 (Core SOT round-trip 완성) | 합격 |
| [`rename_api.md`](2026-06-28/rename_api.md) | project/draft rename API 독립 검증 (CRUD "수정" 완성) | 조건부 합격 |
| [`slice1_docker_and_recheck_closure.md`](2026-06-28/slice1_docker_and_recheck_closure.md) | Slice 1 재검증 폐쇄(R1/R2/R3) + Docker 런타임 독립 검증 | 합격 |
| [`sot_v1_5_archive_readonly.md`](2026-06-28/sot_v1_5_archive_readonly.md) | SoT v1.5 §115 archive 읽기전용 명문화 독립 검증 | 합격 |
| [`source_ref_persistence.md`](2026-06-28/source_ref_persistence.md) | SourceRef persistence 독립 검증 (Slice 1 마무리 / R3 폐쇄) | 합격 |
| [`version_read_api.md`](2026-06-28/version_read_api.md) | version read API 독립 검증 (version/snapshot 재조회 public 표면) | 조건부 합격 |

### 2026-06-26

| 기록 | 대상 | 판정 |
|---|---|---|
| [`core_sot_minimal_skeleton.md`](2026-06-26/core_sot_minimal_skeleton.md) | Slice 1 Core SOT minimal skeleton | 조건부 합격 |

### 2026-06-25

| 기록 | 대상 | 판정 |
|---|---|---|
| [`agent_loop_a2_registry.md`](2026-06-25/agent_loop_a2_registry.md) | AgentLoopRunner A2 (Tool Registry + Strict Arguments + Signature) | 조건부 합격 |
| [`agent_loop_a3_completion_resolution.md`](2026-06-25/agent_loop_a3_completion_resolution.md) | AgentLoopRunner A3 (Completion 판정 + Retry/Budget 합성 + F1 Usage 방어) | 합격 |
| [`agent_loop_provider_runner.md`](2026-06-25/agent_loop_provider_runner.md) | AgentLoopRunner provider composition slice | 합격 |
| [`self_report_parser.md`](2026-06-25/self_report_parser.md) | self-report 종료채널 parser slice | 합격 |
| [`system_contract_sot.md`](2026-06-25/system_contract_sot.md) | System Contract SoT 초안 + A2 I2/I3 보강 | 합격 |

### 2026-06-24

| 기록 | 대상 | 판정 |
|---|---|---|
| [`agent_loop_a1_decision_budget.md`](2026-06-24/agent_loop_a1_decision_budget.md) | AgentLoopRunner A1 (decision + budget 계약 회귀) | 합격 |
| [`completion_criteria_contract.md`](2026-06-24/completion_criteria_contract.md) | flat loop task별 completion criteria 계약 | 조건부 합격 |
| [`flat_loop_tool_registry.md`](2026-06-24/flat_loop_tool_registry.md) | Flat Loop Tool Registry 계약 slice | 합격 |
| [`llm_gateway_f1_f2_closure.md`](2026-06-24/llm_gateway_f1_f2_closure.md) | LLM Gateway Slice 0.1~0.5 F1/F2 폐쇄 delta | 조건부 합격 |
| [`llm_gateway_slice_0_1_to_0_5.md`](2026-06-24/llm_gateway_slice_0_1_to_0_5.md) | LLM Gateway Slice 0.1~0.5 | 조건부 합격 |
| [`llm_gateway_slice_0_6_httpx.md`](2026-06-24/llm_gateway_slice_0_6_httpx.md) | Verification Record — LLM Gateway Slice 0.6 (httpx JSON adapter) | 합격 |
