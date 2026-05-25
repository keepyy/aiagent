import { useMeetingStore } from "../store/meetingStore";
import type { ReviewQueueItem } from "../types";

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
}

function ReviewCard({ item, selected, onSelect }: { item: ReviewQueueItem; selected: boolean; onSelect: () => void }) {
  const previews = item.action_previews || [];
  const passed = item.critic_passed;
  
  const getStatusColor = (status: string) => {
    switch (status) {
      case "已批准":
        return "var(--success)";
      case "已驳回":
        return "var(--danger)";
      case "已编辑":
        return "var(--warn)";
      default:
        return "var(--human)";
    }
  };
  
  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case "已批准":
        return "pass";
      case "已驳回":
        return "fail";
      case "已编辑":
        return "warn";
      default:
        return "";
    }
  };

  return (
    <div
      className={`review-item ${selected ? "selected" : ""}`}
      onClick={onSelect}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
      role="button"
      tabIndex={0}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
        <strong>{item.meeting_id.slice(0, 8)}…</strong>
        <span className={`badge ${getStatusBadgeClass(item.human_status || "")}`} style={{ color: getStatusColor(item.human_status || "") }}>
          {item.human_status || "待人工审核"}
        </span>
      </div>

      <small style={{ display: "block", marginTop: "0.35rem", color: "var(--text)" }}>
        {item.summary || item.transcript_preview}
      </small>

      <small style={{ display: "block", marginTop: "0.35rem", color: "var(--muted)" }}>
        发言 {item.utterance_count ?? "—"} · 待办 {item.todo_count ?? "—"} · 行动项{" "}
        {item.action_count ?? 0}
      </small>

      <small style={{ display: "block", marginTop: "0.25rem" }}>
        <span className={`badge ${passed ? "pass" : "fail"}`}>{item.critic_label || "机审"}</span>
        {item.critic_score != null && (
          <span style={{ color: "var(--muted)", marginLeft: "0.35rem" }}>
            质量分 {item.critic_score.toFixed(2)}（机审，非人工终审）
          </span>
        )}
      </small>

      {previews.length > 0 && (
        <ul
          style={{
            margin: "0.4rem 0 0",
            paddingLeft: "1rem",
            fontSize: "0.72rem",
            color: "var(--muted)",
          }}
        >
          {previews.map((p, idx) => (
            <li key={idx}>
              <strong style={{ color: "var(--accent2)" }}>{p.owner}</strong>
              <span className="badge" style={{ marginLeft: "0.25rem" }}>
                {p.type}
              </span>
              {p.title}
              {p.due_date ? ` · ${p.due_date}` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ReviewQueuePanel({ selectedId, onSelect, onRefresh }: Props) {
  const items = useMeetingStore((s) => s.reviewQueue);

  return (
    <div className="panel">
      <h2>人工审核队列 (HITL)</h2>
      <p style={{ fontSize: "0.72rem", color: "var(--muted)", margin: "0 0 0.5rem" }}>
        卡片展示的是机审摘要，批准/驳回后方为最终结论。
      </p>
      <button type="button" className="btn-ghost" onClick={onRefresh} style={{ marginBottom: "0.5rem" }}>
        刷新队列
      </button>
      {!items.length ? (
        <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>队列为空</p>
      ) : (
        items.map((item) => (
          <ReviewCard
            key={item.meeting_id}
            item={item}
            selected={selectedId === item.meeting_id}
            onSelect={() => onSelect(item.meeting_id)}
          />
        ))
      )}
    </div>
  );
}
