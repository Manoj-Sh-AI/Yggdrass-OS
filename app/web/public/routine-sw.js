/* Notification-only service worker. Never cache private pages, credentials or API traffic. */
self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data?.json() || {};
  } catch {
    /* Show the generic reminder. */
  }
  const token = /^[A-Za-z0-9_-]{32}\.[0-9a-f]{64}$/.test(payload.token)
    ? payload.token
    : "";
  const call = payload.kind === "incoming_call";
  const titles = {
    morning: "Morning brief",
    evening: "Evening review",
    incoming_call: "Incoming reminder call",
  };
  const target = call ? "/today" : "/daily-routines";
  event.waitUntil(
    self.registration.showNotification(
      titles[payload.kind] || "Yggdras reminder",
      {
        body: call ? "Open Yggdras to answer." : "Open Yggdras for details.",
        icon: "/icon.png",
        tag: "daily-" + String(payload.tag || "reminder").slice(0, 40),
        data: { token, target },
        actions: token
          ? [
              { action: "started", title: "Started" },
              { action: "not_yet", title: "Not yet" },
            ]
          : [],
      },
    ),
  );
});

self.addEventListener("notificationclick", (event) => {
  const { token, target } = event.notification.data || {};
  event.notification.close();
  event.waitUntil(
    (async () => {
      if (token && ["started", "not_yet"].includes(event.action)) {
        try {
          const response = await fetch(
            "/api/backend/routine-delivery/respond",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              credentials: "omit",
              body: JSON.stringify({ token, action: event.action }),
            },
          );
          if (response.ok) return;
        } catch {
          /* Offer another attempt when the network returns. */
        }
      }
      const path = token
        ? "/routine-response#" + encodeURIComponent(token)
        : target === "/today"
          ? "/today"
          : "/daily-routines";
      await self.clients.openWindow(path);
    })(),
  );
});
