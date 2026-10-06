/**
 * 작품 기억(정본 canonical memory)의 표시용 라벨·제목 — ProjectOverview 요약과
 * 설정의 작품 기억 탭(2026-10-06)이 같이 쓴다. 백엔드 리터럴의 UI 문구 정본은
 * 이 파일이다(activityActions.ts 와 같은 자리).
 */
import type { CanonicalMemory } from "../api/client";

export const MEMORY_TYPE_LABELS: Record<string, string> = {
  character_observation: "인물",
  event_observation: "사건",
  open_question_observation: "떡밥·미해결 질문",
};

/** payload 필드키 → 사람 문구. taxonomy 필드 집합 그대로(edit 은 키 집합 불변). */
export const MEMORY_FIELD_LABELS: Record<string, string> = {
  name: "이름",
  observation: "관찰",
  aspect: "측면",
  event: "사건",
  question: "질문",
};

export const MEMORY_PROVENANCE_LABELS: Record<string, string> = {
  source_observed: "원문 관찰",
  ai_inferred: "AI 추론",
  human_edited: "사람 수정",
};

export function memoryTypeLabel(memoryType: string): string {
  return MEMORY_TYPE_LABELS[memoryType] ?? memoryType;
}

export function memoryProvenanceLabel(provenance: string): string {
  return MEMORY_PROVENANCE_LABELS[provenance] ?? provenance;
}

export function memoryFieldLabel(field: string): string {
  return MEMORY_FIELD_LABELS[field] ?? field;
}

export function memoryTitle(memory: CanonicalMemory): string {
  const payload = memory.payload;
  const preferred =
    memory.memory_type === "character_observation"
      ? payload.name
      : memory.memory_type === "event_observation"
        ? payload.event
        : payload.question;
  return typeof preferred === "string" ? preferred : "정본 항목";
}

/** 목록·상세가 함께 보여 주는 본문 — 제목이 아닌 관찰 내용 축. */
export function memoryBody(memory: CanonicalMemory): string {
  const value =
    memory.memory_type === "character_observation"
      ? memory.payload.observation
      : memory.memory_type === "event_observation"
        ? memory.payload.event
        : memory.payload.question;
  return typeof value === "string" ? value : "";
}
