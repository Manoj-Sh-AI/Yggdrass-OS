import type { Area, DemoState } from "./types";
export const areas: Area[] = [
  {
    id: "work",
    name: "Work",
    color: "#75a9ff",
    icon: "BriefcaseBusiness",
    description: "Meaningful work. Steady progress.",
  },
  {
    id: "learning",
    name: "University",
    color: "#a7b7e5",
    icon: "GraduationCap",
    description: "Make room for curiosity.",
  },
  {
    id: "german",
    name: "German",
    color: "#f6b75c",
    icon: "Languages",
    description: "A little practice, every day.",
  },
  {
    id: "health",
    name: "Health",
    color: "#5bddaa",
    icon: "Heart",
    description: "Build a life that feels good.",
  },
  {
    id: "projects",
    name: "Projects",
    color: "#79a6ff",
    icon: "FolderKanban",
    description: "Turn your ideas into something real.",
  },
  {
    id: "career",
    name: "Career",
    color: "#b386f8",
    icon: "Building2",
    description: "Your next chapter starts here.",
  },
  {
    id: "people",
    name: "People",
    color: "#b9bada",
    icon: "Users",
    description: "Stay close to the people who matter.",
  },
];
export const areaOf = (id: string) =>
  areas.find((a) => a.id === id) ?? {
    id,
    name: id,
    color: "#a7b7e5",
    icon: "FolderKanban",
    description: "Brain-provided area",
  };
export const brainAreaForApp: Record<string, string> = {
  health: "01-health",
  people: "02-relationships",
  work: "03-work-career",
  career: "03-work-career",
  learning: "04-learning",
  german: "04-learning",
  projects: "10-ideas",
};
export function localDate(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function seed(now = new Date()): DemoState {
  const date = localDate(now),
    updated = now.toISOString();
  const samples = [
    [
      "credit-report",
      "Credit Risk Dashboard",
      "A clearer view of portfolio health.",
      "work",
      "Pull the reporting measures into one calm, useful dashboard.\n\n## Next steps\nCompare this month’s risk indicators and document the assumptions behind each measure.",
      "analytics,reporting",
    ],
    [
      "german-a2",
      "German A2.1",
      "Small conversations, growing confidence.",
      "german",
      "## Today’s practice\nDescribe your day using the perfect tense.\n\nDas Wissen — knowledge\nDie Gewohnheit — habit\nSich erinnern — to remember",
      "vocabulary,language",
    ],
    [
      "thesis",
      "Master’s Thesis",
      "Connecting research to practical insights.",
      "learning",
      "## Research direction\nExplore how connected knowledge systems help people make better decisions.\n\nRead two papers, capture the claims, and connect them to the research question.",
      "research,writing",
    ],
    [
      "second-brain",
      "Second Brain",
      "A home for ideas worth keeping.",
      "projects",
      "## Memory architecture\nCapture without friction. Connect with intention. Review when it matters.\n\nA useful note should make tomorrow’s thinking easier.",
      "knowledge,design",
    ],
    [
      "strength",
      "A stronger everyday",
      "Consistency over intensity.",
      "health",
      "## Strength training\nThree deliberate sessions a week. Start with the basics and track how movement feels.\n\nMake recovery part of the plan.",
      "fitness,habits",
    ],
    [
      "career-next",
      "The next chapter",
      "Thoughtful steps toward meaningful work.",
      "career",
      "## A focused search\nChoose roles that combine analytical thinking with useful products.\n\nUpdate the portfolio and reach out to one new person this week.",
      "career,planning",
    ],
    [
      "weekly-review",
      "The weekly reset",
      "A little space to see the bigger picture.",
      "projects",
      "## Reflection\nWhat moved forward? What needs attention? What can wait?\n\nKeep one small promise to yourself next week.",
      "reflection,habits",
    ],
    [
      "coffee",
      "Conversations worth having",
      "Make time for connection.",
      "people",
      "Catch up with a friend this weekend. Ask what they have been curious about lately.",
      "connection",
    ],
  ];
  const notes = samples.map(
    ([id, title, description, area, content, tags], i) => ({
      id,
      slug: id,
      title,
      description,
      area,
      content,
      tags: tags.split(","),
      also: i === 3 ? ["learning"] : [],
      links:
        i === 3
          ? ["thesis", "weekly-review"]
          : i === 1
            ? ["weekly-review"]
            : i === 2
              ? ["second-brain"]
              : [],
      updated: new Date(now.getTime() - i * 3600000).toISOString(),
    }),
  );
  return {
    version: 1,
    notes,
    tasks: [
      {
        id: "t1",
        title: "Finish the reporting draft",
        area: "work",
        done: true,
        date,
        noteId: "credit-report",
      },
      {
        id: "t2",
        title: "Review German vocabulary",
        area: "german",
        done: true,
        date,
        noteId: "german-a2",
      },
      {
        id: "t3",
        title: "Go to the gym",
        area: "health",
        done: false,
        date,
        noteId: "strength",
      },
      {
        id: "t4",
        title: "Work on brain memory",
        area: "projects",
        done: false,
        date,
        noteId: "second-brain",
      },
      {
        id: "t5",
        title: "Read thesis papers",
        area: "learning",
        done: false,
        date,
        noteId: "thesis",
      },
    ],
    events: [
      {
        id: "e1",
        title: "Deep work",
        description: "Credit risk reporting",
        area: "work",
        date,
        time: "09:00",
        duration: "8h",
        location: "Office",
        noteId: "credit-report",
      },
      {
        id: "e2",
        title: "German",
        description: "A2 practice",
        area: "german",
        date,
        time: "18:00",
        duration: "45m",
        location: "Home",
        noteId: "german-a2",
      },
      {
        id: "e3",
        title: "Gym",
        description: "Strength training",
        area: "health",
        date,
        time: "19:00",
        duration: "1h",
        location: "Fitness studio",
        noteId: "strength",
      },
      {
        id: "e4",
        title: "Second Brain",
        description: "Memory architecture",
        area: "projects",
        date,
        time: "21:00",
        duration: "1h 30m",
        location: "Home",
        noteId: "second-brain",
      },
      {
        id: "e5",
        title: "Thesis meeting",
        description: "Research check-in",
        area: "learning",
        date: localDate(new Date(now.getTime() + 2 * 86400000)),
        time: "11:00",
        duration: "1h",
        location: "University",
        noteId: "thesis",
      },
    ],
    activities: [
      {
        id: "a1",
        title: "Reviewed connected notes",
        kind: "note",
        noteId: "second-brain",
        date: updated,
      },
      {
        id: "a2",
        title: "Updated the reporting draft",
        kind: "note",
        noteId: "credit-report",
        date: new Date(now.getTime() - 7200000).toISOString(),
      },
      {
        id: "a3",
        title: "German vocabulary · 12 words",
        kind: "task",
        noteId: "german-a2",
        date: new Date(now.getTime() - 86400000).toISOString(),
      },
      {
        id: "a4",
        title: "New idea: a calmer calendar",
        kind: "idea",
        noteId: "weekly-review",
        date: new Date(now.getTime() - 90000000).toISOString(),
      },
    ],
    goals: [
      { id: "g1", title: "German (A2)", area: "german", progress: 63 },
      { id: "g2", title: "Thesis", area: "career", progress: 40 },
      { id: "g3", title: "Gym", area: "health", progress: 70 },
      { id: "g4", title: "Job applications", area: "work", progress: 25 },
    ],
    cards: [
      { id: "f1", area: "german", front: "das Wissen", back: "knowledge" },
      { id: "f2", area: "german", front: "die Gewohnheit", back: "habit" },
      { id: "f3", area: "german", front: "sich erinnern", back: "to remember" },
      {
        id: "f4",
        area: "learning",
        front: "What makes a useful research note?",
        back: "A clear claim, its evidence, and a connection to your research question.",
      },
    ],
    preferences: {
      name: "Alex",
      notifications: false,
      reducedMotion: false,
      reducedTransparency: false,
      locationPrompted: false,
      place: {
        name: "Hamburg",
        latitude: 53.55,
        longitude: 9.99,
        timezone: "Europe/Berlin",
      },
      season: "auto",
      phase: "auto",
      sky: "auto",
    },
  };
}
