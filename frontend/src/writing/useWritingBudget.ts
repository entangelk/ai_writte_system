import { useEffect, useState } from "react";
import { getWritingContextBudget, type WritingContextBudget } from "../api/client";

type BudgetByPreset = WritingContextBudget["context_budget_tokens"];

// K-4: WritingPanel 진입 시 1회만 /writing/budget 을 부르고 결과를 모듈 캐시에 둬 탭 전환
// (패널이 계속 마운트)에서 재패치하지 않는다. 예산은 배포·출력 프리셋 단위라 프로젝트에서
// 변하지 않는다. 실패(transport/5xx/403)하면 null — 예산을 모르면 경고를 안 하는 쪽이 거짓
// 경고보다 낫다(안전 축소).
const cache = new Map<string, BudgetByPreset>();

/** 테스트 전용: 모듈 캐시를 비운다. */
export function resetWritingBudgetCache(): void {
  cache.clear();
}

/** 테스트 전용: 캐시에 예산을 시드해 mount fetch 를 스킵한다(기존 fetch 시퀀스를 안 건드린다). */
export function seedWritingBudgetCache(
  projectId: string,
  budget: BudgetByPreset,
): void {
  cache.set(projectId, budget);
}

export function useWritingBudget(
  projectId: string,
): { budgetByPreset: BudgetByPreset | null } {
  const [budgetByPreset, setBudget] = useState<BudgetByPreset | null>(
    () => cache.get(projectId) ?? null,
  );

  useEffect(() => {
    if (cache.has(projectId)) {
      setBudget(cache.get(projectId) ?? null);
      return;
    }
    let cancelled = false;
    getWritingContextBudget(projectId)
      .then((budget) => {
        if (!cancelled) {
          cache.set(projectId, budget.context_budget_tokens);
          setBudget(budget.context_budget_tokens);
        }
      })
      .catch(() => {
        // 안전 축소: 예산을 모르면 경고를 안 한다(거짓 경고 방지).
        if (!cancelled) setBudget(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return { budgetByPreset };
}
