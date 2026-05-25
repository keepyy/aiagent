export type PipelinePhase =
  | "idle"
  | "planning"
  | "diarizing"
  | "extracting"
  | "structuring"
  | "critiquing"
  | "awaiting_human"
  | "approved"
  | "rejected"
  | "failed";

export interface Utterance {
  id: string;
  speaker: string;
  text: string;
  start_offset?: number;
}

export interface Todo {
  id: string;
  text: string;
  assignee?: string | null;
  deadline?: string | null;
  utterance_id?: string;
}

export interface ActionItem {
  action_id: string;
  action_type: string;
  title: string;
  owner?: string | null;
  due_date?: string | null;
  priority: string;
  related_entities: string[];
  dependencies: string[];
  source_utterance_ids: string[];
  confidence: number;
}

export interface MeetingState {
  meeting_id?: string;
  phase?: PipelinePhase;
  plan?: Record<string, unknown>;
  utterances?: Utterance[];
  todos?: Todo[];
  action_items?: ActionItem[];
  critic_report?: {
    passed?: boolean;
    score?: number;
    issues?: { severity: string; target: string; message: string }[];
    metrics?: Record<string, number>;
  };
  critic_passed?: boolean;
  review_decision?: string;
}

export interface StreamEvent {
  type: string;
  meeting_id?: string;
  phase?: string;
  message?: string;
  node?: string;
  partial?: Partial<MeetingState>;
  state?: MeetingState;
  payload?: Record<string, unknown>;
}

export interface ActionPreview {
  owner: string;
  type: string;
  title: string;
  due_date?: string;
}

export interface ReviewQueueItem {
  meeting_id: string;
  transcript_preview: string;
  phase: string;
  created_at: string;
  /** 机审质量分，非人工终审结论 */
  critic_score?: number;
  critic_passed?: boolean;
  critic_label?: string;
  action_count?: number;
  todo_count?: number;
  utterance_count?: number;
  summary?: string;
  action_previews?: ActionPreview[];
  human_status?: string;
  issue_count?: number;
}
