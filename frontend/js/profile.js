if (requireLogin()) {
  const params = new URLSearchParams(location.search);
  let profile = null;
  let linkedinEnabled = false;

  function skillChip(s){
    return el("span", {class: `skill-chip ${s.type}`},
      `${s.name} · ${s.proficiency}`,
      el("button", {type: "button", title: `Remove ${s.name}`, "aria-label": `Remove ${s.name}`, onclick: async () => {
        try { await api(`/skills/${s.id}`, {method: "DELETE"}); toast(`${s.name} removed`); await loadProfile(); }
        catch (err) { toast(err.message, "error"); }
      }}, "×"));
  }

  function renderSkills(){
    const teach = profile.skills.filter(s => s.type === "teach");
    const learn = profile.skills.filter(s => s.type === "learn");
    $("teachList").replaceChildren(...(teach.length ? teach.map(skillChip) : [el("span", {class: "empty"}, "No teaching skills yet.")]));
    $("learnList").replaceChildren(...(learn.length ? learn.map(skillChip) : [el("span", {class: "empty"}, "No learning goals yet.")]));
  }

  function publicUrl(){ return new URL(profileLink(profile.id), location.href).href; }

  function renderVerify(){
    const pill = $("verifyPill"), box = $("verifyBody");
    const status = profile.linkedin_status;
    pill.className = "pill " + (status === "verified" ? "pill-ok" : status === "mismatch" ? "pill-warn" : "");
    pill.textContent = status === "verified" ? "✓ Verified" : status === "mismatch" ? "Name mismatch" : "Not verified";

    const connectBtn = el("button", {class: "btn btn-linkedin", type: "button", disabled: !linkedinEnabled, onclick: startLinkedIn},
      status === "unverified" ? "Verify with LinkedIn" : "Re-check with LinkedIn");
    const items = [];
    if (status !== "unverified") {
      items.push(el("div", {class: "verify-compare"},
        el("div", {}, el("small", {class: "muted"}, "Name on SkillSwap"), el("b", {}, profile.name)),
        el("div", {class: "verify-arrow"}, status === "verified" ? "✓" : "≠"),
        el("div", {}, el("small", {class: "muted"}, "Name on LinkedIn"), el("b", {}, profile.linkedin_name || "—"))),
        el("ul", {class: "checklist"},
          el("li", {class: status === "verified" ? "done" : "bad"}, `Name match: ${profile.linkedin_name_score}%`),
          el("li", {class: profile.linkedin_email_match ? "done" : "neutral"},
            profile.linkedin_email_match ? "Email matches your LinkedIn email" : "LinkedIn email differs from your SkillSwap email (that's okay)"),
          profile.linkedin_checked_at ? el("li", {class: "neutral"}, `Last checked ${formatDate(profile.linkedin_checked_at)}`) : null));
      if (status === "mismatch") {
        items.push(el("p", {class: "muted"}, "Update your name above to match LinkedIn and save, or use your LinkedIn name directly:"),
          el("button", {class: "btn", type: "button", onclick: async () => {
            try { const r = await api("/linkedin/use-name", {method: "POST"}); toast(r.message, "ok"); await loadProfile(); }
            catch (err) { toast(err.message, "error"); }
          }}, `Use “${profile.linkedin_name}”`));
      }
    }
    const actions = el("div", {class: "row-actions"}, connectBtn);
    if (status !== "unverified") actions.append(el("button", {class: "btn btn-outline", type: "button", onclick: async () => {
      if (!confirm("Disconnect LinkedIn and remove your verified badge?")) return;
      try { await api("/linkedin/disconnect", {method: "POST"}); toast("LinkedIn disconnected"); await loadProfile(); }
      catch (err) { toast(err.message, "error"); }
    }}, "Disconnect"));
    items.push(actions);
    if (!linkedinEnabled) items.push(el("p", {class: "form-message"}, "LinkedIn verification hasn't been switched on by the site admin yet."));
    box.replaceChildren(...items);
  }

  async function startLinkedIn(){
    try { const r = await api("/linkedin/start", {method: "POST"}); window.location.href = r.url; }
    catch (err) { toast(err.message, "error"); }
  }

  async function loadProfile(){
    profile = await api("/profile");
    ["name", "college", "branch", "year", "bio", "linkedin_url"].forEach(k => $(k).value = profile[k] || "");
    $("is_public").checked = profile.is_public;
    $("viewProfile").href = profileLink(profile.id);
    $("copyLink").hidden = !profile.is_public;
    renderSkills();
    renderVerify();
  }

  $("profileForm").addEventListener("submit", async e => {
    e.preventDefault();
    const msg = $("profileMessage");
    try {
      const r = await api("/profile", {method: "PUT", body: JSON.stringify({
        name: $("name").value, college: $("college").value, branch: $("branch").value,
        year: $("year").value, bio: $("bio").value, linkedin_url: $("linkedin_url").value,
        is_public: $("is_public").checked,
      })});
      msg.textContent = r.message; toast("Profile saved", "ok");
      const user = getUser(); user.name = $("name").value; localStorage.setItem("skillswap_user", JSON.stringify(user));
      await loadProfile();
    } catch (err) { msg.textContent = err.message; }
  });

  $("copyLink").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(publicUrl()); toast("Public link copied", "ok"); }
    catch { prompt("Copy your public profile link:", publicUrl()); }
  });

  $("skillForm").addEventListener("submit", async e => {
    e.preventDefault();
    const msg = $("skillMessage");
    try {
      await api("/skills", {method: "POST", body: JSON.stringify({
        name: $("skillName").value, type: $("skillType").value, proficiency: $("proficiency").value})});
      $("skillName").value = ""; msg.textContent = "Skill added."; await loadProfile();
    } catch (err) { msg.textContent = err.message; }
  });

  const results = {
    verified: ["LinkedIn verified! Your name matches. ✓", "ok"],
    mismatch: ["LinkedIn connected, but your names don't match. See below.", "error"],
    cancelled: ["LinkedIn verification was cancelled.", "info"],
    expired: ["The verification link expired. Please try again.", "error"],
    already_linked: ["That LinkedIn account is already linked to another SkillSwap account.", "error"],
    error: ["LinkedIn verification failed. Please try again.", "error"],
  };

  // ---------- Verify with Google ----------
  let googleEnabled = false;
  async function renderGoogle(){
    let box = $("googleVerify");
    if (!box) {
      box = el("section", {class: "panel", id: "googleVerify"});
      $("verify").after(box);
    }
    const g = await api("/google/status");
    const pill = el("span", {class: "pill " + (g.status === "verified" ? "pill-ok" : g.status === "mismatch" ? "pill-warn" : "")},
      g.status === "verified" ? "✓ Verified" : g.status === "mismatch" ? "Name mismatch" : "Not verified");
    const items = [el("div", {class: "panel-head"}, el("div", {}, el("span", {class: "eyebrow"}, "TRUST & SAFETY"), el("h2", {}, "Verify with Google")), pill),
      el("p", {class: "muted"}, "No LinkedIn? Sign in with Google instead. We cross-check your Google name and email with this profile.")];
    if (g.status !== "unverified") {
      items.push(el("div", {class: "verify-compare"},
        el("div", {}, el("small", {class: "muted"}, "Name on SkillSwap"), el("b", {}, profile.name)),
        el("div", {class: "verify-arrow"}, g.status === "verified" ? "✓" : "≠"),
        el("div", {}, el("small", {class: "muted"}, "Name on Google"), el("b", {}, g.name || "—"))),
        el("ul", {class: "checklist"}, el("li", {class: g.email_match ? "done" : "neutral"},
          g.email_match ? "Email matches your Google email" : "Google email differs from your SkillSwap email (that's okay)")));
      if (g.status === "mismatch") items.push(el("button", {class: "btn", type: "button", onclick: async () => {
        try { const r = await api("/google/use-name", {method: "POST"}); toast(r.message, "ok"); await loadProfile(); await renderGoogle(); }
        catch (err) { toast(err.message, "error"); }
      }}, `Use “${g.name}”`));
    }
    const actions = el("div", {class: "row-actions"}, el("button", {class: "btn", type: "button", disabled: !googleEnabled, onclick: async () => {
      try { const r = await api("/google/start", {method: "POST"}); window.location.href = r.url; } catch (err) { toast(err.message, "error"); }
    }}, g.status === "unverified" ? "Verify with Google" : "Re-check with Google"));
    if (g.status !== "unverified") actions.append(el("button", {class: "btn btn-outline", type: "button", onclick: async () => {
      try { await api("/google/disconnect", {method: "POST"}); toast("Google disconnected"); await renderGoogle(); } catch (err) { toast(err.message, "error"); }
    }}, "Disconnect"));
    items.push(actions);
    if (!googleEnabled) items.push(el("p", {class: "form-message"}, "Google verification hasn't been switched on by the site admin yet."));
    box.replaceChildren(...items);
  }

  const formFields = [...$("profileForm").elements];
  formFields.forEach(f => f.disabled = true);  // avoid typing before the profile has loaded
  (async () => {
    try {
      linkedinEnabled = (await api("/linkedin/config")).enabled;
      await loadProfile();
      formFields.forEach(f => f.disabled = false);
      api("/skills/suggestions").then(list => $("skillSuggestions").replaceChildren(...list.map(n => el("option", {value: n})))).catch(() => {});
      try { googleEnabled = (await api("/google/config")).enabled; await renderGoogle(); } catch {}
      const gResult = {verified: ["Google verified! Your name matches. ✓", "ok"], mismatch: ["Google connected, but your names don't match. See below.", "error"],
        cancelled: ["Google verification was cancelled.", "info"], expired: ["The verification link expired. Please try again.", "error"],
        already_linked: ["That Google account is already linked to another SkillSwap account.", "error"], error: ["Google verification failed. Please try again.", "error"]}[params.get("google")];
      if (gResult) { toast(...gResult); history.replaceState(null, "", "profile.html#verify"); }
      const result = results[params.get("linkedin")];
      if (result) { toast(...result); history.replaceState(null, "", "profile.html#verify"); }
      if (params.get("welcome")) $("profileMessage").textContent = "Welcome! Fill in your details and add a few skills to get matched.";
    } catch (e) { $("profileMessage").textContent = e.message; }
  })();
}
