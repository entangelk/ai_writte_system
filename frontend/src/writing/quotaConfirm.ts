// 8.4 W3=A · 8.2b §0.4 — quota 확인·안내 문구의 단일 정본.
// 성격이 계약이다: 꾸짖지 않고, 의도를 묻고, 대가를 알린다. WritingPanel(생성·채택)과
// ScratchRecovery(패드 채택)가 같은 문구를 써야 한다 — 두 벌이면 갈라진다.

import type { MyQuota } from "../api/client";

/**
 * 중복 확인 문구 (8.4 W3=A · 8.2b §0.4).
 *
 * 성격이 계약이다 — **꾸짖지 않고, 의도를 묻고, 대가를 알린다.** "중복 요청입니다"는
 * 정당한 사용자를 실수한 사람으로 단정한다. 이 제품에서 같은 지시로 다른 안을
 * 받는 것은 정상 사용이고, 서버는 그 통로를 확인 하나로 열어 둔다(G4=A).
 */
export function confirmPrompt(quota: MyQuota | null): string {
  const remaining =
    quota !== null && !quota.unlimited && quota.remaining !== null
      ? ` (이번 창 잔여 ${quota.remaining}회)`
      : "";
  return `방금 같은 요청을 보냈습니다. 하나 더 만들까요? 새로 만들면 사용량이 1회 더 듭니다.${remaining}`;
}

/** 402 안내에 붙일 초기화 시각. 두 창 중 **먼저 오는 쪽**이 실제 회복 시점이다. */
export function formatResetMoment(quota: MyQuota): string {
  const moments = [quota.daily.resets_at, quota.weekly.resets_at]
    .map((value) => new Date(value))
    .filter((value) => !Number.isNaN(value.getTime()));
  if (moments.length === 0) {
    return "초기화 시각 미상";
  }
  const soonest = new Date(Math.min(...moments.map((m) => m.getTime())));
  return soonest.toLocaleString("ko-KR", {
    month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}
