import type { Role } from "./types";

/** Mirrors the Sprint 1 permission matrix; the server enforces the same rules (AC-03.2). */
export const can = {
  manageUsers: (r: Role) => r === "admin",
  editSites: (r: Role) => r === "manager",
  runProcessing: (r: Role) => r === "admin" || r === "manager",
  viewSignals: (r: Role) => r === "admin" || r === "manager",
  decide: (r: Role) => r === "manager",
  manageTasks: (r: Role) => r === "manager",
  viewTasks: (r: Role) => r === "admin" || r === "manager" || r === "inspector",
  workTasks: (r: Role) => r === "inspector",
  viewOverview: (r: Role) => r === "admin" || r === "manager" || r === "viewer",
  summariseWithAi: (r: Role) => r === "manager" || r === "viewer",
  exportSignals: (r: Role) => r === "admin" || r === "manager",
  exportTasks: (r: Role) => r !== "viewer",
  viewActivity: (r: Role) => r === "admin",
};

export type NavKey = "home" | "queue" | "tasks" | "map" | "reports" | "import" | "processing" | "users" | "activity";

export const NAV: { key: NavKey; href: string; label: string; allowed: (r: Role) => boolean }[] = [
  { key: "home", href: "/", label: "Overview", allowed: () => true },
  { key: "queue", href: "/queue", label: "Attention queue", allowed: can.viewSignals },
  { key: "tasks", href: "/tasks", label: "Tasks", allowed: can.viewTasks },
  { key: "map", href: "/map", label: "Green spaces", allowed: () => true },
  { key: "reports", href: "/reports", label: "Reports", allowed: can.viewOverview },
  { key: "import", href: "/import", label: "Import", allowed: can.editSites },
  { key: "processing", href: "/processing", label: "Satellite data", allowed: can.runProcessing },
  { key: "users", href: "/users", label: "Users", allowed: can.manageUsers },
  { key: "activity", href: "/activity", label: "Activity", allowed: can.viewActivity },
];
