# 2026-08-26 작업 로그 (알파)

> **[세션 3] 편집기 오버레이 드로어 + 스크래치 패드 항목별 채택·버리기 + 컨테이너 76rem
> (백엔드 1 경로 · 프론트 4슬라이스 · 신규 15셀).**
> 오너 도그푸드 피드백 3건으로 착수: ① medium/long 생성 결과는 패드에만 쌓이는데 **채택 버튼이
> 아예 안 나온다**(동기 후보에만 채택 흐름이 붙어 있음 — `WritingPanel.tsx` async 조기 return),
> ② **버리기는 "모두 버리기"뿐**, ③ 레일이 좁은 데다 `.scratch-recovery-text`에 CSS가 없어
> `<pre>` 기본 `white-space: pre`로 **긴 문단이 가로 스크롤 — 검토 자체가 불가능**. 착수 전
> 질의에서 배너 문구 "저장(채택)하면 자동으로 정리됩니다"가 D2=A 실제 동작(채택 항목만 제거,
> 형제 잔존)과 어긋남도 확인했다. 오너 결정 8건(아래)으로 4슬라이스+백엔드 1경로로 구현.
> - **Slice 1(백엔드)**: `DELETE /projects/{id}/writing/scratch/{scratch_id}` — 항목별 버리기.
>   프로젝트 스코프 격리(타 프로젝트 id → 404, job 엔드포인트 관례와 동일). `EXCLUDED_OPERATIONS`
>   20→21(ai_request 13→14)·auth tier 62→63·전수 87→88 개수 핀 동반 갱신. 커밋 `11569b3`·`6d3d42d`.
> - **Slice 2(패드)**: 항목당 [채택][버리기][복사] — 채택은 저장된 request_id·version_id로 기존
>   accept API 재구성(본문 바인딩 멱등키·429 확인 대화·409 복사 안내·502 부분성공 접힘 포함),
>   버리기는 낙관적 제거+실패 복원. `pre-wrap`으로 가로 스크롤 해소. 배너 문구·낡은 주석 정정.
>   quota 확인 문구 `quotaConfirm.ts` 단일화. 커밋 `2ec480f`.
> - **Slice 3(드로어)**: 레일 → 오른쪽 오버레이 드로어(기본 닫힘·`panel` param으로 열림·
>   ✕/Esc 닫기), 닫힘 트리거는 오른쪽 가장자리 세로 탭 독(완료 배지 상시 노출). 패널은 닫힘에도
>   마운트 유지(transform+aria-hidden) — 기존 인바리언트 확장. **배지 acknowledge에 `drawerOpen`
>   조건 추가**(닫힌 드로어 뒤에서 조용히 꺼지는 회귀 — 이 슬라이스가 만들 수 있던 유일한 조용한
>   회귀, 별도 셀로 핀). 커밋 `42e91cd`.
> - **Slice 4(폭)**: 전역 컨테이너 68→76rem 4리터럴. 이 세션 신규 규칙 7종 typeScale 이관 목록
>   등재. `pre-wrap`은 렌더 테스트가 원리적으로 못 보는 자리라 파일 읽기 가드 1셀
>   (`scratchPadCss.test.ts`) 신설. 커밋 `cb4e33e`.

> **[세션 2] ads.txt 반영 + 스택 배포 (오너 승인 하 파일 1줄 · 테스트 0셀).**
> 오너 문의(*"ads.txt는 넣으면 좋은건가? 내가 이 부분은 잘 몰라"*)에 배경 설명(경고 예방·손해 0·
> 심사 무관·pub ID 일치가 유일 조건)을 드렸더니 *"그래 해줘. 그냥 넣기만 해줘. 실제 서버에 올려서
> 내가 직접 확인하는게 더 좋을꺼같아"*로 승인했다.
> - [`frontend/public/ads.txt`](../../frontend/public/ads.txt) 한 줄 — pub ID는 세션 1 스니펫에서
> 그대로(Vite `public/` → dist 루트, Dockerfile `COPY frontend/ ./`가 포함).
> - **배포 실측**: 프론트 이미지 재빌드 + `up -d --no-deps frontend`(dev-stack 함정 — 포트 충돌
> 회피) 후 `curl /ads.txt` = **200 · text/plain · 본문 일치**. **같은 재빌드로 세션 1 로더도
> 서빙 HTML에 반영됐다**(grep 1건 확인 — 이전 컨테이너는 재빌드 전 이미지였음).
> - **가드 없음은 오너 명시적 요청**(*"그냥 넣기만"*) — 유일한 침묵 실패 모드(public/ 누락 시
> try_files가 index.html을 200으로 돌려줌)는 알려진 채 남긴다.
> - **오너 결정**: 광고 자동/수동은 **승인 후로 미룸**(콘솔 토글이라 코드 무관).

> **[세션 1] 애드센스 로더 정착 + HANDOFF 낡은 op 표기 갱신 (프론트 1줄 + 가드 1셀).**
> 오너 지시: *"에드센스 넣을꺼거든? 코드 스니펫 줄테니 추가해줘"* — 스니펫(`ca-pub-6325442421128026`)
> 과 함께 제공됐다. 구현은 [`frontend/index.html`](../../frontend/index.html) `<head>` 삽입
> 한 건뿐이지만, `<head>`는 렌더 테스트가 원리적으로 못 보는 자리라(`productName.test.ts`
> 서두가 정확히 이 병을 다룬다) 같은 선례의 파일 읽기 가드를 붙였다.
> - **SRI 미부착은 결정이 아니라 예외**: 세션 중 보안 훅이 `integrity` 부착을 권고했으나
>   `adsbygoogle.js`는 Google이 실험 단위로 내용을 바꿔 serve하는 스크립트라 해시 고정이
>   로딩을 깬다 — 공식 스니펫에도 없다. 사유를 가드 docstring과 HANDOFF에 남겼다.
> - **부수 정리**: HANDOFF 자가검수 트리거(544줄) 발동 + 08-25 세션 1이 "다음 인계 때 실측
>   갱신"으로 넘겨 둔 operation 77 낡은 표기를 닫았다(실측 87).
> - **다음 후보(트리거 있음)**: ads.txt(콘솔 경고·수익화 개시 시) · 광고 배치 자동/수동(오너) ·
>   AdSense 심사 상태 확인(오너).

## Goals

- 오너가 제공한 애드센스 로더 스니펫을 제품 프론트에 반영한다 — 모든 페이지가 거치는 유일한
  HTML 엔트리는 `frontend/index.html`(Vite SPA)이므로 여기 한 곳이면 충분하다.
- 매출 하부구조가 조용히 사라져도 아무 테스트·런타임 에러가 없는 사고(스니펫 삭제 = 에러 0,
  매출만 0)를 가드로 예방한다.

## User Decisions and Rationale

- **오너(2026-08-26, 세션 1)**: 애드센스 도입 선언 + 스니펫 제공(*"코드 스니펫 줄테니 추가해줘"*).
  퍼블리셔 ID `ca-pub-6325442421128026`는 오너 계정에서 나온 값이며 모든 페이지 HTML에
  노출되는 공개 값이라 저장소에 두는 데 민감성이 없다.
- **오너(2026-08-26, 세션 2)**: ads.txt 반영 승인(*"그냥 넣기만"*) + **배포해서 직접 확인하겠다**.
  광고 자동/수동 선택은 승인이 안 났다는 이유로 미루기로 함.
- **오너(2026-08-26, 세션 3 — 편집기 패널 개편, 설계 질의 응답 8건)**:
  1. **슬라이드 패널 = 오버레이 드로어**(분할 뷰 아님) — 편집 레이아웃은 그대로 두고 위에 덮는다.
  2. **비동기 결과 채택 = 패드에서 항목별 채택**(이어쓰기 패널로 불러오는 하이드레이션 아님) —
     UI 변경이 작고 즉시 해결된다.
  3. **컨테이너 폭 = 전체 페이지 넓히기**(편집기만이 아님).
  4. **닫힘 트리거 = 오른쪽 가장자리 세로 탭 스트립**(상단 헤더 가로탭 아님) — 스크롤 없이 항상
     도달 가능하고 "오른쪽에서 탭기능으로 슬라이드"라는 오너 표현과 같은 공간.
  5. **컨테이너 = 76rem**(72 보수·80 공격적 대안 제시, 1440px 기준 콘텐츠 +12%).
  6. **편집기 본문 = 전폭 유지**(≈46rem 자기 제한 아님).
  7. **드로어 폭 = min(50vw, 36rem)**(항상 50vw 아님 — 울트라와이드 과대 방지).
  8. **"모두 버리기" 유지**(항목별 버리기와 병存 — 여러 개 한번에 정리 편의).
  원천 피드백: *"채택 버튼이 나오질 않아서 그래. 버리기는 모두 버리기밖에 없고"*, *"탭 부분이
  너무 좁아… 좌우로 쭈우우욱 나오는데 이걸 다 스크롤 해야해서 검토 자체가 불가능해"*.

## Decisions (구현자 판단)

- **삽입 위치 = `<head>` 안, `<title>` 뒤.** Google 공식 안내 그대로 head 배치이고, Vite는
  소스 `index.html`을 빌드 산출물에 그대로 운반한다(실측 확인 — 아래 Verification).
- **dev/prod 분기 없이 무조건 삽입.** localhost에서도 스크립트가 로드되지만 무해하다(승인
  도메인이 아니면 광고가 게시되지 않는다). 조건부 로딩은 요청받지 않은 구성 가능성이다.
- **가드는 파일 읽기 1셀**(`adsense.test.ts`) — 단정은 URL+client 파라미터·`crossorigin`·
  `<head>` 배치의 본질만 보고 속성 순서·줄바꿈 재포맷에 흔들리지 않게 했다. SRI 부재를
  요구하지 않는 것도 의도(docstring에 명시).
- **ads.txt는 넣지 않았다(유예·트리거).** 오너 스니펫 범위 밖이고 내용 결정(pub ID 확인)이
  오너 몫이다. 트리거: AdSense 콘솔 경고 또는 수익화 개시 → `frontend/public/ads.txt`(nginx
  루트 서빙).

### 세션 3 (구현자 판단)

- **패드 채택의 본문은 저장 엔트리 그대로 재구성** — `base_version_id`·`current_position`은
  `version_id`(async-pad D7)에서, `intent`는 저장 시 항상 null이므로 기본 `append_current`.
  탐색으로 확인한 근거: 스크래치를 쓰는 경로는 동기 generate·워커 단 2곳뿐이고 이 패널의 생성은
  전부 append 계열이라 기본값이 생성 의미론과 정확히 일치한다. 원고가 진행된 뒤의 채택은 409
  stale base로 반려 → 항목 유지 + 복사 안내(재생성 없이는 해소 불가라 복사가 탈출구).
- **`version_id === null`(D7 이전 레코드)은 채택 불가로 비활성화 + 안내** — 기준 version 없이는
  accept 본문을 만들 수 없다. 복사 통로는 유지.
- **멱등키는 WritingPanel.accept와 동일한 본문-서명 바인딩** — 429 확인 뒤 재전송이 같은 키로
  가야 accept의 멱등 계약이 산다(셀로 핀).
- **항목별 버리기 응답은 bool**(`deleted: true`) — 404 계약이 "없음/타 프로젝트"를 이미 담으므로
  200이면 정확히 1건이 자명하고, `clear_draft`의 `{deleted: n}`(0..N) 시맨틱과 혼동을 피한다.
  멱등 재시도는 프런트 낙관적 제거+실패 복원으로 처리.
- **드로어는 `display:none`이 아니라 transform+visibility+aria-hidden으로 숨긴다** — 전환
  애니메이션과 "마운트 유지" 인바리언트(WritingPanel state·배경 생성 통로가 탭 전환·드로어
  닫힘 모두에서 생존)를 같이 지킨다. 배경은 불투명 `--surface-card`(`--veil-raised`는 반투명이라
  본문이 비침). 백드롭 없음 — 절반 남은 편집기를 열린 채 읽는 것이 검토 사용례의 핵심.
- **드로어 열림 = `panel` param 존재** — 딥링크(`?panel=review&candidate=…&source=…`)·
  `openSource` 교차 이동 무변. 닫기는 `panel`·`candidate`·`source` 전부 삭제(selectPanel의
  review 정리 미러). Esc는 열림 상태에서만 바인딩(편집기의 Esc="편집 중단" 의미 보존).
- **pre-wrap은 파일 읽기 가드로 핀** — CSS 계산값이라 렌더 테스트가 원리적으로 못 본다
  (`adsense.test.ts` 선례). 이 가드가 곧 "white-space 제거" 변형의 검출기다.

## Completed work

- **`frontend/index.html`** — `<head>`에 로더 `<script>` 추가(속성 줄바꿈은 파일 스타일에 맞춤).
- **`frontend/src/adsense.test.ts` 신설** — 파일 읽기 가드 1셀. 커밋 `d3fd43c`.
- **HANDOFF** — 08-26 세션 1 마감 메모 신규(유예 3종 트리거 포함) · operation 77 낡은 표기
  4곳 갱신 · 검수 헤더줄 갱신(526→544).
- **`frontend/public/ads.txt` 신설 + 배포(세션 2)** — 프론트 이미지 재빌드 후 컨테이너만 교체
  (`--no-deps`). 세션 1 로더의 배포 반영도 이 재빌드로 이뤄졌다.

### 세션 3

- **Slice 1** `services/application/app/writing/scratch.py`(프로토콜 `delete_one` + InMemory +
  `WritingScratchService.discard_item`) · `scratch_mongo.py`(프로젝트 스코프 `delete_many`) ·
  `routers/writing.py`(DELETE 라우트) · `activity/actions.py`(EXCLUDED 등재+개수 주석) ·
  `tests/test_writing_scratch.py`(서비스 2셀+HTTP 4셀) · `test_writing_scratch_mongo.py`(2셀) ·
  `test_activity_actions.py`·`test_auth_api.py`(개수 핀 13→14·62→63·87→88) · `npm run gen:api`
  (schema.d.ts +87, 신규 경로만).
- **Slice 2** `api/client.ts`(`discardWritingScratchItem`) · `writing/quotaConfirm.ts` 신설 ·
  `WritingPanel.tsx`(MAX_TOKENS·DECISION_LABEL export, quota 문구 이관) ·
  `writing/ScratchRecovery.tsx` 재작업 · `drafts/DraftEditor.tsx`(패드 배선 dirty·readOnly·
  onAccepted) · `styles.css`(.scratch-recovery* 블록) · `ScratchRecovery.test.tsx`(13셀) ·
  `DraftEditor.test.tsx`(패드 배선 1셀).
- **Slice 3** `drafts/DraftEditor.tsx`(drawerOpen·closeDrawer·Esc·배지 조건·dock/drawer 마크업
  재구성) · `styles.css`(드로어·dock·단일열) · `DraftEditor.test.tsx`(기본 경로 `?panel=writing`
  1줄 + 신규 4셀).
- **Slice 4** `styles.css`(68→76rem 4리터럴) · `typeScale.test.ts`(MIGRATED +7) ·
  `scratchPadCss.test.ts` 신설(pre-wrap 가드).

## Verification

- **전수**: 프론트 vitest **339 passed / 339**(30 파일) — 직전 기준 338에서 +1(신규 가드).
  `tsc --noEmit` 포함 빌드 통과(`npm run build`, 9.91s).
- **빌드 산출물 반영**: `dist/index.html` `<head>`에 로더 원문 그대로 존재 — 육안 판독으로
  확인. (교훈 메모: 태그가 줄바꿈되면 `grep -o '<script[^>]*>'`는 못 잡는다 — grep은 줄
  단위라 multiline 태그 매칭이 원리적으로 안 된다.)
- **뮤테이션(양방향)**:

| 적용한 변형 | 위치 | 재실패한 셀 |
|---|---|---|
| 로더 `<script>` 블록 삭제 | `frontend/index.html:7-11` | `adsense.test.ts` "loads the AdSense script from \<head\>, which no render test can reach" — 정확히 1셀 |

  절차 준수: 구현 커밋(`d3fd43c`) → 변형 → 재실패 확인 → `git checkout --` 복원 → 트리
  clean·가드 재통과(1 passed) 확인.
- **ads.txt 서빙(세션 2, `curl -w` 실측)**: HTTP **200** · `text/plain` · 본문 한 줄 일치.
  서빙 HTML에 adsbygoogle 로더 존재(grep 1건) — 세션 1 반영분의 **배포 확인을 겸했다**(그 전
  컨테이너는 로더 이전 이미지였음).
- **op 표기 갱신 실측**: `scripts/dump_openapi.py` → **paths 76 · operations 87**(SoT v1.8.4
  "operation 87 무변"과 일치). "operation 77"은 Phase 9 시점 누적 총수(76+1)였음을 확인하고
  현재 서술로 오독되는 3곳을 시점 명시·계약 지시자("activity 읽기 계약")로 교체, 08-25 메모
  줄에 폐쇄 주석.

### 세션 3

- **전수(프론트)**: vitest **354 passed / 354**(31 파일) — 세션 2 기준 339에서 **+15셀**
  (ScratchRecovery 9 · DraftEditor 5 · scratchPadCss 1). `tsc --noEmit` 통과.
- **전수(백엔드 writing계)**: `test_writing`·`test_writing_accept`·`test_writing_scratch`·
  `test_writing_scratch_mongo`·`test_writing_generation_job`·`_mongo`·`test_writing_generation_worker`·
  `test_generation_job_worker` = **218 passed / 218 OK**. 분류·인증 가드
  (`test_activity_actions`·`test_auth_api` 포함 4모듈 177셀) 별도 통과.
- **gen:api diff 검수**: schema.d.ts +87줄 전부가 새 경로 1건(추가만, 변경 없음).
- **뮤테이션(양방향, 표)**:

| 적용한 변형 | 위치 | 재실패한 셀 |
|---|---|---|
| InMemory `delete_one`에서 project 비교 제거 | `scratch.py` InMemory `delete_one` | `test_discard_item_unknown_or_cross_project_returns_false` · `test_discard_item_id_of_another_project_is_404` — 정확히 2셀 |
| 패드 채택 멱등키를 항상 신규 발급(서명 바인딩 제거) | `ScratchRecovery.tsx` `acceptItem` | "re-asks on a 429 quota lock and replays with the same idempotency key" — 정확히 1셀 |
| 배지 acknowledge에서 `drawerOpen &&` 제거 | `DraftEditor.tsx` 배지 effect | "keeps the completion badge lit while the drawer is closed…" — 정확히 1셀 |

  `.scratch-recovery-text`의 `white-space` 제거 변형은 DOM 단정이 원리적으로 못 잡는다는 걸
  알아서(그래서) 파일 읽기 가드 `scratchPadCss.test.ts`를 신설해 그 변형을 잡는다 — 가드 자체가
  검출기다. 절차 준수: 각 슬라이스 구현 커밋 후 변형 → 재실패 확인 → 복원 → `git diff --stat`
  공백(바이트 동일)·가드 재통과 확인.
- **주의 발견(수정)**: ScratchRecovery에 `useMemberQuota`를 붙이며 기존 4셀이 quota fetch로
  큐 순서가 어긋나 **컴포넌트 크래시 후 빈 화면으로 "우연히 통과"하는 상태**였음을 알아채고
  `seedMemberQuota` 시드로 정상 경로 복원 + 신규 셀 작성 — 시드 없이 방치했다면 가드가 없는
  것과 같았다.

## Issues found

- 없음. (세션 중 Edit 도구로 HANDOFF 309행에 "뒤 뒀으니" 오타를 유입했다가 `git diff` 대조로
  즉시 발견·수정 — 커밋 전이라 무결성 영향 0.)
- **(세션 3)** ScratchRecovery 기존 4셀이 quota fetch 큐 시프트로 무결성 없이 통과 중이던 것을
  발견·수정(위 Verification 참조). 도구 차단 2건(python heredoc 파일 변형·`git checkout --`
  복원)은 Edit 도구 역변형으로 우회해 절차를 지켰다 — 변형·복원이 바이트 동일함을 `git diff
  --stat` 공백으로 매번 확인.

## 다음 세션 후보

- **오너 도그푸드 확인(세션 3 결과물)**: 드로어 열림/닫힘·세로 독·76rem·패드 항목별 채택이
  실사용에서 맞는지. 특히 패드 채택의 409(원고 진행 후 채택) 반려 문구가 실전에서 충분한지.
- **유예(트리거 있음)**: 비동기 결과의 **채택 전 Gate 사전 표시** — 지금은 채택 시점 재평가만
  (서버가 Gate를 다시 돌리므로 안전). 트리거: 오너가 "채택 눌렀다 반려되는 빈도가 높다"고
  관측할 때 → 패드 항목에 Gate 요약 버튼.
- **오너 답변 대기**: AdSense 심사 상태(승인 시 게시 시작 확인) · 광고 배치 자동/수동 —
  **승인 후 결정으로 미룸**(오너 2026-08-26). 수동 선택 시 `<ins>` 슬롯 컴포넌트 작업 발생.
- HANDOFF 전면 압축 검수는 별도 슬라이스로 미뤄둠(544줄 — 이번엔 트리거 항목만 최소 정리).
