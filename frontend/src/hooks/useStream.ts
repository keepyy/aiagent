import { useCallback, useRef } from "react";
import { apiUrl } from "../config";
import { useMeetingStore } from "../store/meetingStore";
import type { MeetingState, PipelinePhase, StreamEvent } from "../types";

const TERMINAL_TYPES = new Set([
  "completed",
  "awaiting_human",
  "finalized",
  "error",
  "app_error",
]);

const TERMINAL_PHASES = new Set<PipelinePhase>([
  "awaiting_human",
  "approved",
  "rejected",
  "failed",
]);

function isPipelineDone(data: StreamEvent): boolean {
  if (data.type === "app_error") return true;
  if (TERMINAL_TYPES.has(data.type)) return data.type !== "error";
  if (data.phase && TERMINAL_PHASES.has(data.phase as PipelinePhase)) return true;
  if (data.state?.phase && TERMINAL_PHASES.has(data.state.phase as PipelinePhase))
    return true;
  return false;
}

async function fetchMeetingState(meetingId: string) {
  const res = await fetch(apiUrl(`/api/meetings/${meetingId}/state`));
  if (!res.ok) return null;
  return res.json() as Promise<{
    state?: MeetingState;
    next?: string[];
  }>;
}

function applyStateFromPoll(
  body: { state?: MeetingState; next?: string[] },
  mergeState: (p: Partial<MeetingState>) => void,
  finishProcessing: () => void
): boolean {
  const st = body.state;
  const next = body.next || [];
  if (!st) return false;

  mergeState(st);
  if (next.includes("human_review")) {
    mergeState({ phase: "awaiting_human" });
    finishProcessing();
    return true;
  }
  if (st.phase && TERMINAL_PHASES.has(st.phase as PipelinePhase)) {
    finishProcessing();
    return true;
  }
  if (st.critic_passed && (st.utterances?.length ?? 0) > 0) {
    finishProcessing();
    return true;
  }
  return false;
}

export function useMeetingStream() {
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const push = useMeetingStore((s) => s.pushStreamEvent);
  const setProcessing = useMeetingStore((s) => s.setProcessing);
  const setError = useMeetingStore((s) => s.setError);
  const mergeState = useMeetingStore((s) => s.mergeState);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const finishProcessing = useCallback(
    (data?: StreamEvent) => {
      stopPolling();
      setProcessing(false);
      if (data?.type === "error" || data?.type === "app_error") {
        setError(data.message || "处理失败");
      }
    },
    [stopPolling, setProcessing, setError]
  );

  const pollState = useCallback(
    (meetingId: string) => {
      stopPolling();
      let attempts = 0;

      const tick = async () => {
        attempts += 1;
        if (attempts > 90) {
          finishProcessing();
          return;
        }
        try {
          const body = await fetchMeetingState(meetingId);
          if (body && applyStateFromPoll(body, mergeState, () => finishProcessing())) {
            stopPolling();
          }
        } catch {
          /* retry */
        }
      };

      void tick();
      pollRef.current = setInterval(() => void tick(), 1200);
    },
    [stopPolling, mergeState, finishProcessing]
  );

  const handle = useCallback(
    (raw: string) => {
      try {
        const data = JSON.parse(raw) as StreamEvent;
        push(data);
        if (data.phase) mergeState({ phase: data.phase as PipelinePhase });
        if (data.state) mergeState(data.state);
        if (data.partial) mergeState(data.partial);
        if (data.type === "awaiting_human") {
          mergeState({
            ...(data.state || {}),
            phase: "awaiting_human",
          });
          window.dispatchEvent(new CustomEvent("meeting:awaiting_human"));
        }
        if (data.type === "app_error") {
          finishProcessing({ ...data, type: "app_error" });
          return;
        }
        if (isPipelineDone(data)) {
          finishProcessing(data);
        }
      } catch {
        /* ignore */
      }
    },
    [push, mergeState, finishProcessing]
  );

  const connect = useCallback(
    (meetingId: string) => {
      esRef.current?.close();
      stopPolling();
      pollState(meetingId);

      const es = new EventSource(apiUrl(`/api/meetings/${meetingId}/stream`));
      esRef.current = es;

      const onMsg = (e: MessageEvent) => handle(e.data);

      es.addEventListener("connected", onMsg);
      es.addEventListener("phase", onMsg);
      es.addEventListener("state", onMsg);
      es.addEventListener("awaiting_human", onMsg);
      es.addEventListener("completed", onMsg);
      es.addEventListener("finalized", onMsg);
      es.addEventListener("started", onMsg);
      es.addEventListener("message", onMsg);
      es.addEventListener("app_error", onMsg);

      es.onerror = () => {
        /* 依赖轮询 /state 收尾 */
      };
    },
    [handle, pollState, stopPolling]
  );

  const disconnect = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    stopPolling();
  }, [stopPolling]);

  return { connect, disconnect, finishProcessing, stopPolling };
}
