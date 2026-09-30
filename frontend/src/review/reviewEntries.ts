import type { ReviewIdentityGroup, ReviewInboxItem } from "../api/client";

/**
 * One rendered entry: either a lone candidate or a whole identity group.
 *
 * The server sends a flat item list where every member of a group repeats the
 * same `identity_group` object, so the grouping happens here. Order is first
 * appearance — a group sits where its first member did, which keeps the list
 * stable against member churn (a member leaving the inbox must not make the
 * group jump).
 */
export type InboxEntry =
  | { kind: "candidate"; item: ReviewInboxItem }
  | { kind: "group"; group: ReviewIdentityGroup; members: ReviewInboxItem[] };

export function buildEntries(items: ReviewInboxItem[]): InboxEntry[] {
  const entries: InboxEntry[] = [];
  const byGroup = new Map<string, Extract<InboxEntry, { kind: "group" }>>();
  for (const item of items) {
    const group = item.identity_group ?? null;
    if (group === null) {
      entries.push({ kind: "candidate", item });
      continue;
    }
    const existing = byGroup.get(group.group_id);
    if (existing === undefined) {
      const entry = {
        kind: "group" as const,
        group,
        members: [item],
      };
      byGroup.set(group.group_id, entry);
      entries.push(entry);
    } else {
      existing.members.push(item);
    }
  }
  return entries;
}

