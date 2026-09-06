# 최종 저장·분석 연동 5차(승격) 재검증 — N1 폐쇄 판정

## Subject metadata

- 날짜: 2026-09-06
- 요청자: 오너("핸드오프 확인해보고 작업 진행해줘 — ① 최종 저장·분석 연동 5차(승격) 재검증")
- 검증자: Claude Code 세션(구현·1~4차 재검증과 별개 세션)
- 대상: 4차 재검증 조건 **N1**(프런트 finality·분석 표시 축 무셀)의 폐쇄 커밋 —
  `f248d8c` *test: lock the frontend finality display axis (N1)*(`DraftEditor.test.tsx` +260줄) ·
  `a875fc0` *docs: record the N1 closure slice and its mutation table*(`it.each` 제목 정정 + work_log 세션 11 변이 표)
- **현행 HEAD 에서 판정한다**: 폐쇄 뒤 같은 축을 `d02837a`(09-02 dogfood 소비 보강 — finalize 중 로컬
  `running` 표시·payload 수렴)와 `61cd7a1`(payload 회귀 fix)이 다시 건드렸다. 4차 판정문이 요구한
  "집중 셀 + 변이"를 **09-01 스냅샷이 아니라 오늘의 코드에서** 재유도해야 잠금이 지금도 사는지 알 수 있다.
- 정본: [`docs/plans/final-save-analysis-decisions.md`](../../plans/final-save-analysis-decisions.md)
  **Resolved**(D1=B·D2=B·D3=B·D4=A·D5=A) §확정 계약 · §"2026-09-02 dogfood 소비 보강". 상위
  [`docs/system-contract-sot.md`](../../system-contract-sot.md) v1.8.35
- 검증 소스: HEAD `abcee31`(검증 착수 시 `6a6fe4a`). **★ 트리는 이 세션 내내 내 것이 아니었다** —
  착수 시 clean 이었으나 변이 도중 **다른 세션(Slice 6 검증 조건 마감)의 미커밋 7파일**이 관측됐고
  (`CHANGELOG.md`·`README.md`·`docs/…/work_log.md`·`docs/plans/README.md`·페이즈·SoT·`typeScale.test.ts`),
  그 세션이 `c0abd1e`·`abcee31` 로 커밋해 다시 clean 이 됐다. 그래서 **원복에 `git checkout` 을 한 번도
  쓰지 않았다** — [`guides/verification.md`](../../guides/verification.md) §"Mutation testing" 의 세 번째 행
  (남의 미커밋 트리) 절차대로 `cp` 백업 + 역방향 Edit + `diff` 바이트 대조만 사용했다.
- 환경: **알파**(WSL2, `/mnt/f`). `frontend/node_modules` 완비, vitest **3.2.7**, `npx tsc` 사용.
  백엔드 전수·test-mongo 는 이 판정의 대상이 아니다(4차가 이미 종료값까지 실측했고, 이번 축은
  프런트 표시면이며 이 머신에서 백엔드·프런트 전수를 겹쳐 돌리지 않는다).

## Scope

1. N1 폐쇄 셀의 **현존과 구성** — 4차가 열거한 요구 분기(①배지 3상태 ②final 버튼 활성/비활성+사유·
   finalize 성공/부분 성공 안내 ③`미실행`·`진행 중` 라벨)에 기명 셀이 실제로 붙어 있는가
2. 구현자 변이 표 **11종의 독립 재유도** — 줄 번호가 드리프트한 현행 코드에서 diff 를 직접 다시 쓰고
   재실패 셀 **짝까지** 대조
3. ★ **검증자 자체 축**(구현자 표에 없는 방향) — 09-02 신설 축·계약 전제·2층 방어·과잉교정
4. 계약 경계 행렬 재전개(확정 계약 제3조 상태 계산 · D3=B 표시 · D5=A 200 얼굴 · 제7조 목록 표시)와
   **빈 칸 탐색**
5. 산출물·타입·프런트 전수 실측
6. 4차 이후의 문서 표류(4차가 올린 N2·N3 의 현재 상태)

## Methodology

- 요약 count 줄을 읽는다(`grep FAILED` 아님). vitest 는 실패를 `×` 줄로 내므로 `grep -E "×|Tests "` 로
  **기명 실패 줄 + 합계**를 함께 본다.
- 변이는 매번 ① Edit 도구로 적용(이 경로에서 `sed -i`·`perl -0pi` 는 파일을 손상시킨다) ② 집중 스위트
  실행 ③ 역방향 Edit 로 원복 ④ `diff <백업> <파일>` 로 **바이트 동일** 확인.
- 백업: `cp frontend/src/drafts/DraftEditor.tsx <scratchpad>/DraftEditor.tsx.bak`(md5 `529ef34c…`),
  전 변이 종료 후 `diff` 무출력 확인.

```bash
cd frontend
npx vitest run src/drafts/DraftEditor.test.tsx     # 집중
npx tsc --noEmit                                    # 타입
npx vitest run                                      # 프런트 전수
```

## Findings

### 1. N1 셀은 현존하고, 4차가 열거한 분기를 전부 덮는다

`frontend/src/drafts/DraftEditor.test.tsx:1889` `describe("최종 저장 표시 축 (확정 계약 제3조·D3=B —
4차 재검증 N1 폐쇄)")` — **14셀**(09-01 의 12 + 09-02 가 더한 in-flight 2). 파일 전체 **68 passed**
(구현자 09-01 기록의 66 과의 차 +2 가 그 두 셀이다 — 수치 불일치가 아니라 증분이 설명된다).

- 배지 3상태 `:1935`·`:1953`·`:1980`, final 버튼 활성/비활성+사유 `:1947-1950`·`:1972-1977`,
  finalize 성공 `:2006`, 부분 성공 `it.each` 2행 `:2099`(job `failed` / **job 없음 + `analysis_error`**
  = D5=A 의 200 얼굴), 분석 라벨 `it.each` 4행 `:2133`, 상한 `:2168`, 보관 `:2183`.
- 양방향 헬퍼 `expectOnly()` `:1899-1904` 가 **기대 문구만 켜져 있고 나머지는 꺼져 있음**을 상태 바
  (`within(status)`) 안에서 단정한다 — 과잉 표시가 통과하지 못한다. 4차가 지적한
  *"코드 확인은 가드가 아니라 관찰이다"* 의 처방으로 정확히 맞는 모양이다.

### 2. 구현자 변이 표 11종 — 현행 코드에서 재유도, 셀 짝까지 일치(1건 증분 설명됨)

09-01 표의 줄 번호는 전부 드리프트했으므로(`:665`→`:669`, `:721`→`:725`, `:215`→`:219`, `:395`→`:398`)
**diff 를 직접 다시 썼다**. 결과는 재실패 셀 이름까지 일치한다.

| 변이 | 이 세션이 적용한 diff(현행 file:line) | 재실패 | 구현자 주장 | 판정 |
|---|---|---|---|---|
| M1 배지 under | `:669` → `{isFinalized ? "최종 저장됨" : "초안"}` | **1**(`marker 보다 최신 version …`) | 1, 같은 셀 | 일치 |
| M2 배지 over | `:669` → `{isFinalized ? "최종 저장 후 수정됨" : "초안"}` | **4**(배지 셀 + 성공 + 부분 성공 2) | 4, 같은 넷 | 일치 |
| M3 버튼 잠금 | `:725` `disabled=` 에서 `isFinalized ||` 제거 | **3**(mount 2 + 성공) | 3 | 일치 |
| M4 버튼 사유 | `:726` `title={undefined}` | **2**(`marker 가 최신 snapshot 과 같으면 …` + 성공) | 2 | 일치 |
| M5 안내 under | `:398` 조건 → `true`(부분 성공도 성공 문구) | **2**(부분 성공 2행) | 2 | 일치 |
| M6 안내 over | `:398` 조건 → `false`(성공도 부분 성공 문구) | **3**(성공 + in-flight 2) | 1(성공) | **증분 설명** — 09-02 신설 2셀이 성공 문구를 release 뒤에 단정한다. 09-01 시점 값 1 은 그때의 사실 |
| M7 라벨 미실행 | `:220` `latestSnapshotId === null ? "필요"` | **1**(`저장본이 없으면 미실행`) | 1 | 일치 |
| M8 라벨 최신성 | `:210` `draft?.analysis_snapshot_id !== latestSnapshotId ||` → `false ||` | **2**(`성공 job 의 snapshot 이 최신과 다르면 필요` + 배지 셀) | 2 | 일치 |
| M9 라벨 진행 중 | `:215-216` `analysisRunning` 에서 draft 기반 `pending`/`running` 제거 | **2**(pending·running 행) | 2 | 일치 |
| M10 상한 | `:725` `disabled=` 에서 `overLimit` 제거 | **1**(상한 셀) | 1 | 일치 |
| M11 보관 | `:721` `{!readOnly && (` → `{true && (` | **1**(보관 셀) | 1 | 일치 |

구현자 표는 **정직하다** — 유일한 차이 M6 는 표가 쓰인 뒤 셀이 늘어난 결과이고, 방향(성공 셀을 문다)은
그대로다.

### 3. ★ 검증자 자체 축 4종 — 셋이 물지 않았다

| 변이 | 무엇을 노렸나 | 결과 |
|---|---|---|
| **MV-A** `:374` `setAnalysisStatus("running")` 삭제 | 09-02 가 더한 in-flight 표시가 그 두 셀에 실제로 잠겨 있는가 | **2 failed**(in-flight 2셀) — 잠겨 있다 |
| **MV-B** `:379` `crypto.randomUUID()` → 상수 `"fixed-finalize-key"` | **매 클릭 새 키**라는 전제 | **68 passed — 무물림** |
| **MV-C** `:368-370` finalize() 조기 반환에서 `readOnly`·`isFinalized`·`overLimit` 제거 | 버튼 밖의 2층 방어 | **68 passed — 무물림**(흡수층 = 비활성 버튼이라 DOM 에서 클릭이 안 난다. 2층 방어가 설계대로 작동하되 **바깥 층만 잠겨 있다**) |
| **MV-D** `:735` 일반 저장 버튼 `disabled=` 에 `isFinalized ||` 추가 | 확정 계약 *"final marker 뒤의 일반 저장은 허용한다"* 의 **과잉교정 방향** | **68 passed 무물림 · 프런트 전수 418 passed 로도 무물림** |

- **MV-B 의 뜻**: 4차 기록이 N3(같은 키 재전송의 활동 행 중복)를 *"UI 는 매 클릭 `crypto.randomUUID()`
  키를 만들므로 도달 불가"* 로 분류했다. 그 분류의 전제가 **어떤 셀에도 안 걸려 있다.** 더해 S-1 계약
  (SoT v1.8.32)에서 정산된 키의 재제출은 실행 전 409 이므로, 상수 키는 *"finalize 실패 뒤 재시도"*
  경로를 조용히 409 로 바꾼다 — 화면에는 일반 오류로 보인다.
- **MV-D 의 뜻**: 확정 계약은 *"final marker 뒤의 일반 저장은 허용하되 분석을 자동으로 만들지 않는다"*
  라고 못 박고, 백엔드는 그 분기를 프로브 S4(`repro_final_save_flow.py:196-202` — 200·marker 보존·
  `analysis_status` null)로 잠근다. **프런트 쪽 같은 분기는 잠금이 없다.** 그리고 이 분기는 표시 축의
  전제이기도 하다 — 배지 세 번째 상태(`최종 저장 후 수정됨`)에 **사용자가 도달하는 유일한 경로**가
  final 뒤의 일반 저장이다. `:1980` 셀은 그 상태를 픽스처로 *마운트*할 뿐 **저장으로 전이시키지 않는다.**
  따라서 "final 뒤에는 저장도 막자"는 그럴듯한 과잉교정이 들어오면 실앱에서 세 번째 배지가 영원히
  도달 불가가 되는데 **418셀 전부가 초록이다.**

### 4. 경계 행렬 — 채워진 칸과 빈 칸

| 계약 분기 | 정본 | 잠금 |
|---|---|---|
| marker 없음 → `초안` | 제3조 | `:1935` (M1·M2) |
| marker == 최신 snapshot → `최종 저장됨` | 제3조 | `:1953`·`:2006` (M2·M4) |
| marker 보다 최신 version → `최종 저장 후 수정됨` | 제3조 | `:1980` (M1·M8) |
| 저장본 없음 → `분석 미실행` | 제3조 | `:2133` 1행 (M7) |
| 최신 snapshot job `pending`/`running` → `진행 중` | 제3조 | `:2133` 2·3행 (M9) |
| 성공 job 의 snapshot ≠ 최신 → `필요`(시간 아님) | 제3조 | `:2133` 4행·`:1980` (M8) |
| 최신 snapshot 성공 → `완료` | 제3조 | `:2006` (M2 대칭) |
| final 버튼 Scene당 한 번(사유 문언) | D3=B | `:1953`·`:2006` (M3·M4) |
| finalize 성공/부분 성공 안내 2종 | D3=B | `:2006`·`:2099` (M5·M6) |
| 분석 job 없음 + `analysis_error` 도 200 얼굴 | D5=A | `:2099` 2행 |
| 요청 중 `진행 중` 표시 | 09-02 보강 | `:2048`·`:2074` (MV-A) |
| 4000자 상한이 final 도 잠근다 | 확정 계약 | `:2168` (M10) |
| 보관 원고에는 버튼 없음 | 확정 계약 | `:2183` (M11) |
| Scene 목록도 같은 판정을 보인다 | 제7조 | `DraftList.tsx:10-25` + `DraftList.test.tsx:70`·`:98` |
| **final 뒤 일반 저장은 허용된다(should NOT block)** | 확정 계약 | **없음 — MV-D** |

### 5. N2 는 코드·정본에서 이미 닫혔는데 HANDOFF 만 안 따라왔다

4차가 오너 판정으로 올린 N2(Scene 목록이 finality·분석을 안 읽는다)는 정본 브리프
§"2026-09-02 dogfood 소비 보강"이 *"이로써 4차 재검증 N2 를 '배지 구현' 방향으로 닫았다"* 라고 명시하고,
구현도 실재한다 — [`DraftList.tsx:10-18`](../../../frontend/src/drafts/DraftList.tsx) `sceneAnalysisLabel`
(`current` = `analysis_snapshot_id === latest_snapshot_id` 동일성 판정 — 제3조와 같은 규칙),
[`:20-25`](../../../frontend/src/drafts/DraftList.tsx) `sceneFinalityLabel`, 표시 `:296`·`:298`, 셀 2개
(`DraftList.test.tsx:70` 구분 · `:98` "완료로 오인하지 않는다").
그런데 [`HANDOFF.md`](../../../HANDOFF.md) "⚠️ 오너 결정이 있어야 움직이는 것" 표에는 **N2 행이 그대로
남아 있다.** 정본이 둘로 갈린 것이 아니라 인계 문서가 낡은 것이다(정본은 브리프). 이 세션이 그 행을
걷는다 — N3 행은 여전히 열려 있으므로 남긴다.

### 6. 실측

| 표면 | 값 |
|---|---|
| `DraftEditor.test.tsx` 집중 | **68 passed**, rc=0 |
| 프런트 전수 | **418 passed / 35 files**, rc=0, 93.97s |
| `npx tsc --noEmit` | rc=0 |
| 변이 원복 | 전 회차 `diff` **바이트 동일**, 종료 시 `git status --short` 공백 |

프런트 전수는 다른 세션이 `typeScale.test.ts` 를 커밋한 **뒤**의 값이다(그 커밋 전 측정도 418 로 동일).

## Issues / Risks

### Blocking (조건)

1. **B1 — 확정 계약 *"final marker 뒤의 일반 저장은 허용한다"* 의 프런트 과잉교정 방향이 무가드다.**
   MV-D(일반 저장 버튼에 `isFinalized` 추가)가 **프런트 전수 418 전부 초록**으로 통과한다. 이 분기는
   백엔드에서는 프로브 S4 가 잠그고 있어 **한쪽만 잠긴 계약**이고, 표시 축의 세 번째 배지 상태에
   사용자가 도달하는 유일한 경로다. 처방은 셀 1개 — final 성공 직후 본문을 고쳐 **저장 버튼이 활성이고
   저장이 실제로 나가며 배지가 `최종 저장됨` → `최종 저장 후 수정됨` 으로 전이**함을 단정(같은 셀이
   under 방향으로는 배지 전이를, over 방향으로는 저장 차단을 문다).

### Hardening (비차단)

- **H1 — finalize 키의 "매 클릭 새 UUID" 전제에 셀이 없다**(MV-B). 4차가 N3 를 *도달 불가*로 분류한
  근거이자, 실패 뒤 재시도가 409 로 굳지 않게 하는 값이다. 성공 셀에 `sent.idempotency_key` 가
  **두 요청에서 서로 다름**을 더하면 잠긴다.
- **H2 — finalize() 함수 층 가드(`readOnly`·`isFinalized`·`overLimit`)는 무가드다**(MV-C). 흡수층은
  비활성 버튼이므로 설계된 2층 방어가 맞지만, 바깥 층이 무너지면 안쪽도 함께 조용해진다. 잠그려면
  버튼이 아니라 함수를 직접 부르는 셀이 필요하다 — 지금 단계에서 값이 크지 않아 비차단으로 둔다.
- **H3 — HANDOFF 의 N2 행이 낡았다**(§5). 이 세션이 정정한다.
- 4차 Outstanding 의 "다음 전수 기대값 2668/4/3115" 는 그 시점의 사실이고 현행 기준선(2891/1/3792)과
  무관하다 — 기록 대조 시 혼동 주의.

## Verdict

**조건부 합격** — 조건: 확정 계약 *"final marker 뒤의 일반 저장은 허용한다"* 의 프런트 과잉교정 방향
무가드(**B1**) 폐쇄.

4차의 조건 **N1 자체는 폐쇄를 확인했다** — 4차가 열거한 요구 분기(배지 3상태·final 버튼과 사유·
finalize 성공/부분 성공 안내·`미실행`/`진행 중`)에 전부 기명 셀이 붙었고, 구현자 변이 11종을 현행
코드에서 독립 재유도해 **셀 짝까지 일치**했으며(M6 의 1→3 은 09-02 신설 셀로 설명된다), 09-02 가 더한
in-flight 축도 MV-A 로 잠금을 확인했다. 그럼에도 합격으로 올리지 못하는 이유는 **같은 표시 축의 계약
분기 하나(final 뒤 일반 저장 허용)가 검증자 변이로 무가드임이 드러났기 때문**이다 — 이 저장소의 규칙은
"계약 요구 분기는 should-fire 와 should-NOT-fire 양쪽 모두 기명 셀"이고, 초록 막대는 그 규칙을 대신하지
못한다. 행동 자체는 계약과 일치하므로(코드·백엔드 프로브 S4) **결함이 아니라 잠금 공백**이고, 셀 하나로
닫힌다.

## Outstanding items

- **B1 폐쇄 셀 1개**(위 처방). 폐쇄 뒤 6차는 그 셀 + MV-D 재적용만으로 승격 판정이 가능하다.
- **H1·H2** 는 오너가 값을 인정하면 각각 셀 1줄·1개.
- **N3**(같은 finalize 키 재전송의 활동 행 중복)는 **여전히 오너 결정 대기**다. H1 을 닫으면 그
  "도달 불가" 분류의 전제가 잠긴다.
- N2 는 닫혔다(§5) — HANDOFF 행 정정은 이 세션이 함께 시행한다.
- 백엔드 전수는 이 판정에서 돌리지 않았다(프런트 표시 축). 이 기록 등재로 `test_docs_indexes` 의
  건수·분포 주장이 +1 되며, 그 확인은 등재 직후 단독 실행으로 한다.

## Reproduction

```bash
cd frontend
npx vitest run src/drafts/DraftEditor.test.tsx     # 68 passed
npx tsc --noEmit                                   # rc=0
npx vitest run                                     # 418 passed / 35 files

# 변이(각 회차: 백업 → Edit 적용 → 실행 → 역방향 Edit → diff 로 바이트 대조)
cp src/drafts/DraftEditor.tsx /tmp/DraftEditor.bak
#   B1 재현: src/drafts/DraftEditor.tsx 의 일반 저장 버튼(현행 :735)
#   disabled={!dirty || saving || selecting || overLimit}
#   → disabled={isFinalized || !dirty || saving || selecting || overLimit}
npx vitest run                                     # 418 passed — 아무 셀도 물지 않는다
diff /tmp/DraftEditor.bak src/drafts/DraftEditor.tsx   # 원복 후 무출력
```
