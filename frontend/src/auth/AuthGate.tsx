import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { Link } from "react-router";
import {
  ApiError,
  getCurrentUser,
  login,
  logout,
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
        <Link className="brand" to="/">AI Writing System</Link>
        <div className="session-menu">
          {user.is_admin && <Link to="/admin">관리</Link>}
          <span>{user.username}</span>
          <button
            type="button"
            disabled={loggingOut}
            onClick={() => void handleLogout()}
          >
            {loggingOut ? "나가는 중…" : "로그아웃"}
          </button>
        </div>
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
        <p className="eyebrow">AI Writing System</p>
        {children}
      </section>
    </main>
  );
}

function LoginScreen({
  sessionExpired,
  onAuthenticated,
}: {
  sessionExpired: boolean;
  onAuthenticated: (user: User) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mustReplacePassword, setMustReplacePassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirmation, setNewPasswordConfirmation] = useState("");

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
        setError(
          err instanceof ApiError && err.status === 401
            ? "아이디 또는 비밀번호를 확인해 주세요."
            : err instanceof ApiError && err.status === 409
              ? "새 비밀번호를 설정하지 못했습니다. 입력을 확인해 주세요."
              : "로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="login-page page-enter">
        <header className="login-heading">
          <p className="eyebrow">에-라잇</p>
          <h1>{mustReplacePassword ? "새 비밀번호 설정" : "쓴 것을 기억하는 집필 작업실"}</h1>
          <p>
            {mustReplacePassword
              ? "관리자가 만든 초기 비밀번호를 본인만 아는 비밀번호로 바꿔 주세요."
              : "설정과 인물, 지난 원고를 AI가 기억한 채로 이어서 씁니다."}
          </p>
        </header>

        {sessionExpired && (
          <p className="session-expired" role="status">
            세션이 만료되었습니다.
          </p>
        )}

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
        </form>
      </section>
    </main>
  );
}
