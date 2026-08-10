import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  describeApiError,
  listMyActivity,
  listProjects,
  type PersonalActivityEvent,
  type Project,
} from "../api/client";
import { useMemberQuota } from "../quota/useMemberQuota";
import { activityActionLabel } from "../projects/activityActions";

/** 서버가 통합 조회에서 한 번에 주는 최대 건수 (per-project 와 **같은 수** — P2 역전 방지). */
const ACTIVITY_PAGE_SIZE = 100;

/**
 * 개인 허브 `/me` (Phase 9 Slice 9.2).
 *
 * **주어가 "나"인 페이지다.** 프로젝트 페이지의 목차가 아니라, 여기서 프로젝트로
 * 뻗어나간다(오너 2026-08-10: *"개인 페이지 허브에서 프로젝트 별로 뻗어나가는 거지"*).
 *
 * 담는 것 셋:
 * 1. **잔여 사용량** — 이 페이지가 생긴 첫 이유다. `useMemberQuota` 가 화면 없이
 *    떠돌던 것을 여기가 받는다.
 * 2. **통합 활동** — `GET /me/activity` 한 번(P1=ⓐ). 범위는 **소유 프로젝트**(P8=ⓐ).
 * 3. **프로젝트별 진입** — 원고 · 활동 · **관측**(P3=ⓐ 는 진입만이며, 관측 화면은
 *    `React.lazy` 경계 안에 그대로 둔다 — 여기로 끌어오면 진입 번들이 386 kB 는다).
 *
 * **행위자 열이 없는 것은 9.1 S3 과 같은 이유다**(관리자 행위는 이 컬렉션 밖이고
 * 프로젝트는 소유자 1인 소유라 행위자가 항상 보는 사람이다).
 */
export function PersonalHubPage() {
  const { quota } = useMemberQuota();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [events, setEvents] = useState<PersonalActivityEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([listProjects(), listMyActivity()])
      .then(([projectList, activity]) => {
        if (!active) return;
        setProjects(projectList.projects);
        setEvents(activity);
      })
      .catch((cause: unknown) => {
        if (active) setError(describeApiError(cause));
      });
    return () => { active = false; };
  }, []);

  // 활동 행은 `project_id` 만 들고 온다 — 사람이 읽을 수 있게 이름을 붙인다.
  // 이 조인이 없으면 화면에 24자 hex 가 줄마다 뜬다(9.1 에서 행위자 열을 만들지
  // 않기로 한 것과 같은 판단이다).
  const projectName = new Map(
    (projects ?? []).map((project) => [project.id, project.name]),
  );

  return (
    <section className="workspace-page page-enter">
      <header className="page-heading">
        <p className="eyebrow">내 정보</p>
        <h1>내 작업</h1>
        <p>사용량과 최근 활동을 한자리에서 봅니다.</p>
      </header>

      {error !== null && <p className="alert" role="alert">{error}</p>}

      <section className="hub-section">
        <h2>이번 주기 사용량</h2>
        {quota === null ? (
          <p className="status-copy">사용량을 불러오는 중…</p>
        ) : quota.unlimited ? (
          <p className="status-copy">한도가 없는 계정입니다.</p>
        ) : (
          <ul className="quota-summary">
            <li><strong>남은 요청</strong><span>{quota.remaining ?? "—"}회</span></li>
            <li>
              <strong>오늘</strong>
              <span>{quota.daily.used} / {quota.daily.limit ?? "무제한"}</span>
            </li>
            <li>
              <strong>이번 주</strong>
              <span>{quota.weekly.used} / {quota.weekly.limit ?? "무제한"}</span>
            </li>
          </ul>
        )}
      </section>

      <section className="hub-section">
        <h2>내 프로젝트</h2>
        {projects !== null && projects.length === 0 && (
          <div className="empty-state"><p>아직 프로젝트가 없습니다.</p></div>
        )}
        {projects !== null && projects.length > 0 && (
          <ul className="hub-projects">
            {projects.map((project) => (
              <li key={project.id}>
                <Link to={`/projects/${project.id}`}>{project.name}</Link>
                {project.archived && <span className="badge">보관됨</span>}
                <span className="row-actions">
                  <Link to={`/projects/${project.id}/activity`}>활동</Link>
                  <Link to={`/projects/${project.id}/observability`}>관측</Link>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="hub-section">
        <h2>최근 활동</h2>
        <p className="form-hint">
          내 프로젝트 전체에서 최근 {ACTIVITY_PAGE_SIZE}건까지 보여줍니다.
        </p>
        {events === null && error === null && (
          <p className="status-copy">활동 기록을 불러오는 중…</p>
        )}
        {events !== null && events.length === 0 && (
          <div className="empty-state"><p>아직 기록된 활동이 없습니다.</p></div>
        )}
        {events !== null && events.length > 0 && (
          <ul className="access-log access-log-page">
            {events.map((event) => (
              <li key={event.id}>
                <strong>{activityActionLabel(event.action)}</strong>
                <span>
                  {projectName.get(event.project_id) ?? event.project_id}
                  {" · "}
                  {new Date(event.at).toLocaleString("ko-KR")}
                  {(event.before ?? event.after) !== null && (
                    <>
                      {" · "}
                      {event.before !== null && event.before !== undefined
                        ? `${event.before} → ` : ""}
                      {event.after ?? ""}
                    </>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
