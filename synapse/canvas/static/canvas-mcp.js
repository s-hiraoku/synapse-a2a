(function(ns) {
  "use strict";

  const container = document.getElementById("mcp-container");
  const tableWrap = document.getElementById("mcp-table-wrap");
  const countLabel = document.getElementById("mcp-count");
  const searchInput = document.getElementById("mcp-search");

  // Top-level sections (大分類)
  const TOP = Object.freeze({
    PROJECTS: "projects",
    USER:     "user",
  });

  // Agent subsections (中分類 inside User Global)
  const AGENT_META = {
    claude:         { title: "Claude Code",    icon: "ph-sparkle",         order: 0 },
    codex:          { title: "Codex",          icon: "ph-code",            order: 1 },
    gemini:         { title: "Gemini",         icon: "ph-gemini-logo",     order: 2 },
    opencode:       { title: "OpenCode",       icon: "ph-terminal-window", order: 3 },
    claude_desktop: { title: "Claude Desktop", icon: "ph-desktop",         order: 4 },
  };
  const AGENT_SCOPES = Object.keys(AGENT_META);

  function getServers() {
    const data = ns._lastSystemData;
    return data && Array.isArray(data.mcp_servers) ? data.mcp_servers : [];
  }

  function fingerprint(servers) {
    let out = "";
    for (const s of servers) {
      out += (s.name || "") + "\t" + (s.scope || "") + "\t" + (s.command || "") + "\t"
        + (s.args || []).join(" ") + "\t" + (s.env_keys || []).join(",") + "\n";
    }
    return out;
  }

  function commandLine(server) {
    const parts = [server.command || ""];
    for (const a of server.args || []) parts.push(String(a));
    return parts.filter(Boolean).join(" ");
  }

  function basenameOf(p) {
    if (!p) return "";
    const trimmed = p.replace(/\/+$/, "");
    const idx = trimmed.lastIndexOf("/");
    return idx >= 0 ? trimmed.slice(idx + 1) : trimmed;
  }

  // ─────────────────────────────────────────────
  // Grouping + rendering primitives
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

  function makeChildRow(server) {
    const tr = document.createElement("tr");
    tr.className = "skill-row";
    tr.dataset.skillName = server.name;

    const tdName = document.createElement("td");
    tdName.className = "skill-name-cell";
    const nameInner = document.createElement("div");
    nameInner.className = "skill-name-cell-inner";
    const indent = document.createElement("span");
    indent.className = "skill-indent";
    nameInner.appendChild(indent);
    const icon = document.createElement("i");
    icon.className = "ph ph-plugs-connected skill-row-icon";
    nameInner.appendChild(icon);
    const nameSpan = document.createElement("span");
    nameSpan.className = "skill-row-name";
    nameSpan.textContent = server.name;
    nameInner.appendChild(nameSpan);
    tdName.appendChild(nameInner);
    tr.appendChild(tdName);

    const tdCmd = document.createElement("td");
    tdCmd.className = "desc-cell mcp-command-cell";
    tdCmd.textContent = commandLine(server) || "-";
    tdCmd.title = commandLine(server);
    tr.appendChild(tdCmd);

    const tdLoc = document.createElement("td");
    tdLoc.className = "skill-location-cell";

    const envKeys = (server.env_keys || []).filter(Boolean);
    const tline = document.createElement("div");
    tline.className = "skill-location-targets";
    const type = document.createElement("span");
    type.className = "skill-target-chip";
    type.textContent = server.type || "stdio";
    tline.appendChild(type);
    for (const k of envKeys) {
      const chip = document.createElement("span");
      chip.className = "skill-target-chip mcp-env-chip";
      chip.textContent = "env:" + k;
      tline.appendChild(chip);
    }
    tdLoc.appendChild(tline);

    const pline = document.createElement("div");
    pline.className = "skill-location-path";
    pline.textContent = server.source_file || "-";
    pline.title = server.source_file || "";
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
    for (const r of childRows) r.classList.toggle("is-hidden-by-collapse", collapsed);
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

  function appendGroup(tbody, groupKey, labelMain, labelSub, servers, icon) {
    const parentRow = makeGroupRow(labelMain, labelSub, servers.length, groupKey, icon);
    tbody.appendChild(parentRow);
    const childRows = [];
    for (const sv of servers) {
      const child = makeChildRow(sv);
      child.dataset.groupKey = groupKey;
      tbody.appendChild(child);
      childRows.push(child);
    }
    parentRow._childRows = childRows;
    attachToggle(parentRow);
  }

  // ─────────────────────────────────────────────
  // Top-level section builders
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
    for (const col of ["NAME", "COMMAND", "DETAILS"]) {
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

  function appendEmptyProjectRow(tbody, root) {
    const tr = document.createElement("tr");
    tr.className = "skill-group-row skill-group-row--empty";
    tr.dataset.groupKey = "projects::" + root;

    const td = document.createElement("td");
    td.colSpan = 3;
    td.className = "skill-group-cell";

    const row = document.createElement("div");
    row.className = "skill-group-cell-row";

    const spacer = document.createElement("i");
    spacer.className = "ph skill-group-caret skill-group-caret--empty";
    row.appendChild(spacer);

    const gicon = document.createElement("i");
    gicon.className = "ph ph-folder-dashed skill-group-icon skill-group-icon--empty";
    row.appendChild(gicon);

    const title = document.createElement("span");
    title.className = "skill-group-title skill-group-title--empty";
    title.textContent = basenameOf(root) || "(unknown)";
    row.appendChild(title);

    const sub = document.createElement("span");
    sub.className = "skill-group-subtitle";
    sub.textContent = root;
    row.appendChild(sub);

    const note = document.createElement("span");
    note.className = "skill-group-empty-note";
    note.textContent = "no .mcp.json";
    row.appendChild(note);

    td.appendChild(row);
    tr.appendChild(td);
    tr._childRows = [];  // Filter loop expects this field
    tbody.appendChild(tr);
  }

  function getProjectRoots() {
    const data = ns._lastSystemData;
    return data && Array.isArray(data.project_roots) ? data.project_roots : [];
  }

  function buildProjectsSection(servers) {
    // Collect all known roots — from active agents + any that had servers.
    // This lets us render empty rows for projects that don't have a
    // .mcp.json yet, so the user knows they were scanned.
    const allRoots = new Set(getProjectRoots());
    const byRoot = new Map();
    for (const s of servers) {
      const root = s.project_root || "";
      allRoots.add(root);
      if (!byRoot.has(root)) byRoot.set(root, []);
      byRoot.get(root).push(s);
    }
    if (!allRoots.size) return null;

    const { wrap, tbody } = makeSection("projects", "Projects", "ph-folder-open", servers.length);
    const roots = Array.from(allRoots).sort((a, b) => a.localeCompare(b));

    for (const root of roots) {
      const items = (byRoot.get(root) || []).sort((a, b) => (a.name || "").localeCompare(b.name || ""));
      if (items.length === 0) {
        appendEmptyProjectRow(tbody, root);
      } else {
        appendGroup(tbody, "projects::" + root, basenameOf(root) || "(unknown)", root, items, "ph-folder");
      }
    }
    return wrap;
  }

  function buildUserSection(servers) {
    if (!servers.length) return null;
    const { wrap, tbody } = makeSection("user", "User Global", "ph-user", servers.length);

    // Group by agent scope, ordered by AGENT_META.order
    const byAgent = new Map();
    for (const s of servers) {
      const scope = String(s.scope || "").toLowerCase();
      if (!byAgent.has(scope)) byAgent.set(scope, []);
      byAgent.get(scope).push(s);
    }
    const scopes = Array.from(byAgent.keys()).sort((a, b) => {
      const oa = AGENT_META[a]?.order ?? 99;
      const ob = AGENT_META[b]?.order ?? 99;
      return oa - ob;
    });

    for (const scope of scopes) {
      const meta = AGENT_META[scope] || { title: scope, icon: "ph-folder" };
      const items = byAgent.get(scope).sort((a, b) => (a.name || "").localeCompare(b.name || ""));
      const source = items[0] ? (items[0].source_file || "") : "";
      appendGroup(tbody, "user::" + scope, meta.title, source, items, meta.icon);
    }
    return wrap;
  }

  function applyFilter() {
    const q = (searchInput ? searchInput.value : "").trim().toLowerCase();
    const filtering = q.length > 0;
    const total = getServers().length;
    let visible = 0;

    const sections = tableWrap.querySelectorAll(".harness-section");
    for (const section of sections) {
      let sectionVisible = 0;
      const groupRows = section.querySelectorAll("tr.skill-group-row");
      for (const parent of groupRows) {
        const children = parent._childRows || [];
        let matchCount = 0;
        for (const child of children) {
          const name = (child.dataset.skillName || "").toLowerCase();
          const hit = !filtering || name.includes(q);
          child.classList.toggle("is-hidden-by-filter", !hit);
          if (hit) matchCount++;
        }
        const groupHasMatches = !filtering || matchCount > 0;
        parent.classList.toggle("is-hidden-by-filter", !groupHasMatches);
        if (filtering && groupHasMatches && parent.classList.contains("is-collapsed")) {
          setCollapsed(parent, false);
        }
        if (groupHasMatches) sectionVisible += filtering ? matchCount : children.length;
      }
      section.classList.toggle("is-hidden-by-filter", filtering && sectionVisible === 0);
      visible += sectionVisible;
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

  function renderAll(servers) {
    const frag = document.createDocumentFragment();
    const projectServers = servers.filter(s => s.scope === TOP.PROJECTS || s.scope === "project");
    const userServers = servers.filter(s => AGENT_SCOPES.includes(String(s.scope || "").toLowerCase()));

    if (!servers.length && !getProjectRoots().length) {
      frag.appendChild(renderEmpty("No MCP servers configured in project or user scopes."));
      return frag;
    }

    // User Global first (matches the Skills viewer), Projects underneath.
    const userSec = buildUserSection(userServers);
    if (userSec) frag.appendChild(userSec);

    const projSec = buildProjectsSection(projectServers);
    if (projSec) frag.appendChild(projSec);

    return frag;
  }

  let _lastFingerprint = null;

  function refreshRender(force) {
    if (!tableWrap) return;
    const servers = getServers();
    const fp = fingerprint(servers);
    if (!force && fp === _lastFingerprint) return;
    _lastFingerprint = fp;

    if (countLabel) countLabel.textContent = `(${servers.length})`;
    tableWrap.innerHTML = "";
    tableWrap.appendChild(renderAll(servers));
    if (searchInput && searchInput.value) applyFilter();
  }

  async function loadMcpView() {
    if (!container) return;

    if (ns._lastSystemData && Array.isArray(ns._lastSystemData.mcp_servers)) {
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
      console.error("Failed to load MCP servers:", e);
      if (tableWrap) {
        tableWrap.innerHTML = "";
        tableWrap.appendChild(renderEmpty("Failed to load MCP servers. Check the Canvas server logs."));
      }
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyFilter);
  }

  document.addEventListener("synapse:system-updated", function() {
    if (ns.currentRoute !== "mcp") return;
    refreshRender(false);
  });

  ns.loadMcpView = loadMcpView;
})(window.SynapseCanvas);
