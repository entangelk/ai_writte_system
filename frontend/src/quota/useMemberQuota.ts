import { useCallback, useEffect, useState } from "react";
import { getMyQuota, type MyQuota } from "../api/client";

/**
 * 회원 자기 사용량 (Slice 8.4 W5=B).
 *
 * `useWritingBudget` 선례를 따르되 **캐시하지 않는다** — 예산은 배포 단위라 안 변하고
 * 사용량은 클릭마다 변한다. mount 시 한 번 읽고, 유료 요청이 끝나면 호출부가
 * `refresh()` 한다. **폴링은 없다**: 사용량은 이 화면의 행동으로만 움직이므로
 * 주기 조회는 조용한 배경 트래픽이 될 뿐이다.
 *
 * 실패는 삼킨다. 잔여 표시는 **보조 정보**여서, 여기서 화면을 에러로 만들면 조회
 * 하나가 글쓰기를 막는다 — 진짜 초과는 유료 요청 자체가 402로 알려 준다.
 */

/** 테스트 전용 오프라인 값. 있으면 이 훅은 네트워크를 아예 쓰지 않는다. */
let seeded: MyQuota | null = null;

/**
 * 테스트 전용 — mount·refresh 의 fetch 를 통째로 건너뛴다.
 *
 * `seedWritingBudgetCache` 와 같은 이유이자 같은 모양이다: 화면 테스트는 유료 요청의
 * 응답 **시퀀스**를 세는데, 보조 조회가 그 사이에 끼면 세던 것이 어긋난다. 갱신
 * 자체(유료 요청 뒤 다시 읽는다)는 시드하지 않는 별도 셀이 잠근다.
 */
export function seedMemberQuota(quota: MyQuota): void {
  seeded = quota;
}

/** 테스트 전용: 시드를 지워 실제 조회로 되돌린다. */
export function resetMemberQuota(): void {
  seeded = null;
}

export function useMemberQuota(): {
  quota: MyQuota | null;
  refresh: () => void;
} {
  const [quota, setQuota] = useState<MyQuota | null>(seeded);

  const refresh = useCallback(() => {
    if (seeded !== null) {
      setQuota(seeded);
      return;
    }
    getMyQuota()
      .then(setQuota)
      .catch(() => {
        /* 보조 정보다 — 위 주석 참조 */
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { quota, refresh };
}

/** "남은 사용 N회". 무제한이면 표시할 것이 없다(무제한을 숫자로 말하지 않는다). */
export function describeRemaining(quota: MyQuota | null): string | null {
  if (quota === null) {
    return null;
  }
  if (quota.status === "suspended") {
    return "계정 정지됨";
  }
  if (quota.unlimited || quota.remaining === null) {
    return null;
  }
  return `남은 사용 ${quota.remaining}회`;
}
