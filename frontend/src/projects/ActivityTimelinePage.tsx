import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import {
  describeApiError,
  listDrafts,
  listProjectActivity,
  type ActivityEvent,
} from "../api/client";
import { activityActionLabel, activityTargetHref } from "./activityActions";
import { groupActivityByDay } from "./activityDays";

/** 서버가 한 번에 주는 최대 건수. 화면이 이 수를 **문장으로** 말한다(브리프 S2=ⓐ). */
const ACTIVITY_PAGE_SIZE = 100;

/**
 * 활동 타임라인 (Phase 9 Slice 9.1).
 *
 * **행위자 열이 없는 것은 의도다**(S3=ⓑ): 관리자 행위는 이 컬렉션 밖이고(분류표가
 * `admin_audited` 로 제외한다 — `admin_audit_events`·`access_grant_uses` 가 담는다)
 * 프로젝트는 소유자 1인 소유라, `actor_user_id` 는 **항상 이 화면을 보는 그 사람**이다.
 * 공동 작업이 생기는 날 열만 켜면 된다(응답 필드는 그대로 있다).
 *
 * **replay 를 접지 않는 것도 의도다**(S5=ⓐ): 같은 저장이 여러 줄로 보일 수 있다.
 * 얼마나 잦은지 아무도 모르는 상태라 **이 화면이 그 첫 관측**이고, 접는 것은 그것을
 * 보고 나서 판단한다.
 */
export function ActivityTimelinePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [events, setEvents] = useState<ActivityEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 원고 purge(2026-08-28) 뒤에도 활동 행은 남는다 — 살아 있는 원고 id 집합을
  // 알아야 죽은 draft 행에 링크를 안 걸 수 있다. 보관분까지 포함해 읽는다.
  const [draftIds, setDraftIds] = useState<ReadonlySet<string> | null>(null);

  useEffect(() => {
    if (projectId === undefined) {
      setError("프로젝트 경로가 올바르지 않습니다.");
      return;
    }
    let active = true;
    listProjectActivity(projectId)
      .then((result) => {
        if (active) setEvents(result);
      })
      .catch((cause: unknown) => {
        if (active) setError(describeApiError(cause));
      });
    // GET /drafts 는 보관분을 포함한 전체 목록을 준다 — purge 로 사라진 원고만
    // 이 집합에 없다.
    listDrafts(projectId)
      .then((result) => {
        if (active) setDraftIds(new Set(result.drafts.map((draft) => draft.id)));
      })
      .catch(() => {
        // 원고 집합을 못 얻으면 행은 종전처럼 링크로 둔다(활동 조회가 주 요청이다).
        if (active) setDraftIds(null);
      });
    return () => { active = false; };
  }, [projectId]);

  return (
    <>
      <p className="form-hint">
        이 프로젝트에서 무엇이 언제 바뀌었는지 최신순으로 봅니다.
        {" "}최근 {ACTIVITY_PAGE_SIZE}건까지 보여줍니다.
      </p>

      {error !== null && <p className="alert" role="alert">{error}</p>}
      {events === null && error === null && (
        <p className="status-copy">활동 기록을 불러오는 중…</p>
      )}
      {events !== null && events.length === 0 && (
        <div className="empty-state"><p>아직 기록된 활동이 없습니다.</p></div>
      )}
      {events !== null && events.length > 0 && groupActivityByDay(events).map((day) => (
        // 10.2: 날짜 머리글 아래로 그 날의 행만. 100건 상한은 그대로이며(D3=ⓓ 가
        // 커서를 유예했다) 위 문장이 여전히 그 수를 말한다.
        <section className="activity-day" key={day.key}>
          <h2>{day.label}</h2>
          <ul className="access-log access-log-page">
            {day.events.map((event) => {
              const href = projectId === undefined ? null : activityTargetHref(
                projectId, event.target_type, event.target_id,
                draftIds ?? undefined,
              );
              const changed = [event.before, event.after]
                .some((value) => value !== null && value !== undefined);
              return (
                <li key={event.id}>
                  <strong>{activityActionLabel(event.action)}</strong>
                  <span>
                    {new Date(event.at).toLocaleTimeString("ko-KR", {
                      hour: "2-digit", minute: "2-digit",
                    })}
                    {changed && (
                      <>
                        {" · "}
                        {event.before !== null && event.before !== undefined
                          ? `${event.before} → ` : ""}
                        {event.after ?? ""}
                      </>
                    )}
                    {href !== null && <>{" · "}<Link className="inline-navigation-link" to={href}>원고 열기</Link></>}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </>
  );
}
