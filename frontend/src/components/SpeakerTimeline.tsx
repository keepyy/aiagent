import type { Utterance } from "../types";

export function SpeakerTimeline({ utterances }: { utterances: Utterance[] }) {
  if (!utterances?.length) {
    return <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>暂无发言分段</p>;
  }
  return (
    <div>
      {utterances.map((u) => (
        <div key={u.id} className="utterance">
          <span className="speaker">{u.speaker}</span>
          <span>{u.text}</span>
        </div>
      ))}
    </div>
  );
}
