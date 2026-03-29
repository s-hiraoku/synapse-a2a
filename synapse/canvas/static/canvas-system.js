(function(ns) {
  "use strict";
  ns = ns || (window.SynapseCanvas = {});
  // ----------------------------------------------------------------
  // System Panel
  // ----------------------------------------------------------------
  async function loadSystemPanel() {
    if (!systemPanel) return;
    try {
      const resp = await fetch("/api/system");
      if (!resp.ok) return;
      const text = await resp.text();
      // Skip re-render if data hasn't changed (prevents flicker on polling)
      if (text === _lastSystemJSON) return;
      const data = JSON.parse(text);
      // Update cache only after successful parse
      _lastSystemJSON = text;
      systemAgents = Array.isArray(data.agents) ? data.agents : [];
      _lastSystemData = data;
      if (currentRoute === "system") {
        renderSystemPanel(data);
      }
      if (currentRoute === "dashboard") {
        renderDashboard(data);
      }
      if (currentRoute === "history") {
        renderAll();
      }
      if (currentRoute === "admin") {
        loadAdminAgents();
      }
    } catch (e) {
      console.error("Failed to load system panel:", e);
    }
  }

  function renderSystemPanel(data) {
    if (!systemPanel) return;

    const userProfileCount = Array.isArray(data.user_agent_profiles) ? data.user_agent_profiles.length : 0;
    const activeProjectProfileCount = Array.isArray(data.active_project_agent_profiles) ? data.active_project_agent_profiles.length : 0;
    const skillCount = Array.isArray(data.skills) ? data.skills.length : 0;
    const skillSetCount = Array.isArray(data.skill_sets) ? data.skill_sets.length : 0;
    const sessionCount = Array.isArray(data.sessions) ? data.sessions.length : 0;
    const workflowCount = Array.isArray(data.workflows) ? data.workflows.length : 0;

    // Content wrapper
    const content = document.createElement("div");
    content.id = "system-panel-content";

    // ── Information / Tips ──
    if (Array.isArray(data.tips) && data.tips.length > 0) {
      content.appendChild(renderSystemTips(data.tips));
    }

    // ── Saved Agent Profiles ──
    if (userProfileCount > 0) {
      content.appendChild(
        createSystemSection(
          "user-agent-profiles",
          "User Scope Saved Agents (" + userProfileCount + ")",
          renderSystemProfiles(data.user_agent_profiles)
        )
      );
    }

    if (activeProjectProfileCount > 0) {
      content.appendChild(
        createSystemSection(
          "active-project-agent-profiles",
          "Active-Project Saved Agents (" + activeProjectProfileCount + ")",
          renderSystemProfiles(data.active_project_agent_profiles)
        )
      );
    }

    // ── Skills (full-width, wide tables) ──
    content.appendChild(
      createSystemSection(
        "skills",
        "Skills (" + skillCount + ")",
        renderSystemSkills(Array.isArray(data.skills) ? data.skills : [])
      )
    );
    if (skillSetCount > 0) {
      content.appendChild(
        createSystemSection(
          "skill-sets",
          "Skill Sets (" + skillSetCount + ")",
          renderSystemSkillSets(data.skill_sets)
        )
      );
    }

    // ── Configuration group (sessions, workflows, environment) ──
    const configGroup = document.createElement("div");
    configGroup.className = "system-group";

    if (sessionCount > 0) {
      configGroup.appendChild(
        createSystemSection(
          "sessions",
          "Sessions (" + sessionCount + ")",
          renderSystemSessions(data.sessions)
        )
      );
    }
    if (workflowCount > 0) {
      configGroup.appendChild(
        createSystemSection(
          "workflows",
          "Workflows (" + workflowCount + ")",
          renderSystemWorkflows(data.workflows)
        )
      );
    }
    if (data.environment && Object.keys(data.environment).length > 0) {
      configGroup.appendChild(
        createSystemSection(
          "environment",
          "Environment",
          renderSystemEnvironment(data.environment)
        )
      );
    }
    if (configGroup.children.length > 0) {
      content.appendChild(configGroup);
    }

    if (!_systemPanelRendered) {
      content.classList.add('is-new');
      content.querySelectorAll('.system-section').forEach(function(s) {
        s.classList.add('is-new');
      });
      _systemPanelRendered = true;
    }
    // Use replaceChildren to swap content in a single frame (avoids blank flash)
    systemPanel.replaceChildren(content);
  }

  // ----------------------------------------------------------------
  // Dashboard renderers
  // ----------------------------------------------------------------

  var _dashExpandState = {};
  var _dashboardRendered = false;

  function createDashHeader(iconClass, titleText) {
    var header = document.createElement("div");
    header.className = "dash-widget-header";
    var icon = document.createElement("i");
    icon.className = "ph " + iconClass;
    header.appendChild(icon);
    var title = document.createElement("span");
    title.textContent = titleText;
    header.appendChild(title);
    return header;
  }

  /**
   * Create a dashboard widget with summary + expandable detail.
   * @param {string} widgetKey - unique key for expand state persistence
   * @param {string} iconClass - Phosphor icon class (e.g. "ph-robot")
   * @param {string} titleText - header title
   * @param {HTMLElement|null} summaryEl - summary content (always visible)
   * @param {function} detailBuilder - returns HTMLElement (lazy, called only when expanded)
   * @returns {DocumentFragment}
   */
  function createDashWidget(widgetKey, iconClass, titleText, summaryEl, detailBuilder) {
    var frag = document.createDocumentFragment();
    var isExpanded = !!_dashExpandState[widgetKey];

    var wrapper = document.createElement("div");
    wrapper.className = "dash-widget-inner";
    wrapper.setAttribute("data-widget-key", widgetKey);
    wrapper._dashDetailBuilder = detailBuilder;

    // Header with chevron
    var header = createDashHeader(iconClass, titleText);
    var chevron = document.createElement("i");
    chevron.className = "ph ph-caret-down dash-widget-chevron" + (isExpanded ? " expanded" : "");
    header.appendChild(chevron);

    // Detail wrapper — content built lazily on first expand
    var detail = document.createElement("div");
    detail.className = "dash-widget-detail" + (isExpanded ? " expanded" : "");
    if (isExpanded && wrapper._dashDetailBuilder) detail.appendChild(wrapper._dashDetailBuilder());

    header.addEventListener("click", function () {
      _dashExpandState[widgetKey] = !_dashExpandState[widgetKey];
      chevron.classList.toggle("expanded");
      detail.classList.toggle("expanded");
      var builder = wrapper._dashDetailBuilder;
      if (_dashExpandState[widgetKey] && builder) {
        detail.innerHTML = "";
        detail.appendChild(builder());
      }
    });

    var summarySlot = document.createElement("div");
    summarySlot.className = "dash-widget-summary-slot";
    if (summaryEl) summarySlot.appendChild(summaryEl);
    wrapper.appendChild(header);
    wrapper.appendChild(summarySlot);
    wrapper.appendChild(detail);
    frag.appendChild(wrapper);
    return frag;
  }

  function updateDashWidget(el, titleText, summaryBuilder, detailBuilder) {
    var existing = el.querySelector("[data-widget-key]");
    if (!existing) return false;
    var widgetKey = existing.getAttribute("data-widget-key");
    existing._dashDetailBuilder = detailBuilder;

    var headerTitle = existing.querySelector(".dash-widget-header span");
    if (headerTitle) headerTitle.textContent = titleText;

    var slot = existing.querySelector(".dash-widget-summary-slot");
    if (slot) {
      slot.innerHTML = "";
      slot.appendChild(summaryBuilder());
    }

    if (_dashExpandState[widgetKey] && detailBuilder) {
      var detail = existing.querySelector(".dash-widget-detail");
      if (detail) {
        detail.innerHTML = "";
        detail.appendChild(detailBuilder());
      }
    }
    return true;
  }

  function formatElapsed(isoOrUnix) {
    if (!isoOrUnix) return "";
    var ts = typeof isoOrUnix === "number" ? isoOrUnix : new Date(isoOrUnix).getTime() / 1000;
    var elapsed = Math.floor(Date.now() / 1000 - ts);
    if (elapsed < 0) elapsed = 0;
    var mins = Math.floor(elapsed / 60);
    var secs = elapsed % 60;
    return mins > 0 ? mins + "m " + secs + "s" : secs + "s";
  }

  function renderDashboard(data) {
    renderDashAgents(Array.isArray(data.agents) ? data.agents : []);
    renderDashFileLocks(Array.isArray(data.file_locks) ? data.file_locks : []);
    renderDashWorktrees(Array.isArray(data.worktrees) ? data.worktrees : []);
    renderDashMemory(Array.isArray(data.memories) ? data.memories : []);
    renderDashErrors(Array.isArray(data.registry_errors) ? data.registry_errors : []);
    if (!_dashboardRendered) {
      var dashboardView = document.getElementById("dashboard-view");
      if (dashboardView) {
        var widgets = dashboardView.querySelectorAll(".dash-widget");
        for (var wi = 0; wi < widgets.length; wi++) widgets[wi].classList.add("is-new");
        var strips = dashboardView.querySelectorAll(".dash-strip");
        for (var si = 0; si < strips.length; si++) strips[si].classList.add("is-new");
      }
      _dashboardRendered = true;
    }
  }

  var AGENT_STATUSES = ["ready", "processing", "waiting", "done"];

  function countAgentStatuses(agents) {
    var counts = {};
    for (var i = 0; i < agents.length; i++) {
      var s = (agents[i].status || "unknown").toLowerCase();
      counts[s] = (counts[s] || 0) + 1;
    }
    return counts;
  }

  function buildStatusStrip(agents) {
    var strip = document.createElement("div");
    strip.className = "dash-strip";

    var counts = countAgentStatuses(agents);

    var statuses = AGENT_STATUSES;
    for (var si = 0; si < statuses.length; si++) {
      var status = statuses[si];
      var count = counts[status] || 0;
      if (si > 0) {
        var sep = document.createElement("div");
        sep.className = "dash-strip-separator";
        strip.appendChild(sep);
      }
      var item = document.createElement("div");
      item.className = "dash-strip-item";
      var countEl = document.createElement("span");
      countEl.className = "dash-strip-count";
      countEl.style.color = statusColor(status);
      countEl.textContent = String(count);
      item.appendChild(countEl);
      var label = document.createElement("span");
      label.className = "dash-strip-label";
      label.textContent = status.toUpperCase();
      item.appendChild(label);
      strip.appendChild(item);
    }
    return strip;
  }

  function renderDashAgents(agents) {
    var el = document.getElementById("dash-agents");
    if (!el) return;

    var existingCounts = el.querySelectorAll(".dash-strip-count");
    if (existingCounts.length === AGENT_STATUSES.length) {
      var counts = countAgentStatuses(agents);
      for (var si = 0; si < AGENT_STATUSES.length; si++) {
        existingCounts[si].textContent = String(counts[AGENT_STATUSES[si]] || 0);
        existingCounts[si].style.color = statusColor(AGENT_STATUSES[si]);
      }
      var headerTitle = el.querySelector(".dash-widget-header span");
      if (headerTitle) headerTitle.textContent = "Agents (" + agents.length + ")";
      if (_dashExpandState["agents"]) {
        var detail = el.querySelector(".dash-widget-detail");
        if (detail) {
          detail.innerHTML = "";
          detail.appendChild(renderSystemAgents(agents));
        }
      }
      return;
    }

    el.innerHTML = "";
    var summary = buildStatusStrip(agents);
    el.appendChild(createDashWidget("agents", "ph-robot", "Agents (" + agents.length + ")", summary, function () { return renderSystemAgents(agents); }));
  }

  function buildMemoryList(memories) {
    var list = document.createElement("div");
    list.className = "dash-memory-list";
    var shown = memories.slice(0, 8);
    for (var i = 0; i < shown.length; i++) {
      var m = shown[i];
      var item = document.createElement("div");
      item.className = "dash-memory-item";

      var header = document.createElement("div");
      header.className = "dash-memory-item-header";

      var key = document.createElement("span");
      key.className = "dash-memory-key";
      key.textContent = m.key || "";
      header.appendChild(key);

      if (m.scope && m.scope !== "global") {
        var scope = document.createElement("span");
        scope.className = "tag-chip";
        scope.textContent = m.scope;
        header.appendChild(scope);
      }

      var author = document.createElement("span");
      author.className = "dash-memory-author";
      author.textContent = m.author || "";
      header.appendChild(author);

      item.appendChild(header);

      var content = document.createElement("div");
      content.className = "dash-memory-content";
      var contentText = m.content || "";
      content.textContent = contentText.length > 120 ? contentText.slice(0, 120) + "\u2026" : contentText;
      content.title = contentText;
      item.appendChild(content);

      list.appendChild(item);
    }
    return list;
  }

  function renderDashMemory(memories) {
    var el = document.getElementById("dash-memory");
    if (!el) return;

    if (memories.length === 0) {
      el.innerHTML = "";
      el.appendChild(createDashHeader("ph-brain", "Shared Memory (0)"));
      el.appendChild(emptyState("No shared memories"));
      return;
    }

    var titleText = "Shared Memory (" + memories.length + ")";
    var detailFn = function () { return renderSystemMemories(memories); };

    if (updateDashWidget(el, titleText, function () { return buildMemoryList(memories); }, detailFn)) return;

    el.innerHTML = "";
    el.appendChild(createDashWidget("memory", "ph-brain", titleText, buildMemoryList(memories), detailFn));
  }

  function buildLockSummary(locks) {
    var summary = document.createElement("div");
    summary.className = "dash-widget-summary";
    summary.textContent = locks.length + " file" + (locks.length !== 1 ? "s" : "") + " locked";
    return summary;
  }

  function renderDashFileLocks(locks) {
    var el = document.getElementById("dash-file-locks");
    if (!el) return;

    if (locks.length === 0) {
      el.innerHTML = "";
      el.appendChild(createDashHeader("ph-lock", "File Locks (0)"));
      el.appendChild(emptyState("No active file locks"));
      return;
    }

    var titleText = "File Locks (" + locks.length + ")";
    var detailFn = function () { return renderSystemFileLocks(locks); };

    if (updateDashWidget(el, titleText, function () { return buildLockSummary(locks); }, detailFn)) return;

    el.innerHTML = "";
    el.appendChild(createDashWidget("file-locks", "ph-lock", titleText, buildLockSummary(locks), detailFn));
  }

  function buildWorktreeSummary(worktrees) {
    var summary = document.createElement("div");
    summary.className = "dash-widget-summary";
    var branches = [];
    for (var i = 0; i < worktrees.length && i < 3; i++) {
      branches.push(worktrees[i].branch || worktrees[i].agent_name || worktrees[i].agent_id);
    }
    summary.textContent = worktrees.length + " worktree" + (worktrees.length !== 1 ? "s" : "") + " — " + branches.join(", ") + (worktrees.length > 3 ? "…" : "");
    return summary;
  }

  function renderDashWorktrees(worktrees) {
    var el = document.getElementById("dash-worktrees");
    if (!el) return;

    if (worktrees.length === 0) {
      el.innerHTML = "";
      el.appendChild(createDashHeader("ph-git-branch", "Worktrees (0)"));
      el.appendChild(emptyState("No active worktrees"));
      return;
    }

    var titleText = "Worktrees (" + worktrees.length + ")";
    var detailFn = function () { return renderSystemWorktrees(worktrees); };

    if (updateDashWidget(el, titleText, function () { return buildWorktreeSummary(worktrees); }, detailFn)) return;

    el.innerHTML = "";
    el.appendChild(createDashWidget("worktrees", "ph-git-branch", titleText, buildWorktreeSummary(worktrees), detailFn));
  }

  function buildErrorSummary(errors) {
    var summary = document.createElement("div");
    summary.className = "dash-widget-summary";
    summary.style.color = "var(--color-danger)";
    summary.textContent = errors.length + " error" + (errors.length !== 1 ? "s" : "") + " detected";
    return summary;
  }

  function renderDashErrors(errors) {
    var el = document.getElementById("dash-errors");
    if (!el) return;
    if (errors.length === 0) {
      el.innerHTML = "";
      el.style.display = "none";
      return;
    }
    el.style.display = "";

    var titleText = "Registry Errors (" + errors.length + ")";
    var detailFn = function () { return renderRegistryErrors(errors); };

    if (updateDashWidget(el, titleText, function () { return buildErrorSummary(errors); }, detailFn)) return;

    el.innerHTML = "";
    el.appendChild(createDashWidget("errors", "ph-warning-circle", titleText, buildErrorSummary(errors), detailFn));
  }

  // System section key → Phosphor icon class
  var SECTION_ICONS = {
    agents: "ph-robot",
    "agent-profiles": "ph-user-circle",
    tasks: "ph-kanban",
    "file-locks": "ph-lock",
    history: "ph-clock-counter-clockwise",
    memories: "ph-brain",
    worktrees: "ph-git-branch",
    skills: "ph-puzzle-piece",
    "skill-sets": "ph-stack",
    sessions: "ph-folder-open",
    workflows: "ph-flow-arrow",
    environment: "ph-gear",
    errors: "ph-warning-circle",
  };

  function createSystemSection(key, title, bodyContent) {
    const section = document.createElement("section");
    section.className = "system-section";

    const header = document.createElement("div");
    header.className = "system-section-header";

    var sectionIcon = SECTION_ICONS[key] || "ph-circle";
    var iconEl = document.createElement("i");
    iconEl.className = "ph " + sectionIcon;
    header.appendChild(iconEl);

    var titleSpan = document.createElement("span");
    titleSpan.textContent = title;
    header.appendChild(titleSpan);

    const body = document.createElement("div");
    body.className = "system-section-body";
    body.appendChild(bodyContent);

    section.appendChild(header);
    section.appendChild(body);
    return section;
  }

  function emptyState(message) {
    const el = document.createElement("div");
    el.className = "system-empty";
    el.textContent = message;
    return el;
  }

  function scopeBadge(scope) {
    const el = document.createElement("span");
    el.className = "scope-badge";
    el.dataset.scope = scope;
    if (scope === "user") {
      el.textContent = "User Scope";
    } else if (scope === "active-project") {
      el.textContent = "Active Project";
    } else {
      el.textContent = scope;
    }
    return el;
  }

  function buildAgentRow(agent) {
    var tr = document.createElement("tr");
    tr.setAttribute("data-agent-id", agent.agent_id);

    var tdDot = document.createElement("td");
    tdDot.className = "agent-dot-cell";
    var dot = document.createElement("span");
    dot.className = "system-status-dot";
    dot.style.background = statusColor(agent.status);
    tdDot.appendChild(dot);
    tr.appendChild(tdDot);

    var tdType = document.createElement("td");
    tdType.textContent = agent.agent_type || "";
    tr.appendChild(tdType);

    var tdName = document.createElement("td");
    tdName.className = "agent-name-cell";
    tdName.textContent = agent.name || "-";
    tr.appendChild(tdName);

    var tdRole = document.createElement("td");
    tdRole.className = "agent-role-cell";
    tdRole.textContent = agent.role || "-";
    tr.appendChild(tdRole);

    var tdSkill = document.createElement("td");
    tdSkill.className = "agent-role-cell";
    tdSkill.textContent = agent.skill_set || "-";
    tr.appendChild(tdSkill);

    var tdStatus = document.createElement("td");
    tdStatus.className = "agent-status-cell";
    tdStatus.textContent = agent.status || "-";
    tdStatus.style.color = statusColor(agent.status);
    tr.appendChild(tdStatus);

    var tdPort = document.createElement("td");
    tdPort.className = "agent-port-cell";
    tdPort.textContent = agent.port || "-";
    tr.appendChild(tdPort);

    var tdDir = document.createElement("td");
    tdDir.className = "agent-dir-cell";
    tdDir.textContent = agent.working_dir || "-";
    tr.appendChild(tdDir);

    var tdCurrent = document.createElement("td");
    tdCurrent.className = "agent-current-cell";
    var preview = agent.current_task_preview || "-";
    if (preview !== "-" && agent.task_received_at) {
      tdCurrent.textContent = preview + " (" + formatElapsed(agent.task_received_at) + ")";
    } else {
      tdCurrent.textContent = preview;
    }
    tr.appendChild(tdCurrent);

    return tr;
  }

  function renderSystemAgents(agents, options) {
    var wrap = document.createElement("div");
    if (agents.length === 0) {
      wrap.appendChild(emptyState("No agents running"));
      return wrap;
    }

    var onRowClick = options && options.onRowClick;
    var onRowDblClick = options && options.onRowDblClick;
    var onRowContextMenu = options && options.onRowContextMenu;
    var selectedId = options && options.selectedId;

    var table = document.createElement("table");
    table.className = "system-agents-table agents-nowrap" + (onRowClick ? " admin-selectable-table" : "");

    var thead = document.createElement("thead");
    var hrow = document.createElement("tr");
    var cols = ["", "TYPE", "NAME", "ROLE", "SKILL SET", "STATUS", "PORT", "DIR", "CURRENT"];
    for (var ci = 0; ci < cols.length; ci++) {
      var th = document.createElement("th");
      th.textContent = cols[ci];
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    for (var i = 0; i < agents.length; i++) {
      (function(agent) {
        var tr = buildAgentRow(agent);
        if (selectedId && selectedId === agent.agent_id) tr.classList.add("admin-row-selected");
        if (onRowClick) {
          tr.style.cursor = "pointer";
          tr.addEventListener("click", function() {
            tbody.querySelectorAll("tr").forEach(function(r) { r.classList.remove("admin-row-selected"); });
            tr.classList.add("admin-row-selected");
            onRowClick(agent);
          });
        }
        if (onRowDblClick) {
          tr.addEventListener("dblclick", function() {
            onRowDblClick(agent);
          });
        }
        if (onRowContextMenu) {
          tr.addEventListener("contextmenu", function(e) {
            onRowContextMenu(agent, e);
          });
        }
        tbody.appendChild(tr);
      })(agents[i]);
    }
    table.appendChild(tbody);

    wrap.appendChild(table);
    return wrap;
  }

  function renderRegistryErrors(errors) {
    const wrap = document.createElement("div");
    const table = document.createElement("table");
    table.className = "system-agents-table";
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["FILE", "ERROR"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const err of errors) {
      const tr = document.createElement("tr");
      tr.style.color = "var(--color-danger)";
      const tdFile = document.createElement("td");
      tdFile.textContent = err.source;
      tr.appendChild(tdFile);
      const tdMsg = document.createElement("td");
      tdMsg.textContent = err.message;
      tr.appendChild(tdMsg);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemFileLocks(locks) {
    const wrap = document.createElement("div");
    if (locks.length === 0) {
      wrap.appendChild(emptyState("No active file locks"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table";
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["FILE", "AGENT"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const lock of locks) {
      const tr = document.createElement("tr");
      const tdFile = document.createElement("td");
      tdFile.className = "agent-dir-cell";
      tdFile.textContent = lock.path;
      tr.appendChild(tdFile);
      const tdAgent = document.createElement("td");
      tdAgent.textContent = lock.agent_id;
      tr.appendChild(tdAgent);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemMemories(memories) {
    const wrap = document.createElement("div");
    if (memories.length === 0) {
      wrap.appendChild(emptyState("No shared memories"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table";
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["KEY", "CONTENT", "SCOPE", "AUTHOR", "TAGS", "UPDATED"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const mem of memories) {
      const tr = document.createElement("tr");

      const tdKey = document.createElement("td");
      tdKey.className = "agent-name-cell";
      tdKey.textContent = mem.key;
      tr.appendChild(tdKey);

      const tdContent = document.createElement("td");
      tdContent.className = "agent-dir-cell";
      var contentStr = mem.content || "";
      tdContent.textContent = contentStr.length > 80 ? contentStr.slice(0, 80) + "\u2026" : contentStr;
      tdContent.title = contentStr;
      tr.appendChild(tdContent);

      const tdScope = document.createElement("td");
      tdScope.textContent = mem.scope || "global";
      tr.appendChild(tdScope);

      const tdAuthor = document.createElement("td");
      tdAuthor.textContent = mem.author;
      tr.appendChild(tdAuthor);

      const tdTags = document.createElement("td");
      const tags = Array.isArray(mem.tags) ? mem.tags : [];
      if (tags.length > 0) {
        for (const t of tags) {
          const chip = document.createElement("span");
          chip.className = "tag-chip";
          chip.textContent = t;
          tdTags.appendChild(chip);
        }
      } else {
        tdTags.textContent = "-";
      }
      tr.appendChild(tdTags);

      const tdTime = document.createElement("td");
      tdTime.className = "agent-port-cell";
      tdTime.textContent = formatTimeShort(mem.updated_at);
      tr.appendChild(tdTime);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemWorktrees(worktrees) {
    const wrap = document.createElement("div");
    if (!worktrees || worktrees.length === 0) {
      wrap.appendChild(emptyState("No active worktrees"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table";
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["AGENT", "PATH", "BRANCH", "BASE"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const wt of worktrees) {
      const tr = document.createElement("tr");

      const tdAgent = document.createElement("td");
      tdAgent.className = "agent-name-cell";
      tdAgent.textContent = wt.agent_name || wt.agent_id;
      tr.appendChild(tdAgent);

      const tdPath = document.createElement("td");
      tdPath.className = "agent-dir-cell";
      tdPath.textContent = wt.path;
      tr.appendChild(tdPath);

      const tdBranch = document.createElement("td");
      tdBranch.className = "agent-dir-cell";
      tdBranch.textContent = wt.branch;
      tr.appendChild(tdBranch);

      const tdBase = document.createElement("td");
      tdBase.className = "agent-dir-cell";
      tdBase.textContent = wt.base_branch;
      tr.appendChild(tdBase);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemHistory(history) {
    const wrap = document.createElement("div");
    if (history.length === 0) {
      wrap.appendChild(emptyState("No task history"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table";
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["", "AGENT", "TASK", "STATUS", "TIME"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const item of history) {
      const tr = document.createElement("tr");

      // Status icon
      const tdIcon = document.createElement("td");
      tdIcon.className = "agent-dot-cell";
      const dot = document.createElement("span");
      dot.className = "system-status-dot";
      dot.style.background = historyStatusColor(item.status);
      tdIcon.appendChild(dot);
      tr.appendChild(tdIcon);

      const tdAgent = document.createElement("td");
      tdAgent.textContent = item.agent_name || "-";
      tr.appendChild(tdAgent);

      const tdInput = document.createElement("td");
      tdInput.className = "agent-current-cell";
      tdInput.textContent = item.input || "-";
      tdInput.title = item.input || "";
      tr.appendChild(tdInput);

      const tdStatus = document.createElement("td");
      tdStatus.className = "agent-status-cell";
      tdStatus.textContent = item.status || "-";
      tdStatus.style.color = historyStatusColor(item.status);
      tr.appendChild(tdStatus);

      const tdTime = document.createElement("td");
      tdTime.className = "agent-port-cell";
      tdTime.textContent = formatTimeShort(item.timestamp);
      tr.appendChild(tdTime);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemProfiles(profiles) {
    const wrap = document.createElement("div");
    if (!profiles || profiles.length === 0) {
      wrap.appendChild(emptyState("No saved agent definitions"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table";
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["ID", "NAME", "PROFILE", "ROLE", "SKILL SET", "SCOPE"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const p of profiles) {
      const tr = document.createElement("tr");

      const tdId = document.createElement("td");
      tdId.className = "agent-dir-cell";
      tdId.textContent = p.id;
      tr.appendChild(tdId);

      const tdName = document.createElement("td");
      tdName.className = "agent-name-cell";
      tdName.textContent = p.name;
      tr.appendChild(tdName);

      const tdProfile = document.createElement("td");
      tdProfile.textContent = p.profile;
      tr.appendChild(tdProfile);

      const tdRole = document.createElement("td");
      tdRole.className = "agent-role-cell";
      tdRole.textContent = p.role || "-";
      tr.appendChild(tdRole);

      const tdSkill = document.createElement("td");
      tdSkill.className = "agent-role-cell";
      tdSkill.textContent = p.skill_set || "-";
      tr.appendChild(tdSkill);

      const tdScope = document.createElement("td");
      tdScope.appendChild(scopeBadge(p.scope));
      tr.appendChild(tdScope);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemSkills(skills) {
    const wrap = document.createElement("div");
    if (skills.length === 0) {
      wrap.appendChild(emptyState("No skills discovered"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table has-desc";
    const colgroup = document.createElement("colgroup");
    for (const w of ["15%", "50%", "10%", "25%"]) {
      const col = document.createElement("col");
      col.style.width = w;
      colgroup.appendChild(col);
    }
    table.appendChild(colgroup);
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["NAME", "DESCRIPTION", "SCOPE", "TARGETS"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const sk of skills) {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      tdName.className = "agent-name-cell";
      tdName.textContent = sk.name;
      tr.appendChild(tdName);

      const tdDesc = document.createElement("td");
      tdDesc.className = "desc-cell";
      tdDesc.textContent = sk.description || "-";
      tr.appendChild(tdDesc);

      const tdScope = document.createElement("td");
      tdScope.appendChild(scopeBadge(sk.scope));
      tr.appendChild(tdScope);

      const tdDirs = document.createElement("td");
      tdDirs.className = "agent-dir-cell";
      tdDirs.textContent = (sk.agent_dirs || []).join(", ") || "-";
      tr.appendChild(tdDirs);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemSkillSets(sets) {
    const wrap = document.createElement("div");
    if (!sets || sets.length === 0) {
      wrap.appendChild(emptyState("No skill sets defined"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table has-desc";
    const colgroup = document.createElement("colgroup");
    for (const w of ["15%", "45%", "40%"]) {
      const col = document.createElement("col");
      col.style.width = w;
      colgroup.appendChild(col);
    }
    table.appendChild(colgroup);
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["NAME", "DESCRIPTION", "SKILLS"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const ss of sets) {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      tdName.className = "agent-name-cell";
      tdName.textContent = ss.name;
      tr.appendChild(tdName);

      const tdDesc = document.createElement("td");
      tdDesc.className = "desc-cell";
      tdDesc.textContent = ss.description || "-";
      tr.appendChild(tdDesc);

      const tdSkills = document.createElement("td");
      tdSkills.className = "skill-list-cell";
      for (const sk of (ss.skills || [])) {
        const tag = document.createElement("span");
        tag.className = "skill-tag";
        tag.textContent = sk;
        tdSkills.appendChild(tag);
      }
      tr.appendChild(tdSkills);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemSessions(sessions) {
    const wrap = document.createElement("div");
    if (!sessions || sessions.length === 0) {
      wrap.appendChild(emptyState("No saved sessions"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table";
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["NAME", "SCOPE", "AGENTS", "DIRECTORY", "CREATED"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const s of sessions) {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      tdName.className = "agent-name-cell";
      tdName.textContent = s.name;
      tr.appendChild(tdName);

      const tdScope = document.createElement("td");
      tdScope.appendChild(scopeBadge(s.scope));
      tr.appendChild(tdScope);

      const tdCount = document.createElement("td");
      tdCount.className = "agent-port-cell";
      tdCount.textContent = s.agent_count;
      tr.appendChild(tdCount);

      const tdDir = document.createElement("td");
      tdDir.className = "agent-dir-cell";
      tdDir.textContent = s.working_dir ? s.working_dir.split("/").pop() : "-";
      tr.appendChild(tdDir);

      const tdCreated = document.createElement("td");
      tdCreated.textContent = formatTimeShort(s.created_at);
      tr.appendChild(tdCreated);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemWorkflows(workflows) {
    const wrap = document.createElement("div");
    if (!workflows || workflows.length === 0) {
      wrap.appendChild(emptyState("No saved workflows"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table has-desc";
    const colgroup = document.createElement("colgroup");
    for (const w of ["15%", "55%", "15%", "15%"]) {
      const col = document.createElement("col");
      col.style.width = w;
      colgroup.appendChild(col);
    }
    table.appendChild(colgroup);
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["NAME", "DESCRIPTION", "SCOPE", "STEPS"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const wf of workflows) {
      const tr = document.createElement("tr");

      const tdName = document.createElement("td");
      tdName.className = "agent-name-cell";
      tdName.textContent = wf.name;
      tr.appendChild(tdName);

      const tdDesc = document.createElement("td");
      tdDesc.className = "desc-cell";
      tdDesc.textContent = wf.description || "-";
      tr.appendChild(tdDesc);

      const tdScope = document.createElement("td");
      tdScope.appendChild(scopeBadge(wf.scope));
      tr.appendChild(tdScope);

      const tdSteps = document.createElement("td");
      tdSteps.className = "agent-port-cell";
      tdSteps.textContent = wf.step_count;
      tr.appendChild(tdSteps);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemEnvironment(env) {
    const wrap = document.createElement("div");
    if (!env || Object.keys(env).length === 0) {
      wrap.appendChild(emptyState("No environment variables"));
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table system-env-table has-desc";
    const colgroup = document.createElement("colgroup");
    for (const w of ["30%", "25%", "45%"]) {
      const col = document.createElement("col");
      col.style.width = w;
      colgroup.appendChild(col);
    }
    table.appendChild(colgroup);
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["VARIABLE", "VALUE", "DESCRIPTION"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const [key, entry] of Object.entries(env)) {
      const tr = document.createElement("tr");
      // Support both old format (string) and new format ({value, description})
      const value = typeof entry === "string" ? entry : (entry.value || "");
      const description = typeof entry === "object" ? (entry.description || "") : "";

      const tdKey = document.createElement("td");
      tdKey.className = "env-key-cell";
      tdKey.textContent = key;
      tr.appendChild(tdKey);

      const tdVal = document.createElement("td");
      tdVal.className = "env-val-cell";
      const isDefault = value.startsWith("(default:");
      if (isDefault) {
        tdVal.style.color = "var(--color-text-muted)";
      } else if (value === "true") {
        tdVal.style.color = "var(--color-success)";
      } else if (value === "false") {
        tdVal.style.color = "var(--color-text-muted)";
      }
      // Mask sensitive values
      if (key.includes("KEY") || key.includes("SECRET")) {
        tdVal.textContent = value && !isDefault ? "\u2022\u2022\u2022\u2022\u2022\u2022" : value;
      } else {
        tdVal.textContent = value;
      }
      tr.appendChild(tdVal);

      const tdDesc = document.createElement("td");
      tdDesc.className = "desc-cell";
      tdDesc.textContent = description;
      tr.appendChild(tdDesc);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemTips(tips) {

    const count = document.createElement("span");
    count.className = "system-tips-count";
    count.textContent = tips.length + " tips";
    banner.appendChild(count);

    return banner;
  }

  function historyStatusColor(status) {
    switch (String(status || "").toLowerCase()) {
      case "completed": return "var(--color-success)";
      case "failed": return "var(--color-danger)";
      case "canceled": return "var(--color-warning)";
      default: return "var(--color-text-muted)";
    }
  }

  function formatTimeShort(ts) {
    if (!ts) return "";
    try {
      const d = new Date(ts + (ts.includes("Z") || ts.includes("+") ? "" : "Z"));
      const now = new Date();
      const diff = now - d;
      if (diff < 60000) return "just now";
      if (diff < 3600000) return Math.floor(diff / 60000) + "m ago";
      if (diff < 86400000) return Math.floor(diff / 3600000) + "h ago";
      return d.toLocaleDateString();
    } catch {
      return ts;
    }
  }

  // ----------------------------------------------------------------
  // Simple markdown parser (no external dependency)
  // ----------------------------------------------------------------

  Object.assign(ns, {
    loadSystemPanel: loadSystemPanel,
    renderSystemPanel: renderSystemPanel,
    renderDashboard: renderDashboard,
    renderDashAgents: renderDashAgents,
    renderDashMemory: renderDashMemory,
    renderDashFileLocks: renderDashFileLocks,
    renderDashWorktrees: renderDashWorktrees,
    renderDashErrors: renderDashErrors,
    createSystemSection: createSystemSection,
    emptyState: emptyState,
    scopeBadge: scopeBadge,
    renderSystemAgents: renderSystemAgents,
    renderRegistryErrors: renderRegistryErrors,
    renderSystemFileLocks: renderSystemFileLocks,
    renderSystemMemories: renderSystemMemories,
    renderSystemWorktrees: renderSystemWorktrees,
    renderSystemHistory: renderSystemHistory,
    renderSystemProfiles: renderSystemProfiles,
    renderSystemSkills: renderSystemSkills,
    renderSystemSkillSets: renderSystemSkillSets,
    renderSystemSessions: renderSystemSessions,
    renderSystemWorkflows: renderSystemWorkflows,
    renderSystemEnvironment: renderSystemEnvironment,
    renderSystemTips: renderSystemTips,
    historyStatusColor: historyStatusColor,
    formatTimeShort: formatTimeShort,
  });

})(window.SynapseCanvas || (window.SynapseCanvas = {}));
