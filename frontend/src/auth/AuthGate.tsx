import { useCallback, useEffect, useState } from "react";
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

export function AuthGate({ children }: { children: React.ReactNode }) {
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
        }}
      />
    );
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link className="brand" to="/">AI Writing System</Link>
        <div className="session-menu">
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
      });
      setPassword("");
      onAuthenticated(result.user);
    } catch (err) {
      setPassword("");
      setError(
        err instanceof ApiError && err.status === 401
          ? "아이디 또는 비밀번호를 확인해 주세요."
          : "로그인하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="login-page page-enter">
        <header className="login-heading">
          <p className="eyebrow">AI Writing System</p>
          <h1>작업실 입장</h1>
          <p>계정으로 로그인해 내 프로젝트와 원고를 이어서 작업하세요.</p>
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
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error !== null && (
            <p className="login-error" role="alert">{error}</p>
          )}
          <button
            className="auth-submit"
            type="submit"
            disabled={username.trim() === "" || password === "" || submitting}
          >
            {submitting ? "확인하는 중…" : "작업실 입장"}
          </button>
        </form>
      </section>
    </main>
  );
}
