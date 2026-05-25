import { useCallback, useEffect, useState } from "react";
import { ActionItemsKG } from "./components/ActionItemsKG";
import { PipelineStatus } from "./components/PipelineStatus";
import { ReviewQueuePanel } from "./components/ReviewQueue";
import { SpeakerTimeline } from "./components/SpeakerTimeline";
import { StreamLog } from "./components/StreamLog";
import { apiUrl } from "./config";
import { useMeetingStream } from "./hooks/useStream";
import { useMeetingStore } from "./store/meetingStore";
import type { MeetingState } from "./types";

const SAMPLE = `主持人：今天我们过一下 Q2 上线进度和风险。
张三：后端接口下周可以联调，我负责把 OpenAPI 文档补齐。
李四：前端还有一个阻塞项，需要产品确认埋点方案，下周五前给结论。
王五：待办是本周五前提交压测报告，预算方面风险已经上报。`;

export default function App() {
  const transcript = useMeetingStore((s) => s.transcript);
  const setTranscript = useMeetingStore((s) => s.setTranscript);
  const meetingId = useMeetingStore((s) => s.meetingId);
  const state = useMeetingStore((s) => s.state);
  const isProcessing = useMeetingStore((s) => s.isProcessing);
  const error = useMeetingStore((s) => s.error);
  const setMeetingId = useMeetingStore((s) => s.setMeetingId);
  const setProcessing = useMeetingStore((s) => s.setProcessing);
  const mergeState = useMeetingStore((s) => s.mergeState);
  const setReviewQueue = useMeetingStore((s) => s.setReviewQueue);
  const reset = useMeetingStore((s) => s.reset);

  const { connect, disconnect } = useMeetingStream();
  const [selectedReview, setSelectedReview] = useState<string | null>(null);
  const [canDecide, setCanDecide] = useState(false);
  const setError = useMeetingStore((s) => s.setError);

  const refreshQueue = useCallback(async () => {
    const res = await fetch(apiUrl("/api/review-queue"));
    if (!res.ok) return;
    const data = await res.json();
    setReviewQueue(data.items || []);
  }, [setReviewQueue]);

  useEffect(() => {
    refreshQueue();
    const t = setInterval(refreshQueue, 8000);
    return () => clearInterval(t);
  }, [refreshQueue]);

  const checkPending = useCallback(async (id: string) => {
    try {
      const res = await fetch(apiUrl(`/api/meetings/${id}/pending`));
      if (!res.ok) {
        setCanDecide(false);
        return;
      }
      const data = await res.json();
      const isPending = Boolean(data.can_decide);
      setCanDecide(isPending);
      if (isPending) void refreshQueue();
    } catch {
      setCanDecide(false);
    }
  }, [refreshQueue]);

  useEffect(() => {
    if (meetingId && (state.phase === "awaiting_human" || selectedReview)) {
      void checkPending(meetingId);
    } else {
      setCanDecide(false);
    }
  }, [meetingId, state.phase, selectedReview, checkPending]);

  useEffect(() => {
    const onAwaiting = () => {
      void refreshQueue();
      if (meetingId) void checkPending(meetingId);
    };
    window.addEventListener("meeting:awaiting_human", onAwaiting);
    return () => window.removeEventListener("meeting:awaiting_human", onAwaiting);
  }, [meetingId, refreshQueue, checkPending]);

  const startProcess = async () => {
    if (transcript.trim().length < 10) return;
    reset();
    setTranscript(transcript);
    setProcessing(true);
    setError(null);
    try {
      const res = await fetch(apiUrl("/api/meetings/process"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript, max_retries: 2 }),
        signal: AbortSignal.timeout(15000),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(
          detail || `请求失败 (${res.status})，请确认后端已启动：http://127.0.0.1:8000/health`
        );
      }
      const data = await res.json();
      const id = data.meeting_id as string;
      if (!id) throw new Error("后端未返回 meeting_id");
      setMeetingId(id);
      connect(id);
      void refreshQueue();
    } catch (e) {
      const msg =
        e instanceof DOMException && e.name === "TimeoutError"
          ? "请求超时：请确认后端 http://127.0.0.1:8000 已启动"
          : String(e);
      useMeetingStore.getState().setError(msg);
      setProcessing(false);
    }
  };

  const loadReviewDetail = async (id: string) => {
    const res = await fetch(apiUrl(`/api/review-queue/${id}`));
    const data = await res.json();
    mergeState({ ...(data.state as MeetingState), phase: "awaiting_human" });
    setMeetingId(id);
    setSelectedReview(id);
    setProcessing(false);
  };

  const decide = async (decision: "approved" | "rejected" | "edited") => {
    const id = selectedReview || meetingId;
    if (!id) return;
    setError(null);
    try {
      const res = await fetch(apiUrl(`/api/review-queue/${id}/decide`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, edits: null }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || `审核失败 (${res.status})`);
      }
      const data = await res.json();
      mergeState({
        ...(data.state as MeetingState),
        phase: decision === "rejected" ? "rejected" : "approved",
        review_decision: decision,
      });
      setCanDecide(false);
      setSelectedReview(null);
      void refreshQueue();
      disconnect();
    } catch (e) {
      setError(String(e));
    }
  };

  const critic = state.critic_report;

  return (
    <>
      <h1>智能会议纪要系统</h1>
      <p className="subtitle">
        LangGraph · Plan-Executor-Critic · 知识图谱槽位 · Human-in-the-loop
      </p>

      <div className="layout">
        <div>
          <div className="panel">
            <h2>会议转写输入</h2>
            <textarea
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              placeholder="粘贴或输入带说话人标记的转写…"
            />
            <div className="actions-row">
              <button
                type="button"
                className="btn-primary"
                disabled={isProcessing || transcript.length < 10}
                onClick={startProcess}
              >
                {isProcessing ? "处理中…" : "启动多 Agent 流水线"}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setTranscript(SAMPLE)}
              >
                加载示例
              </button>
            </div>
            {meetingId && (
              <p style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: "0.5rem" }}>
                meeting_id: <code>{meetingId}</code>
              </p>
            )}
            {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
          </div>

          <div className="panel" style={{ marginTop: "1rem" }}>
            <h2>流水线状态</h2>
            <PipelineStatus />
            <pre className="arch-diagram">{`START → Planner → Diarize → Extract → Structure → Critic
                              ↑___________|  (retry, max 2)
                              ↓ pass
                         [INTERRUPT] Human Review → Finalize → END`}</pre>
            {critic && (
              <p style={{ fontSize: "0.85rem" }}>
                Critic{" "}
                <span className={`badge ${critic.passed ? "pass" : "fail"}`}>
                  {critic.passed ? "通过" : "待改进"}
                </span>{" "}
                得分 {critic.score ?? "—"}
              </p>
            )}
          </div>

          <div className="panel" style={{ marginTop: "1rem" }}>
            <h2>说话人分离</h2>
            <SpeakerTimeline utterances={state.utterances || []} />
          </div>

          <div className="panel" style={{ marginTop: "1rem" }}>
            <h2>待办项</h2>
            {(state.todos || []).map((t) => (
              <div key={t.id} className="kg-card">
                {t.text}
                <div className="kg-slots">
                  <span>
                    assignee: <strong>{t.assignee || "—"}</strong>
                  </span>
                  <span>
                    deadline: <strong>{t.deadline || "—"}</strong>
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="panel" style={{ marginTop: "1rem" }}>
            <h2>行动项 · 知识图谱槽位</h2>
            <ActionItemsKG items={state.action_items || []} />
          </div>

          {(state.phase === "awaiting_human" || selectedReview) && (
            <div className="panel" style={{ marginTop: "1rem", borderColor: "var(--human)" }}>
              <h2>人工审核 (HITL)</h2>
              <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                Critic 通过后图在 human_review 节点前 interrupt，由人工批准/驳回/编辑后 resume。
              </p>
              {!canDecide && (
                <p style={{ fontSize: "0.85rem", color: "var(--warn)" }}>
                  当前无法提交审核：审核队列为空或后端已重启导致状态丢失。请重新点击「启动多 Agent
                  流水线」，或确认 meeting_id 与后端为同一次会话。
                </p>
              )}
              <div className="actions-row">
                <button
                  type="button"
                  className="btn-success"
                  disabled={!canDecide}
                  onClick={() => decide("approved")}
                >
                  批准发布
                </button>
                <button
                  type="button"
                  className="btn-danger"
                  disabled={!canDecide}
                  onClick={() => decide("rejected")}
                >
                  驳回
                </button>
              </div>
            </div>
          )}
        </div>

        <aside>
          <ReviewQueuePanel
            selectedId={selectedReview}
            onSelect={(id) => loadReviewDetail(id)}
            onRefresh={refreshQueue}
          />
          <div style={{ marginTop: "1rem" }}>
            <StreamLog />
          </div>
        </aside>
      </div>
    </>
  );
}
