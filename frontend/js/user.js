(async () => {
  const id = Number(new URLSearchParams(location.search).get("id"));
  const view = $("userView");
  if (!id) { view.textContent = "No student selected."; return; }
  let u;
  try { u = await api(`/users/${id}`); }
  catch (e) {
    view.replaceChildren(el("section", {class: "panel"}, el("h2", {}, "Profile unavailable"),
      el("p", {class: "muted"}, e.message),
      getToken() ? null : el("a", {class: "btn", href: "login.html"}, "Log in to view more students")));
    return;
  }
  document.title = `${u.name} | SkillSwap`;
  const teach = u.skills.filter(s => s.type === "teach");
  const learn = u.skills.filter(s => s.type === "learn");
  const chips = list => list.length ? list.map(s => el("span", {class: "skill-chip"}, `${s.name} · ${s.proficiency}`)) : [el("span", {class: "empty"}, "None listed")];

  const actions = el("div", {class: "row-actions"});
  if (u.is_me) {
    actions.append(el("a", {class: "btn", href: "profile.html"}, "Edit my profile"));
    if (u.is_public) actions.append(el("button", {class: "btn btn-outline", onclick: async () => {
      try { await navigator.clipboard.writeText(location.href); toast("Link copied", "ok"); } catch { prompt("Copy link:", location.href); }
    }}, "Copy public link"));
  } else if (!getToken()) {
    actions.append(el("a", {class: "btn", href: "register.html"}, `Join SkillSwap to connect with ${u.name.split(" ")[0]}`));
  } else if (u.relationship === "connected") {
    actions.append(el("a", {class: "btn", href: `chat.html?partner=${u.id}`}, "Message"),
                   el("a", {class: "btn btn-outline", href: `sessions.html?partner=${u.id}`}, "Plan a session"));
  } else if (u.relationship === "pending_received") {
    actions.append(el("a", {class: "btn", href: "requests.html"}, "Respond to their request"));
  } else {
    const b = el("button", {class: "btn", disabled: u.relationship === "pending_sent"}, u.relationship === "pending_sent" ? "Request sent" : "Send learning request");
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await api("/requests", {method: "POST", body: JSON.stringify({receiver_id: u.id, message: "Hi! I found your profile on SkillSwap. Would you like to exchange skills?"})}); b.textContent = "Request sent"; toast("Request sent", "ok"); }
      catch (e) { toast(e.message, "error"); b.disabled = false; }
    });
    actions.append(b);
  }

  const reviews = el("section", {class: "panel", id: "review"},
    el("h2", {}, "Reviews ", u.review_count ? el("span", {class: "rating"}, `★ ${u.avg_rating} · ${u.review_count}`) : null),
    ...(u.reviews.length ? u.reviews.map(r => el("div", {class: "request-row"},
      el("div", {class: "request-head"}, el("b", {}, r.reviewer_name), el("span", {class: "stars"}, "★".repeat(r.rating) + "☆".repeat(5 - r.rating))),
      r.comment ? el("p", {class: "small"}, r.comment) : null)) : [el("p", {class: "empty"}, "No reviews yet.")]));

  if (u.relationship === "connected") {
    let rating = u.my_review?.rating || 0;
    const starBox = el("div", {class: "star-input", role: "radiogroup", "aria-label": "Rating"});
    const paint = () => [...starBox.children].forEach((s, i) => s.classList.toggle("on", i < rating));
    for (let i = 1; i <= 5; i++) starBox.append(el("button", {type: "button", "aria-label": `${i} star${i > 1 ? "s" : ""}`, onclick: () => { rating = i; paint(); }}, "★"));
    paint();
    const comment = el("textarea", {rows: 2, maxlength: 500, placeholder: "How was learning with them?"});
    comment.value = u.my_review?.comment || "";
    const form = el("form", {class: "review-form"}, el("h3", {}, u.my_review ? "Update your review" : "Leave a review"), starBox, comment,
      el("button", {class: "btn", type: "submit"}, "Save review"));
    form.addEventListener("submit", async e => {
      e.preventDefault();
      if (!rating) { toast("Pick a star rating", "error"); return; }
      try { const r = await api("/reviews", {method: "POST", body: JSON.stringify({reviewed_user_id: u.id, rating, comment: comment.value})}); toast(r.message, "ok"); setTimeout(() => location.reload(), 600); }
      catch (err) { toast(err.message, "error"); }
    });
    reviews.append(form);
  }

  view.replaceChildren(
    el("section", {class: "panel profile-hero"},
      avatar(u, "large"),
      el("div", {class: "grow"},
        el("span", {class: "eyebrow"}, u.is_me ? "YOUR PROFILE" : "STUDENT PROFILE"),
        el("h1", {class: "profile-name"}, u.name),
        el("p", {class: "muted"}, [u.college, u.branch, u.year].filter(Boolean).join(" · ") || "Student"),
        el("div", {class: "badge-row"}, verifiedBadge(u), ratingText(u),
          u.linkedin_url ? el("a", {href: u.linkedin_url, target: "_blank", rel: "noopener noreferrer"}, "LinkedIn profile ↗") : null,
          u.is_me && !u.is_public ? el("span", {class: "pill"}, "Private — only logged-in students can see this") : null),
        u.bio ? el("p", {class: "bio"}, u.bio) : null,
        actions)),
    el("section", {class: "panel"}, el("h2", {}, "Can teach"), el("div", {class: "skill-list"}, ...chips(teach)),
      el("h2", {class: "mt"}, "Wants to learn"), el("div", {class: "skill-list"}, ...chips(learn))),
    reviews);
  if (location.hash === "#review") $("review").scrollIntoView();
})();
