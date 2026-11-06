if (requireLogin()) {
  const params = new URLSearchParams(location.search);
  let partners = [];
  let partner = null;
  let lastId = 0;
  let timer = null;
  const box = $("chatMessages");

  function bubble(m){
    return el("div", {class: "chat-bubble" + (m.mine ? " mine" : "")},
      el("div", {}, m.body), el("time", {}, formatDate(m.created_at)));
  }

  async function fetchMessages(reset){
    if (!partner) return;
    try {
      const messages = await api(`/messages/${partner.id}${reset ? "" : `?after=${lastId}`}`);
      if (reset) box.replaceChildren(...(messages.length ? [] : [el("p", {class: "empty"}, "No messages yet. Say hi! 👋")]));
      if (messages.length) {
        if (!reset && box.querySelector(".empty")) box.replaceChildren();
        const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
        messages.forEach(m => box.append(bubble(m)));
        lastId = messages[messages.length - 1].id;
        if (reset || nearBottom) box.scrollTop = box.scrollHeight;
      }
      $("chatStatus").textContent = "";
    } catch (e) { $("chatStatus").textContent = e.message; }
  }

  function openChat(p){
    partner = p; lastId = 0;
    document.querySelectorAll(".partner-item").forEach(n => n.classList.toggle("active", n.dataset.id == p.id));
    $("chatHeader").replaceChildren(avatar(p, "small"), el("div", {},
      el("a", {href: profileLink(p.id)}, el("b", {}, p.name)), " ", verifiedBadge(p),
      el("div", {class: "muted small"}, [p.college, p.branch].filter(Boolean).join(" · "))));
    $("chatHeader").classList.remove("muted");
    $("messageForm").hidden = false;
    history.replaceState(null, "", `chat.html?partner=${p.id}`);
    fetchMessages(true);
    clearInterval(timer);
    timer = setInterval(() => { if (!document.hidden) fetchMessages(false); }, 5000);
  }

  $("messageForm").addEventListener("submit", async e => {
    e.preventDefault();
    const text = $("messageBody").value.trim();
    if (!text || !partner) return;
    try {
      await api(`/messages/${partner.id}`, {method: "POST", body: JSON.stringify({body: text})});
      $("messageBody").value = "";
      await fetchMessages(false);
      box.scrollTop = box.scrollHeight;
    } catch (err) { $("chatStatus").textContent = err.message; }
  });
  $("messageBody").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("messageForm").requestSubmit(); }
  });

  (async () => {
    try {
      partners = await api("/connections");
      if (!partners.length) {
        $("partnerList").replaceChildren(el("p", {class: "empty"}, "No partners yet. Once a learning request is accepted, they'll appear here."),
          el("a", {href: "matches.html"}, "Find matches →"));
        return;
      }
      $("partnerList").replaceChildren(...partners.map(p => el("button", {class: "partner-item", "data-id": p.id, onclick: () => openChat(p)},
        avatar(p, "small"), el("div", {class: "grow"}, el("b", {}, p.name),
          el("div", {class: "muted small"}, p.last_message || "No messages yet")))));
      const wanted = partners.find(p => p.id === Number(params.get("partner")));
      if (wanted) openChat(wanted);
      else if (params.get("partner")) $("chatStatus").textContent = "You can only message students whose learning request was accepted.";
    } catch (e) { $("partnerList").textContent = e.message; }
  })();
}
