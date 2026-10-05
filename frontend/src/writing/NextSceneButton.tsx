import { useRef, useState } from "react";
import { describeApiError } from "../api/client";

export type NextSceneSeed = { requestId: string; title: string; text: string };
export type CreateNextScene = (seed: NextSceneSeed) => Promise<boolean>;

export function NextSceneButton({ seed, onCreate, disabled }: {
  seed: NextSceneSeed;
  onCreate: CreateNextScene;
  disabled: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);

  async function create() {
    if (busyRef.current || created || disabled) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      setCreated(await onCreate(seed));
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  return (
    <span>
      <button type="button" disabled={disabled || busy || created} onClick={() => void create()}>
        {busy ? "새 장면을 여는 중…" : created ? "새 장면을 열었습니다" : "이 내용으로 다음 장면 만들기"}
      </button>
      {error !== null && <span className="candidate-copy-error" role="alert">{error}</span>}
    </span>
  );
}
