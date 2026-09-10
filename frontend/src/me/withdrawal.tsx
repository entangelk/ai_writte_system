import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  ApiError,
  cancelMyWithdrawal,
  describeApiError,
  getMyWithdrawal,
  requestMyWithdrawal,
  type Withdrawal,
} from "../api/client";

/**
 * 계정 탈퇴 유예 상태 — 앱 셸이 들고 화면들이 나눠 쓴다 (Slice 4, D1=ⓐ 2026-09-10).
 *
 * **상태가 셸에 있는 이유는 배너가 전역이기 때문이다**(브리프 D1=ⓐ): D1=ⓒ 가
 * 쓰기를 **전 화면에서** 막으므로, 유예 중 사용자는 편집기에서 저장을 눌렀을 때
 * 403 을 받는다. 배너가 `/me` 에만 있으면 그 403 은 **원인에서 가장 먼 자리**에서
 * 정체불명으로 뜬다(HANDOFF §14 가 기록한 함정과 같은 모양).
 *
 * **★ 상태는 한 벌이다.** `/me` 의 요청·취소가 이 상태를 갱신하고 배너가 그것을
 * 읽는다 — 두 자리가 각자 조회하면 취소한 뒤에도 배너가 남는다. 그래서 두 화면이
 * 쓰는 것은 `useWithdrawal()` 하나이고, 응답을 그대로 밀어 넣는다(`apply`).
 */
const WithdrawalContext = createContext<{
  withdrawal: Withdrawal | null;
  apply: (next: Withdrawal) => void;
} | null>(null);

/** 테스트 전용 오프라인 값. 있으면 이 provider 는 네트워크를 아예 쓰지 않는다. */
let seeded: Withdrawal | null = null;

/**
 * 테스트 전용 — mount 조회를 통째로 건너뛴다.
 *
 * `seedMemberQuota` 와 **같은 이유이자 같은 모양**이다: 화면 테스트는 응답
 * **시퀀스**를 세는데 셸의 보조 조회가 그 사이에 끼면 세던 것이 어긋난다. 그래서
 * `vitest.setup.ts` 의 기본값은 *탈퇴 중 아님* 이고, 탈퇴 축 셀만 자기 값을 시드하거나
 * `resetWithdrawal()` 로 실제 조회를 켠다.
 */
export function seedWithdrawal(value: Withdrawal): void {
  seeded = value;
}

/** 테스트 전용: 시드를 지워 실제 조회로 되돌린다. */
export function resetWithdrawal(): void {
  seeded = null;
}

export function WithdrawalProvider({ children }: { children: React.ReactNode }) {
  const [withdrawal, setWithdrawal] = useState<Withdrawal | null>(seeded);

  useEffect(() => {
    if (seeded !== null) {
      setWithdrawal(seeded);
      return;
    }
    let active = true;
    getMyWithdrawal()
      .then((next) => {
        if (active) setWithdrawal(next);
      })
      .catch(() => {
        // 실패는 삼킨다 — `useMemberQuota` 와 같은 판단이다. 조회 하나가 앱 전체를
        // 에러 화면으로 만들면 안 되고, 진짜 제한은 쓰기 요청 자체가 403 으로 말한다.
      });
    return () => { active = false; };
  }, []);

  const apply = useCallback((next: Withdrawal) => setWithdrawal(next), []);

  return (
    <WithdrawalContext.Provider value={{ withdrawal, apply }}>
      {children}
    </WithdrawalContext.Provider>
  );
}

export function useWithdrawal(): {
  withdrawal: Withdrawal | null;
  apply: (next: Withdrawal) => void;
} {
  const value = useContext(WithdrawalContext);
  if (value === null) {
    throw new Error("useWithdrawal must be used inside WithdrawalProvider");
  }
  return value;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * 파기까지 **남은 일수**. 탈퇴 중이 아니면 `null`.
 *
 * **★ 30 을 여기에 박지 않는다.** 유예 기간의 정본은 서버 상수 한 곳
 * (`auth/users.py::WITHDRAWAL_GRACE_PERIOD`)이고, 서버는 그 산술을 이미 끝낸
 * `purge_due_at` 를 준다 — 화면은 **빼기만** 한다. 프런트가 30 을 박으면 두 번째
 * 정본이 생기고, 상수를 고친 날 화면만 다른 날을 말한다(Slice 2 브리프 후속 고려).
 *
 * **올림이다.** 판정은 서버에서 `now >= purge_due_at` 이므로 남은 시간이 0.2일이어도
 * **아직 파기 전**이다 — 내림하면 화면이 "0일" 이라 말하는 동안 취소가 여전히
 * 가능해서, 남은 일수가 곧 "취소할 수 있는 날 수"라는 뜻을 잃는다.
 */
export function remainingGraceDays(
  withdrawal: Withdrawal | null,
  now: Date = new Date(),
): number | null {
  if (withdrawal?.purge_due_at == null) {
    return null;
  }
  const due = new Date(withdrawal.purge_due_at).getTime();
  if (Number.isNaN(due)) {
    return null;
  }
  return Math.max(0, Math.ceil((due - now.getTime()) / DAY_MS));
}

/** 유예 중인가 — 요청 시각이 곧 그 사실이다(취소는 시각을 지운다, D5=A). */
export function isWithdrawing(withdrawal: Withdrawal | null): boolean {
  return withdrawal?.withdrawal_requested_at != null;
}

/**
 * 앱 셸 전역 배너 (D1=ⓐ).
 *
 * **배너의 값은 남은 일수가 아니라 "지금 왜 저장이 안 되는가"다.** 그래서 문구가
 * 제한을 먼저 말하고, 취소가 **어디서나 한 번에** 닿는다.
 *
 * `role="status"` 다 — 마운트되자마자 그려지는 **상시** 표시라 `role="alert"`
 * (그 자리에서 방금 일어난 일)의 자리가 아니다.
 */
export function WithdrawalBanner() {
  const { withdrawal, apply } = useWithdrawal();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isWithdrawing(withdrawal)) {
    return null;
  }

  const days = remainingGraceDays(withdrawal);

  async function cancel() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      apply(await cancelMyWithdrawal());
    } catch (cause: unknown) {
      // 409 = 취소할 것이 없다(다른 탭에서 이미 취소했다). 계정이 없다는 뜻이
      // 아니므로 오류로 말하지 않고 **서버의 지금 상태를 다시 읽어** 화면을 맞춘다.
      // H3 가 `detail` 분기를 금지하므로 판정은 상태코드로만 한다.
      if (cause instanceof ApiError && cause.status === 409) {
        try {
          apply(await getMyWithdrawal());
          return;
        } catch {
          setError("탈퇴 상태를 다시 읽지 못했습니다. 새로고침해 주세요.");
          return;
        }
      }
      setError(describeApiError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="header-alert withdrawal-banner" role="status">
      <span>
        탈퇴 예정 계정입니다 — 저장·생성이 되지 않습니다.{" "}
        {days !== null && <strong>남은 기간 {days}일</strong>}
      </span>
      <button type="button" disabled={busy} onClick={() => void cancel()}>
        {busy ? "취소하는 중…" : "탈퇴 취소"}
      </button>
      {error !== null && <span role="alert">{error}</span>}
    </div>
  );
}

/** 파기 예정 시각을 사람이 읽는 날짜로. 값이 없으면 빈 문자열. */
function dueDateLabel(withdrawal: Withdrawal | null): string {
  if (withdrawal?.purge_due_at == null) {
    return "";
  }
  return new Date(withdrawal.purge_due_at).toLocaleDateString("ko-KR", {
    year: "numeric", month: "long", day: "numeric",
  });
}

/**
 * `/me` 의 계정 탈퇴 절 (Slice 4).
 *
 * **불가역 확인은 프로젝트 파기 UI 선례를 그대로 쓴다**(계획서 Slice 4 문언):
 * `.confirm-panel` + 이름 입력 + `.danger-button`. 프로젝트가 **프로젝트 이름**을
 * 받았으니 계정은 **사용자명**을 받는다.
 *
 * **★ 사용자명을 prop 으로 받는다 — `useAuthenticatedUser()` 를 부르지 않는다.**
 * `AuthGate` 가 이 모듈의 `WithdrawalProvider`·`WithdrawalBanner` 를 부르므로 여기서
 * `AuthGate` 를 import 하면 **순환**이다(백엔드의 `routers/* → main` 금지와 같은 이유).
 * 부르는 쪽이 이미 세션을 들고 있으니 값을 내려 주는 것이 맞다.
 *
 * **취소 버튼이 여기에도 있는 이유**: 배너가 전역이라 취소는 어디서나 닿지만,
 * 탈퇴를 **관리하러 온 사람**이 자기 계정 절에서 취소를 못 찾으면 그 절이 거짓말을
 * 한다. 둘은 같은 상태(`useWithdrawal`)를 갱신하므로 어느 쪽을 눌러도 둘 다 바뀐다.
 */
export function WithdrawalSection({ username }: { username: string }) {
  const { withdrawal, apply } = useWithdrawal();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const withdrawing = isWithdrawing(withdrawal);
  const days = remainingGraceDays(withdrawal);

  async function submit() {
    if (busy || confirmation !== username) return;
    setBusy(true);
    setError(null);
    try {
      apply(await requestMyWithdrawal());
      setOpen(false);
      setConfirmation("");
    } catch (cause: unknown) {
      // D6 — 마지막 활성 관리자는 떠날 수 없다. `deactivate_user` 와 **같은 규칙·같은
      // 상태코드**이고, H3 가 `detail` 분기를 금지하므로 판정은 상태코드로만 한다.
      if (cause instanceof ApiError && cause.status === 409) {
        setError(
          "마지막 활성 관리자는 탈퇴할 수 없습니다. 다른 관리자를 먼저 만들어 주세요.",
        );
      } else {
        setError(describeApiError(cause));
      }
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      apply(await cancelMyWithdrawal());
    } catch (cause: unknown) {
      // 배너의 취소와 같은 처분 — 409 는 "취소할 것이 없다" 이지 오류가 아니다.
      if (cause instanceof ApiError && cause.status === 409) {
        try {
          apply(await getMyWithdrawal());
          return;
        } catch {
          setError("탈퇴 상태를 다시 읽지 못했습니다. 새로고침해 주세요.");
          return;
        }
      }
      setError(describeApiError(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="hub-section account-withdrawal-section">
      <h2>계정 탈퇴</h2>
      {withdrawing ? (
        <>
          <p className="status-copy">
            탈퇴가 접수됐습니다. <strong>{dueDateLabel(withdrawal)}</strong>
            {days !== null && <> · 남은 기간 {days}일</>} 뒤에 계정과 모든 프로젝트가
            영구히 파기됩니다. 그때까지는 언제든 취소할 수 있고, 유예 중에는 조회만
            되고 저장·생성은 되지 않습니다.
          </p>
          {error !== null && <p className="alert" role="alert">{error}</p>}
          <button type="button" disabled={busy} onClick={() => void cancel()}>
            {busy ? "취소하는 중…" : "탈퇴 취소"}
          </button>
        </>
      ) : (
        <>
          <p className="status-copy">
            탈퇴를 요청하면 유예 기간이 시작됩니다. 유예가 끝나면 계정과 모든
            프로젝트·원고·기억이 영구히 사라지며 되돌릴 수 없습니다. 유예 중에는
            조회와 취소만 가능합니다.
          </p>
          {error !== null && <p className="alert" role="alert">{error}</p>}
          {!open ? (
            <button type="button" onClick={() => setOpen(true)}>계정 탈퇴…</button>
          ) : (
            <div className="confirm-panel">
              <label htmlFor="account-withdrawal-confirmation">
                탈퇴를 원하면 사용자명 <strong>{username}</strong> 을(를)
                입력하세요
              </label>
              <input
                id="account-withdrawal-confirmation"
                value={confirmation}
                autoComplete="off"
                disabled={busy}
                onChange={(event) => setConfirmation(event.target.value)}
              />
              <div className="confirm-actions">
                <button
                  type="button"
                  className="danger-button"
                  disabled={busy || confirmation !== username}
                  onClick={() => void submit()}
                >
                  {busy ? "요청하는 중…" : "탈퇴 요청"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setOpen(false);
                    setConfirmation("");
                    setError(null);
                  }}
                >
                  취소
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
