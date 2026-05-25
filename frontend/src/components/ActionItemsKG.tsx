import type { ActionItem } from "../types";

export function ActionItemsKG({ items }: { items: ActionItem[] }) {
  if (!items?.length) {
    return <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>暂无结构化行动项</p>;
  }
  return (
    <div>
      {items.map((a) => (
        <div key={a.action_id} className="kg-card">
          <div>
            <span className="badge">{a.action_type}</span>
            <span className="badge">{a.priority}</span>
            <strong> {a.title}</strong>
          </div>
          <div className="kg-slots">
            <span>
              owner: <strong>{a.owner || "—"}</strong>
            </span>
            <span>
              due: <strong>{a.due_date || "—"}</strong>
            </span>
            <span>
              entities: <strong>{a.related_entities?.join(", ") || "—"}</strong>
            </span>
            <span>
              deps: <strong>{a.dependencies?.join(", ") || "—"}</strong>
            </span>
            <span>
              sources: <strong>{a.source_utterance_ids?.join(", ") || "—"}</strong>
            </span>
            <span>
              conf: <strong>{(a.confidence * 100).toFixed(0)}%</strong>
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
