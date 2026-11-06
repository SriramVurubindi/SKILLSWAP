if (requireLogin()) {
  (async () => {
    try {
      const d = await api("/dashboard");
      $("studentName").textContent = d.name;
      $("teachCount").textContent = d.teach_count;
      $("learnCount").textContent = d.learn_count;
      $("connectionCount").textContent = d.connections;
      $("pendingCount").textContent = d.pending_incoming;
      $("upcomingCount").textContent = d.upcoming_count;

      $("completePercent").textContent = d.completeness.percent;
      $("completeBar").style.width = `${d.completeness.percent}%`;
      $("profileSummary").textContent = [d.college, d.branch].filter(Boolean).join(" · ") ||
        "Complete these steps so other students can find and trust you:";
      $("missingList").replaceChildren(...(d.completeness.missing.length
        ? d.completeness.missing.map(m => el("li", {}, el("a", {href: m.includes("LinkedIn") ? "profile.html#verify" : "profile.html"}, m)))
        : [el("li", {class: "done"}, "Your profile is complete. Nice work!")]));

      const li = $("linkedinCard");
      if (d.linkedin_status === "verified") {
        li.replaceChildren(el("p", {}, verifiedBadge(d)),
          el("p", {class: "muted"}, "Your name has been cross-checked with LinkedIn. Other students see your verified badge."));
      } else if (d.linkedin_status === "mismatch") {
        li.replaceChildren(el("p", {}, el("span", {class: "pill pill-warn"}, "Name mismatch")),
          el("p", {class: "muted"}, "The name on your profile doesn't match your LinkedIn name."),
          el("a", {class: "btn btn-small", href: "profile.html#verify"}, "Fix it"));
      } else {
        li.replaceChildren(el("p", {class: "muted"}, "Verified students get more accepted requests. It takes 30 seconds."),
          el("a", {class: "btn btn-small", href: "profile.html#verify"}, "Verify with LinkedIn"));
      }

      $("upcomingList").replaceChildren(...(d.upcoming_sessions.length
        ? d.upcoming_sessions.map(s => el("div", {class: "request-row"},
            el("b", {}, s.topic), el("div", {class: "muted"},
              `${formatDate(s.session_date)}${s.partner_name ? " · with " + s.partner_name : ""}`)))
        : [el("p", {class: "empty"}, "No upcoming sessions. "), el("a", {href: "sessions.html"}, "Plan one →")]));
    } catch (e) { $("profileSummary").textContent = e.message; }
  })();
}
