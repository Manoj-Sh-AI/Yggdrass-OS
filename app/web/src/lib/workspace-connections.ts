import { applicationApi } from "./api";
import type { CalendarDateItem, AvailabilityWindow } from "./planning";
export type WorkKind = "task" | "event" | "date_item" | "availability";
export type Relation = "source" | "context" | "result";
export type LinkedTask = {
  id: string;
  title: string;
  objective: string;
  state: string;
  done: boolean;
  due_date: string | null;
  version: number;
  kind: Relation;
  source_revision: string | null;
};
export type LinkedEvent = {
  id: string;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string;
  timezone: string;
  cancelled: boolean;
  version: number;
  kind: Relation;
  source_revision: string | null;
};
export type NoteWork = {
  tasks: LinkedTask[];
  events: LinkedEvent[];
  date_items?: (CalendarDateItem & {
    relation: Relation;
    source_revision: string | null;
  })[];
  availability?: (AvailabilityWindow & {
    relation: Relation;
    source_revision: string | null;
  })[];
  truncated: { tasks: boolean; events: boolean };
};
export type NoteReference = {
  id: string;
  external_id: string;
  observed_title: string;
  observed_revision: string;
  kind: Relation;
  source_revision: string | null;
};
export type WorkContext = {
  notes: NoteReference[];
  tasks?: { id: string; title: string; state: string }[];
  events?: { id: string; title: string; cancelled: boolean }[];
  truncated: { notes: boolean; tasks?: boolean; events?: boolean };
};
export type ConnectionResult = {
  id?: string;
  version: number;
  link_id: string;
  source_revision?: string;
};
const root = "application/connections";
export const connectionsApi = {
  capabilities: (signal?: AbortSignal) =>
    applicationApi<{ linked_work: boolean; automatic_interpretation: boolean }>(
      `${root}/capabilities`,
      { signal },
    ),
  read: <T>(path: string, signal?: AbortSignal) =>
    applicationApi<T>(`${root}/${path}`, { signal }),
  create: (
    key: string,
    kind: WorkKind,
    slug: string,
    revision: string,
    data: Record<string, unknown>,
  ) =>
    applicationApi<ConnectionResult>(`${root}/from-note`, {
      method: "POST",
      body: JSON.stringify({
        key,
        operation: `${kind}.create`,
        note_slug: slug,
        note_revision: revision,
        [kind]: data,
      }),
    }),
  link: (
    key: string,
    kind: WorkKind,
    id: string,
    version: number,
    slug: string,
    relation: Relation = "context",
    remove = false,
  ) =>
    applicationApi<ConnectionResult>(`${root}/commands`, {
      method: "POST",
      body: JSON.stringify({
        key,
        operation: `${kind}.${remove ? "unlink" : "link"}_note`,
        entity_id: id,
        version,
        note_slug: slug,
        relation,
      }),
    }),
};
export function connectionsChanged() {
  window.dispatchEvent(new Event("yggdress:connections-changed"));
  window.dispatchEvent(new Event("yggdress:tasks-changed"));
}
