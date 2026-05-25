import { useMeetingStore } from "../store/meetingStore";

export function StreamLog() {
  const log = useMeetingStore((s) => s.streamLog);
  return (
    <div className="panel">
      <h2>流式事件 (SSE)</h2>
      <div className="stream-log">
        {log.length === 0 ? (
          <div>等待事件…</div>
        ) : (
          log
            .slice()
            .reverse()
            .map((e, i) => (
              <div key={i}>
                [{e.type}] {e.phase || e.node || ""} {e.message || JSON.stringify(e.partial || "").slice(0, 60)}
              </div>
            ))
        )}
      </div>
    </div>
  );
}
