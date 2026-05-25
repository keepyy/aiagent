import { create } from "zustand";
import type { MeetingState, PipelinePhase, ReviewQueueItem, StreamEvent } from "../types";

const PHASE_ORDER: PipelinePhase[] = [
  "idle",
  "planning",
  "diarizing",
  "extracting",
  "structuring",
  "critiquing",
  "awaiting_human",
  "approved",
  "rejected",
];

interface MeetingStore {
  meetingId: string | null;
  phase: PipelinePhase;
  transcript: string;
  state: MeetingState;
  streamLog: StreamEvent[];
  reviewQueue: ReviewQueueItem[];
  isProcessing: boolean;
  error: string | null;

  setTranscript: (t: string) => void;
  setMeetingId: (id: string | null) => void;
  setPhase: (p: PipelinePhase) => void;
  mergeState: (partial: Partial<MeetingState>) => void;
  pushStreamEvent: (e: StreamEvent) => void;
  setReviewQueue: (items: ReviewQueueItem[]) => void;
  setProcessing: (v: boolean) => void;
  setError: (e: string | null) => void;
  reset: () => void;
  phaseIndex: () => number;
}

export const useMeetingStore = create<MeetingStore>((set, get) => ({
  meetingId: null,
  phase: "idle",
  transcript: "",
  state: {},
  streamLog: [],
  reviewQueue: [],
  isProcessing: false,
  error: null,

  setTranscript: (t) => set({ transcript: t }),
  setMeetingId: (id) => set({ meetingId: id }),
  setPhase: (p) => set({ phase: p }),
  mergeState: (partial) =>
    set((s) => ({
      state: { ...s.state, ...partial },
      phase: (partial.phase as PipelinePhase) || s.phase,
    })),
  pushStreamEvent: (e) =>
    set((s) => ({
      streamLog: [...s.streamLog.slice(-99), e],
      phase: (e.phase as PipelinePhase) || (e.partial?.phase as PipelinePhase) || s.phase,
      state: e.state
        ? { ...s.state, ...e.state }
        : e.partial
          ? { ...s.state, ...e.partial }
          : s.state,
    })),
  setReviewQueue: (items) => set({ reviewQueue: items }),
  setProcessing: (v) => set({ isProcessing: v }),
  setError: (e) => set({ error: e }),
  reset: () =>
    set({
      meetingId: null,
      phase: "idle",
      state: {},
      streamLog: [],
      isProcessing: false,
      error: null,
    }),
  phaseIndex: () => {
    const p = get().phase;
    const i = PHASE_ORDER.indexOf(p);
    return i < 0 ? 0 : i;
  },
}));

export { PHASE_ORDER };
