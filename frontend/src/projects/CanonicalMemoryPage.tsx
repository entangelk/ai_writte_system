import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  describeApiError,
  listCanonicalMemory,
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

/**
 * 설정 탭 "작품 기억" (2026-10-06) — 승인된 정본 기억의 목록·상세·이력·수정.
 *
 * 개요 화면의 요약 그리드가 제목만 보여 줘서 "무엇이 승인됐는지"를 알 수 없다는
 * 것이 이 탭의 동기다(오너 지적). 수정은 append-only 다 — 저장하면 새 canonical
 * 버전이 발행되고 옛 버전은 superseded 로 보존된다(서버 계약, 같은 날 B안).
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

  function startEdit(entry: CanonicalMemory): void {
    const next: Record<string, string> = {};
    for (const [field, value] of Object.entries(entry.payload)) {
      next[field] = typeof value === "string" ? value : renderValue(value);
    }
    setDraft(next);
    setEditingId(entry.id);
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
      const listed = await listCanonicalMemory(projectId);
      setEntries(listed.memory);
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <p className="status-copy">작품 기억을 불러오는 중…</p>;
  }

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
        검토함에서 승인된 기억의 정본 목록입니다. 수정하면 새 version 이 발행되고
        이전 값은 이력에 보존됩니다(append-only).
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

      {canonical.length === 0 ? (
        <div className="empty-state">
          <p>승인된 작품 기억이 없습니다.</p>
          <span>분석 후보는 검토함에서 승인한 뒤 여기에 표시됩니다.</span>
        </div>
      ) : (
        <ul className="memory-list">
          {canonical.map((entry) => {
            const chain = versionChain(entry, byId);
            const editing = editingId === entry.id;
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
                  </div>
                </div>

                {editing && draft !== null ? (
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
