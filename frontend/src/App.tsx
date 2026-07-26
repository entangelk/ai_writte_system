import { Suspense, lazy } from "react";
import { Link, Route, Routes } from "react-router";
import { DraftList } from "./drafts/DraftList";
import { DraftEditor } from "./drafts/DraftEditor";
import { ProjectList } from "./projects/ProjectList";
import { ProjectOverview } from "./projects/ProjectOverview";
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

export function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <Link className="brand" to="/">AI Writing System</Link>
        <span>로컬 집필실</span>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<ProjectList />} />
          <Route path="/projects/:projectId" element={<DraftList />} />
          <Route path="/projects/:projectId/overview" element={<ProjectOverview />} />
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
      </main>
    </div>
  );
}
