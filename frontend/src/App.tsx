import { Suspense, lazy } from "react";
import { Link, Navigate, Route, Routes, useParams } from "react-router";
import { AuthGate, useAuthenticatedUser } from "./auth/AuthGate";
import { DraftList } from "./drafts/DraftList";
import { DraftEditor } from "./drafts/DraftEditor";
import { ProjectList } from "./projects/ProjectList";
import { ProjectSettingsPage } from "./projects/ProjectSettingsPage";
import { AccessLogPage } from "./projects/AccessLogPage";
import { LegalPage } from "./legal/LegalPage";
import { PersonalHubPage } from "./me/PersonalHubPage";
import { SceneNotesPage } from "./notes/SceneNotesPage";
import { ReviewInbox } from "./review/ReviewInbox";
import { ReviewInboxDetail } from "./review/ReviewInboxDetail";

// Split out of the main bundle: this is the only screen that pulls in the chart
// library, and it is an occasional operations view. Loading it eagerly nearly
// doubled the entry bundle (399 kB → 786 kB), which every writing session would
// have paid for a page most sessions never open.
const ObservabilityDashboard = lazy(async () => ({
  default: (await import("./observability/ObservabilityDashboard"))
    .ObservabilityDashboard,
}));
const AdminConsole = lazy(async () => ({
  default: (await import("./admin/AdminConsole")).AdminConsole,
}));
const AdminUserDetail = lazy(async () => ({
  default: (await import("./admin/AdminUserDetail")).AdminUserDetail,
}));

/**
 * 라우트는 **두 구간**이다 (브리프 `landing-page-scope`, 착수 순서 ②).
 *
 * 약관·방침은 **가입하기 전에** 읽어야 하는 문서라 세션 확인 앞에 선다 — 그래서
 * `AuthGate` 가 앱 전체가 아니라 **보호 구간만** 감싼다(9.2 P6=ⓐ 가 "자리만
 * 확보"라고 예고한 모양이다). 보호 구간은 `path="*"` 한 자리로 남아 있어
 * `AuthGate` 는 이동할 때마다 다시 마운트되지 않는다 — 세션 확인이 라우트마다
 * 되풀이되면 화면마다 "세션을 확인하는 중…" 이 번쩍인다.
 *
 * **공개 라우트가 느는 것은 API 가 느는 것이 아니다** — 공개 API 표면은 그대로
 * `/health`·`/auth/login`·`/auth/signup`·`/auth/logout` 넷이다.
 */
export function App() {
  return (
    <Routes>
      <Route path="/terms" element={<LegalPage name="terms" />} />
      <Route path="/privacy" element={<LegalPage name="privacy" />} />
      <Route path="*" element={<ProtectedRoutes />} />
    </Routes>
  );
}

function ProtectedRoutes() {
  return (
    <AuthGate>
      <Routes>
        <Route path="/" element={<ProjectList />} />
        <Route path="/admin" element={<AdminRoute><AdminConsole /></AdminRoute>} />
        <Route
          path="/admin/users/:userId"
          element={<AdminRoute><AdminUserDetail /></AdminRoute>}
        />
        <Route path="/me" element={<PersonalHubPage />} />
        <Route path="/projects/:projectId" element={<DraftList />} />
        <Route path="/projects/:projectId/settings" element={<ProjectSettingsPage />} />
        {/* 오너 2026-08-27: 개요·활동은 설정 탭 아래로 모였다. 옛 주소는
            남겨 둔 링크·북마크가 죽지 않도록 그 탭으로 넘긴다. */}
        <Route path="/projects/:projectId/overview" element={<SettingsRedirect tab="brief" />} />
        <Route path="/projects/:projectId/activity" element={<SettingsRedirect tab="activity" />} />
        <Route path="/projects/:projectId/access-log" element={<AccessLogPage />} />
        <Route path="/projects/:projectId/notes" element={<SceneNotesPage />} />
        <Route
          path="/projects/:projectId/review"
          element={<ReviewInbox />}
        />
        <Route
          path="/projects/:projectId/review/:candidateId"
          element={<ReviewInboxDetail />}
        />
        <Route
          path="/projects/:projectId/observability"
          element={
            <Suspense
              fallback={<p className="status-copy">지표 화면을 불러오는 중…</p>}
            >
              <ObservabilityDashboard />
            </Suspense>
          }
        />
        <Route
          path="/projects/:projectId/drafts/:draftId"
          element={<DraftEditor />}
        />
        <Route
          path="*"
          element={
            <section className="workspace-page page-enter">
              <p className="eyebrow">찾을 수 없음</p>
              <h1>이 작업 공간은 없습니다.</h1>
              <Link className="back-link" to="/">프로젝트로 돌아가기</Link>
            </section>
          }
        />
      </Routes>
    </AuthGate>
  );
}

function SettingsRedirect({ tab }: { tab: string }) {
  const { projectId } = useParams<{ projectId: string }>();
  return <Navigate replace to={`/projects/${projectId}/settings?tab=${tab}`} />;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const user = useAuthenticatedUser();
  if (!user.is_admin) {
    return (
      <section className="workspace-page page-enter">
        <p className="eyebrow">접근 제한</p>
        <h1>관리자 권한이 필요합니다.</h1>
        <Link className="back-link" to="/">프로젝트로 돌아가기</Link>
      </section>
    );
  }
  return (
    <Suspense fallback={<p className="status-copy">관리 화면을 불러오는 중…</p>}>
      {children}
    </Suspense>
  );
}
