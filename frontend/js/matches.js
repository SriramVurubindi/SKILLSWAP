if (requireLogin()) {
  const container = $("matchList");
  let people = [];

  function requestButton(p){
    const labels = {connected: "Message partner", pending_sent: "Request sent", pending_received: "Respond to their request"};
    if (p.relationship === "connected") return el("a", {class: "btn", href: `chat.html?partner=${p.id}`}, labels.connected);
    if (p.relationship === "pending_received") return el("a", {class: "btn btn-outline", href: "requests.html"}, labels.pending_received);
    const button = el("button", {class: "btn", disabled: p.relationship === "pending_sent"},
      labels[p.relationship] || "Send learning request");
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api("/requests", {method: "POST", body: JSON.stringify({receiver_id: p.id,
          message: "Hi! I found your profile on SkillSwap. Would you like to exchange skills?"})});
        p.relationship = "pending_sent"; button.textContent = "Request sent"; toast(`Request sent to ${p.name}`, "ok");
      } catch (e) { toast(e.message, "error"); button.disabled = false; }
    });
    return button;
  }

  function tags(label, list){
    return el("div", {class: "tag-row"}, el("b", {}, label + " "),
      ...(list.length ? list.map(x => el("span", {class: "tag"}, x)) : [el("span", {class: "tag tag-empty"}, "No direct match")]));
  }

  function card(p){
    return el("article", {class: "match-card"},
      el("div", {class: "match-top"}, avatar(p),
        el("div", {class: "grow"},
          el("h3", {}, el("a", {href: profileLink(p.id)}, p.name)),
          el("p", {class: "muted small"}, [p.college, p.branch, p.year].filter(Boolean).join(" · ") || "Student")),
        el("div", {class: "match-score"}, `${p.score}%`, el("small", {}, p.mutual ? "two-way" : "match"))),
      el("div", {class: "badge-row"}, verifiedBadge(p), ratingText(p)),
      p.bio ? el("p", {class: "bio"}, p.bio) : null,
      tags("Can teach you:", p.they_can_teach_me),
      tags("You can teach:", p.i_can_teach_them),
      el("div", {class: "row-actions"}, requestButton(p), el("a", {class: "btn btn-outline", href: profileLink(p.id)}, "View profile")));
  }

  function render(){
    const q = $("search").value.trim().toLowerCase();
    const list = people.filter(p =>
      (!$("mutualOnly").checked || p.mutual) &&
      (!$("verifiedOnly").checked || p.linkedin_verified || p.google_verified) &&
      (!q || [p.name, p.college, p.branch, ...p.they_can_teach_me, ...p.i_can_teach_them].join(" ").toLowerCase().includes(q)));
    if (!people.length) {
      container.replaceChildren(el("div", {class: "empty-state"},
        el("p", {}, "No matches yet. Add skills you can teach and want to learn, then check again."),
        el("a", {class: "btn", href: "profile.html"}, "Add skills")));
      return;
    }
    container.replaceChildren(...(list.length ? list.map(card) : [el("p", {class: "empty"}, "No matches for these filters.")]));
  }

  ["search", "mutualOnly", "verifiedOnly"].forEach(id => $(id).addEventListener("input", render));
  (async () => {
    try { people = await api("/matches"); render(); }
    catch (e) { container.textContent = e.message; }
  })();
}
