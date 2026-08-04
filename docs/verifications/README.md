# 독립 검증 기록

이 디렉터리는 **구현자가 아닌 검증자가** 각 슬라이스를 다시 뜯어본 기록이다. 2026-06-24부터
**41일치 · 216건**이 쌓여 있다.

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

## 판정 분포 (2026-08-04 기준)

| 판정 | 건수 | 뜻 |
|---|---|---|
| 합격 | 144 | blocking 결함 없음 |
| **조건부 합격** | **57** | 합격이되 닫아야 할 조건이 있었다 |
| **불합격** | **1** | 핵심 계약 위반으로 다음 슬라이스 진행이 차단됐다 |
| 서술형 | 14 | 초기 기록(판정 문구가 정형화되기 전) |

**조건부 합격이 27%**라는 것이 이 절차가 형식이 아니라는 증거다. 검증이 실제로 지적을 냈고,
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

### 2026-08-04

| 기록 | 대상 | 판정 |
|---|---|---|
| [`slice_8_2b_duplicate_request_lock_recheck.md`](2026-08-04/slice_8_2b_duplicate_request_lock_recheck.md) | Phase 8 Slice 8.2b 재검증 — 독립 검증 FAIL(`c0e9ba9`)의 B1·B2 폐쇄 + H1~H3 보강(`2969a09`)을 뮤테이션·실 Mongo로 확인 | **합격** |
| [`slice_8_3_quota_enforcement.md`](2026-08-04/slice_8_3_quota_enforcement.md) | Phase 8 Slice 8.3 quota 시행(Q1=C·Q1-a=A·Q1-b=A·Q3=E·Q3-a=A·Q4~Q9) — 정산 wrapper·입장 뮤텍스·auth_support 우회를 반증 시도, 2145/1/1921 + 뮤테이션 재실패로 확인 | **합격** |

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
| [`slice1_context_budget_accounting_fix.md`](2026-07-29/slice1_context_budget_accounting_fix.md) | 슬라이스 1 / 컨텍스트 예산 회계 수정 (포인터 렌더링 회계 반영) | — |
| [`slice1a_io_token_breakdown_audit.md`](2026-07-29/slice1a_io_token_breakdown_audit.md) | 슬라이스 1a / 감사에 입력·출력 토큰 분해 남기기 (K-3 관측 1a) | — |
| [`slice1b_context_window_output_cap_reaudit.md`](2026-07-29/slice1b_context_window_output_cap_reaudit.md) | 독립 재검증 — K-3 관측 1b 컨텍스트 창·출력 상한 | — |

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
| [`auth_d8_slice1.md`](2026-07-27/auth_d8_slice1.md) | 인증 D8 슬라이스 1 (User·세션·로그인 API) 2026-07-27 | — |
| [`auth_d8_slice2_owner_id.md`](2026-07-27/auth_d8_slice2_owner_id.md) | 인증 D8-2 (Project.owner_id) 슬라이스 2a·2b 2026-07-27 | — |
| [`stack_bringup_handoff_machine_section.md`](2026-07-27/stack_bringup_handoff_machine_section.md) | 스택 기동 + HANDOFF 머신 구분 절 (2026-07-27) | — |

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
| [`auto-promote-503-partial-envelope.md`](2026-07-24/auto-promote-503-partial-envelope.md) | `auto_promote_job` 503 partial envelope (SoT v1.7.35) | — |
| [`observability-kpi-foundation-increments.md`](2026-07-24/observability-kpi-foundation-increments.md) | 관측 KPI 페이즈 기반 증분 1~3 (per-call 감사 레코드 + 게이트 파생점수) | 합격 |
| [`run_endpoint_storage_503_narrowing.md`](2026-07-24/run_endpoint_storage_503_narrowing.md) | `POST …/analysis/jobs/{id}/run` 저장소 장애 502→503 좁히기 (SoT v1.7.40, (B)) | — |
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
| [`legacy_drafts_500_503_integrity_mapping.md`](2026-07-22/legacy_drafts_500_503_integrity_mapping.md) | 레거시-데이터 `/drafts` 500 근본 수정 (DraftOrderIntegrityError 서브클래스 + 503 매핑) | — |
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
| [`frontend_editor_save.md`](2026-07-16/frontend_editor_save.md) | Frontend editor/save A1 슬라이스 (SoT v1.6.98) | 합격 |
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
| [`worker_compose_increment1_b6.md`](2026-07-09/worker_compose_increment1_b6.md) | (b-6) 증분1 worker compose 서비스 (주장 v1.6.56) | — |

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
| [`analysis_job_state_runner_slice2.md`](2026-06-29/analysis_job_state_runner_slice2.md) | Phase 2A job-state runner integration verification | 합격 |
| [`analysis_mongo_persistence.md`](2026-06-29/analysis_mongo_persistence.md) | Phase 2A Analysis Mongo persistence 독립 검증 | 조건부 합격 |
| [`analysis_mongo_persistence_hardening.md`](2026-06-29/analysis_mongo_persistence_hardening.md) | Phase 2A Analysis Mongo persistence 보강 독립 재검증 | 합격 |
| [`analysis_phase2a_slice1.md`](2026-06-29/analysis_phase2a_slice1.md) | Phase 2A Slice 1 (analysis domain model + in-memory repository) 독립 검증 | — |
| [`analysis_phase2a_slice2.md`](2026-06-29/analysis_phase2a_slice2.md) | Phase 2A Slice 2 (taxonomy extraction schema + logical_key derivation) 독립 검증 | — |
| [`analysis_phase2a_slice3.md`](2026-06-29/analysis_phase2a_slice3.md) | Phase 2A Slice 3 (anchor order idempotency gap closure) 독립 검증 | — |
| [`analysis_phase2a_slice4.md`](2026-06-29/analysis_phase2a_slice4.md) | Phase 2A Slice 4 (extraction runner + anchor-set identity closure) 독립 검증 | — |
| [`analysis_write_error_and_job_state_commits.md`](2026-06-29/analysis_write_error_and_job_state_commits.md) | Analysis write-error and job-state commits verification | 합격 |

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
