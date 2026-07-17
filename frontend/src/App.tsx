import { Link, Route, Routes } from "react-router";
import { DraftList } from "./drafts/DraftList";
import { DraftEditor } from "./drafts/DraftEditor";
import { ProjectList } from "./projects/ProjectList";
import { ReviewInbox } from "./review/ReviewInbox";
import { ReviewInboxDetail } from "./review/ReviewInboxDetail";

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
          <Route
            path="/projects/:projectId/review"
            element={<ReviewInbox />}
          />
          <Route
            path="/projects/:projectId/review/:candidateId"
            element={<ReviewInboxDetail />}
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
