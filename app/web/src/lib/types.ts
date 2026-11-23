export type Area = {
  id: string;
  name: string;
  color: string;
  icon: string;
  description: string;
};
export type Note = {
  id: string;
  slug: string;
  title: string;
  description: string;
  content: string;
  area: string;
  also: string[];
  tags: string[];
  links: string[];
  updated: string;
  filename?: string;
};
export type Task = {
  version?: number;
  id: string;
  title: string;
  description?: string;
  area: string;
  done: boolean;
  date: string;
  noteId?: string;
};
export type AgendaEvent = {
  id: string;
  title: string;
  description: string;
  area: string;
  date: string;
  time: string;
  duration: string;
  location: string;
  noteId: string;
};
export type Activity = {
  id: string;
  title: string;
  date: string;
  noteId?: string;
  kind: "note" | "task" | "idea" | "file";
};
export type Goal = {
  id: string;
  title: string;
  area: string;
  progress: number;
};
export type Flashcard = {
  id: string;
  area: string;
  front: string;
  back: string;
};
export type Season = "spring" | "summer" | "autumn" | "winter";
export type DayPhase = "sunrise" | "afternoon" | "night";
export type Sky = "clear" | "rainy";
export type Place = {
  name: string;
  latitude: number;
  longitude: number;
  timezone: string;
};
export type Preferences = {
  name: string;
  notifications: boolean;
  reducedMotion: boolean;
  reducedTransparency?: boolean;
  locationPrompted: boolean;
  place: Place;
  season: Season | "auto";
  phase: DayPhase | "auto";
  sky: Sky | "auto";
};
export type DemoState = {
  version: 1;
  notes: Note[];
  tasks: Task[];
  events: AgendaEvent[];
  activities: Activity[];
  goals: Goal[];
  cards: Flashcard[];
  preferences: Preferences;
};
export type CaptureInput = {
  shelfId?: string;
  kind: Activity["kind"];
  title: string;
  content: string;
  area: string;
  tags: string[];
  date: string;
  filename?: string;
};
