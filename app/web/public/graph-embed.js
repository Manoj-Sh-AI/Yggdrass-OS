/* Presentation bridge only. The existing Brain viewer owns data and rendering. */
(() => {
  const send = (event, extra = {}) =>
    parent.postMessage(
      { type: "yggdras:graph", event, ...extra },
      location.origin,
    );
  if (
    typeof DATA === "undefined" ||
    typeof g3 === "undefined" ||
    typeof spin3d !== "function"
  ) {
    send("error");
    return;
  }
  let paused = true;
  let preferStill = false;
  const existingSpin = spin3d;
  spin3d = function () {
    existingSpin();
    if ((paused || preferStill) && g3.graph?.controls()) {
      g3.graph.controls().autoRotate = false;
      document.body.dataset.spin = "0";
    }
  };
  Object.assign(LOOK.dark, {
    bg: "#242b2d",
    accent: "#dce2cf",
    halo: "rgba(36,43,45,.85)",
    veil: "rgba(36,43,45,.8)",
  });
  Object.assign(CLASSIC.dark, {
    bg: "#242b2d",
    card: "#303638",
    cardLine: "#78867f",
    halo: "rgba(36,43,45,.85)",
    veil: "rgba(36,43,45,.8)",
  });
  applyTheme("dark");
  const theme = document.getElementById("theme");
  theme?.addEventListener("change", () => {
    if (state.theme === "dark") applyLook();
  });
  const info = document.getElementById("info");
  const decorate = () => {
    const node = DATA.nodes.find((n) => n.id === state.selected);
    const link = info?.querySelector("a");
    if (link && node) {
      link.href = `/notes?note=${encodeURIComponent(node.slug)}`;
      link.removeAttribute("target");
      link.dataset.noteSlug = node.slug;
    }
    document.querySelectorAll(".jump, #results li").forEach((item) => {
      item.tabIndex = 0;
      item.setAttribute("role", "button");
    });
  };
  if (info)
    new MutationObserver(decorate).observe(info, {
      childList: true,
      subtree: true,
    });
  const results = document.getElementById("results");
  if (results)
    new MutationObserver(decorate).observe(results, { childList: true });
  document.addEventListener("keydown", (event) => {
    if (
      (event.key === "Enter" || event.key === " ") &&
      event.target.matches(".jump, #results li")
    ) {
      event.preventDefault();
      event.target.click();
    }
  });
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-note-slug]");
    if (link) {
      event.preventDefault();
      send("open-note", { slug: link.dataset.noteSlug });
    }
  });
  window.addEventListener("message", (event) => {
    if (event.origin !== location.origin || event.source !== parent) return;
    if (event.data?.type === "yggdras:graph-appearance") {
      document.documentElement.dataset.transparency = event.data
        .reducedTransparency
        ? "reduced"
        : "glass";
      preferStill = event.data.reducedMotion === true;
      spin3d();
      return;
    }
    if (event.data?.type !== "yggdras:graph-control") return;
    paused = event.data.paused === true;
    spin3d();
  });
  let notified = false;
  const report = () => {
    if (document.body.dataset.error) {
      send("error");
      return;
    }
    if (
      !notified &&
      (document.body.dataset.ready3d === "1" || state.dim === "2d")
    ) {
      notified = true;
      send("ready");
    }
  };
  new MutationObserver(report).observe(document.body, {
    attributes: true,
    attributeFilter: ["data-ready3d", "data-error", "data-dim"],
  });
  ready2d.then(report);
  report();
  document.addEventListener("visibilitychange", () => {
    if (!g3.graph) return;
    if (document.hidden) g3.graph.pauseAnimation();
    else if (state.dim === "3d") g3.graph.resumeAnimation();
  });
})();
