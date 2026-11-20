export type Task = {
  id: string;
  title: string;
  objective: string;
  description: string;
  area: string;
  due_date: string | null;
  deadline_at: string | null;
  timezone: string;
  state: "todo" | "in_progress" | "paused" | "completed" | "skipped";
  progress: number;
  version: number;
  done: boolean;
  estimated_minutes: number;
  actual_seconds: number;
  priority: number;
  effort: string;
  tags: string[];
  goal_id: string | null;
  project_id: string | null;
  parent_id: string | null;
  dependencies?: string[];
};
export type TimedItem = {
  id: string;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  version: number;
};
export type DateItem = {
  id: string;
  title: string;
  description: string;
  starts_on: string;
  ends_before: string;
  kind: string;
  version: number;
};
export type Snapshot = {
  dependencies?: { task_id: string; depends_on: string }[];
  tasks: Task[];
  events: TimedItem[];
  date_items: DateItem[];
  availability: TimedItem[];
  blocks: {
    id: string;
    task_id: string;
    starts_at: string;
    ends_at: string;
    version: number;
  }[];
  sessions: {
    id: string;
    task_id: string;
    started_at: string;
    ended_at: string | null;
  }[];
  goals: { id: string; title: string; description: string; version: number }[];
  routines: {
    id: string;
    title: string;
    objective: string;
    window_start: string;
    window_end: string;
    expected_minutes: number;
    version: number;
    description: string;
    timezone: string;
    area: string;
    frequency: "daily" | "weekly";
    interval_count: number;
    weekdays: number[];
    starts_on: string;
    ends_on: string | null;
    priority: number;
    goal_id: string | null;
    essential: boolean;
    active: boolean;
  }[];
  server_now: string;
};
export type Conversation = {
  id: string;
  title: string;
  archived: boolean;
  version: number;
  agent_id: string;
  model_id: string;
};
export type Message = {
  id: string;
  content: string;
  role: "user" | "assistant";
  version: number;
  deleted_at: string | null;
  ordinal: number;
};
export type Attachment = {
  id: string;
  name: string;
  media_type: string;
  size: number;
  message_id: string | null;
};
export type ChatRequest = {
  id: string;
  user_message_id: string;
  version: number;
  state: "held" | "queued" | "streaming" | "completed" | "failed" | "cancelled";
  error: string;
};
export type History = {
  conversation: Conversation;
  messages: Message[];
  requests: ChatRequest[];
  attachments: Attachment[];
  next_before: number | null;
};
export type Catalog = {
  agents: { id: string; name: string; available: boolean; models: string[] }[];
  models: { id: string; name: string; available: boolean }[];
};
export type Session = { origin: string; token: string; expires_at: string };
