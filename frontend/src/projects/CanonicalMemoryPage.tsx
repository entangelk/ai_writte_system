import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  describeApiError,
  listCanonicalMemory,
  mergeCanonicalMemory,
  putCanonicalMemory,
  type CanonicalMemory,
} from "../api/client";
import {
  memoryBody,
  memoryFieldLabel,
  memoryProvenanceLabel,
  memoryTitle,
  memoryTypeLabel,
} from "./memoryPresentation";

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

/** canonical 항목의 사슬을 옛 버전부터 배열한다(append-only 이력). */
function versionChain(
  entry: CanonicalMemory,
  byId: Map<string, CanonicalMemory>,
): CanonicalMemory[] {
  const chain: CanonicalMemory[] = [];
  let cursor: CanonicalMemory | undefined = entry;
  while (cursor !== undefined) {
    chain.unshift(cursor);
    cursor =
      cursor.supersedes === null ? undefined : byId.get(cursor.supersedes);
  }
  return chain;
}

/** 병합 폼의 초안 관찰 — 양쪽을 구분 표시로 이어 미리 채운다(편집 기반 통합). */
function joinedObservation(
  survivor: CanonicalMemory,
  absorbed: CanonicalMemory,
): string {
  const a = memoryBody(survivor);
  const b = memoryBody(absorbed);
  return b === "" ? a : `${a}\n${b}`;
}

/**
 * 설정 탭 "작품 기억" (2026-10-06) — 승인된 정본 기억의 목록·상세·이력·수정·병합.
 *
 * 개요 화면의 요약 그리드가 제목만 보여 줘서 "무엇이 승인됐는지"를 알 수 없다는
 * 것이 이 탭의 동기다(오너 지적). 수정·병합 모두 append-only 다 — 저장하면 새
 * canonical 버전이 발행되고 옛 버전은 superseded 로 보존된다(서버 계약, 같은 날
 * B안·A안). 병합은 분석이 "나"/"주인공" 처럼 갈라 만든 같은 인물의 정본 둘을 하나로
 * 합친다: 결과는 생존 쪽의 다음 버전이고 흡수된 항목은 merged_into 로 결과를
 * 가리키며 이력에 남는다.
 */
export function CanonicalMemoryPage({
  projectId,
  archived,
}: {
  projectId: string;
  archived: boolean;
}) {
  const [entries, setEntries] = useState<CanonicalMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  // 편집 초안 — 후보 수정(ReviewInboxDetail)과 같은 규칙: payload 는 키 집합이
  // 정확히 고정돼 있어 기존 필드를 그 자리에서 고친다(추가·제거는 서버가 거절).
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [saving, setSaving] = useState(false);
  // 병합: 1단계 생존 항목 선택(mergeSourceId) → 2단계 흡수 상대 선택 → 폼.
  const [mergeSourceId, setMergeSourceId] = useState<string | null>(null);
  const [mergeTargetId, setMergeTargetId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void listCanonicalMemory(projectId)
      .then((response) => {
        if (active) {
          setEntries(response.memory);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (active) setError(describeApiError(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const canonical = entries.filter((entry) => entry.status === "canonical");
  const mergeSource =
    mergeSourceId === null ? undefined : byId.get(mergeSourceId);
  const mergeTarget =
    mergeTargetId === null || mergeSource === undefined
      ? undefined
      : byId.get(mergeTargetId);
  // 병합 대상 후보 — 같은 타입(1차 인물)의 다른 canonical 만.
  const mergeCandidates =
    mergeSource === undefined
      ? []
      : canonical.filter(
          (entry) =>
            entry.id !== mergeSource.id &&
            entry.memory_type === mergeSource.memory_type,
        );

  function startEdit(entry: CanonicalMemory): void {
    const next: Record<string, string> = {};
    for (const [field, value] of Object.entries(entry.payload)) {
      next[field] = typeof value === "string" ? value : renderValue(value);
    }
    setDraft(next);
    setEditingId(entry.id);
  }

  /** 병합 폼을 연다 — 관찰은 양쪽을 이어 미리 채우고 사람이 다듬는다. */
  function startMergeDraft(
    survivor: CanonicalMemory,
    absorbed: CanonicalMemory,
  ): void {
    const next: Record<string, string> = {};
    for (const [field, value] of Object.entries(survivor.payload)) {
      next[field] = typeof value === "string" ? value : renderValue(value);
    }
    next.observation = joinedObservation(survivor, absorbed);
    setDraft(next);
    setEditingId(survivor.id);
  }

  async function reload(): Promise<void> {
    const listed = await listCanonicalMemory(projectId);
    setEntries(listed.memory);
  }

  async function save(entry: CanonicalMemory): Promise<void> {
    if (draft === null || saving) return;
    setSaving(true);
    setNotice(null);
    try {
      const response = await putCanonicalMemory(projectId, entry.id, {
        base_version: entry.version,
        idempotency_key: crypto.randomUUID(),
        payload: draft,
      });
      setError(null);
      setNotice(
        response.idempotent_replay
          ? "이미 저장된 편집입니다(재시도가 그대로 반영됐습니다)."
          : `기억 version ${response.memory.version}을 저장했습니다. 이전 버전은 이력에 보존됩니다.`,
      );
      setEditingId(null);
      setDraft(null);
      setExpandedId(response.memory.id);
      await reload();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  async function saveMerge(
    survivor: CanonicalMemory,
    absorbed: CanonicalMemory,
  ): Promise<void> {
    if (draft === null || saving) return;
    setSaving(true);
    setNotice(null);
    try {
      const response = await mergeCanonicalMemory(projectId, {
        survivor_memory_id: survivor.id,
        absorbed_memory_id: absorbed.id,
        base_survivor_version: survivor.version,
        base_absorbed_version: absorbed.version,
        idempotency_key: crypto.randomUUID(),
        payload: draft,
      });
      setError(null);
      setNotice(
        response.idempotent_replay
          ? "이미 저장된 병합입니다(재시도가 그대로 반영됐습니다)."
          : `병합했습니다 — 기억 version ${response.memory.version}. 흡수된 기억의 이력은 아래에 보존됩니다.`,
      );
      setEditingId(null);
      setDraft(null);
      setMergeSourceId(null);
      setMergeTargetId(null);
      setExpandedId(response.memory.id);
      await reload();
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="status-copy">작품 기억을 불러오는 중…</p>;
  }

  const mergingPair =
    mergeSource !== undefined && mergeTarget !== undefined
      ? { survivor: mergeSource, absorbed: mergeTarget }
      : null;

  return (
    <section className="overview-section" aria-labelledby="memory-tab-heading">
      <div className="overview-heading">
        <div>
          <p className="eyebrow">Canonical memory · 정본</p>
          <h2 id="memory-tab-heading">작품 기억</h2>
        </div>
        <Link
          className="inline-navigation-link"
          to={`/projects/${projectId}/review`}
        >
          검토함 →
        </Link>
      </div>

      <p className="form-hint">
        검토함에서 승인된 기억의 정본 목록입니다. 수정·병합하면 새 version 이
        발행되고 이전 값은 이력에 보존됩니다(append-only).
      </p>

      {error !== null && <p className="alert" role="alert">{error}</p>}
      {notice !== null && (
        <p className="source-jump-notice" role="status">{notice}</p>
      )}

      {archived && (
        <p className="read-only-note">
          보관된 프로젝트의 작품 기억은 읽기만 가능합니다.
        </p>
      )}

      {mergeSource !== undefined && (
        <div className="merge-hint" role="status">
          <p>
            <strong>{memoryTitle(mergeSource)}</strong> 와(과) 합칠 다른 기억을
            아래에서 선택하세요. 같은 종류(인물)의 항목만 선택할 수 있습니다.
          </p>
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              setMergeSourceId(null);
              setMergeTargetId(null);
            }}
          >
            병합 취소
          </button>
        </div>
      )}

      {canonical.length === 0 ? (
        <div className="empty-state">
          <p>승인된 작품 기억이 없습니다.</p>
          <span>분석 후보는 검토함에서 승인한 뒤 여기에 표시됩니다.</span>
        </div>
      ) : (
        <ul className="memory-list">
          {canonical.map((entry) => {
            const chain = versionChain(entry, byId);
            // 병합으로 흡수돼 이 항목으로 이어진 사슬들(앞링크의 역방향).
            const absorbedChains = entries
              .filter((candidate) => candidate.merged_into === entry.id)
              .map((absorbed) => versionChain(absorbed, byId));
            const editing = editingId === entry.id;
            const isMergingSurvivor =
              mergingPair !== null &&
              mergingPair.survivor.id === entry.id &&
              draft !== null;
            const editIncomplete =
              draft !== null && Object.values(draft).some((v) => v.trim() === "");
            return (
              <li className="memory-item" key={entry.id}>
                <div className="memory-item-head">
                  <span>
                    {memoryTypeLabel(entry.memory_type)} · v{entry.version} ·{" "}
                    {memoryProvenanceLabel(entry.provenance)}
                  </span>
                  <strong>{memoryTitle(entry)}</strong>
                  <p className="memory-item-body">{memoryBody(entry)}</p>
                  <div className="row-actions">
                    <button
                      type="button"
                      className="ghost"
                      aria-expanded={expandedId === entry.id}
                      onClick={() =>
                        setExpandedId(expandedId === entry.id ? null : entry.id)
                      }
                    >
                      {expandedId === entry.id ? "접기" : "상세·이력"}
                    </button>
                    {!archived && !editing && (
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => startEdit(entry)}
                      >
                        수정
                      </button>
                    )}
                    {!archived && !editing && entry.memory_type === "character_observation" && (
                      <button
                        type="button"
                        className="ghost"
                        onClick={() => {
                          setMergeSourceId(entry.id);
                          setMergeTargetId(null);
                        }}
                      >
                        다른 기억과 병합…
                      </button>
                    )}
                    {!archived &&
                      mergeSource !== undefined &&
                      mergeSource.id !== entry.id &&
                      mergeCandidates.some((candidate) => candidate.id === entry.id) && (
                        <button
                          type="button"
                          onClick={() => {
                            setMergeTargetId(entry.id);
                            startMergeDraft(mergeSource, entry);
                          }}
                        >
                          이 항목과 병합
                        </button>
                      )}
                  </div>
                </div>

                {isMergingSurvivor && mergingPair !== null ? (
                  <form
                    className="edit-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (!editIncomplete) {
                        void saveMerge(
                          mergingPair.survivor,
                          mergingPair.absorbed,
                        );
                      }
                    }}
                  >
                    <p className="row-meta">
                      병합 — <strong>{memoryTitle(mergingPair.survivor)}</strong>
                      에 <strong>{memoryTitle(mergingPair.absorbed)}</strong> 을(를)
                      흡수합니다. 관찰에 양쪽 내용이 이어져 있으니 하나의 문장으로
                      다듬어 저장하세요.
                    </p>
                    {Object.entries(draft).map(([field, value]) => (
                      <div className="edit-field" key={field}>
                        <label htmlFor={`memory-edit-${entry.id}-${field}`}>
                          {memoryFieldLabel(field)}
                        </label>
                        <textarea
                          id={`memory-edit-${entry.id}-${field}`}
                          value={value}
                          rows={field === "name" ? 1 : 5}
                          onChange={(event) =>
                            setDraft({
                              ...draft,
                              [field]: event.target.value,
                            })
                          }
                        />
                      </div>
                    ))}
                    <div className="row-actions">
                      <button type="submit" disabled={editIncomplete || saving}>
                        병합 저장
                      </button>
                      <button
                        type="button"
                        className="ghost"
                        disabled={saving}
                        onClick={() => {
                          setEditingId(null);
                          setDraft(null);
                          setMergeSourceId(null);
                          setMergeTargetId(null);
                        }}
                      >
                        취소
                      </button>
                    </div>
                  </form>
                ) : editing && draft !== null ? (
                  <form
                    className="edit-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      if (!editIncomplete) void save(entry);
                    }}
                  >
                    {Object.entries(draft).map(([field, value]) => (
                      <div className="edit-field" key={field}>
                        <label htmlFor={`memory-edit-${entry.id}-${field}`}>
                          {memoryFieldLabel(field)}
                        </label>
                        <textarea
                          id={`memory-edit-${entry.id}-${field}`}
                          value={value}
                          rows={field === "name" ? 1 : 3}
                          onChange={(event) =>
                            setDraft({
                              ...draft,
                              [field]: event.target.value,
                            })
                          }
                        />
                      </div>
                    ))}
                    <div className="row-actions">
                      <button type="submit" disabled={editIncomplete || saving}>
                        저장
                      </button>
                      <button
                        type="button"
                        className="ghost"
                        disabled={saving}
                        onClick={() => {
                          setEditingId(null);
                          setDraft(null);
                        }}
                      >
                        취소
                      </button>
                    </div>
                  </form>
                ) : expandedId === entry.id ? (
                  <div className="memory-item-detail">
                    <dl className="detail-fields">
                      {Object.entries(entry.payload).map(([field, value]) => (
                        <div className="detail-field" key={field}>
                          <dt>{memoryFieldLabel(field)}</dt>
                          <dd>{renderValue(value)}</dd>
                        </div>
                      ))}
                      <div className="detail-field">
                        <dt>근거</dt>
                        <dd>{entry.source_ref_ids.length}건</dd>
                      </div>
                    </dl>
                    <h3 className="section-title">버전 이력</h3>
                    <ul className="memory-history">
                      {chain.map((version) => (
                        <li key={version.id}>
                          <span>
                            v{version.version} ·{" "}
                            {version.status === "canonical"
                              ? "현재 정본"
                              : "보존됨"}
                          </span>
                          <strong>{memoryTitle(version)}</strong>
                          <p className="memory-item-body">
                            {memoryBody(version)}
                          </p>
                        </li>
                      ))}
                    </ul>
                    {absorbedChains.length > 0 && (
                      <>
                        <h3 className="section-title">병합으로 합쳐진 기억</h3>
                        <ul className="memory-history">
                          {absorbedChains.flat().map((version) => (
                            <li key={version.id}>
                              <span>
                                v{version.version} · 보존됨 · 병합됨 →{" "}
                                {memoryTitle(entry)}(v{entry.version})
                              </span>
                              <strong>{memoryTitle(version)}</strong>
                              <p className="memory-item-body">
                                {memoryBody(version)}
                              </p>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
