import type { AdminUser } from "../api/client";

/**
 * 관리 목록의 계정 상태 한 줄 (오너 2026-08-27, dogfood).
 *
 * **`is_active` 와 `status` 는 다른 축이다.** 가입 요청 행은 `is_active=True`
 * 로 저장되므로(auth/models.py 의 주석) 활성 플래그만 읽으면 **로그인조차 못
 * 하는 계정이 "활성"으로 표시된다** — 그것이 이 함수가 생긴 이유다.
 *
 * 비활성화는 단방향(D6)이라 승인 축보다 **앞선다**: 거절된 계정을 나중에
 * 비활성화했다면 화면은 "비활성"이라고 말해야 한다.
 */
export function adminUserStateLabel(user: AdminUser): string {
  if (!user.is_active) return "비활성";
  if (user.status === "pending") return "승인 대기";
  if (user.status === "rejected") return "거절됨";
  return "활성";
}

/**
 * 탈퇴 축 한 줄 (계정 탈퇴 Slice 4b, 2026-09-12).
 *
 * **승인 축·활성 축과 별개인 세 번째 축이다.** `adminUserStateLabel` 의 라벨
 * 순서(비활성 > 승인 대기 > 거절됨 > 활성, D6 단방향 축)에 섞이지 않는다 —
 * 유예 중 계정도 활성이고, 파기 중 계정은 그 아래 단계다. 두 스탬프가 없으면
 * 이 축은 화면에 나오지도 않는다(빈 라벨).
 */
export function adminWithdrawalLabel(user: AdminUser): string {
  if (user.purge_started_at !== null) return "파기 진행";
  if (user.withdrawal_requested_at !== null) return "탈퇴 유예";
  return "";
}
