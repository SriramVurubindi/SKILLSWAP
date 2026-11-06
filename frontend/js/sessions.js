if (requireLogin()) {
  const params = new URLSearchParams(location.search);
  let sessions = [];
  const PILL = {planned: "pill", completed: "pill pill-ok", cancelled: "pill pill-bad"};

  function sessionRow(s){
    const actions = el("div", {class: "row-actions"});
    const setStatus = status => async () => {
      try { await api(`/sessions/${s.id}`, {method: "PUT", body: JSON.stringify({status})}); toast(`Session ${status}`, "ok"); load(); }
      catch (e) { toast(e.message, "error"); }
    };
    if (s.status === "planned") {
      actions.append(el("button", {class: "btn btn-small", onclick: setStatus("completed")}, "Mark completed"),
                     el("button", {class: "btn btn-small btn-outline", onclick: setStatus("cancelled")}, "Cancel"));
    } else {
      actions.append(el("button", {class: "btn btn-small btn-outline", onclick: setStatus("planned")}, "Reopen"));
    }
    if (s.status === "completed" && s.partner_id)
      actions.append(el("a", {class: "btn btn-small btn-outline", href: `${profileLink(s.partner_id)}#review`}, "Review partner"));
    if (s.created_by_me)
      actions.append(el("button", {class: "btn btn-small btn-ghost", onclick: async () => {
        if (!confirm("Delete this session?")) return;
        try { await api(`/sessions/${s.id}`, {method: "DELETE"}); toast("Session deleted"); load(); }
        catch (e) { toast(e.message, "error"); }
      }}, "Delete"));
    return el("div", {class: "request-row"},
      el("div", {class: "request-head"}, el("b", {}, s.topic), el("span", {class: PILL[s.status]}, s.status)),
      el("div", {class: "muted small"}, `${formatDate(s.session_date)} · ${s.duration_minutes} min`,
        s.partner_name ? ` · with ${s.partner_name}` : " · solo",
        s.created_by_me ? "" : " (planned by partner)"),
      actions);
  }

  function render(){
    const filter = $("statusFilter").value;
    const list = sessions.filter(s => !filter || s.status === filter);
    $("sessionList").replaceChildren(...(list.length ? list.map(sessionRow) : [el("p", {class: "empty"}, "No sessions here yet.")]));
  }

  async function load(){
    try { sessions = await api("/sessions"); render(); }
    catch (e) { $("sessionList").textContent = e.message; }
  }

  $("statusFilter").addEventListener("change", render);
  $("sessionForm").addEventListener("submit", async e => {
    e.preventDefault();
    const msg = $("sessionMessage");
    try {
      await api("/sessions", {method: "POST", body: JSON.stringify({
        topic: $("topic").value, partner_id: $("partner").value || null,
        session_date: $("sessionDate").value || null, duration_minutes: Number($("duration").value)})});
      msg.textContent = "Session created."; toast("Session created", "ok");
      $("topic").value = ""; $("sessionDate").value = "";
      load();
    } catch (err) { msg.textContent = err.message; }
  });

  (async () => {
    try {
      const partners = await api("/connections");
      partners.forEach(p => $("partner").append(el("option", {value: p.id}, p.name)));
      if (params.get("partner")) $("partner").value = params.get("partner");
      if (!partners.length) $("sessionMessage").textContent = "Tip: accept a learning request to schedule sessions with a partner.";
    } catch {}
    load();
  })();
}
