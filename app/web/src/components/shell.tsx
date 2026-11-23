"use client";
import { PageContextProvider } from "@/features/side-chat/page-context";
import { SideChat, SideChatToggle } from "@/features/side-chat/side-chat";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { weatherLabel } from "@/lib/scenes";
import { logout } from "@/lib/api";
import { useApp } from "./provider";
import { SceneBackground, useScenery } from "./scenery";
import type { CaptureKind } from "./capture";
import { PlanningTaskSheet, TaskForm } from "./planning-ui";
import { Icon, Modal, rememberFocus } from "./ui";
import { WorkspaceSearch } from "./workspace-search";
import { WorkflowReview } from "./workflow-review";
import { IncomingCall } from "./incoming-call";

type CaptureEvent = CustomEvent<{ kind: CaptureKind; title?: string }>;
// Older entry points route to the connected editor rather than a mock adapter.
export function launchCapture(kind: CaptureKind = "note", title = "") {
  rememberFocus();
  window.dispatchEvent(
    new CustomEvent("yggdras:capture", { detail: { kind, title } }),
  );
}
function Sidebar({ close }: { close: () => void }) {
  const pathname = usePathname();
  return (
    <>
      <Link href="/today" onClick={close} className="brand">
        <span className="brand-mark brand-logo">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/logo-mark.png" alt="" width={30} height={30} />
        </span>
        Yggdras
      </Link>
      <nav aria-label="Main navigation">
        {[
          ["/today", "Today", "CalendarDays"],
          ["/calendar", "Calendar", "Calendar"],
          ["/tasks", "Tasks", "SquareCheck"],
          ["/notes", "Notes", "NotebookPen"],
          ["/graph", "Graph", "Network"],
          ["/chat", "Chat", "MessageCircle"],
          ["/connectors", "Connectors", "Plug"],
          ["/skills", "Skills", "BookOpen"],
          ["/feedback", "Yggdras log", "Activity"],
        ].map(([href, label, icon]) => (
          <Link
            key={href}
            href={href}
            onClick={close}
            className={`nav-item ${pathname === href ? "active" : ""}`}
            aria-current={pathname === href ? "page" : undefined}
          >
            <Icon name={icon} />
            <span>{label}</span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <Link
          href="/settings"
          onClick={close}
          className={`nav-item ${pathname === "/settings" ? "active" : ""}`}
          aria-current={pathname === "/settings" ? "page" : undefined}
        >
          <Icon name="Settings2" />
          <span>Settings</span>
        </Link>
      </div>
    </>
  );
}
export function AppShell({ children }: { children: ReactNode }) {
  const { state, error } = useApp();
  const { now, weather, status, scene } = useScenery();
  const path = usePathname();
  const router = useRouter();
  const [mobile, setMobile] = useState(false);
  const [account, setAccount] = useState(false);
  const [taskCapture, setTaskCapture] = useState(false);
  useEffect(() => {
    document.documentElement.dataset.transparency = state.preferences
      .reducedTransparency
      ? "reduced"
      : "glass";
    document.documentElement.dataset.motion = state.preferences.reducedMotion
      ? "reduced"
      : "full";
  }, [state.preferences.reducedTransparency, state.preferences.reducedMotion]);
  useEffect(() => {
    const capture = (event: Event) => {
      if ((event as CaptureEvent).detail.kind === "task") setTaskCapture(true);
      else router.push("/notes?new=1");
    };
    const shortcut = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.shiftKey &&
        event.key.toLowerCase() === "n"
      ) {
        event.preventDefault();
        router.push("/notes?new=1");
      }
    };
    window.addEventListener("yggdras:capture", capture);
    window.addEventListener("keydown", shortcut);
    return () => {
      window.removeEventListener("yggdras:capture", capture);
      window.removeEventListener("keydown", shortcut);
    };
  }, [router]);
  const timezone = weather?.timezone || state.preferences.place.timezone;
  const fresh = weather && now.getTime() - weather.fetchedAt <= 7200000;
  return (
    <PageContextProvider>
      <div
        className={`app-frame signal-workspace ${state.preferences.reducedMotion ? "reduce-motion" : ""}`}
      >
        <SceneBackground />
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <aside className="sidebar">
          <Sidebar close={() => setMobile(false)} />
        </aside>
        <Modal open={mobile} onOpenChange={setMobile} title="Navigation">
          <div className="mobile-nav">
            <Sidebar close={() => setMobile(false)} />
          </div>
        </Modal>
        <div className="workspace">
          <header className="topbar">
            <button
              className="icon-button mobile-toggle"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Icon name="Menu" />
            </button>
            <WorkspaceSearch />
            <div className="topbar-right">
              <Link
                href="/settings"
                className="weather"
                aria-label="Weather and scenery settings"
                title={fresh ? weatherLabel(weather.code) : status}
              >
                <Icon
                  name={
                    fresh && weather.code >= 51
                      ? "CloudRain"
                      : (fresh ? weather.isDay : scene.phase !== "night")
                        ? "Sun"
                        : "Moon"
                  }
                  size={19}
                />
                <span>
                  <strong>
                    {new Intl.DateTimeFormat("en", {
                      timeZone: timezone,
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                    }).format(now)}
                  </strong>
                  <small>
                    {state.preferences.place.name}
                    {fresh ? `, ${Math.round(weather.temperature)}°C` : ""}
                  </small>
                </span>
              </Link>
              <button
                className="avatar account-button"
                aria-label="Open account menu"
                onClick={() => setAccount(true)}
              >
                {state.preferences.name.slice(0, 1)}
              </button>
              <SideChatToggle />
              <WorkflowReview />
              <IncomingCall />
            </div>
          </header>
          <main id="main" tabIndex={-1}>
            {path === "/settings" && error && (
              <div className="error-banner" role="alert">
                {error}
              </div>
            )}
            {children}
          </main>
        </div>
        <SideChat />
        <PlanningTaskSheet />
        <Modal
          open={taskCapture}
          onOpenChange={setTaskCapture}
          title="New task"
        >
          <TaskForm onSaved={() => setTaskCapture(false)} />
        </Modal>
        <Modal open={account} onOpenChange={setAccount} title="Account">
          <div className="account-card">
            <h3>{state.preferences.name}</h3>
            <button className="button" onClick={() => void logout()}>
              Sign out
            </button>
            <Link
              className="button"
              href="/settings"
              onClick={() => setAccount(false)}
            >
              Settings
            </Link>
          </div>
        </Modal>
      </div>
    </PageContextProvider>
  );
}
