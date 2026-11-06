if (requireLogin()) {
  const STATUS = {pending: "pill", accepted: "pill pill-ok", rejected: "pill pill-bad"};

  function row(r){
    const head = el("div", {class: "request-head"},
      el("a", {href: profileLink(r.student_id)}, el("b", {}, r.student_name)),
      r.linkedin_verified ? el("span", {class: "badge badge-verified"}, "✓") : null,
      el("span", {class: STATUS[r.status] || "pill"}, r.status));
    const box = el("div", {class: "request-row"}, head);
    if (r.message) box.append(el("p", {class: "muted small"}, `“${r.message}”`));
    if (r.created_at) box.append(el("div", {class: "muted small"}, formatDate(r.created_at, false)));
    const actions = el("div", {class: "row-actions"});

    if (r.direction === "incoming" && r.status === "pending") {
      [["accepted", "Accept", "btn"], ["rejected", "Decline", "btn btn-outline"]].forEach(([status, label, cls]) =>
        actions.append(el("button", {class: cls, onclick: async () => {
          try { await api(`/requests/${r.id}`, {method: "PUT", body: JSON.stringify({status})}); toast(`Request ${status}`, "ok"); load(); }
          catch (e) { toast(e.message, "error"); }
        }}, label)));
    }
    if (r.direction === "outgoing" && r.status === "pending") {
      actions.append(el("button", {class: "btn btn-outline", onclick: async () => {
        try { await api(`/requests/${r.id}`, {method: "DELETE"}); toast("Request cancelled"); load(); }
        catch (e) { toast(e.message, "error"); }
      }}, "Cancel request"));
    }
    if (r.status === "accepted") {
      actions.append(el("a", {class: "btn", href: `chat.html?partner=${r.student_id}`}, "Message partner"),
                     el("a", {class: "btn btn-outline", href: `sessions.html?partner=${r.student_id}`}, "Plan a session"));
    }
    if (actions.childNodes.length) box.append(actions);
    return box;
  }

  async function load(){
    try {
      const data = await api("/requests");
      $("incoming").replaceChildren(...(data.incoming.length ? data.incoming.map(row) : [el("p", {class: "empty"}, "No incoming requests.")]));
      $("outgoing").replaceChildren(...(data.outgoing.length ? data.outgoing.map(row) : [el("p", {class: "empty"}, "No sent requests. "), el("a", {href: "matches.html"}, "Find matches →")]));
    } catch (e) { $("incoming").textContent = e.message; }
  }
  load();
}
