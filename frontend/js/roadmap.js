if (requireLogin()) {
  // Very small, safe Markdown renderer: headings, bullets, numbered lists, bold, code.
  function inline(text, parent){
    text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).forEach(part => {
      if (/^\*\*[^*]+\*\*$/.test(part)) parent.append(el("strong", {}, part.slice(2, -2)));
      else if (/^`[^`]+`$/.test(part)) parent.append(el("code", {}, part.slice(1, -1)));
      else if (part) parent.append(part.replace(/(^|\s)\*([^*]+)\*/g, "$1$2"));
    });
    return parent;
  }
  function renderMarkdown(md){
    const out = document.createDocumentFragment();
    let list = null;
    md.split(/\r?\n/).forEach(raw => {
      const line = raw.trimEnd();
      const heading = line.match(/^(#{1,4})\s+(.*)/);
      const bullet = line.match(/^\s*[-*•]\s+(.*)/);
      const numbered = line.match(/^\s*\d+[.)]\s+(.*)/);
      if (bullet || numbered) {
        const type = bullet ? "ul" : "ol";
        if (!list || list.tagName.toLowerCase() !== type) { list = el(type); out.append(list); }
        list.append(inline((bullet || numbered)[1], el("li")));
        return;
      }
      list = null;
      if (heading) out.append(inline(heading[2], el(`h${Math.min(heading[1].length + 1, 4)}`)));
      else if (/^\s*([-*_]){3,}\s*$/.test(line)) out.append(el("hr"));
      else if (line.trim()) out.append(inline(line, el("p")));
    });
    return out;
  }

  let lastRoadmap = "";
  $("roadmapForm").addEventListener("submit", async e => {
    e.preventDefault();
    const result = $("roadmapResult"), button = $("roadmapBtn");
    result.textContent = "Generating your roadmap… this can take 10–20 seconds.";
    button.disabled = true; $("roadmapActions").hidden = true;
    try {
      const data = await api("/ai/roadmap", {method: "POST", body: JSON.stringify({
        topic: $("topic").value, level: $("level").value, goal: $("goal").value})});
      lastRoadmap = data.roadmap;
      result.replaceChildren(renderMarkdown(data.roadmap));
      $("roadmapActions").hidden = false;
    } catch (err) { result.textContent = err.message; }
    button.disabled = false;
  });
  $("copyRoadmap").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(lastRoadmap); toast("Roadmap copied", "ok"); } catch { toast("Couldn't copy", "error"); }
  });
  $("printRoadmap").addEventListener("click", () => window.print());
}
