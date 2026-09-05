import {
  createContext, useCallback, useContext, useEffect, useRef, useState,
} from "react";
import { useLocation, useNavigate } from "react-router";
import { Link } from "react-router";
import {
  ApiError,
  getCurrentUser,
  login,
  logout,
  requestSignup,
  subscribeUnauthorized,
  type User,
} from "../api/client";

type AuthState = "checking" | "authenticated" | "anonymous" | "error";
const AuthUserContext = createContext<User | null>(null);

export function useAuthenticatedUser(): User {
  const user = useContext(AuthUserContext);
  if (user === null) {
    throw new Error("useAuthenticatedUser must be used inside AuthGate");
  }
  return user;
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [state, setState] = useState<AuthState>("checking");
  const [user, setUser] = useState<User | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  const checkSession = useCallback(async () => {
    setState("checking");
    try {
      setUser(await getCurrentUser());
      setSessionExpired(false);
      setState("authenticated");
    } catch (err) {
      setUser(null);
      if (err instanceof ApiError && err.status === 401) {
        setState("anonymous");
      } else {
        setState("error");
      }
    }
  }, []);

  useEffect(() => {
    return subscribeUnauthorized(() => {
      setUser(null);
      setSessionExpired(true);
      setState("anonymous");
    });
  }, []);

  useEffect(() => {
    void checkSession();
  }, [checkSession]);

  async function handleLogout() {
    if (loggingOut) {
      return;
    }
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await logout();
      setUser(null);
      setSessionExpired(false);
      setState("anonymous");
    } catch {
      setLogoutError("로그아웃하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setLoggingOut(false);
    }
  }

  if (state === "checking") {
    return (
      <AuthStatus>
        <p className="status-copy">세션을 확인하는 중…</p>
      </AuthStatus>
    );
  }

  if (state === "error") {
    return (
      <AuthStatus>
        <p className="auth-status-title" role="alert">
          세션을 확인하지 못했습니다.
        </p>
        <p>서버 연결을 확인한 뒤 다시 시도해 주세요.</p>
        <button
          className="auth-submit"
          type="button"
          onClick={() => void checkSession()}
        >
          다시 시도
        </button>
      </AuthStatus>
    );
  }

  if (state === "anonymous" || user === null) {
    return (
      <LoginScreen
        sessionExpired={sessionExpired}
        onAuthenticated={(nextUser) => {
          setUser(nextUser);
          setSessionExpired(false);
          setState("authenticated");
          // P5=ⓐ — 관리자는 로그인 직후 관리자 화면으로 간다.
          //
          // ★ **루트에서 로그인했을 때만** 옮긴다. 이 게이트는 URL 을 바꾸지 않고
          // **제자리에서** 로그인 화면을 그리므로 `/projects/X` 로 들어온 사람은
          // 로그인만 하면 그 화면을 그대로 받는다 — 무조건 옮기면 **의도한 도착지를
          // 삼킨다**(브리프 P5 의 딥링크 지적).
          //
          // ★ 그래서 `?next=` 를 만들지 않았다: 목적지가 이미 주소에 있는데 그것을
          // 쿼리로 한 번 더 실어 나르면 **open redirect 표면(S-2)을 없던 데서 만드는
          // 것**이다. 이 앱에는 `next` 를 만드는 흐름이 하나도 없다.
          if (nextUser.is_admin && location.pathname === "/") {
            navigate("/admin", { replace: true });
          }
        }}
      />
    );
  }

  return (
    <AuthUserContext.Provider value={user}>
    <div className="app-shell">
      <header className="app-header">
        <Link className="brand" to="/">에-라잇</Link>
        <SessionMenu
          user={user}
          loggingOut={loggingOut}
          onLogout={() => void handleLogout()}
        />
      </header>
      {logoutError !== null && (
        <p className="header-alert" role="alert">
          {logoutError}
        </p>
      )}
      <main>{children}</main>
    </div>
    </AuthUserContext.Provider>
  );
}

function AuthStatus({ children }: { children: React.ReactNode }) {
  return (
    <main className="auth-shell">
      <section className="auth-status page-enter" aria-live="polite">
        <p className="eyebrow">에-라잇</p>
        {children}
      </section>
    </main>
  );
}

/**
 * 헤더의 계정 메뉴 (Phase 10 Slice 10.0, D4 = ⓐ+ⓒ).
 *
 * **ⓐ 와 ⓒ 를 함께 확정한 결과의 형태다**(오너 2026-08-11): username 이 **누를 수
 * 있는 자리**이고(ⓐ), 누르면 **내 작업 · 관리 · 로그아웃**이 열린다(ⓒ). 그전까지
 * username 은 `<span>` 이었고 **`/me` 로 가는 링크가 저장소 전체에 하나도 없어서**
 * 주소를 직접 쳐야 도달했다 — 9.2 가 만든 화면이 도달 불가였다.
 *
 * **★ `role="menu"` 를 쓰지 않는다.** 브리프 §D4 는 `role="menu"`/`menuitem` 을
 * 적었지만 구현하며 고쳤다. ARIA 의 menu 는 **애플리케이션 명령 메뉴**용이고
 * 화살표 키 탐색·타입어헤드를 사용자에게 약속한다 — 여기 담긴 것은 **내비게이션
 * 링크 둘 + 액션 하나**라 그 약속을 지킬 이유도 방법도 없다. 그래서 표준
 * disclosure(버튼 + 접히는 영역)로 간다. 부수 효과로 `<a>` 의 link 역할이 보존돼
 * 기존 셀(`getByRole("link", { name: "관리" })`)이 그대로 유효하다 —
 * `role="menuitem"` 을 얹었으면 그 역할이 덮여 무효가 됐을 것이다.
 *
 * 지켜야 하는 것 셋:
 * 1. **관리 링크는 조건부**다(`is_admin`). 조건을 잃으면 비관리자에게 404 로 가는
 *    링크가 보인다 — over-strict 셀이 문다.
 * 2. **로그아웃은 옮긴 것이지 다시 쓴 것이 아니다** — `loggingOut`·`disabled`·
 *    "나가는 중…" 문구와 `logoutError` 배너는 `AuthGate` 에 그대로 있다.
 * 3. **Esc 로 닫히고 포커스가 트리거로 돌아온다.** 열어 놓고 키보드로 빠져나갈 수
 *    없으면 그 자리가 함정이 된다.
 */
function SessionMenu({
  user,
  loggingOut,
  onLogout,
}: {
  user: User;
  loggingOut: boolean;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) {
      triggerRef.current?.focus();
    }
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    // 바깥을 누르면 닫는다. 트리거 자신은 제 onClick 이 토글하므로 제외하지
    // 않으면 "닫고 다시 여는" 두 번이 한 클릭에 일어난다.
    function onPointerDown(event: MouseEvent) {
      if (!wrapperRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  return (
    <div
      className="session-menu"
      ref={wrapperRef}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.stopPropagation();
          close(true);
        }
      }}
    >
      <button
        type="button"
        className="session-trigger"
        ref={triggerRef}
        aria-expanded={open}
        aria-controls="session-menu-panel"
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        {user.username}
      </button>
      {open && (
        <div className="session-panel" id="session-menu-panel">
          <Link to="/me" onClick={() => close(false)}>내 작업</Link>
          {user.is_admin && (
            <Link to="/admin" onClick={() => close(false)}>관리</Link>
          )}
          {/*
            ★ 누를 때 패널을 닫지 않는다. 닫으면 "나가는 중…"·`disabled` 가 그
            즉시 화면에서 사라져 **진행 중이라는 유일한 신호를 잃는다**. 성공하면
            셸 전체가 로그인 화면으로 바뀌며 함께 사라지고, 실패하면 열린 채로
            남아 사용자가 바로 다시 누를 수 있다(오류는 헤더 아래 배너).
          */}
          <button type="button" disabled={loggingOut} onClick={onLogout}>
            {loggingOut ? "나가는 중…" : "로그아웃"}
          </button>
        </div>
      )}
    </div>
  );
}

/** 로그인 화면의 세 얼굴 (승인제 가입, 2026-08-22).
 *
 * - "signin": 아이디·비밀번호 (+ 관리자 1회용 비밀번호 교체 분기)
 * - "signup": 새 계정 요청 — **요청만** 만들고, 계정은 관리자 승인 뒤 생긴다.
 * - "requested": 요청 접수 안내 — 세션이 없으니 "가입됐다"가 아니라
 *   "접수됐다"고만 말한다(과잉 안내는 승인 전 로그인 시도로 이어진다).
 *
 * 로그인 403 은 detail 두 문구로 대기/거절을 구분해 보여준다 — H3 "detail 로
 * 분기하지 않는다"의 **등재된 유일 예외**(백엔드 슬라이스 1-b, 오너 2026-08-22).
 * 그 403 을 받았다는 것 자체가 비밀번호까지 맞았다는 뜻이라, 사실상 본인에게만
 * 보이는 안내다.
 */
type LoginMode = "signin" | "signup" | "requested";

function LoginScreen({
  sessionExpired,
  onAuthenticated,
}: {
  sessionExpired: boolean;
  onAuthenticated: (user: User) => void;
}) {
  const [mode, setMode] = useState<LoginMode>("signin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [signupPasswordConfirmation, setSignupPasswordConfirmation] =
    useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mustReplacePassword, setMustReplacePassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirmation, setNewPasswordConfirmation] = useState("");

  function switchMode(next: LoginMode) {
    setMode(next);
    setError(null);
    setPassword("");
    setSignupPasswordConfirmation("");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const normalizedUsername = username.trim();
    if (normalizedUsername === "" || password === "" || submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await login({
        username: normalizedUsername,
        password,
        ...(mustReplacePassword ? { new_password: newPassword } : {}),
      });
      setPassword("");
      setNewPassword("");
      setNewPasswordConfirmation("");
      onAuthenticated(result.user);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && !mustReplacePassword) {
        setMustReplacePassword(true);
        setError(null);
      } else {
        if (err instanceof ApiError && err.status === 401) {
          setPassword("");
        }
        setError(signinErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function submitSignup(event: React.FormEvent) {
    event.preventDefault();
    const normalizedUsername = username.trim();
    if (
      normalizedUsername === "" || password.length < 12 ||
      password !== signupPasswordConfirmation || submitting
    ) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await requestSignup({ username: normalizedUsername, password });
      setPassword("");
      setSignupPasswordConfirmation("");
      setMode("requested");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("이미 사용 중인 아이디입니다. 다른 아이디를 사용해 주세요.");
      } else if (err instanceof ApiError && err.status === 429) {
        // Phase S-3(2026-09-05): 발신 축 레이트리밋과 승인 대기열 상한이 같은
        // 429 를 쓴다 — 둘을 구분해 알려 주면 홍수를 보내는 쪽에 어느 상한에
        // 걸렸는지를 알려 주게 되므로, 화면도 한 문구로 답한다.
        setError("가입 요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.");
      } else if (err instanceof ApiError && err.status === 400) {
        setError(
          "요청 내용을 확인해 주세요. 비밀번호는 12자 이상 256자 이하, " +
          "아이디는 64자 이하여야 합니다."
        );
      } else {
        setError("가입 요청을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (mode === "requested") {
    return (
      <main className="auth-shell">
        <section className="login-page page-enter">
          <header className="login-heading">
            <p className="eyebrow">에-라잇</p>
            <h1>가입 요청이 접수되었습니다</h1>
            <p>
              관리자가 승인하면 입력하신 아이디와 비밀번호로 로그인할 수 있습니다.
              승인까지 시간이 걸릴 수 있으니 조금 뒤에 다시 시도해 주세요.
            </p>
          </header>
          <form className="login-form" onSubmit={(e) => e.preventDefault()}>
            <button
              className="auth-submit"
              type="button"
              onClick={() => switchMode("signin")}
            >
              로그인 화면으로
            </button>
          </form>
        </section>
      </main>
    );
  }

  const signupForm = mode === "signup";

  return (
    <main className="auth-shell">
      <section className="login-page page-enter">
        <header className="login-heading">
          <p className="eyebrow">에-라잇</p>
          <h1>
            {mustReplacePassword
              ? "새 비밀번호 설정"
              : signupForm ? "새 계정 요청" : "쓴 것을 기억하는 집필 작업실"}
          </h1>
          <p>
            {mustReplacePassword
              ? "관리자가 만든 초기 비밀번호를 본인만 아는 비밀번호로 바꿔 주세요."
              : signupForm
                ? "요청하면 관리자 승인 뒤 계정이 열립니다. 비밀번호는 12자 이상입니다."
                : "설정과 인물, 지난 원고를 AI가 기억한 채로 이어서 씁니다."}
          </p>
        </header>

        {sessionExpired && !signupForm && (
          <p className="session-expired" role="status">
            세션이 만료되었습니다.
          </p>
        )}

        {signupForm ? (
          <form className="login-form" onSubmit={submitSignup}>
            <label htmlFor="signup-username">
              <span>아이디</span>
              <input
                id="signup-username"
                name="username"
                value={username}
                autoComplete="username"
                autoFocus
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label htmlFor="signup-password">
              <span>비밀번호</span>
              <input
                id="signup-password"
                name="new-password"
                type="password"
                value={password}
                minLength={12}
                autoComplete="new-password"
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <label htmlFor="signup-password-confirmation">
              <span>비밀번호 확인</span>
              <input
                id="signup-password-confirmation"
                type="password"
                value={signupPasswordConfirmation}
                minLength={12}
                autoComplete="new-password"
                onChange={(event) =>
                  setSignupPasswordConfirmation(event.target.value)
                }
              />
            </label>
            <p className="form-hint">12자 이상, 두 입력이 같아야 합니다.</p>
            {error !== null && (
              <p className="login-error" role="alert">{error}</p>
            )}
            <button
              className="auth-submit"
              type="submit"
              disabled={
                username.trim() === "" || password.length < 12 ||
                password !== signupPasswordConfirmation || submitting
              }
            >
              {submitting ? "보내는 중…" : "가입 요청 보내기"}
            </button>
            <button
              className="auth-switch"
              type="button"
              onClick={() => switchMode("signin")}
            >
              이미 계정이 있나요? 로그인
            </button>
          </form>
        ) : (
          <form className="login-form" onSubmit={submit}>
            <label htmlFor="login-username">
              <span>아이디</span>
              <input
                id="login-username"
                name="username"
                value={username}
                autoComplete="username"
                autoFocus
                disabled={mustReplacePassword}
                onChange={(event) => setUsername(event.target.value)}
              />
            </label>
            <label htmlFor="login-password">
              <span>비밀번호</span>
              <input
                id="login-password"
                name="password"
                type="password"
                value={password}
                disabled={mustReplacePassword}
                autoComplete="current-password"
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {mustReplacePassword && (
              <>
                <label htmlFor="login-new-password">
                  <span>새 비밀번호</span>
                  <input
                    id="login-new-password"
                    type="password"
                    value={newPassword}
                    minLength={12}
                    autoComplete="new-password"
                    autoFocus
                    onChange={(event) => setNewPassword(event.target.value)}
                  />
                </label>
                <label htmlFor="login-new-password-confirmation">
                  <span>새 비밀번호 확인</span>
                  <input
                    id="login-new-password-confirmation"
                    type="password"
                    value={newPasswordConfirmation}
                    minLength={12}
                    autoComplete="new-password"
                    onChange={(event) => setNewPasswordConfirmation(event.target.value)}
                  />
                </label>
                <p className="form-hint">12자 이상, 두 입력이 같아야 합니다.</p>
              </>
            )}
            {error !== null && (
              <p className="login-error" role="alert">{error}</p>
            )}
            <button
              className="auth-submit"
              type="submit"
              disabled={
                username.trim() === "" || password === "" || submitting ||
                (mustReplacePassword &&
                  (newPassword.length < 12 || newPassword !== newPasswordConfirmation))
              }
            >
              {submitting
                ? "확인하는 중…"
                : mustReplacePassword ? "비밀번호 바꾸고 입장" : "작업실 입장"}
            </button>
            {/* 승인제(2026-08-22): 요청은 누구나 — 승인은 관리자. 비밀번호 교체
                분기에서는 숨긴다(그 흐름의 다음 단계는 교체지 가입이 아니다). */}
            {!mustReplacePassword && (
              <button
                className="auth-switch"
                type="button"
                onClick={() => switchMode("signup")}
              >
                계정이 없나요? 새 계정 요청
              </button>
            )}
          </form>
        )}
      </section>
    </main>
  );
}

/** 로그인 실패 안내문. 403 두 detail 만 구분한다(H3 등재 예외의 유일 소비자). */
function signinErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 403) {
    if (err.detail === "account approval pending") {
      return "가입 승인 대기 중입니다. 관리자가 승인하면 로그인할 수 있어요.";
    }
    if (err.detail === "signup request rejected") {
      return "가입 요청이 거절되었습니다. 다른 아이디로 다시 요청할 수 있어요.";
    }
  }
  if (err instanceof ApiError && err.status === 401) {
    return "아이디 또는 비밀번호를 확인해 주세요.";
  }
  if (err instanceof ApiError && err.status === 409) {
    return "새 비밀번호를 설정하지 못했습니다. 입력을 확인해 주세요.";
  }
  return "로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}
