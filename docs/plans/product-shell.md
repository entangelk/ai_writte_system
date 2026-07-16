# Product Shell. 프로젝트와 원고 작업 공간

상태: `Draft`  
적용 범위: Phase 1의 프로젝트/원고 저장 위에 구축하고 Phase 2~6의 상태와 기능을 한 작업 공간으로 연결

구현 진행: SoT v1.6.96에서 `/` 프로젝트 목록/생성과 `/projects/:projectId` 원고 목록/생성까지 연결했다. 본문 editor·명시적 version save·version 목록·export가 다음 Product shell slice이며, 전체 수용 기준이 닫힐 때까지 본 문서 상태는 `Draft`를 유지한다.

## 확정된 제품 경계

- 이 제품은 우선 혼자 사용하는 단일 사용자 시스템이다.
- MVP에는 계정, 로그인, 회원가입, 사용자 초대, 역할·권한 관리가 없다.
- 여러 작품의 데이터가 섞이지 않도록 `project_id` 격리는 유지한다.
- 기존 `docs/` 아이디에이션의 `users` 컬렉션은 MVP 필수 계약으로 보지 않는다.

## 목표

내부 AI 파이프라인과 별개로 사용자가 프로젝트를 만들고, 원고를 관리하고, 처리 상태를 확인하고, 완성된 글을 꺼낼 수 있는 최소 제품 껍데기를 제공한다.

## 최소 사용자 표면

### 프로젝트 목록과 기본 CRUD

- 프로젝트 생성
- 프로젝트 목록과 최근 작업 진입
- 프로젝트 상세 조회
- 제목, 설명, 장르, 상태 등 최소 metadata 수정
- 프로젝트 보관 또는 삭제

삭제는 snapshot과 구조화 기억에 영향을 주므로 hard delete를 기본값으로 가정하지 않는다. archive/soft delete/hard delete 정책은 Phase 1과 함께 확정한다.

### 프로젝트 작업 공간

- 현재 원고와 draft/chapter/scene 탐색
- 원고 작성, 수정, 저장과 version 확인
- 분석·색인·검색 준비 상태 확인
- 검토 대기 후보와 Gate finding 진입
- 프로젝트 설정과 WritingBrief 진입

### 제작 관리

“제작 관리”의 MVP 의미는 아직 논의 대상이다. 우선 다음 후보만 검토한다.

- 프로젝트 상태: idea/drafting/revising/completed/archived 등의 최소 단계
- 원고 구조와 작성량/최근 수정 시각
- 분석 대기, 처리 중, 실패, 검토 대기 상태
- chapter/scene 단위 진행 상태 또는 목표

분량 목표, 일정, 태스크 보드, 통계 대시보드는 실제 필요가 확인되기 전까지 확정 범위에 넣지 않는다.

### 원고 내보내기

- 선택한 프로젝트 또는 원고 version을 읽을 수 있는 파일로 내보낸다.
- 원고 본문과 AI 분석 metadata를 기본적으로 분리한다.
- 현재 저장된 어떤 version을 내보냈는지 추적 가능해야 한다.
- 최소 형식은 plain text/Markdown 중에서 결정하고, DOCX/PDF/EPUB은 후속 검토한다.

## 내부 시스템 연결

| 사용자 동작 | 내부 연결 |
|---|---|
| 프로젝트 생성/수정/보관 | Phase 1 project CRUD |
| 원고 저장 | Phase 1 snapshot 후 Phase 2 분석 trigger |
| 처리 상태 확인 | Analysis Job 및 Index Sync 상태 |
| 기억/분석 검토 | Phase 6 Review UI |
| 이어쓰기/수정 요청 | Phase 4 ContextPackage 후 Phase 5 Writing AI |
| 내보내기 | Phase 1의 선택된 draft version 읽기 |

## 산출물

1. 프로젝트 목록/상세/생성/수정/보관 화면과 API 연결
2. 프로젝트 내부 원고 탐색 및 editor shell
3. 분석·색인·검토 상태 표시
4. 원고 version 선택과 export service/UI
5. single-user 로컬 실행 진입점과 기본 설정

## 수용 기준

- 계정 생성 없이 앱을 열어 프로젝트를 만들고 다시 진입할 수 있다.
- 프로젝트 A에서 프로젝트 B의 원고·기억·상태가 보이지 않는다.
- 원고 저장과 비동기 분석 상태를 구분해 표시한다.
- 내보낸 본문이 선택한 draft version과 일치한다.
- AI 분석 정보가 사용자의 원고 본문에 몰래 삽입되지 않는다.
- 보관/삭제 동작이 snapshot과 파생 인덱스 정책을 따른다.

## 착수 전 결정사항

- [ ] desktop/local web 중 첫 실행 형태
- [ ] 프로젝트 metadata의 최소 필드와 상태 literal
- [ ] draft/chapter/scene 계층을 UI와 저장소에서 어디까지 고정할지
- [ ] autosave, 명시적 save, version 생성 UX
- [ ] 제작 관리에서 실제 필요한 진행 정보
- [x] 첫 export 형식: plain text + Markdown(SoT v1.6.14). 파일 구성/DOCX/PDF/EPUB은 후속
- [ ] archive/soft delete/hard delete 정책

## 관련 계획

- [`00-foundations.md`](00-foundations.md)
- [`01-core-sot.md`](01-core-sot.md)
- [`05-writing-ai.md`](05-writing-ai.md)
- [`06-review-ui.md`](06-review-ui.md)
