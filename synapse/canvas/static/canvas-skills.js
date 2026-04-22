(function(ns) {
  "use strict";

  const container = document.getElementById("skills-container");
  const tableWrap = document.getElementById("skills-table-wrap");
  const countLabel = document.getElementById("skills-count");
  const searchInput = document.getElementById("skills-search");

  const SCOPE = Object.freeze({
    USER: "user",
    PROJECT: "project",
    PLUGIN: "plugin",
    SYNAPSE: "synapse",
  });

  // Agent bucket metadata — splits ".claude/skills" (Claude Code) from
  // ".agents/skills" (shared by Codex / OpenCode / Gemini / Copilot).
  const AGENT_BUCKETS = [
    { id: "claude",  title: "Claude Code",                       icon: "ph-sparkle", dir: ".claude" },
    { id: "agents",  title: "Codex / OpenCode / Gemini / Copilot", icon: "ph-robot",   dir: ".agents" },
  ];

  function getSkills() {
    const data = ns._lastSystemData;
    return data && Array.isArray(data.skills) ? data.skills : [];
  }

  function fingerprint(skills) {
    // Include agent_dirs and project_root so changes in grouping/location
    // trigger a re-render, not just changes to name/scope/path/description.
    let out = "";
    for (const s of skills) {
      const dirs = (s.agent_dirs || []).slice().sort().join(",");
      out += (s.name || "") + "\t" + (s.scope || "") + "\t" + (s.path || "") + "\t"
        + (s.description || "") + "\t" + dirs + "\t" + (s.project_root || "") + "\n";
    }
    return out;
  }

  function basenameOf(p) {
    if (!p) return "";
    const trimmed = p.replace(/\/+$/, "");
    const idx = trimmed.lastIndexOf("/");
    return idx >= 0 ? trimmed.slice(idx + 1) : trimmed;
  }

  function hasAgentDir(skill, dirName) {
    return (skill.agent_dirs || []).includes(dirName);
  }

  // ─────────────────────────────────────────────
  // Rendering primitives (shared with MCP viewer)
  // ─────────────────────────────────────────────

  function makeGroupRow(labelMain, labelSub, count, key, icon) {
    const tr = document.createElement("tr");
    tr.className = "skill-group-row";
    tr.dataset.groupKey = key;
    tr.setAttribute("role", "button");
    tr.setAttribute("aria-expanded", "true");
    tr.tabIndex = 0;

    const td = document.createElement("td");
    td.colSpan = 3;
    td.className = "skill-group-cell";

    const row = document.createElement("div");
    row.className = "skill-group-cell-row";

    const caret = document.createElement("i");
    caret.className = "ph ph-caret-down skill-group-caret";
    row.appendChild(caret);

    const gicon = document.createElement("i");
    gicon.className = "ph " + (icon || "ph-folder") + " skill-group-icon";
    row.appendChild(gicon);

    const title = document.createElement("span");
    title.className = "skill-group-title";
    title.textContent = labelMain || "(unknown)";
    row.appendChild(title);

    if (labelSub) {
      const sub = document.createElement("span");
      sub.className = "skill-group-subtitle";
      sub.textContent = labelSub;
      row.appendChild(sub);
    }

    const countEl = document.createElement("span");
    countEl.className = "skill-group-count";
    countEl.textContent = String(count);
    row.appendChild(countEl);

    td.appendChild(row);
    tr.appendChild(td);
    return tr;
  }

  function makeChildRow(skill) {
    const tr = document.createElement("tr");
    tr.className = "skill-row";
    tr.dataset.skillName = skill.name;

    const tdName = document.createElement("td");
    tdName.className = "skill-name-cell";
    const nameInner = document.createElement("div");
    nameInner.className = "skill-name-cell-inner";
    const indent = document.createElement("span");
    indent.className = "skill-indent";
    nameInner.appendChild(indent);
    const icon = document.createElement("i");
    icon.className = "ph ph-puzzle-piece skill-row-icon";
    nameInner.appendChild(icon);
    const nameSpan = document.createElement("span");
    nameSpan.className = "skill-row-name";
    nameSpan.textContent = skill.name;
    nameInner.appendChild(nameSpan);
    tdName.appendChild(nameInner);
    tr.appendChild(tdName);

    const tdDesc = document.createElement("td");
    tdDesc.className = "desc-cell";
    tdDesc.textContent = skill.description || "-";
    tr.appendChild(tdDesc);

    const tdLoc = document.createElement("td");
    tdLoc.className = "skill-location-cell";

    const targets = (skill.agent_dirs || []).filter(Boolean);
    const tline = document.createElement("div");
    tline.className = "skill-location-targets";
    if (targets.length === 0) {
      tline.textContent = "-";
    } else {
      for (const t of targets) {
        const chip = document.createElement("span");
        chip.className = "skill-target-chip";
        chip.textContent = t;
        tline.appendChild(chip);
      }
    }
    tdLoc.appendChild(tline);

    const pline = document.createElement("div");
    pline.className = "skill-location-path";
    pline.textContent = skill.path || "-";
    pline.title = skill.source_file || skill.path || "";
    tdLoc.appendChild(pline);

    tr.appendChild(tdLoc);

    return tr;
  }

  function setCollapsed(parentRow, collapsed) {
    parentRow.classList.toggle("is-collapsed", collapsed);
    parentRow.setAttribute("aria-expanded", collapsed ? "false" : "true");
    const caret = parentRow.querySelector(".skill-group-caret");
    if (caret) {
      caret.classList.toggle("ph-caret-down", !collapsed);
      caret.classList.toggle("ph-caret-right", collapsed);
    }
    const childRows = parentRow._childRows || [];
    if (collapsed) {
      for (const r of childRows) r.classList.add("is-hidden-by-collapse");
      return;
    }
    // Expanding: reveal direct children, but respect any nested groups that
    // are still collapsed (their own children should remain hidden).
    const hiddenNested = new Set();
    for (const r of childRows) {
      if (r.classList.contains("skill-group-row") && r.classList.contains("is-collapsed")) {
        for (const nr of r._childRows || []) hiddenNested.add(nr);
      }
    }
    for (const r of childRows) {
      if (hiddenNested.has(r)) continue;
      r.classList.remove("is-hidden-by-collapse");
    }
  }

  function toggleGroup(parentRow) {
    setCollapsed(parentRow, !parentRow.classList.contains("is-collapsed"));
  }

  function attachToggle(parentRow) {
    const toggle = () => toggleGroup(parentRow);
    parentRow.addEventListener("click", toggle);
    parentRow.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggle();
      }
    });
  }

  function appendGroup(tbody, groupKey, labelMain, labelSub, skills, icon) {
    const parentRow = makeGroupRow(labelMain, labelSub, skills.length, groupKey, icon);
    tbody.appendChild(parentRow);
    const childRows = [];
    for (const sk of skills) {
      const child = makeChildRow(sk);
      child.dataset.groupKey = groupKey;
      tbody.appendChild(child);
      childRows.push(child);
    }
    parentRow._childRows = childRows;
    attachToggle(parentRow);
  }

  // ─────────────────────────────────────────────
  // Section builders
  // ─────────────────────────────────────────────

  function makeSection(id, title, icon, count) {
    const wrap = document.createElement("section");
    wrap.className = "harness-section";
    wrap.dataset.sectionId = id;

    const header = document.createElement("header");
    header.className = "harness-section-header";
    const hicon = document.createElement("i");
    hicon.className = "ph " + icon + " harness-section-icon";
    header.appendChild(hicon);
    const htitle = document.createElement("h3");
    htitle.className = "harness-section-title";
    htitle.textContent = title;
    header.appendChild(htitle);
    const hcount = document.createElement("span");
    hcount.className = "harness-section-count";
    hcount.textContent = "(" + count + ")";
    header.appendChild(hcount);
    wrap.appendChild(header);

    const tableWrapEl = document.createElement("div");
    tableWrapEl.className = "harness-section-table-wrap";
    const table = document.createElement("table");
    table.className = "system-agents-table has-desc skills-tree-table";

    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["NAME", "DESCRIPTION", "LOCATION"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    table.appendChild(tbody);
    tableWrapEl.appendChild(table);
    wrap.appendChild(tableWrapEl);
    return { wrap, tbody };
  }

  function bucketByAgentDir(skills) {
    // Returns ordered buckets [{bucket, skills: [...]}] covering known agent
    // dirs plus an "other" fallback for anything outside .claude/.agents.
    const buckets = new Map(AGENT_BUCKETS.map(b => [b.id, []]));
    const other = [];
    for (const sk of skills) {
      let placed = false;
      for (const b of AGENT_BUCKETS) {
        if (hasAgentDir(sk, b.dir)) {
          buckets.get(b.id).push(sk);
          placed = true;
        }
      }
      if (!placed) other.push(sk);
    }
    const out = [];
    for (const meta of AGENT_BUCKETS) {
      const items = buckets.get(meta.id);
      if (items.length) out.push({ meta, skills: items });
    }
    if (other.length) {
      out.push({ meta: { id: "other", title: "Other", icon: "ph-folder" }, skills: other });
    }
    return out;
  }

  function buildUserSection(skills) {
    if (!skills.length) return null;
    const { wrap, tbody } = makeSection("user", "User Global", "ph-user", skills.length);
    for (const b of bucketByAgentDir(skills)) {
      const sorted = b.skills.slice().sort((a, b2) => (a.name || "").localeCompare(b2.name || ""));
      appendGroup(tbody, "user::" + b.meta.id, b.meta.title, b.meta.dir || "", sorted, b.meta.icon);
    }
    return wrap;
  }

  function buildSynapseSection(skills) {
    if (!skills.length) return null;
    const { wrap, tbody } = makeSection("synapse", "Synapse Central Store", "ph-globe", skills.length);
    // Synapse has flat structure under ~/.synapse/skills/, no agent split.
    const sorted = skills.slice().sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    for (const sk of sorted) {
      const row = makeChildRow(sk);
      tbody.appendChild(row);
    }
    return wrap;
  }

  function buildProjectsSection(skills) {
    if (!skills.length) return null;
    const { wrap, tbody } = makeSection("projects", "Projects", "ph-folder-open", skills.length);

    // Group by project root; within each project, sub-group by agent dir
    const byRoot = new Map();
    for (const sk of skills) {
      const root = sk.project_root || "";
      if (!byRoot.has(root)) byRoot.set(root, []);
      byRoot.get(root).push(sk);
    }
    const roots = Array.from(byRoot.keys()).sort((a, b) => a.localeCompare(b));

    for (const root of roots) {
      const rootSkills = byRoot.get(root);
      const buckets = bucketByAgentDir(rootSkills);
      // Render a top-level row per project directory; then each agent bucket
      // as a nested collapsible group underneath. We reuse the same row shape
      // (makeGroupRow) for both levels — nesting-indent-style is purely visual.
      const rootKey = "projects::" + root;
      const rootRow = makeGroupRow(basenameOf(root), root, rootSkills.length, rootKey, "ph-folder");
      tbody.appendChild(rootRow);
      const rootChildren = [];

      for (const b of buckets) {
        const bucketKey = rootKey + "::" + b.meta.id;
        const sorted = b.skills.slice().sort((a, c) => (a.name || "").localeCompare(c.name || ""));

        if (buckets.length === 1) {
          // Only one agent bucket for this project — skip the inner header
          // and render skills directly under the project row.
          for (const sk of sorted) {
            const row = makeChildRow(sk);
            row.dataset.groupKey = rootKey;
            tbody.appendChild(row);
            rootChildren.push(row);
          }
        } else {
          const agentRow = makeGroupRow(b.meta.title, b.meta.dir || "", sorted.length, bucketKey, b.meta.icon);
          agentRow.classList.add("skill-group-row--nested");
          tbody.appendChild(agentRow);
          rootChildren.push(agentRow);
          const agentChildren = [];
          for (const sk of sorted) {
            const row = makeChildRow(sk);
            row.dataset.groupKey = bucketKey;
            row.classList.add("skill-row--nested");
            tbody.appendChild(row);
            rootChildren.push(row);
            agentChildren.push(row);
          }
          agentRow._childRows = agentChildren;
          attachToggle(agentRow);
        }
      }
      rootRow._childRows = rootChildren;
      attachToggle(rootRow);
    }
    return wrap;
  }

  function applyFilter() {
    const q = (searchInput ? searchInput.value : "").trim().toLowerCase();
    const filtering = q.length > 0;
    const total = getSkills().length;
    let visible = 0;

    const sections = tableWrap.querySelectorAll(".harness-section");
    for (const section of sections) {
      const visibleRows = new Set();
      const groupRows = section.querySelectorAll("tr.skill-group-row");
      if (groupRows.length) {
        for (const parent of groupRows) {
          const children = parent._childRows || [];
          let matchCount = 0;
          for (const child of children) {
            if (child.classList.contains("skill-group-row")) continue;
            const name = (child.dataset.skillName || "").toLowerCase();
            const hit = !filtering || name.includes(q);
            child.classList.toggle("is-hidden-by-filter", !hit);
            if (hit) {
              matchCount++;
              visibleRows.add(child);
            }
          }
          const groupHasMatches = !filtering || matchCount > 0;
          parent.classList.toggle("is-hidden-by-filter", !groupHasMatches);
          if (filtering && groupHasMatches && parent.classList.contains("is-collapsed")) {
            setCollapsed(parent, false);
          }
        }
      }
      // Flat rows (sections without group headers, e.g. Synapse)
      const flat = section.querySelectorAll("tr.skill-row:not([data-group-key])");
      for (const r of flat) {
        const name = (r.dataset.skillName || "").toLowerCase();
        const hit = !filtering || name.includes(q);
        r.classList.toggle("is-hidden-by-filter", !hit);
        if (hit) visibleRows.add(r);
      }
      section.classList.toggle("is-hidden-by-filter", filtering && visibleRows.size === 0);
      visible += visibleRows.size;
    }

    if (countLabel) {
      countLabel.textContent = filtering ? `(${visible} / ${total})` : `(${total})`;
    }
  }

  function renderEmpty(message) {
    return ns.emptyState
      ? ns.emptyState(message)
      : Object.assign(document.createElement("div"), { className: "system-empty", textContent: message });
  }

  function renderAll(skills) {
    const frag = document.createDocumentFragment();
    if (!skills.length) {
      frag.appendChild(renderEmpty("No skills discovered in project or user scopes."));
      return frag;
    }

    const userSkills    = skills.filter(s => s.scope === SCOPE.USER);
    const projectSkills = skills.filter(s => s.scope === SCOPE.PROJECT || s.scope === SCOPE.PLUGIN);
    const synapseSkills = skills.filter(s => s.scope === SCOPE.SYNAPSE);

    const userSec = buildUserSection(userSkills);
    if (userSec) frag.appendChild(userSec);

    const projSec = buildProjectsSection(projectSkills);
    if (projSec) frag.appendChild(projSec);

    const synSec = buildSynapseSection(synapseSkills);
    if (synSec) frag.appendChild(synSec);

    return frag;
  }

  let _lastFingerprint = null;

  function refreshRender(force) {
    if (!tableWrap) return;
    const skills = getSkills();
    const fp = fingerprint(skills);
    if (!force && fp === _lastFingerprint) return;
    _lastFingerprint = fp;

    if (countLabel) countLabel.textContent = `(${skills.length})`;
    tableWrap.innerHTML = "";
    tableWrap.appendChild(renderAll(skills));
    if (searchInput && searchInput.value) applyFilter();
  }

  async function loadSkillsView() {
    if (!container) return;

    if (ns._lastSystemData && Array.isArray(ns._lastSystemData.skills)) {
      refreshRender(true);
      ns.loadSystemPanel && ns.loadSystemPanel();
      return;
    }

    try {
      const resp = await fetch("/api/system");
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      ns._lastSystemData = await resp.json();
      refreshRender(true);
    } catch (e) {
      console.error("Failed to load skills:", e);
      if (tableWrap) {
        tableWrap.innerHTML = "";
        tableWrap.appendChild(renderEmpty("Failed to load skills. Check the Canvas server logs."));
      }
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyFilter);
  }

  document.addEventListener("synapse:system-updated", function() {
    if (ns.currentRoute !== "skills") return;
    refreshRender(false);
  });

  ns.loadSkillsView = loadSkillsView;
})(window.SynapseCanvas);
