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

  const formFields = [...$("profileForm").elements];
  formFields.forEach(f => f.disabled = true);  // avoid typing before the profile has loaded
  (async () => {
    try {
      linkedinEnabled = (await api("/linkedin/config")).enabled;
      await loadProfile();
      formFields.forEach(f => f.disabled = false);
      api("/skills/suggestions").then(list => $("skillSuggestions").replaceChildren(...list.map(n => el("option", {value: n})))).catch(() => {});
      const result = results[params.get("linkedin")];
      if (result) { toast(...result); history.replaceState(null, "", "profile.html#verify"); }
      if (params.get("welcome")) $("profileMessage").textContent = "Welcome! Fill in your details and add a few skills to get matched.";
    } catch (e) { $("profileMessage").textContent = e.message; }
  })();
}
