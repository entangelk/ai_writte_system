/**
 * 활동 목록을 **날짜로 묶는다** (Phase 10 Slice 10.2, D3=ⓓ).
 *
 * 그전까지 두 화면 모두 최대 100건을 **한 덩어리로 주르륵** 세로로 쌓았다. 오너가
 * 육안 확인에서 지적한 자리다(*"최근 100건이 전부 주르륵 나열은 아니겠지?"*).
 *
 * **★ 커서 페이징이 아니라 날짜 그룹인 이유**(D3=ⓓ): 100건 상한을 없애려면 API 에
 * 커서가 필요한데(operation 78 변경), **지금 100건이 부족하다는 증거가 없다.** 증거
 * 없이 계약을 움직이지 않는다 — 커서는 유예이고 **트리거는 *실사용자가 100건을 채워
 * "더 이전"을 필요로 할 때*** 다(9.1 브리프 §"나중에 여는 문" F1 이 정본).
 * 그래서 여기는 **backend 0줄**이고, 이미 받은 목록을 나누기만 한다.
 *
 * 지켜야 하는 것 셋:
 *
 * 1. **★ 서버가 준 순서를 다시 정렬하지 않는다.** 정렬의 정본은 저장소다
 *    (`log_mongo.py` 가 `at` DESC). 여기서 한 번 더 정렬하면 **순서를 정하는 곳이
 *    둘**이 되고, 언젠가 조용히 갈린다. 이 함수는 **인접한 같은 날을 접기만** 한다.
 * 2. **★ 그룹 경계는 브라우저 로컬 날짜다 — KST 고정이 아니다.** 각 행이 이미
 *    `toLocaleString("ko-KR")` 로 **로컬 시각**을 찍고 있어서, 머리글만 고정 시간대로
 *    계산하면 *"오늘"* 아래에 어제 시각이 적힌 행이 앉는다. **머리글은 옆에 적힌
 *    시각과 같은 날을 말해야 한다.** (저장소의 유일한 KST 지점인
 *    `quota/policy.py` 와 다른 판단이다 — 그쪽은 **시행 창**이라 서버가 정하는
 *    계약이고, 여기는 **표시**라 보는 사람의 달력을 따른다.)
 * 3. **`now` 를 주입받는다.** "오늘"·"어제"는 실행 시각에 따라 달라지므로, 고정하지
 *    않으면 자정 근처에서 깨지는 테스트가 된다.
 */

export type ActivityDayGroup<TEvent> = {
  /** 안정적인 key — 로컬 날짜 `YYYY-MM-DD`. */
  key: string;
  /** 사람이 읽는 머리글. */
  label: string;
  events: TEvent[];
};

function localDayKey(value: Date): string {
  // `toISOString()` 은 UTC 로 바꾸므로 쓸 수 없다 — 로컬 자정 경계가 밀린다.
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dayLabel(day: Date, now: Date): string {
  const todayKey = localDayKey(now);
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);

  const key = localDayKey(day);
  if (key === todayKey) return "오늘";
  if (key === localDayKey(yesterday)) return "어제";

  const sameYear = day.getFullYear() === now.getFullYear();
  return sameYear
    ? `${day.getMonth() + 1}월 ${day.getDate()}일`
    : `${day.getFullYear()}년 ${day.getMonth() + 1}월 ${day.getDate()}일`;
}

/**
 * 최신순으로 온 목록을 **인접한 같은 날끼리** 묶는다. 순서는 보존된다.
 *
 * 날짜를 해석할 수 없는 값(`at` 이 깨진 경우)은 **버리지 않고** 마지막 그룹으로
 * 모은다 — 활동 기록에서 행이 조용히 사라지는 것이 잘못된 머리글보다 나쁘다.
 */
export function groupActivityByDay<TEvent extends { at: string }>(
  events: readonly TEvent[],
  now: Date = new Date(),
): ActivityDayGroup<TEvent>[] {
  const groups: ActivityDayGroup<TEvent>[] = [];

  for (const event of events) {
    const at = new Date(event.at);
    const parsed = !Number.isNaN(at.getTime());
    const key = parsed ? localDayKey(at) : "unknown";
    const label = parsed ? dayLabel(at, now) : "날짜를 읽을 수 없음";

    const last = groups[groups.length - 1];
    if (last !== undefined && last.key === key) {
      last.events.push(event);
    } else {
      groups.push({ key, label, events: [event] });
    }
  }

  return groups;
}
