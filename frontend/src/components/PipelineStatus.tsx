import { PHASE_ORDER, useMeetingStore } from "../store/meetingStore";

const LABELS: Record<string, string> = {
  idle: "空闲",
  planning: "Planner",
  diarizing: "说话人分离",
  extracting: "待办抽取",
  structuring: "KG 结构化",
  critiquing: "Critic",
  awaiting_human: "人工审核",
  approved: "已通过",
  rejected: "已驳回",
};

export function PipelineStatus() {
  const phase = useMeetingStore((s) => s.phase);
  const idx = PHASE_ORDER.indexOf(phase);

  return (
    <div className="pipeline">
      {PHASE_ORDER.filter((p) => p !== "idle" && p !== "rejected").map((p, i) => {
        const done = i < idx;
        const active = p === phase;
        const human = p === "awaiting_human";
        let cls = "phase-chip";
        if (done) cls += " done";
        if (active) cls += human ? " human active" : " active";
        return (
          <span key={p} className={cls}>
            {LABELS[p] || p}
          </span>
        );
      })}
    </div>
  );
}
