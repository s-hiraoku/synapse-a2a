/* Synapse Canvas — browser-side card rendering with SSE live updates. */

(function () {
  "use strict";

  const grid = document.getElementById("canvas-grid");
  const filterType = document.getElementById("filter-type");
  const filterAgent = document.getElementById("filter-agent");
  const cardCount = document.getElementById("card-count");
  const themeToggle = document.getElementById("theme-toggle");
  const filterBar = document.getElementById("filter-bar");
  const toastContainer = document.getElementById("toast-container");
  const systemPanel = document.getElementById("system-panel");
  const liveFeedList = document.getElementById("live-feed-list");
  const canvasView = document.getElementById("canvas-view");
  const canvasSpotlight = document.getElementById("canvas-spotlight");
  const dashboardView = document.getElementById("dashboard-view");
  const historyView = document.getElementById("history-view");
  const systemView = document.getElementById("system-view");
  const adminView = document.getElementById("admin-view");
  const adminFeed = document.getElementById("admin-feed");
  const adminTargetBadge = document.getElementById("admin-target-badge");
  const adminAgentsWidget = document.getElementById("admin-agents-widget");
  const adminMessageInput = document.getElementById("admin-message-input");
  const adminSendBtn = document.getElementById("admin-send-btn");
  const adminSplitter = document.getElementById("admin-splitter");
  const workflowView = document.getElementById("workflow-view");
  const workflowListPanel = document.getElementById("workflow-list-panel");
  const workflowDetailPanel = document.getElementById("workflow-detail-panel");
  const workflowDetailEmpty = document.getElementById("workflow-detail-empty");
  const workflowDetailContent = document.getElementById("workflow-detail-content");
  var _workflowData = [];
  var _workflowRuns = [];
  var _selectedWorkflow = null;
  var _selectedAdminTarget = "";
  var _selectedAdminName = "";
  const navLinks = document.querySelectorAll(".nav-link");
  const sidebar = document.getElementById("sidebar");
  const sidebarOverlay = document.getElementById("sidebar-overlay");
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebarCollapseBtn = document.getElementById("sidebar-collapse");
  const topbarTitle = document.getElementById("topbar-title");
  const SPOTLIGHT_SWAP_DELAY = 420;

  // Route labels for topbar
  var ROUTE_LABELS = { canvas: "Canvas", dashboard: "Dashboard", history: "Canvas / History", workflow: "Workflow", system: "System", admin: "Agent Control" };

  // Current route
  let currentRoute = "canvas";
  // Track displayed card to skip redundant rebuilds
  let _spotlightCardId = "";
  let _spotlightUpdatedAt = "";
  let _spotlightSwapTimer = 0;

  // Card cache: card_id -> card data
  const cards = new Map();
  // Known agents for filter dropdown
  const knownAgents = new Set();
  // System agents cache for panel rendering
  let systemAgents = [];
  // Cached system data for instant rendering on route change
  let _lastSystemData = null;
  var _systemPanelRendered = false;
  var _lastSystemJSON = "";

  // ----------------------------------------------------------------
  // Download card as file
  // ----------------------------------------------------------------
  function downloadCard(cardId, format) {
    var url = "/api/cards/" + encodeURIComponent(cardId) + "/download";
    if (format) url += "?format=" + encodeURIComponent(format);
    fetch(url).then(function (resp) {
      if (!resp.ok) {
        showToast("Download failed: " + resp.status, "error");
        return;
      }
      var disposition = resp.headers.get("Content-Disposition") || "";
      var match = disposition.match(/filename="([^"]+)"/);
      var filename = match ? match[1] : "download";
      return resp.blob().then(function (blob) {
        var objUrl = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = objUrl;
        a.download = filename;
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(objUrl);
      });
    }).catch(function (err) {
      showToast("Download failed: " + err.message, "error");
    });
  }

  function createDownloadButton(getCardId) {
    var btn = document.createElement("button");
    btn.className = "canvas-dl-btn";
    btn.title = "Download";
    btn.type = "button";
    btn.setAttribute("aria-label", "Download");
    btn.innerHTML = '<i class="ph ph-download-simple"></i>';
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var id = typeof getCardId === "function" ? getCardId() : getCardId;
      if (id) downloadCard(id);
    });
    return btn;
  }

  // ----------------------------------------------------------------
  // Initial load
  // ----------------------------------------------------------------
  async function loadCards() {
    try {
      const resp = await fetch("/api/cards");
      const list = await resp.json();
      cards.clear();
      for (const card of list) {
        cards.set(card.card_id, card);
        trackAgent(card);
      }
      renderCurrentView();
    } catch (e) {
      console.error("Failed to load cards:", e);
    }
  }

  // ----------------------------------------------------------------
  // SSE connection
  // ----------------------------------------------------------------
  function connectSSE() {
    const es = new EventSource("/api/stream");

    es.addEventListener("card_created", (e) => {
      const card = JSON.parse(e.data);
      cards.set(card.card_id, card);
      trackAgent(card);
      renderCurrentView();
      showToast(card.title || "New card", card.agent_name || card.agent_id);
    });

    es.addEventListener("card_updated", (e) => {
      const card = JSON.parse(e.data);
      cards.set(card.card_id, card);
      trackAgent(card);
      renderCurrentView();
      showToast(card.title || "Card updated", card.agent_name || card.agent_id);
    });

    es.addEventListener("card_deleted", (e) => {
      const data = JSON.parse(e.data);
      const deleted = cards.get(data.card_id);
      cards.delete(data.card_id);
      if (data.card_id === _spotlightCardId) {
        _spotlightCardId = "";
        _spotlightUpdatedAt = "";
      }
      renderCurrentView();
      showToast(deleted ? deleted.title : "Card deleted", "Removed");
    });

    es.addEventListener("system_update", () => {
      loadSystemPanel();
      if (currentRoute === "admin") loadAdminAgents();
    });

    es.addEventListener("workflow_update", () => {
      if (currentRoute === "workflow") loadWorkflowRuns();
    });

    var _sseHasConnected = false;
    es.onopen = () => {
      if (_sseHasConnected) {
        // Re-sync only on RE-connect (not initial connect, which already has loadCards)
        loadCards();
      }
      _sseHasConnected = true;
    };

    es.onerror = () => {
      // EventSource auto-reconnects; just log
      console.warn("SSE connection lost, reconnecting...");
    };
  }

  // ----------------------------------------------------------------
  // Agent tracking for filter dropdown
  // ----------------------------------------------------------------
  function trackAgent(card) {
    const label = card.agent_name || card.agent_id;
    if (!knownAgents.has(label)) {
      knownAgents.add(label);
      const opt = document.createElement("option");
      opt.value = label;
      opt.textContent = label;
      filterAgent.appendChild(opt);
    }
  }

  // ----------------------------------------------------------------
  // Filtering
  // ----------------------------------------------------------------
  function getFilteredCards() {
    const typeVal = filterType.value;
    const agentVal = filterAgent.value;
    const result = [];

    for (const card of cards.values()) {
      // Type filter: check content JSON for format match
      if (typeVal) {
        const content = parseContent(card.content);
        const blocks = Array.isArray(content) ? content : [content];
        const hasType = blocks.some((b) => b.format === typeVal);
        if (!hasType) continue;
      }

      // Agent filter
      if (agentVal) {
        const label = card.agent_name || card.agent_id;
        if (label !== agentVal) continue;
      }

      result.push(card);
    }

    return result;
  }

  // ----------------------------------------------------------------
  // Rendering
  // ----------------------------------------------------------------
  let _renderRAF = 0;
  function markAsNew(el) {
    if (!el || !el.classList) return;
    el.classList.remove("is-new");
    void el.offsetWidth;
    el.classList.add("is-new");
    if (typeof window !== "undefined" && typeof window.setTimeout === "function") {
      window.setTimeout(() => {
        el.classList.remove("is-new");
      }, 900);
    }
  }

  function syncChildren(parent, nodes) {
    const desired = new Set(nodes);
    for (const child of Array.from(parent.children)) {
      if (!desired.has(child)) {
        parent.removeChild(child);
      }
    }
    for (let i = 0; i < nodes.length; i += 1) {
      const node = nodes[i];
      const current = parent.children[i];
      if (current !== node) {
        parent.insertBefore(node, current || null);
      }
    }
  }

  function populateLiveFeedItem(item, card) {
    item.className = "live-feed-item";
    item.dataset.cardId = card.card_id;
    item.dataset.updatedAt = card.updated_at || "";
    item.innerHTML = "";

    const header = document.createElement("div");
    header.className = "live-feed-item-header";

    const agentInfo = systemAgents.find(a => a.agent_id === card.agent_id);
    const dot = document.createElement("span");
    dot.className = "live-feed-status-dot";
    dot.style.background = statusColor(agentInfo ? agentInfo.status : "");
    header.appendChild(dot);

    const badge = document.createElement("span");
    badge.className = "agent-badge";
    badge.textContent = card.agent_name || card.agent_id;
    header.appendChild(badge);

    const agentId = document.createElement("span");
    agentId.className = "live-feed-agent-id";
    agentId.textContent = card.agent_id;
    header.appendChild(agentId);

    const title = document.createElement("span");
    title.className = "live-feed-title";
    title.textContent = card.title || "Untitled";
    header.appendChild(title);

    const time = document.createElement("span");
    time.className = "live-feed-time";
    time.textContent = formatTimeShort(card.updated_at);
    header.appendChild(time);

    item.appendChild(header);

    const content = parseContent(card.content);
    const blocks = Array.isArray(content) ? content : [content];
    for (const block of blocks) {
      item.appendChild(renderBlock(block));
    }
  }

  function renderCurrentView() {
    cancelAnimationFrame(_renderRAF);
    _renderRAF = requestAnimationFrame(() => {
      if (currentRoute === "canvas") {
        renderSpotlight();
      } else if (currentRoute === "system" || currentRoute === "dashboard") {
        // rendered by loadSystemPanel; no-op here
      } else {
        renderAll();
      }
    });
  }

  function renderAll() {
    const allCards = [...cards.values()];
    const filtered = getFilteredCards();
    const countText = `${filtered.length} card${filtered.length !== 1 ? "s" : ""}`;
    const agentVal = filterAgent.value;
    cardCount.textContent = countText;
    cardCount.style.display = "";

    // Sort agent messages by recency only.
    filtered.sort((a, b) => {
      return (b.updated_at || "").localeCompare(a.updated_at || "");
    });

    // Group cards by agent
    const agentGroups = new Map();

    // Seed panels from system agents (so empty agents get a panel)
    for (const agent of systemAgents) {
      const label = agent.name || agent.agent_id;
      if (agentVal && label !== agentVal) continue;
      if (!agentGroups.has(label)) {
        agentGroups.set(label, {
          label,
          agentId: agent.agent_id,
          status: agent.status,
          cards: [],
        });
      }
    }

    // Add cards to their agent group
    for (const card of filtered) {
      const label = card.agent_name || card.agent_id;
      if (!agentGroups.has(label)) {
        agentGroups.set(label, {
          label,
          agentId: card.agent_id,
          status: null,
          cards: [],
        });
      }
      agentGroups.get(label).cards.push(card);
    }

    // Latest Posts ignores dashboard filters and always shows the newest cards.
    const byTime = allCards.sort((a, b) =>
      (b.updated_at || "").localeCompare(a.updated_at || "")
    );
    renderLiveFeed(byTime.slice(0, 3));

    const existingPanels = new Map();
    for (const child of Array.from(grid.children)) {
      if (child.dataset && child.dataset.agentKey) {
        existingPanels.set(child.dataset.agentKey, child);
      }
    }

    const nextPanels = [];
    for (const group of agentGroups.values()) {
      const panelKey = group.agentId || group.label;
      const existingPanel = existingPanels.get(panelKey);
      const panel = existingPanel || createAgentPanel(group);
      panel.dataset.agentKey = panelKey;
      updateAgentPanel(panel, group);
      if (!existingPanel) markAsNew(panel);
      nextPanels.push(panel);
    }
    syncChildren(grid, nextPanels);

    // Re-run mermaid on any new diagrams
    runMermaid(".mermaid-pending");
  }

  function renderLiveFeed(recentCards) {
    if (!liveFeedList) return;
    const existingItems = new Map();
    for (const child of Array.from(liveFeedList.children)) {
      if (child.dataset && child.dataset.cardId) {
        existingItems.set(child.dataset.cardId, child);
      }
    }

    if (recentCards.length === 0) {
      const empty = document.createElement("div");
      empty.className = "live-feed-empty";
      empty.textContent = "Waiting for agent messages...";
      syncChildren(liveFeedList, [empty]);
      return;
    }

    const nextItems = [];
    for (const card of recentCards) {
      const existingItem = existingItems.get(card.card_id);
      const item = existingItem || document.createElement("div");
      const previousUpdatedAt = item.dataset.updatedAt || "";
      const changed = !existingItem || previousUpdatedAt !== (card.updated_at || "");
      if (changed) {
        populateLiveFeedItem(item, card);
        markAsNew(item);
      }
      nextItems.push(item);
    }
    syncChildren(liveFeedList, nextItems);

    // Re-run mermaid on live feed diagrams
    runMermaid("#live-feed-list .mermaid-pending");
  }

  function createAgentPanel(group) {
    const panel = document.createElement("div");
    panel.className = "agent-panel";
    panel.dataset.agentKey = group.agentId || group.label;

    // Header
    const header = document.createElement("div");
    header.className = "agent-panel-header";

    const dot = document.createElement("span");
    dot.className = "agent-panel-dot";
    dot.style.background = statusColor(group.status);
    header.appendChild(dot);

    const name = document.createElement("span");
    name.className = "agent-panel-name";
    name.textContent = group.label;
    header.appendChild(name);

    const id = document.createElement("span");
    id.className = "agent-panel-id";
    id.textContent = group.agentId;
    header.appendChild(id);

    const count = document.createElement("span");
    count.className = "agent-panel-count";
    count.textContent = `${group.cards.length}`;
    header.appendChild(count);

    const arrow = document.createElement("span");
    arrow.className = "agent-panel-arrow";
    const storageKey = `agent-panel-${group.agentId}`;
    const isCollapsed = localStorage.getItem(storageKey) === "collapsed";
    if (isCollapsed) arrow.classList.add("collapsed");
    arrow.textContent = "\u25BC";
    header.appendChild(arrow);

    panel.appendChild(header);

    // Body
    const body = document.createElement("div");
    body.className = "agent-panel-body";
    if (isCollapsed) body.classList.add("collapsed");

    header.addEventListener("click", () => {
      body.classList.toggle("collapsed");
      arrow.classList.toggle("collapsed");
      localStorage.setItem(
        storageKey,
        body.classList.contains("collapsed") ? "collapsed" : "expanded"
      );
    });

    panel.appendChild(body);
    return panel;
  }

  function updateAgentPanel(panel, group) {
    panel.dataset.agentKey = group.agentId || group.label;

    const header = panel.querySelector(".agent-panel-header");
    const body = panel.querySelector(".agent-panel-body");
    if (!header || !body) return;

    const dot = header.querySelector(".agent-panel-dot");
    if (dot) dot.style.background = statusColor(group.status);

    const name = header.querySelector(".agent-panel-name");
    if (name) name.textContent = group.label;

    const id = header.querySelector(".agent-panel-id");
    if (id) id.textContent = group.agentId;

    const count = header.querySelector(".agent-panel-count");
    if (count) count.textContent = `${group.cards.length}`;

    const existingCards = new Map();
    for (const child of Array.from(body.children)) {
      if (child.dataset && child.dataset.cardId) {
        existingCards.set(child.dataset.cardId, child);
      }
    }

    if (group.cards.length === 0) {
      const empty = document.createElement("div");
      empty.className = "agent-panel-empty";
      empty.textContent = "No messages";
      syncChildren(body, [empty]);
      return;
    }

    const nextCards = [];
    for (const card of group.cards) {
      const existingCard = existingCards.get(card.card_id);
      const cardEl = existingCard || createCardElement(card);
      const previousUpdatedAt = cardEl.dataset.updatedAt || "";
      const cardChanged = !existingCard || previousUpdatedAt !== (card.updated_at || "");
      if (cardChanged) {
        updateCardElement(cardEl, card);
        markAsNew(cardEl);
      }
      nextCards.push(cardEl);
    }
    syncChildren(body, nextCards);
  }

  // Format type → Phosphor icon class (v2: requires "ph" base class)
  var FORMAT_ICONS = {
    mermaid: "ph-tree-structure",
    markdown: "ph-text-aa",
    table: "ph-table",
    html: "ph-code",
    json: "ph-brackets-curly",
    code: "ph-terminal",
    diff: "ph-git-diff",
    chart: "ph-chart-bar",
    log: "ph-scroll",
    status: "ph-pulse",
    metric: "ph-gauge",
    checklist: "ph-check-square",
    timeline: "ph-clock-countdown",
    alert: "ph-warning",
    "file-preview": "ph-file-text",
    trace: "ph-graph",
    "task-board": "ph-kanban",
    tip: "ph-lightbulb",
    image: "ph-image",
  };

  function createCardElement(card) {
    const el = document.createElement("article");
    el.className = "canvas-card";
    el.dataset.cardId = card.card_id;
    updateCardElement(el, card);
    return el;
  }

  function updateCardElement(el, card) {
    el.className = "canvas-card";
    el.dataset.cardId = card.card_id;
    el.dataset.updatedAt = card.updated_at || "";
    el.innerHTML = "";

    // Detect primary format
    var content = parseContent(card.content);
    var blocks = Array.isArray(content) ? content : [content];
    var primaryFormat = blocks.length > 0 ? blocks[0].format : "";

    // Header
    const header = document.createElement("header");

    // Format icon
    var iconClass = FORMAT_ICONS[primaryFormat] || "ph-article";
    var fmtIcon = document.createElement("i");
    fmtIcon.className = "ph " + iconClass + " card-format-icon";
    header.appendChild(fmtIcon);

    const title = document.createElement("h2");
    title.textContent = card.title || "Untitled";
    header.appendChild(title);

    header.appendChild(createDownloadButton(card.card_id));

    el.appendChild(header);

    // Tags
    const tags = card.tags || [];
    if (tags.length > 0) {
      const tagBar = document.createElement("div");
      tagBar.className = "tag-bar";
      for (const t of tags) {
        const chip = document.createElement("span");
        chip.className = "tag-chip";
        chip.textContent = t;
        tagBar.appendChild(chip);
      }
      el.appendChild(tagBar);
    }

    // Content blocks — delegate to template renderer if applicable

    if (card.template && card.template_data) {
      const td =
        typeof card.template_data === "string"
          ? JSON.parse(card.template_data)
          : card.template_data;
      const rendered = renderTemplate(card.template, blocks, td, false, null);
      if (rendered) {
        el.appendChild(rendered);
      } else {
        for (const block of blocks) {
          el.appendChild(renderBlock(block, null));
        }
      }
    } else {
      for (const block of blocks) {
        el.appendChild(renderBlock(block, null));
      }
    }

    // Footer
    const footer = document.createElement("footer");
    footer.textContent = formatTime(card.updated_at);
    el.appendChild(footer);
  }

  function parseContent(raw) {
    try {
      return JSON.parse(raw);
    } catch {
      return { format: "markdown", body: raw };
    }
  }

  // ----------------------------------------------------------------
  // Block renderers
  // ----------------------------------------------------------------
  function parseBody(body) {
    if (typeof body === "string") { try { return JSON.parse(body); } catch (_e) { /* ignore */ } }
    return body;
  }

  var _ansiMap = {
    "1": '<span class="ansi-bold">',
    "30": '<span class="ansi-black">',
    "31": '<span class="ansi-red">',
    "32": '<span class="ansi-green">',
    "33": '<span class="ansi-yellow">',
    "34": '<span class="ansi-blue">',
    "35": '<span class="ansi-magenta">',
    "36": '<span class="ansi-cyan">',
    "37": '<span class="ansi-white">',
    "90": '<span class="ansi-bright-black">',
    "91": '<span class="ansi-bright-red">',
    "92": '<span class="ansi-bright-green">',
    "93": '<span class="ansi-bright-yellow">',
    "94": '<span class="ansi-bright-blue">',
    "95": '<span class="ansi-bright-magenta">',
    "96": '<span class="ansi-bright-cyan">',
    "97": '<span class="ansi-bright-white">',
  };

  function renderBlock(block, options) {
    // Normalize legacy envelope shapes where metadata was embedded in body
    if (block.body && typeof block.body === "object" && !Array.isArray(block.body)) {
      block = Object.assign({}, block);
      var b = block.body;
      if (b.source !== undefined) {
        block.x_title = block.x_title || b.title;
        block.x_filename = block.x_filename || b.filename;
        block.body = b.source;
      } else if (b.data !== undefined && block.format === "json") {
        block.x_title = block.x_title || b.title;
        block.x_filename = block.x_filename || b.filename;
        block.body = b.data;
      } else if (b.code !== undefined) {
        block.x_title = block.x_title || b.title;
        block.x_filename = block.x_filename || b.filename;
        block.lang = block.lang || b.lang;
        block.body = b.code;
      }
    }

    const wrap = document.createElement("div");
    wrap.className = `content-block format-${block.format}`;

    switch (block.format) {
      case "mermaid":
        renderMermaid(wrap, block.body, block);
        break;
      case "markdown":
        renderMarkdown(wrap, block.body);
        break;
      case "html":
      case "artifact":
        renderHTML(wrap, block.body, options);
        break;
      case "table":
        renderTable(wrap, block.body);
        break;
      case "json":
        renderJSON(wrap, block.body, block);
        break;
      case "diff":
        renderDiff(wrap, block.body);
        break;
      case "code":
        renderCode(wrap, block.body, block.lang, block);
        break;
      case "image":
        renderImage(wrap, block.body);
        break;
      case "chart":
        renderChart(wrap, block.body);
        break;
      case "log":
        renderLog(wrap, block.body, block);
        break;
      case "status":
        renderStatus(wrap, block.body);
        break;
      case "metric":
        renderMetric(wrap, block.body);
        break;
      case "checklist":
        renderChecklist(wrap, block.body, block);
        break;
      case "timeline":
        renderTimeline(wrap, block.body);
        break;
      case "alert":
        renderAlert(wrap, block.body);
        break;
      case "file-preview":
        renderFilePreview(wrap, block.body);
        break;
      case "trace":
        renderTrace(wrap, block.body, block);
        break;
      case "task-board":
        renderTaskBoard(wrap, block.body);
        break;
      case "tip":
        renderTip(wrap, block.body, block);
        break;
      case "progress":
        renderProgress(wrap, block.body);
        break;
      case "terminal":
        renderTerminal(wrap, block.body);
        break;
      case "dependency-graph":
        renderDependencyGraph(wrap, block.body);
        break;
      case "cost":
        renderCost(wrap, block.body);
        break;
      case "link-preview":
        renderLinkPreview(wrap, block.body);
        break;
      default:
        wrap.textContent = block.body;
    }

    return wrap;
  }

  // ----------------------------------------------------------------
  // Template renderer dispatcher
  // ----------------------------------------------------------------
  function renderTemplate(templateName, blocks, td, compact, renderOptions) {
    switch (templateName) {
      case "briefing":
        return renderBriefing(blocks, td, compact, renderOptions);
      case "comparison":
        return renderComparison(blocks, td, compact, renderOptions);
      case "dashboard":
        return renderDashboardTemplate(blocks, td, compact, renderOptions);
      case "steps":
        return renderStepsTemplate(blocks, td, compact, renderOptions);
      case "slides":
        return renderSlidesTemplate(blocks, td, compact, renderOptions);
      case "plan":
        return renderPlanTemplate(blocks, td, compact, renderOptions);
      default:
        return null;
    }
  }

  // ----------------------------------------------------------------
  // Briefing template renderer
  // ----------------------------------------------------------------
  function renderBriefing(blocks, templateData, compact, renderOptions) {
    const container = document.createElement("div");
    container.className = "briefing-container";
    if (compact) container.classList.add("briefing-compact");

    const sections = templateData.sections || [];
    const defaultCollapsed = compact;

    // Summary
    if (templateData.summary) {
      const summary = document.createElement("div");
      summary.className = "briefing-summary";
      summary.innerHTML = simpleMarkdown(templateData.summary);
      container.appendChild(summary);
    }

    // TOC (3+ sections, non-compact only)
    if (sections.length >= 3 && !compact) {
      const toc = document.createElement("nav");
      toc.className = "briefing-toc";
      const tocTitle = document.createElement("div");
      tocTitle.className = "briefing-toc-title";
      tocTitle.textContent = "Contents";
      toc.appendChild(tocTitle);
      for (let i = 0; i < sections.length; i++) {
        const item = document.createElement("a");
        item.className = "briefing-toc-item";
        item.textContent = sections[i].title || `Section ${i + 1}`;
        item.href = "#";
        item.addEventListener("click", function (e) {
          e.preventDefault();
          const target = container.querySelectorAll(".briefing-section")[i];
          if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
        });
        toc.appendChild(item);
      }
      container.appendChild(toc);
    }

    // Expand All / Collapse All
    if (sections.length > 1) {
      const toggleAll = document.createElement("button");
      toggleAll.className = "briefing-toggle-all";
      toggleAll.textContent = defaultCollapsed ? "Expand All" : "Collapse All";
      toggleAll.addEventListener("click", function () {
        const allSections = container.querySelectorAll(".briefing-section-body");
        const allHeaders = container.querySelectorAll(".briefing-section-header");
        const expanding = toggleAll.textContent === "Expand All";
        for (const body of allSections) {
          body.classList.toggle("collapsed", !expanding);
        }
        for (const hdr of allHeaders) {
          hdr.classList.toggle("collapsed", !expanding);
        }
        toggleAll.textContent = expanding ? "Collapse All" : "Expand All";
      });
      container.appendChild(toggleAll);
    }

    // Sections
    for (let i = 0; i < sections.length; i++) {
      const section = sections[i];
      const sectionEl = document.createElement("div");
      sectionEl.className = "briefing-section";

      // Section header with toggle
      const header = document.createElement("div");
      header.className = "briefing-section-header";
      if (defaultCollapsed) header.classList.add("collapsed");

      const titleEl = document.createElement("h3");
      titleEl.className = "briefing-section-title";
      titleEl.textContent = section.title || `Section ${i + 1}`;
      header.appendChild(titleEl);

      sectionEl.appendChild(header);

      // Section summary
      if (section.summary) {
        const sSum = document.createElement("div");
        sSum.className = "briefing-section-summary";
        sSum.innerHTML = simpleMarkdown(section.summary);
        sectionEl.appendChild(sSum);
      }

      // Section body with blocks
      const blockIndices = section.blocks || [];
      if (blockIndices.length > 0) {
        const body = document.createElement("div");
        body.className = "briefing-section-body";
        if (defaultCollapsed) body.classList.add("collapsed");

        for (const idx of blockIndices) {
          if (idx >= 0 && idx < blocks.length) {
            body.appendChild(renderBlock(blocks[idx], renderOptions));
          }
        }

        // Toggle on header click
        header.addEventListener("click", function () {
          body.classList.toggle("collapsed");
          header.classList.toggle("collapsed");
        });
        header.style.cursor = "pointer";

        sectionEl.appendChild(body);
      } else {
        // Title-only section (divider)
        sectionEl.classList.add("briefing-section-divider");
      }

      container.appendChild(sectionEl);
    }

    return container;
  }

  // ----------------------------------------------------------------
  // Comparison template renderer
  // ----------------------------------------------------------------
  function renderComparison(blocks, templateData, compact, renderOptions) {
    const container = document.createElement("div");
    container.className = "comparison-container";
    const layout = templateData.layout || "side-by-side";
    container.classList.add(`comparison-${layout}`);

    if (templateData.summary) {
      const summary = document.createElement("div");
      summary.className = "comparison-summary";
      summary.innerHTML = simpleMarkdown(templateData.summary);
      container.appendChild(summary);
    }

    const sidesWrap = document.createElement("div");
    sidesWrap.className = "comparison-sides";

    const sides = templateData.sides || [];
    for (let i = 0; i < sides.length; i++) {
      const side = sides[i];
      const sideEl = document.createElement("div");
      sideEl.className = "comparison-side";

      const label = document.createElement("div");
      label.className = "comparison-side-label";
      label.textContent = side.label || `Side ${i + 1}`;
      sideEl.appendChild(label);

      const body = document.createElement("div");
      body.className = "comparison-side-body";
      const sideBlocks = side.blocks || [];
      for (const idx of sideBlocks) {
        if (idx >= 0 && idx < blocks.length) {
          body.appendChild(renderBlock(blocks[idx], renderOptions));
        }
      }
      sideEl.appendChild(body);
      sidesWrap.appendChild(sideEl);
    }

    container.appendChild(sidesWrap);
    return container;
  }

  // ----------------------------------------------------------------
  // Dashboard template renderer
  // ----------------------------------------------------------------
  function renderDashboardTemplate(blocks, templateData, compact, renderOptions) {
    const container = document.createElement("div");
    container.className = "dashboard-template";
    const cols = templateData.cols || 2;
    container.style.setProperty("--dashboard-cols", cols);

    const widgets = templateData.widgets || [];
    for (let i = 0; i < widgets.length; i++) {
      const widget = widgets[i];
      const cell = document.createElement("div");
      cell.className = "dashboard-widget";
      const size = widget.size || "1x1";
      const [spanCol, spanRow] = size.split("x").map(Number);
      if (spanCol > 1) cell.style.gridColumn = `span ${spanCol}`;
      if (spanRow > 1) cell.style.gridRow = `span ${spanRow}`;

      const title = document.createElement("div");
      title.className = "dashboard-widget-title";
      title.textContent = widget.title || `Widget ${i + 1}`;
      cell.appendChild(title);

      const body = document.createElement("div");
      body.className = "dashboard-widget-body";
      const widgetBlocks = widget.blocks || [];
      for (const idx of widgetBlocks) {
        if (idx >= 0 && idx < blocks.length) {
          body.appendChild(renderBlock(blocks[idx], renderOptions));
        }
      }
      cell.appendChild(body);
      container.appendChild(cell);
    }

    return container;
  }

  // ----------------------------------------------------------------
  // Steps template renderer
  // ----------------------------------------------------------------
  function renderStepsTemplate(blocks, templateData, compact, renderOptions) {
    const container = document.createElement("div");
    container.className = "steps-container";

    if (templateData.summary) {
      const summary = document.createElement("div");
      summary.className = "steps-summary";
      summary.innerHTML = simpleMarkdown(templateData.summary);
      container.appendChild(summary);
    }

    // Progress bar
    const steps = templateData.steps || [];
    const doneCount = steps.filter(function (s) { return s.done; }).length;
    const progressWrap = document.createElement("div");
    progressWrap.className = "steps-progress";
    const progressBar = document.createElement("div");
    progressBar.className = "steps-progress-bar";
    const pct = steps.length > 0 ? (doneCount / steps.length) * 100 : 0;
    progressBar.style.width = pct + "%";
    progressWrap.appendChild(progressBar);
    const progressLabel = document.createElement("span");
    progressLabel.className = "steps-progress-label";
    progressLabel.textContent = doneCount + "/" + steps.length + " complete";
    progressWrap.appendChild(progressLabel);
    container.appendChild(progressWrap);

    // Steps
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i];
      const stepEl = document.createElement("div");
      stepEl.className = "steps-step";
      if (step.done) stepEl.classList.add("steps-step-done");

      const marker = document.createElement("div");
      marker.className = "steps-step-marker";
      marker.textContent = step.done ? "\u2713" : String(i + 1);
      stepEl.appendChild(marker);

      const content = document.createElement("div");
      content.className = "steps-step-content";

      const title = document.createElement("div");
      title.className = "steps-step-title";
      title.textContent = step.title || "Step " + (i + 1);
      content.appendChild(title);

      if (step.description) {
        const desc = document.createElement("div");
        desc.className = "steps-step-description";
        desc.innerHTML = simpleMarkdown(step.description);
        content.appendChild(desc);
      }

      const stepBlocks = step.blocks || [];
      if (stepBlocks.length > 0) {
        const body = document.createElement("div");
        body.className = "steps-step-body";
        for (const idx of stepBlocks) {
          if (idx >= 0 && idx < blocks.length) {
            body.appendChild(renderBlock(blocks[idx], renderOptions));
          }
        }
        content.appendChild(body);
      }

      stepEl.appendChild(content);

      // Connector line (except last)
      if (i < steps.length - 1) {
        const connector = document.createElement("div");
        connector.className = "steps-connector";
        stepEl.appendChild(connector);
      }

      container.appendChild(stepEl);
    }

    return container;
  }

  // ----------------------------------------------------------------
  // Plan template renderer — Mermaid DAG + step list with status
  // ----------------------------------------------------------------
  function renderPlanTemplate(blocks, templateData, compact, renderOptions) {
    var STEP_STATUS_ICONS = {
      pending: "\u23F3",      // ⏳
      blocked: "\uD83D\uDD12", // 🔒
      in_progress: "\uD83D\uDD04", // 🔄
      completed: "\u2705",    // ✅
      failed: "\u274C"        // ❌
    };
    var PLAN_STATUS_LABELS = {
      proposed: "PROPOSED",
      active: "ACTIVE",
      completed: "COMPLETED",
      cancelled: "CANCELLED"
    };

    var container = document.createElement("div");
    container.className = "plan-container";

    // Plan header with status badge
    var planStatus = templateData.status || "proposed";
    var header = document.createElement("div");
    header.className = "plan-header";
    var badge = document.createElement("span");
    badge.className = "plan-status-badge plan-status-" + planStatus;
    badge.textContent = PLAN_STATUS_LABELS[planStatus] || planStatus.toUpperCase();
    header.appendChild(badge);
    container.appendChild(header);

    // Mermaid DAG section (uses same wrapper as renderMermaid for runMermaid() compat)
    if (templateData.mermaid) {
      var dagSection = document.createElement("div");
      dagSection.className = "plan-dag format-mermaid";
      var mermaidPanel = document.createElement("div");
      mermaidPanel.className = "mermaid-panel";
      var pre = document.createElement("pre");
      pre.className = "mermaid-pending mermaid";
      pre.textContent = templateData.mermaid;
      pre.dataset.mermaidSource = templateData.mermaid;
      mermaidPanel.appendChild(pre);
      dagSection.appendChild(mermaidPanel);
      container.appendChild(dagSection);
    }

    // Steps section
    var steps = templateData.steps || [];
    if (steps.length > 0) {
      // Progress bar
      var doneCount = steps.filter(function (s) { return s.status === "completed"; }).length;
      var progressWrap = document.createElement("div");
      progressWrap.className = "plan-progress";
      var progressBar = document.createElement("div");
      progressBar.className = "plan-progress-bar";
      var pct = (doneCount / steps.length) * 100;
      progressBar.style.width = pct + "%";
      progressWrap.appendChild(progressBar);
      var progressLabel = document.createElement("span");
      progressLabel.className = "plan-progress-label";
      progressLabel.textContent = doneCount + "/" + steps.length + " completed";
      progressWrap.appendChild(progressLabel);
      container.appendChild(progressWrap);

      // Step list
      var stepList = document.createElement("div");
      stepList.className = "plan-step-list";

      for (var i = 0; i < steps.length; i++) {
        var step = steps[i];
        var stepStatus = step.status || "pending";
        var item = document.createElement("div");
        item.className = "plan-step-item";
        if (stepStatus === "completed") item.classList.add("plan-step-item-completed");

        var icon = document.createElement("span");
        icon.className = "plan-step-icon";
        icon.textContent = STEP_STATUS_ICONS[stepStatus] || STEP_STATUS_ICONS.pending;
        item.appendChild(icon);

        var subject = document.createElement("span");
        subject.className = "plan-step-subject";
        subject.textContent = step.subject || "Step " + (i + 1);
        item.appendChild(subject);

        if (step.agent) {
          var agent = document.createElement("span");
          agent.className = "plan-step-agent";
          agent.textContent = step.agent;
          item.appendChild(agent);
        }

        var statusLabel = document.createElement("span");
        statusLabel.className = "plan-step-status";
        statusLabel.textContent = stepStatus;
        item.appendChild(statusLabel);

        stepList.appendChild(item);
      }

      container.appendChild(stepList);
    }

    return container;
  }

  // ----------------------------------------------------------------
  // Slides template renderer
  // ----------------------------------------------------------------
  function renderSlidesTemplate(blocks, templateData, compact, renderOptions) {
    const container = document.createElement("div");
    container.className = "slides-container";

    const slides = templateData.slides || [];
    if (slides.length === 0) return container;

    let currentSlide = 0;

    const viewport = document.createElement("div");
    viewport.className = "slides-viewport";

    // Build all slide elements
    const slideEls = [];
    for (let i = 0; i < slides.length; i++) {
      const slide = slides[i];
      const slideEl = document.createElement("div");
      slideEl.className = "slides-slide";
      if (i !== 0) slideEl.classList.add("slides-slide-hidden");

      if (slide.title) {
        const title = document.createElement("div");
        title.className = "slides-slide-title";
        title.textContent = slide.title;
        slideEl.appendChild(title);
      }

      const body = document.createElement("div");
      body.className = "slides-slide-body";
      const slideBlocks = slide.blocks || [];
      for (const idx of slideBlocks) {
        if (idx >= 0 && idx < blocks.length) {
          body.appendChild(renderBlock(blocks[idx], renderOptions));
        }
      }
      slideEl.appendChild(body);

      if (slide.notes) {
        const notes = document.createElement("div");
        notes.className = "slides-slide-notes";
        notes.innerHTML = simpleMarkdown(slide.notes);
        slideEl.appendChild(notes);
      }

      viewport.appendChild(slideEl);
      slideEls.push(slideEl);
    }

    container.appendChild(viewport);

    // Navigation
    if (slides.length > 1) {
      const nav = document.createElement("div");
      nav.className = "slides-nav";

      const prevBtn = document.createElement("button");
      prevBtn.className = "slides-nav-btn";
      prevBtn.textContent = "\u25C0 Prev";
      prevBtn.disabled = true;

      const indicator = document.createElement("span");
      indicator.className = "slides-nav-indicator";
      indicator.textContent = "1 / " + slides.length;

      const nextBtn = document.createElement("button");
      nextBtn.className = "slides-nav-btn";
      nextBtn.textContent = "Next \u25B6";

      function showSlide(idx) {
        slideEls[currentSlide].classList.add("slides-slide-hidden");
        currentSlide = idx;
        slideEls[currentSlide].classList.remove("slides-slide-hidden");
        indicator.textContent = (currentSlide + 1) + " / " + slides.length;
        prevBtn.disabled = currentSlide === 0;
        nextBtn.disabled = currentSlide === slides.length - 1;
      }

      prevBtn.addEventListener("click", function () {
        if (currentSlide > 0) showSlide(currentSlide - 1);
      });
      nextBtn.addEventListener("click", function () {
        if (currentSlide < slides.length - 1) showSlide(currentSlide + 1);
      });

      nav.appendChild(prevBtn);
      nav.appendChild(indicator);
      nav.appendChild(nextBtn);
      container.appendChild(nav);
    }

    return container;
  }

  function buildMetaRow(prefix, block) {
    var t = block.x_title;
    var f = block.x_filename;
    if (!t && !f) return null;
    const meta = document.createElement("div");
    meta.className = prefix + "-view-meta";
    if (t) {
      const title = document.createElement("div");
      title.className = prefix + "-title";
      title.textContent = String(t);
      meta.appendChild(title);
    }
    if (f) {
      const filename = document.createElement("div");
      filename.className = prefix + "-filename";
      filename.textContent = String(f);
      meta.appendChild(filename);
    }
    return meta;
  }

  function renderMermaid(el, body, block) {
    const meta = buildMetaRow("mermaid", block);

    const pre = document.createElement("pre");
    pre.className = "mermaid-pending mermaid";
    pre.textContent = body;
    pre.dataset.mermaidSource = body;

    if (meta) {
      const wrapper = document.createElement("div");
      wrapper.className = "mermaid-panel";
      wrapper.appendChild(meta);
      wrapper.appendChild(pre);
      el.appendChild(wrapper);
    } else {
      el.appendChild(pre);
    }
  }

  /** Run mermaid on pending diagrams and fix SVG heights afterward. */
  function runMermaid(selector) {
    if (typeof mermaid === "undefined") return;
    const target = selector || ".mermaid-pending";
    mermaid.run({ querySelector: target }).then(function () {
      // After mermaid replaces <pre> with <svg>, remove fixed height attributes
      // so the SVG flows naturally within its container.
      document.querySelectorAll(".format-mermaid svg, .dep-graph svg, .workflow-step-flow svg").forEach(function (svg) {
        // Mermaid sets inline style="max-width: XXXpx" based on diagram complexity.
        // Preserve it but cap at container width. Only override height.
        svg.removeAttribute("height");
        svg.removeAttribute("width");
        svg.style.height = "auto";
        svg.style.display = "block";
        svg.style.margin = "0 auto";
      });
    }).catch(function () { /* mermaid parse errors are non-fatal */ });
  }

  function renderMarkdown(el, body) {
    // Simple markdown: headings, bold, italic, code, links, lists
    const html = simpleMarkdown(body);
    el.innerHTML = html;
  }

  function formatCanvasHTMLDocument(body, isCanvasView) {
    // Minimal layout reset — avoid overflow:hidden and min-height:100%
    // which clip content and break user layouts
    const documentStyle = isCanvasView ? [
      "<style>",
      "html, body { height: 100%; margin: 0; }",
      "</style>",
    ].join("") : "";

    // Theme CSS variables that agent-generated HTML can use
    var artifactStyle = [
      "<style>",
      ':root { color-scheme: dark; --bg: #1a1a2e; --fg: #e0e0e0; --border: #333; }',
      ':root[data-theme="light"] { color-scheme: light; --bg: #fff; --fg: #1a1a1a; --border: #ddd; }',
      "body { background: var(--bg); color: var(--fg); }",
      "</style>",
    ].join("");

    // Listen for theme changes from parent
    var artifactScript = [
      "<script>",
      'window.addEventListener("message", function(e) {',
      '  if (e.data && e.data.type === "synapse-theme") {',
      '    document.documentElement.setAttribute("data-theme", e.data.theme);',
      "    document.documentElement.style.colorScheme = e.data.theme;",
      "  }",
      "});",
      "</script>",
    ].join("");

    // Notify parent of content height changes for auto-resize
    var resizeScript = [
      "<script>",
      "(function() {",
      "  var _lastH = 0;",
      "  function notifyHeight() {",
      "    var b = document.body; if (!b) return;",
      "    var prev = b.style.overflow;",
      "    b.style.overflow = 'visible';",
      "    var h = Math.max(b.scrollHeight, b.offsetHeight);",
      "    b.style.overflow = prev;",
      '    if (h !== _lastH) { _lastH = h; parent.postMessage({ type: "synapse-resize", height: h }, "*"); }',
      "  }",
      '  window.addEventListener("load", function() {',
      '    if (typeof ResizeObserver !== "undefined") { new ResizeObserver(notifyHeight).observe(document.body); }',
      "    else { setTimeout(notifyHeight, 50); }",
      "  });",
      "})();",
      "</script>",
    ].join("");

    var injected = documentStyle + artifactStyle + artifactScript + resizeScript;

    // Normalize full documents to fragments to avoid head-semantics issues
    // (CSP meta, script ordering, overflow conflicts) in sandboxed iframes.
    // Extract head content and body content, then wrap uniformly.
    var headContent = "";
    var innerBody = body;

    if (/<html[\s>]/i.test(body) || /<!doctype/i.test(body)) {
      // Extract content between <head> and </head>
      var headMatch = body.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
      if (headMatch) {
        headContent = headMatch[1];
      }
      // Extract content between <body> and </body>
      var bodyMatch = body.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
      if (bodyMatch) {
        innerBody = bodyMatch[1];
      } else {
        // No <body> tag — strip doctype/html/head wrappers
        innerBody = body
          .replace(/<!doctype[^>]*>/i, "")
          .replace(/<\/?html[^>]*>/gi, "")
          .replace(/<head[^>]*>[\s\S]*?<\/head>/i, "");
      }
    }

    return [
      "<!doctype html>",
      "<html>",
      "<head>",
      injected,
      headContent,
      "</head>",
      "<body>",
      innerBody,
      "</body>",
      "</html>",
    ].join("");
  }

  function broadcastThemeToIframes(theme) {
    document.querySelectorAll(".format-html iframe, .format-artifact iframe").forEach(function(iframe) {
      if (iframe.contentWindow) {
        iframe.contentWindow.postMessage({ type: "synapse-theme", theme: theme }, "*");
      }
    });
  }

  function renderHTML(el, body, options) {
    // Sandboxed iframe for raw HTML
    const iframe = document.createElement("iframe");
    iframe.sandbox = "allow-scripts";
    iframe.style.width = "100%";
    iframe.style.border = "1px solid var(--color-border)";
    iframe.style.borderRadius = "4px";
    // In canvas view, fill the available content area
    const isCanvasView = options && options.inCanvasView === true;
    if (!isCanvasView) {
      iframe.style.minHeight = "200px";
    }
    iframe.srcdoc = formatCanvasHTMLDocument(body, isCanvasView);
    // Auto-resize (dashboard only — canvas uses CSS flex)
    iframe.onload = function () {
      if (!isCanvasView) {
        // Fallback: try direct DOM access (works when not cross-origin)
        try {
          iframe.style.height = iframe.contentDocument.body.scrollHeight + 20 + "px";
        } catch { /* cross-origin — postMessage resize will handle it */ }
      }
      // Send initial theme to iframe
      broadcastThemeToIframes(document.documentElement.getAttribute("data-theme") || "dark");
    };
    el.appendChild(iframe);
  }

  function renderTable(el, body) {
    // body is JSON: { headers: [...], rows: [[...], ...] }
    let data;
    try {
      data = typeof body === "string" ? JSON.parse(body) : body;
    } catch {
      el.textContent = body;
      return;
    }

    const table = document.createElement("table");
    if (data.headers) {
      const thead = document.createElement("thead");
      const tr = document.createElement("tr");
      for (const h of data.headers) {
        const th = document.createElement("th");
        th.textContent = h;
        tr.appendChild(th);
      }
      thead.appendChild(tr);
      table.appendChild(thead);
    }

    if (data.rows) {
      const tbody = document.createElement("tbody");
      for (const row of data.rows) {
        const tr = document.createElement("tr");
        for (const cell of row) {
          const td = document.createElement("td");
          td.textContent = cell;
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
    }

    el.appendChild(table);
  }

  function renderJSON(el, body, block) {
    let obj;
    try {
      obj = typeof body === "string" ? JSON.parse(body) : body;
    } catch {
      obj = body;
    }

    const meta = buildMetaRow("json", block);
    if (meta) el.appendChild(meta);

    const pre = document.createElement("pre");
    pre.className = "json-view";
    const content = document.createElement("code");
    try {
      content.textContent = JSON.stringify(obj, null, 2);
    } catch {
      content.textContent = body;
    }
    pre.appendChild(content);
    el.appendChild(pre);
  }

  function buildDiffPane(lines, className) {
    const pane = document.createElement("div");
    pane.className = "diff-pane " + className;
    const pre = document.createElement("pre");
    for (const l of lines) {
      const row = document.createElement("div");
      row.className = "diff-row diff-" + l.type;
      const numSpan = document.createElement("span");
      numSpan.className = "diff-line-num";
      numSpan.textContent = l.num;
      row.appendChild(numSpan);
      const textSpan = document.createElement("span");
      textSpan.className = "diff-line-text";
      textSpan.textContent = l.text;
      row.appendChild(textSpan);
      pre.appendChild(row);
    }
    pane.appendChild(pre);
    return pane;
  }

  function renderDiff(el, body) {
    const container = document.createElement("div");
    container.className = "diff-side-by-side";

    const lines = body.split("\n");
    const leftLines = [];
    const rightLines = [];
    let leftNum = 0;
    let rightNum = 0;

    for (const line of lines) {
      if (line.startsWith("@@")) {
        // Parse hunk header for line numbers
        const match = line.match(/@@ -(\d+)/);
        if (match) leftNum = parseInt(match[1], 10) - 1;
        const matchR = line.match(/\+(\d+)/);
        if (matchR) rightNum = parseInt(matchR[1], 10) - 1;
        leftLines.push({ type: "hunk", text: line, num: "" });
        rightLines.push({ type: "hunk", text: line, num: "" });
      } else if (line.startsWith("---") || line.startsWith("+++") || line.startsWith("diff ") || line.startsWith("index ")) {
        // File headers — show on both sides
        leftLines.push({ type: "header", text: line, num: "" });
        rightLines.push({ type: "header", text: line, num: "" });
      } else if (line.startsWith("-")) {
        leftNum++;
        leftLines.push({ type: "del", text: line.slice(1), num: leftNum });
        rightLines.push({ type: "empty", text: "", num: "" });
      } else if (line.startsWith("+")) {
        rightNum++;
        leftLines.push({ type: "empty", text: "", num: "" });
        rightLines.push({ type: "add", text: line.slice(1), num: rightNum });
      } else {
        leftNum++;
        rightNum++;
        const text = line.startsWith(" ") ? line.slice(1) : line;
        leftLines.push({ type: "ctx", text, num: leftNum });
        rightLines.push({ type: "ctx", text, num: rightNum });
      }
    }

    container.appendChild(buildDiffPane(leftLines, "diff-pane-left"));
    container.appendChild(buildDiffPane(rightLines, "diff-pane-right"));
    el.appendChild(container);
  }

  function renderCode(el, body, lang, block) {
    const meta = buildMetaRow("code", block);

    const pre = document.createElement("pre");
    if (meta) pre.appendChild(meta);

    const code = document.createElement("code");
    if (lang) code.className = `language-${lang}`;
    code.textContent = body;
    pre.appendChild(code);
    el.appendChild(pre);
    if (typeof hljs !== "undefined") {
      hljs.highlightElement(code);
    }
  }

  function renderImage(el, body) {
    const img = document.createElement("img");
    img.src = body;
    img.style.maxWidth = "100%";
    img.alt = "Canvas image";
    el.appendChild(img);
  }

  function renderChart(el, body) {
    // Try Chart.js JSON config first, fall back to Mermaid syntax
    let config;
    try {
      config = typeof body === "string" ? JSON.parse(body) : body;
    } catch {
      // Not JSON — treat as Mermaid pie/bar syntax
      const pre = document.createElement("pre");
      pre.className = "mermaid-pending mermaid";
      pre.textContent = body;
      pre.dataset.mermaidSource = body;
      el.appendChild(pre);
      return;
    }

    if (typeof Chart === "undefined") {
      // Chart.js not loaded — show raw JSON
      const pre = document.createElement("pre");
      pre.className = "json-view";
      pre.textContent = JSON.stringify(config, null, 2);
      el.appendChild(pre);
      return;
    }

    const canvas = document.createElement("canvas");
    el.appendChild(canvas);
    new Chart(canvas, config);
  }

  function renderLog(el, body, block) {
    const data = parseBody(body);
    const entries = Array.isArray(data) ? data : [];
    const meta = buildMetaRow("log", block);
    if (meta) el.appendChild(meta);
    const pre = document.createElement("pre");
    pre.className = "log-view";
    for (const entry of entries) {
      const line = document.createElement("div");
      const level = String(entry.level || "info").toLowerCase();
      line.className = `log-${level === "warning" ? "warn" : level}`;
      line.textContent = `${entry.ts || ""} [${entry.level || "INFO"}] ${entry.msg || ""}`.trim();
      pre.appendChild(line);
    }
    el.appendChild(pre);
  }

  function renderStatus(el, body) {
    const data = body && typeof body === "object" ? body : {};
    const badge = document.createElement("div");
    badge.className = "status-badge";

    const dot = document.createElement("span");
    dot.className = `status-dot ${data.state || "running"}`;
    badge.appendChild(dot);

    const label = document.createElement("div");
    label.className = "status-label";
    label.textContent = `${statusIcon(data.state)} ${data.label || data.state || "Unknown"}`;
    badge.appendChild(label);

    el.appendChild(badge);

    if (data.detail) {
      const detail = document.createElement("div");
      detail.className = "status-detail";
      detail.textContent = data.detail;
      el.appendChild(detail);
    }
  }

  function renderMetric(el, body) {
    const data = body && typeof body === "object" ? body : {};
    const valueRow = document.createElement("div");

    const value = document.createElement("span");
    value.className = "metric-value";
    value.textContent = data.value ?? "";
    valueRow.appendChild(value);

    if (data.unit) {
      const unit = document.createElement("span");
      unit.className = "metric-unit";
      unit.textContent = data.unit;
      valueRow.appendChild(unit);
    }

    el.appendChild(valueRow);

    if (data.label) {
      const label = document.createElement("div");
      label.className = "metric-label";
      label.textContent = data.label;
      el.appendChild(label);
    }
  }

  function renderChecklist(el, body, block) {
    const data = parseBody(body);
    const items = Array.isArray(data) ? data : [];
    const meta = buildMetaRow("checklist", block);
    if (meta) el.appendChild(meta);
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "checklist-item";
      if (item.checked) row.classList.add("checked");
      row.textContent = `${item.checked ? "☑" : "☐"} ${item.text || ""}`;
      el.appendChild(row);
    }
  }

  function renderTimeline(el, body) {
    const items = Array.isArray(body) ? body : [];
    const timeline = document.createElement("div");
    timeline.className = "timeline";
    for (const item of items) {
      const event = document.createElement("div");
      event.className = "timeline-event";

      const ts = document.createElement("div");
      ts.className = "timeline-ts";
      ts.textContent = item.ts || "";
      event.appendChild(ts);

      const text = document.createElement("div");
      text.className = "timeline-text";
      text.textContent = item.event || "";
      event.appendChild(text);

      if (item.agent) {
        const agent = document.createElement("div");
        agent.className = "timeline-agent";
        agent.textContent = item.agent;
        event.appendChild(agent);
      }

      timeline.appendChild(event);
    }
    el.appendChild(timeline);
  }

  function renderAlert(el, body) {
    const data = body && typeof body === "object" ? body : {};
    const card = document.createElement("div");
    card.className = "alert-card";
    if (data.severity) card.classList.add(data.severity);

    const message = document.createElement("div");
    message.className = "alert-message";
    message.textContent = data.message || "";
    card.appendChild(message);

    if (data.source) {
      const source = document.createElement("div");
      source.className = "alert-source";
      source.textContent = data.source;
      card.appendChild(source);
    }

    el.appendChild(card);
  }

  function renderFilePreview(el, body) {
    const data = body && typeof body === "object" ? body : {};

    const path = document.createElement("div");
    path.className = "file-path";
    path.textContent = data.path || "";
    el.appendChild(path);

    const pre = document.createElement("pre");
    const code = document.createElement("code");
    if (data.lang) code.className = `language-${data.lang}`;

    const startLine = Number.isFinite(Number(data.start_line)) ? Number(data.start_line) : 1;
    const lines = String(data.snippet || "").split("\n");
    code.textContent = lines
      .map((line, index) => `${String(startLine + index).padStart(4, " ")} | ${line}`)
      .join("\n");
    pre.appendChild(code);
    el.appendChild(pre);
    if (data.lang && typeof hljs !== "undefined") {
      hljs.highlightElement(code);
    }
  }

  function renderTrace(el, body, block) {
    const data = parseBody(body);
    const spans = Array.isArray(data) ? data : [];
    const meta = buildMetaRow("trace", block);
    if (meta) el.appendChild(meta);
    const tree = document.createElement("div");
    for (const span of spans) {
      tree.appendChild(renderTraceSpan(span));
    }
    el.appendChild(tree);
  }

  function renderTraceSpan(span) {
    const wrap = document.createElement("div");
    wrap.className = "trace-span";

    const bar = document.createElement("span");
    bar.className = "trace-bar";
    if (span.status === "error") bar.classList.add("error");
    const width = Math.max(4, Math.min(120, Number(span.duration_ms) || 4));
    bar.style.width = `${width}px`;
    wrap.appendChild(bar);

    const text = document.createElement("span");
    text.textContent = `${span.name || "span"} (${span.duration_ms || 0}ms)`;
    wrap.appendChild(text);

    if (Array.isArray(span.children) && span.children.length > 0) {
      const children = document.createElement("div");
      children.className = "trace-children";
      for (const child of span.children) {
        children.appendChild(renderTraceSpan(child));
      }
      wrap.appendChild(children);
    }

    return wrap;
  }

  function renderTaskBoard(el, body) {
    const data = body && typeof body === "object" ? body : {};
    const board = document.createElement("div");
    board.className = "task-board";

    for (const column of data.columns || []) {
      const col = document.createElement("div");
      col.className = "task-column";

      const header = document.createElement("div");
      header.className = "task-column-header";
      header.textContent = column.name || "";
      col.appendChild(header);

      for (const item of column.items || []) {
        const card = document.createElement("div");
        card.className = "task-item";
        card.textContent = `${item.id || ""} ${item.subject || ""}`.trim();
        if (item.assignee) {
          const assignee = document.createElement("div");
          assignee.className = "task-assignee";
          assignee.textContent = item.assignee;
          card.appendChild(assignee);
        }
        col.appendChild(card);
      }

      board.appendChild(col);
    }

    el.appendChild(board);
  }

  function renderTip(el, body, block) {
    const meta = buildMetaRow("tip", block);
    if (meta) el.appendChild(meta);

    const text = document.createElement("div");
    text.className = "tip-view";
    text.textContent = typeof body === "string" ? body : String(body || "");
    el.appendChild(text);
  }

  function renderProgress(el, body) {
    var data = parseBody(body);
    data = data && typeof data === "object" ? data : {};
    var current = Number(data.current) || 0;
    var total = Number(data.total) || 1;
    var pct = Math.min(100, Math.round((current / total) * 100));
    var status = (data.status || "in_progress").replace(/[^a-z_-]/g, "");

    // Label
    if (data.label) {
      var lbl = document.createElement("div");
      lbl.className = "progress-label";
      lbl.textContent = data.label;
      el.appendChild(lbl);
    }

    // Bar
    var barWrap = document.createElement("div");
    barWrap.className = "progress-bar";
    var fill = document.createElement("div");
    fill.className = "progress-fill progress-" + status;
    fill.style.width = pct + "%";
    barWrap.appendChild(fill);
    var pctLabel = document.createElement("span");
    pctLabel.className = "progress-pct";
    pctLabel.textContent = pct + "%";
    barWrap.appendChild(pctLabel);
    el.appendChild(barWrap);

    // Counter
    var counter = document.createElement("div");
    counter.className = "progress-counter";
    counter.textContent = current + " / " + total;
    el.appendChild(counter);

    // Steps
    if (Array.isArray(data.steps) && data.steps.length > 0) {
      var stepList = document.createElement("div");
      stepList.className = "progress-steps";
      for (var i = 0; i < data.steps.length; i++) {
        var step = document.createElement("div");
        step.className = "progress-step";
        if (i < current) {
          step.classList.add("done");
        } else if (i === current) {
          step.classList.add("active");
        }
        var icon = i < current ? "\u2714" : i === current ? "\u25b6" : "\u25cb";
        step.textContent = icon + " " + data.steps[i];
        stepList.appendChild(step);
      }
      el.appendChild(stepList);
    }
  }

  function renderTerminal(el, body) {
    var text = typeof body === "string" ? body : String(body || "");
    var pre = document.createElement("pre");
    pre.className = "terminal-output";
    // Parse ANSI escape codes into styled spans
    pre.innerHTML = ansiToHtml(text);
    el.appendChild(pre);
  }

  var _ansiRe = new RegExp("\u001b\\[(\\d+(?:;\\d+)*)m", "g");
  function ansiToHtml(text) {
    var escaped = escapeHtml(text);
    var openSpans = 0;
    return escaped.replace(_ansiRe, function (_match, params) {
      var codes = params.split(";");
      var result = "";
      for (var ci = 0; ci < codes.length; ci++) {
        var code = codes[ci];
        if (code === "0") {
          while (openSpans > 0) { result += "</span>"; openSpans--; }
        } else {
          var tag = _ansiMap[code];
          if (tag) { result += tag; openSpans++; }
        }
      }
      return result;
    });
  }

  function renderDependencyGraph(el, body) {
    var data = parseBody(body);
    data = data && typeof data === "object" ? data : {};
    var nodes = Array.isArray(data.nodes) ? data.nodes : [];
    var edges = Array.isArray(data.edges) ? data.edges : [];

    // Build Mermaid graph syntax with unique internal IDs
    var lines = ["graph TD"];
    var groups = {};
    var idMap = {}; // original node id → unique mermaid id
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var origId = n.id || "node" + i;
      var mId = "n" + i;
      idMap[origId] = mId;
      var label = origId.replace(/["[\]]/g, "");
      lines.push("  " + mId + '["' + label + '"]');
      if (n.group) {
        if (!groups[n.group]) groups[n.group] = [];
        groups[n.group].push(mId);
      }
    }
    // Subgraph grouping (appended after node declarations)
    var groupKeys = Object.keys(groups);
    for (var k = 0; k < groupKeys.length; k++) {
      var gName = groupKeys[k].replace(/["[\]]/g, "");
      lines.push("  subgraph " + gName);
      var members = groups[groupKeys[k]];
      for (var m = 0; m < members.length; m++) {
        lines.push("    " + members[m]);
      }
      lines.push("  end");
    }
    // Edges after subgraphs
    for (var j = 0; j < edges.length; j++) {
      var e = edges[j];
      if (!idMap[e.from] || !idMap[e.to]) continue;
      var fromId = idMap[e.from];
      var toId = idMap[e.to];
      var edgeLabel = e.label ? " -->|" + e.label.replace(/[|]/g, "") + "| " : " --> ";
      lines.push("  " + fromId + edgeLabel + toId);
    }

    var wrap = document.createElement("div");
    wrap.className = "dep-graph";
    var mermaidPre = document.createElement("pre");
    mermaidPre.className = "mermaid-pending mermaid";
    var mermaidSrc = lines.join("\n");
    mermaidPre.textContent = mermaidSrc;
    mermaidPre.dataset.mermaidSource = mermaidSrc;
    wrap.appendChild(mermaidPre);
    el.appendChild(wrap);
  }

  function renderCost(el, body) {
    var data = parseBody(body);
    data = data && typeof data === "object" ? data : {};
    var agents = Array.isArray(data.agents) ? data.agents : [];
    var currency = data.currency || "USD";

    var table = document.createElement("table");
    table.className = "cost-table";

    var thead = document.createElement("thead");
    var headerRow = document.createElement("tr");
    var cols = ["Agent", "Input Tokens", "Output Tokens", "Cost (" + currency + ")"];
    for (var i = 0; i < cols.length; i++) {
      var th = document.createElement("th");
      th.textContent = cols[i];
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    for (var j = 0; j < agents.length; j++) {
      var a = agents[j];
      var row = document.createElement("tr");
      var cells = [
        a.name || "",
        formatNumber(a.input_tokens),
        formatNumber(a.output_tokens),
        typeof a.cost === "number" ? a.cost.toFixed(4) : "-",
      ];
      for (var c = 0; c < cells.length; c++) {
        var td = document.createElement("td");
        td.textContent = cells[c];
        row.appendChild(td);
      }
      tbody.appendChild(row);
    }
    table.appendChild(tbody);

    var tfoot = document.createElement("tfoot");
    var totalRow = document.createElement("tr");
    var totalLabel = document.createElement("td");
    totalLabel.colSpan = 3;
    totalLabel.textContent = "Total";
    totalRow.appendChild(totalLabel);
    var totalVal = document.createElement("td");
    totalVal.textContent = typeof data.total_cost === "number" ? data.total_cost.toFixed(4) + " " + currency : "-";
    totalRow.appendChild(totalVal);
    tfoot.appendChild(totalRow);
    table.appendChild(tfoot);

    el.appendChild(table);
  }

  function renderLinkPreview(el, body) {
    var data = body && typeof body === "object" ? body : {};
    var url = data.url || data.og_url || "";
    var domain = data.domain || "";
    var title = data.og_title || data.title || domain || url;
    var description = data.og_description || data.description || "";
    var image = data.og_image || data.image || "";
    var siteName = data.og_site_name || data.site_name || domain;
    var favicon = data.favicon || "";

    var card = document.createElement(url ? "a" : "div");
    card.className = "link-preview-card";
    if (url) {
      card.href = url;
      card.target = "_blank";
      card.rel = "noopener noreferrer";
    }

    // Left text section
    var textSection = document.createElement("div");
    textSection.className = "link-preview-text";

    // Site name row (favicon + site name)
    var siteRow = document.createElement("div");
    siteRow.className = "link-preview-site";
    if (favicon) {
      var favImg = document.createElement("img");
      favImg.className = "link-preview-favicon";
      favImg.src = favicon;
      favImg.alt = "";
      favImg.width = 16;
      favImg.height = 16;
      favImg.onerror = function () { this.style.display = "none"; };
      siteRow.appendChild(favImg);
    }
    var siteSpan = document.createElement("span");
    siteSpan.textContent = siteName;
    siteRow.appendChild(siteSpan);
    textSection.appendChild(siteRow);

    // Title
    var titleEl = document.createElement("div");
    titleEl.className = "link-preview-title";
    titleEl.textContent = title;
    textSection.appendChild(titleEl);

    // Description
    if (description) {
      var descEl = document.createElement("div");
      descEl.className = "link-preview-description";
      descEl.textContent = description;
      textSection.appendChild(descEl);
    }

    // URL display
    var urlEl = document.createElement("div");
    urlEl.className = "link-preview-url";
    urlEl.textContent = url;
    textSection.appendChild(urlEl);

    card.appendChild(textSection);

    // Right thumbnail image
    if (image) {
      var imgWrap = document.createElement("div");
      imgWrap.className = "link-preview-thumbnail";
      var img = document.createElement("img");
      img.src = image;
      img.alt = title;
      img.onerror = function () { imgWrap.style.display = "none"; };
      imgWrap.appendChild(img);
      card.appendChild(imgWrap);
    }

    el.appendChild(card);
  }

  function formatNumber(n) {
    if (n == null) return "-";
    return Number(n).toLocaleString();
  }

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
  var _dashTaskViewState = "status";
  var _dashTaskExpandedIds = {};
  var TASK_STATUSES = ["pending", "in_progress", "completed", "failed"];
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
    renderDashTasks(data.tasks || {});
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

  function buildTaskBars(tasks) {
    var total = 0;
    var statuses = TASK_STATUSES;
    var counts = {};
    for (var i = 0; i < statuses.length; i++) {
      var items = tasks[statuses[i]] || [];
      counts[statuses[i]] = items.length;
      total += items.length;
    }
    if (total === 0) return { bars: null, total: 0 };

    var bars = document.createElement("div");
    bars.className = "dash-task-bars";

    var colors = { pending: "var(--color-warning)", in_progress: "var(--color-accent)", completed: "var(--color-success)", failed: "var(--color-danger)" };
    var labels = { pending: "Pending", in_progress: "In Progress", completed: "Completed", failed: "Failed" };

    for (var j = 0; j < statuses.length; j++) {
      var s = statuses[j];
      var c = counts[s];
      if (c === 0 && s === "failed") continue;
      var row = document.createElement("div");
      row.className = "dash-task-bar-row";

      var labelEl = document.createElement("span");
      labelEl.className = "dash-task-bar-label";
      labelEl.textContent = labels[s];
      row.appendChild(labelEl);

      var track = document.createElement("div");
      track.className = "dash-task-bar-track";
      var fill = document.createElement("div");
      fill.className = "dash-task-bar-fill";
      fill.style.width = (total > 0 ? Math.round((c / total) * 100) : 0) + "%";
      fill.style.background = colors[s];
      track.appendChild(fill);
      row.appendChild(track);

      var countEl = document.createElement("span");
      countEl.className = "dash-task-bar-count";
      countEl.style.color = colors[s];
      countEl.textContent = String(c);
      row.appendChild(countEl);

      bars.appendChild(row);
    }
    return { bars: bars, total: total };
  }

  function renderDashTasks(tasks) {
    var el = document.getElementById("dash-tasks");
    if (!el) return;

    var result = buildTaskBars(tasks);

    if (result.total === 0) {
      el.innerHTML = "";
      el.appendChild(createDashHeader("ph-kanban", "Task Board (0)"));
      el.appendChild(emptyState("No tasks"));
      return;
    }

    if (updateDashWidget(el, "Task Board (" + result.total + ")", function () { return buildTaskBars(tasks).bars; }, function () { return renderSystemTasks(tasks); })) return;

    el.innerHTML = "";
    el.appendChild(createDashWidget("tasks", "ph-kanban", "Task Board (" + result.total + ")", result.bars, function () { return renderSystemTasks(tasks); }));
  }

  function buildMemoryList(memories) {
    var list = document.createElement("div");
    list.className = "dash-memory-list";
    var shown = memories.slice(0, 5);
    for (var i = 0; i < shown.length; i++) {
      var m = shown[i];
      var item = document.createElement("div");
      item.className = "dash-memory-item";

      var key = document.createElement("span");
      key.className = "dash-memory-key";
      key.textContent = m.key || "";
      item.appendChild(key);

      var content = document.createElement("span");
      content.className = "dash-memory-content";
      content.textContent = m.content || "";
      item.appendChild(content);

      var author = document.createElement("span");
      author.className = "dash-memory-author";
      author.textContent = m.author || "";
      item.appendChild(author);

      list.appendChild(item);
    }
    return list;
  }

  function renderDashMemory(memories) {
    var el = document.getElementById("dash-memory");
    if (!el) return;

    if (memories.length === 0) {
      el.innerHTML = "";
      el.appendChild(createDashHeader("ph-brain", "Shared Knowledge (0)"));
      el.appendChild(emptyState("No shared memories"));
      return;
    }

    var titleText = "Shared Knowledge (" + memories.length + ")";
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

  function renderSystemTasks(tasks) {
    const wrapper = document.createElement("div");

    // View toggle: Status | Group | Component
    const toggleBar = document.createElement("div");
    toggleBar.className = "task-view-toggle";
    const views = [
      { key: "status", label: "Status" },
      { key: "group", label: "Group" },
      { key: "component", label: "Component" },
    ];
    function renderBoard() {
      const existing = wrapper.querySelector(".task-board");
      if (existing) existing.remove();

      const board = document.createElement("div");
      board.className = "task-board";

      const grouped = groupTasksBy(tasks, _dashTaskViewState);
      for (const [groupName, items] of Object.entries(grouped)) {
        const column = document.createElement("div");
        column.className = "task-column";
        column.dataset.group = groupName;

        const header = document.createElement("div");
        header.className = "task-column-header";
        const label = document.createElement("span");
        label.textContent = groupName.replace("_", " ");
        header.appendChild(label);
        const countEl = document.createElement("span");
        countEl.className = "task-column-count";
        countEl.textContent = items.length;
        header.appendChild(countEl);
        column.appendChild(header);

        for (const item of items) {
          column.appendChild(renderTaskCard(item));
        }

        board.appendChild(column);
      }
      wrapper.appendChild(board);
    }

    for (const v of views) {
      const btn = document.createElement("button");
      btn.className = "task-view-btn" + (v.key === _dashTaskViewState ? " active" : "");
      btn.textContent = v.label;
      btn.addEventListener("click", function () {
        _dashTaskViewState = v.key;
        toggleBar.querySelectorAll(".task-view-btn").forEach(function (b) {
          b.classList.toggle("active", b.textContent === v.label);
        });
        renderBoard();
      });
      toggleBar.appendChild(btn);
    }
    wrapper.appendChild(toggleBar);
    renderBoard();
    return wrapper;
  }

  function groupTasksBy(tasks, viewKey) {
    if (viewKey === "status") {
      const result = {};
      for (const name of TASK_STATUSES) {
        if ((tasks[name] || []).length > 0) {
          result[name] = tasks[name];
        }
      }
      return result;
    }
    // Flatten all tasks from status buckets, then group by field
    const all = TASK_STATUSES.flatMap(function (name) { return tasks[name] || []; });
    const grouped = {};
    for (const item of all) {
      const key = viewKey === "group"
        ? (item.group_title || item.group_id || "(ungrouped)")
        : (item.component || "(ungrouped)");
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(item);
    }
    return grouped;
  }

  function renderTaskCard(item) {
    const taskId = item.id || "";
    const card = document.createElement("div");
    card.className = "task-item";
    card.style.cursor = "pointer";

    card.dataset.taskId = taskId;

    const title = document.createElement("div");
    title.className = "task-item-title";
    title.textContent = (taskId.slice(0, 8) + " " + (item.subject || "")).trim();
    title.title = taskId;
    card.appendChild(title);

    if (item.assignee_name || item.assignee) {
      const assignee = document.createElement("div");
      assignee.className = "task-assignee";
      assignee.textContent = item.assignee_name || item.assignee;
      card.appendChild(assignee);
    }

    // Show fail_reason for failed tasks
    if (item.fail_reason) {
      const failRow = document.createElement("div");
      failRow.className = "task-fail-reason";
      failRow.textContent = item.fail_reason;
      card.appendChild(failRow);
    }

    const detail = document.createElement("div");
    detail.className = "task-item-detail";

    // Description rendered as markdown
    const descBody = item.description || "";
    if (descBody && descBody !== "-") {
      const descRow = document.createElement("div");
      descRow.className = "task-detail-row task-detail-desc";
      const descLabel = document.createElement("span");
      descLabel.className = "task-detail-label";
      descLabel.textContent = "Description";
      descRow.appendChild(descLabel);
      const descValue = document.createElement("div");
      descValue.className = "task-detail-md";
      renderMarkdown(descValue, descBody);
      descRow.appendChild(descValue);
      detail.appendChild(descRow);
    }

    const fields = [
      ["Priority", "P" + String(item.priority || 3)],
      ["Assignee", item.assignee_name || item.assignee || "-"],
      ["Created by", item.created_by_name || item.created_by || "-"],
      ["Created", item.created_at ? formatTimeShort(item.created_at) : "-"],
      ["Updated", item.updated_at ? formatTimeShort(item.updated_at) : "-"],
    ];
    if (item.group_title) fields.push(["Group", item.group_title]);
    if (item.component) fields.push(["Component", item.component]);
    if (item.milestone) fields.push(["Milestone", item.milestone]);

    for (const [label, value] of fields) {
      const row = document.createElement("div");
      row.className = "task-detail-row";
      const labelEl = document.createElement("span");
      labelEl.className = "task-detail-label";
      labelEl.textContent = label;
      row.appendChild(labelEl);
      const valueEl = document.createElement("span");
      valueEl.textContent = value;
      row.appendChild(valueEl);
      detail.appendChild(row);
    }
    card.appendChild(detail);

    // Restore expand state from previous render
    if (_dashTaskExpandedIds[taskId]) {
      detail.classList.add("expanded");
    }

    card.addEventListener("click", function (e) {
      if (e.target.closest('a, button, input, textarea, select, [role="button"]')) return;
      detail.classList.toggle("expanded");
      _dashTaskExpandedIds[taskId] = detail.classList.contains("expanded");
    });

    return card;
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
    for (const col of ["KEY", "AUTHOR", "TAGS", "UPDATED"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const mem of memories) {
      const tr = document.createElement("tr");
      tr.title = mem.content || "";

      const tdKey = document.createElement("td");
      tdKey.className = "agent-name-cell";
      tdKey.textContent = mem.key;
      tr.appendChild(tdKey);

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
    const banner = document.createElement("div");
    banner.className = "system-tips";

    const icon = document.createElement("span");
    icon.className = "system-tips-icon";
    icon.textContent = "\uD83D\uDCA1";
    banner.appendChild(icon);

    // Pick a random tip
    const tip = tips[Math.floor(Math.random() * tips.length)];

    const text = document.createElement("span");
    text.className = "system-tips-text";
    text.textContent = tip.text || tip;
    banner.appendChild(text);

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
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /** Inline markdown formatting (bold, italic, code, links, strikethrough). */
  function inlineMarkdown(line) {
    // Extract code spans and links first to protect them from bold/italic
    var slots = [];
    var ph = "\x00";
    var result = line
      .replace(/`([^`]+)`/g, function(m) { slots.push("<code>" + m.slice(1, -1) + "</code>"); return ph + (slots.length - 1) + ph; })
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, function(_, text, href) {
        if (/^(https?:|mailto:|#)/i.test(href) && !/^javascript:/i.test(href)) {
          slots.push('<a href="' + href + '" target="_blank" rel="noopener">' + text + '</a>');
        } else {
          slots.push(text);
        }
        return ph + (slots.length - 1) + ph;
      });
    // Apply bold/italic/strikethrough on remaining text
    result = result
      .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/~~(.+?)~~/g, "<del>$1</del>");
    // Restore protected slots
    return result.replace(new RegExp(ph + "(\\d+)" + ph, "g"), function(_, idx) { return slots[parseInt(idx, 10)]; });
  }

  /** Line-based markdown parser with block-level element support. */
  function simpleMarkdown(text) {
    var lines = text.split("\n");
    var out = [];
    var i = 0;

    while (i < lines.length) {
      var line = lines[i];

      // Code block
      if (/^```/.test(line)) {
        var lang = (line.match(/^```(\w*)/) || [])[1] || "";
        var codeLines = [];
        i++;
        while (i < lines.length && !/^```$/.test(lines[i])) {
          codeLines.push(lines[i]);
          i++;
        }
        i++; // skip closing ```
        out.push('<pre><code class="language-' + lang + '">' + escapeHtml(codeLines.join("\n")) + "</code></pre>");
        continue;
      }

      // Table: detect header row (| ... | ... |)
      if (/^\|(.+\|)+\s*$/.test(line) && i + 1 < lines.length && /^\|[\s:]*-+/.test(lines[i + 1])) {
        var headers = line.split("|").filter(function(c) { return c.trim() !== ""; });
        // Parse alignment from separator row
        var sepCells = lines[i + 1].split("|").filter(function(c) { return c.trim() !== ""; });
        var aligns = sepCells.map(function(c) {
          var t = c.trim();
          if (t.charAt(0) === ":" && t.charAt(t.length - 1) === ":") return "center";
          if (t.charAt(t.length - 1) === ":") return "right";
          return "left";
        });
        var tableHtml = "<table><thead><tr>";
        for (var h = 0; h < headers.length; h++) {
          tableHtml += '<th style="text-align:' + (aligns[h] || "left") + '">' + inlineMarkdown(escapeHtml(headers[h].trim())) + "</th>";
        }
        tableHtml += "</tr></thead><tbody>";
        i += 2; // skip header + separator
        while (i < lines.length && /^\|(.+\|)+\s*$/.test(lines[i])) {
          var cells = lines[i].split("|").filter(function(c) { return c.trim() !== ""; });
          tableHtml += "<tr>";
          for (var c = 0; c < cells.length; c++) {
            tableHtml += '<td style="text-align:' + (aligns[c] || "left") + '">' + inlineMarkdown(escapeHtml(cells[c].trim())) + "</td>";
          }
          tableHtml += "</tr>";
          i++;
        }
        tableHtml += "</tbody></table>";
        out.push(tableHtml);
        continue;
      }

      var escaped = escapeHtml(line);

      // Horizontal rule
      if (/^-{3,}\s*$/.test(line) || /^\*{3,}\s*$/.test(line)) {
        out.push("<hr>");
        i++;
        continue;
      }

      // Headings
      if (/^### /.test(line)) { out.push("<h4>" + inlineMarkdown(escaped.slice(4)) + "</h4>"); i++; continue; }
      if (/^## /.test(line)) { out.push("<h3>" + inlineMarkdown(escaped.slice(3)) + "</h3>"); i++; continue; }
      if (/^# /.test(line)) { out.push("<h2>" + inlineMarkdown(escaped.slice(2)) + "</h2>"); i++; continue; }

      // Blockquote (consecutive > lines)
      if (/^> /.test(line)) {
        var bqLines = [];
        while (i < lines.length && /^> /.test(lines[i])) {
          bqLines.push(lines[i].slice(2));
          i++;
        }
        out.push("<blockquote>" + bqLines.map(function(l) { return inlineMarkdown(escapeHtml(l)); }).join("<br>") + "</blockquote>");
        continue;
      }

      // List (unordered or ordered, with nesting support)
      if (/^\s*([-*] |\d+\. )/.test(line)) {
        var stack = []; // [{type: "ul"|"ol", indent: number}]
        while (i < lines.length) {
          var lm = lines[i].match(/^(\s*)([-*] |\d+\. )(.*)/);
          if (!lm) break;
          var indent = lm[1].length;
          var listType = /^\d/.test(lm[2]) ? "ol" : "ul";
          var content = lm[3];
          if (stack.length === 0) {
            out.push("<" + listType + ">");
            stack.push({ type: listType, indent: indent });
          } else if (indent > stack[stack.length - 1].indent) {
            out.push("<" + listType + ">");
            stack.push({ type: listType, indent: indent });
          } else {
            while (stack.length > 1 && indent < stack[stack.length - 1].indent) {
              out.push("</li></" + stack.pop().type + ">");
            }
            if (stack.length > 0 && stack[stack.length - 1].type !== listType && indent === stack[stack.length - 1].indent) {
              out.push("</li></" + stack.pop().type + ">");
              out.push("<" + listType + ">");
              stack.push({ type: listType, indent: indent });
            } else {
              out.push("</li>");
            }
          }
          out.push("<li>" + inlineMarkdown(escapeHtml(content)));
          i++;
        }
        while (stack.length > 0) {
          out.push("</li></" + stack.pop().type + ">");
        }
        continue;
      }

      // Empty line → paragraph break
      if (line.trim() === "") {
        out.push("");
        i++;
        continue;
      }

      // Regular paragraph
      out.push("<p>" + inlineMarkdown(escaped) + "</p>");
      i++;
    }

    return out.join("\n");
  }

  // ----------------------------------------------------------------
  // Helpers
  // ----------------------------------------------------------------
  function formatTime(ts) {
    if (!ts) return "";
    try {
      const d = new Date(ts + "Z"); // UTC
      return d.toLocaleString();
    } catch {
      return ts;
    }
  }

  // ----------------------------------------------------------------
  // Toast Notifications
  // ----------------------------------------------------------------
  // Toast batching — collect messages within a short window and show one summary
  const _toastQueue = [];
  let _toastTimer = 0;
  const TOAST_BATCH_MS = 300;

  function showToast(title, agentLabel) {
    _toastQueue.push({ title: title || "Card updated", agent: agentLabel });
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(_flushToasts, TOAST_BATCH_MS);
  }

  function _flushToasts() {
    const batch = _toastQueue.splice(0);
    if (batch.length === 0) return;

    const toast = document.createElement("div");
    toast.className = "toast";

    if (batch.length === 1) {
      const titleEl = document.createElement("div");
      titleEl.className = "toast-title";
      titleEl.textContent = batch[0].title;
      toast.appendChild(titleEl);
      if (batch[0].agent) {
        const agentEl = document.createElement("div");
        agentEl.className = "toast-agent";
        agentEl.textContent = batch[0].agent;
        toast.appendChild(agentEl);
      }
    } else {
      const titleEl = document.createElement("div");
      titleEl.className = "toast-title";
      titleEl.textContent = batch.length + " cards updated";
      toast.appendChild(titleEl);
      const agents = new Set(batch.map((b) => b.agent).filter(Boolean));
      if (agents.size > 0) {
        const agentEl = document.createElement("div");
        agentEl.className = "toast-agent";
        agentEl.textContent = Array.from(agents).join(", ");
        toast.appendChild(agentEl);
      }
    }

    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }

  // ----------------------------------------------------------------
  // Theme Toggle
  // ----------------------------------------------------------------
  function setThemeLabel(theme) {
    var icon = theme === "dark" ? "ph-sun" : "ph-moon";
    var label = theme === "dark" ? "Light" : "Dark";
    themeToggle.innerHTML = '<i class="ph ' + icon + '"></i><span>' + label + '</span>';
  }

  function initTheme() {
    const saved = localStorage.getItem("canvas-theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    setThemeLabel(saved);
    initMermaidTheme(saved);
  }

  /** Rebuild all mermaid diagrams from stored source with current theme. */
  function reRenderMermaid() {
    if (typeof mermaid === "undefined") return;
    document.querySelectorAll("[data-mermaid-source]").forEach(function (el) {
      if (!el.parentNode) return;
      var src = el.dataset.mermaidSource;
      var pre = document.createElement("pre");
      pre.className = "mermaid-pending mermaid";
      pre.textContent = src;
      pre.dataset.mermaidSource = src;
      el.parentNode.replaceChild(pre, el);
    });
    runMermaid(".mermaid-pending");
  }

  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("canvas-theme", next);
    setThemeLabel(next);
    initMermaidTheme(next);
    reRenderMermaid();
    broadcastThemeToIframes(next);
  });

  function statusIcon(state) {
    switch (state) {
      case "success":
        return "●";
      case "warn":
        return "▲";
      case "error":
        return "✕";
      case "running":
        return "◌";
      default:
        return "•";
    }
  }

  function statusColor(status) {
    switch (String(status || "").toLowerCase()) {
      case "ready":
        return "var(--color-success)";
      case "waiting":
        return "var(--color-accent)";
      case "processing":
        return "var(--color-warning)";
      case "done":
        return "var(--color-signal)";
      case "shutting_down":
        return "var(--color-danger)";
      case "success":
      case "completed":
        return "var(--color-success)";
      case "running":
      case "in_progress":
        return "var(--color-accent)";
      case "pending":
      case "warn":
        return "var(--color-warning)";
      case "error":
      case "failed":
        return "var(--color-danger)";
      default:
        return "var(--color-text-muted)";
    }
  }

  // ----------------------------------------------------------------
  // Router
  // ----------------------------------------------------------------
  function getRoute() {
    const hash = location.hash || "#/";
    if (hash === "#/dashboard") return "dashboard";
    if (hash === "#/history") return "history";
    if (hash === "#/system") return "system";
    if (hash === "#/workflow") return "workflow";
    if (hash === "#/admin") return "admin";
    return "canvas";
  }

  // Sidebar toggle (mobile)
  function openSidebar() {
    sidebar.classList.add("open");
    sidebarOverlay.classList.add("active");
  }
  function closeSidebar() {
    sidebar.classList.remove("open");
    sidebarOverlay.classList.remove("active");
  }

  if (sidebarToggle) sidebarToggle.addEventListener("click", openSidebar);
  if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeSidebar);

  // Sidebar collapse/expand (desktop only)
  function syncCollapseLabel(collapsed) {
    if (!sidebarCollapseBtn) return;
    var label = collapsed ? "Expand sidebar" : "Collapse sidebar";
    sidebarCollapseBtn.title = label;
    sidebarCollapseBtn.setAttribute("aria-label", label);
  }
  function toggleSidebarCollapse() {
    if (window.innerWidth <= 768) return;
    document.body.classList.toggle("sidebar-collapsed");
    var collapsed = document.body.classList.contains("sidebar-collapsed");
    syncCollapseLabel(collapsed);
    try { localStorage.setItem("canvas-sidebar", collapsed ? "collapsed" : "expanded"); } catch (e) { /* ignore */ }
  }
  // Restore saved sidebar state (desktop only)
  try {
    if (localStorage.getItem("canvas-sidebar") === "collapsed" && window.innerWidth > 768) {
      document.body.classList.add("sidebar-collapsed");
      syncCollapseLabel(true);
    }
  } catch (e) { /* ignore */ }
  if (sidebarCollapseBtn) sidebarCollapseBtn.addEventListener("click", toggleSidebarCollapse);

  // Close sidebar on nav link click (mobile)
  navLinks.forEach(function (link) {
    link.addEventListener("click", closeSidebar);
  });

  function navigate() {
    currentRoute = getRoute();

    // Update nav links — Canvas parent stays active when History sub-route is shown
    navLinks.forEach(link => {
      var isActive = link.dataset.route === currentRoute;
      if (link.dataset.route === "canvas" && currentRoute === "history") isActive = true;
      link.classList.toggle("active", isActive);
    });

    // Update topbar title
    if (topbarTitle) topbarTitle.textContent = ROUTE_LABELS[currentRoute] || "Canvas";

    // Close sidebar on mobile after navigation
    closeSidebar();

    // Hide all views, then show active
    canvasView.classList.add("view-hidden");
    if (dashboardView) dashboardView.classList.add("view-hidden");
    historyView.classList.add("view-hidden");
    systemView.classList.add("view-hidden");
    if (workflowView) workflowView.classList.add("view-hidden");
    if (adminView) adminView.classList.add("view-hidden");

    _dashboardRendered = false;
    _systemPanelRendered = false;

    // Clean up workflow polling timer when leaving workflow view
    if (currentRoute !== "workflow" && _workflowRunPollingTimer) {
      clearInterval(_workflowRunPollingTimer);
      _workflowRunPollingTimer = 0;
    }

    if (currentRoute === "canvas") {
      canvasView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      renderSpotlight();
    } else if (currentRoute === "dashboard") {
      if (dashboardView) dashboardView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      if (_lastSystemData) renderDashboard(_lastSystemData);
      loadSystemPanel();
    } else if (currentRoute === "system") {
      systemView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      if (_lastSystemData) renderSystemPanel(_lastSystemData);
    } else if (currentRoute === "workflow") {
      if (workflowView) workflowView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      loadWorkflows();
    } else if (currentRoute === "admin") {
      if (adminView) adminView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      loadAdminAgents();
    } else {
      historyView.classList.remove("view-hidden");
      filterBar.style.display = "";
      renderAll();
    }
  }

  // ----------------------------------------------------------------
  // Canvas View — full-viewport projection of latest card
  // ----------------------------------------------------------------
  function renderSpotlight() {
    if (!canvasSpotlight) return;

    const allCards = [...cards.values()];
    if (allCards.length === 0) {
      // Empty state
      const empty = document.createElement("div");
      empty.className = "canvas-empty";
      const icon = document.createElement("div");
      icon.className = "canvas-empty-icon";
      icon.textContent = "\u25EF"; // ◯
      empty.appendChild(icon);
      const text = document.createElement("div");
      text.className = "canvas-empty-text";
      text.textContent = "Canvas is ready";
      empty.appendChild(text);
      const sub = document.createElement("div");
      sub.className = "canvas-empty-sub";
      sub.textContent = "Waiting for agent messages\u2026";
      empty.appendChild(sub);
      syncChildren(canvasSpotlight, [empty]);
      canvasView.style.removeProperty("--canvas-glow");
      _spotlightCardId = "";
      _spotlightUpdatedAt = "";
      return;
    }

    // Find the most recently updated card (O(n) instead of sorting)
    const card = allCards.reduce((latest, c) =>
      (c.updated_at || "") > (latest.updated_at || "") ? c : latest
    );

    const previousCardId = _spotlightCardId;
    const isSameCard = card.card_id === previousCardId;

    // Skip rebuild if the same card version is already displayed
    if (isSameCard && card.updated_at === _spotlightUpdatedAt) {
      return;
    }

    const agentInfo = systemAgents.find(a => a.agent_id === card.agent_id);
    const agentStatus = agentInfo ? agentInfo.status : "";

    // Set ambient glow color based on agent status
    canvasView.style.setProperty("--canvas-glow", statusColor(agentStatus));

    const frame = ensureSpotlightFrame();
    frame.titleText.textContent = card.title || "Untitled";
    renderSpotlightContent(frame.content, card);
    renderSpotlightInfo(frame.infoBar, card, agentStatus);

    if (previousCardId && !isSameCard) {
      markSpotlightSwap();
    }

    _spotlightCardId = card.card_id;
    _spotlightUpdatedAt = card.updated_at;

    // Re-run mermaid
    runMermaid("#canvas-spotlight .mermaid-pending");
  }

  function ensureSpotlightFrame() {
    let titleBar = canvasSpotlight.querySelector(".canvas-title-bar");
    let titleText = titleBar ? titleBar.querySelector(".canvas-title-text") : null;
    if (!titleBar) {
      titleBar = document.createElement("div");
      titleBar.className = "canvas-title-bar";
    }
    if (!titleText) {
      titleText = document.createElement("h2");
      titleText.className = "canvas-title-text";
    }
    let dlBtn = titleBar.querySelector(".canvas-dl-btn");
    if (!dlBtn) {
      dlBtn = createDownloadButton(function () { return _spotlightCardId; });
    }
    syncChildren(titleBar, [titleText, dlBtn]);

    let content = canvasSpotlight.querySelector(".canvas-content");
    if (!content) {
      content = document.createElement("div");
      content.className = "canvas-content";
    }

    let infoBar = canvasSpotlight.querySelector(".canvas-info-bar");
    if (!infoBar) {
      infoBar = document.createElement("div");
      infoBar.className = "canvas-info-bar";
    }

    syncChildren(canvasSpotlight, [titleBar, content, infoBar]);
    return { titleBar, titleText, content, infoBar };
  }

  function renderSpotlightContent(content, card) {
    content.innerHTML = "";
    const parsed = parseContent(card.content);
    const blocks = Array.isArray(parsed) ? parsed : [parsed];

    if (card.template && card.template_data) {
      const td =
        typeof card.template_data === "string"
          ? JSON.parse(card.template_data)
          : card.template_data;
      const rendered = renderTemplate(
        card.template,
        blocks,
        td,
        false,
        { inCanvasView: true }
      );
      if (rendered) {
        content.appendChild(rendered);
      } else {
        for (const block of blocks) {
          content.appendChild(renderBlock(block, { inCanvasView: true }));
        }
      }
    } else {
      for (const block of blocks) {
        content.appendChild(renderBlock(block, { inCanvasView: true }));
      }
    }
  }

  function renderSpotlightInfo(infoBar, card, agentStatus) {
    infoBar.innerHTML = "";

    const dot = document.createElement("span");
    dot.className = "canvas-info-dot";
    const dotColor = statusColor(agentStatus);
    dot.style.background = dotColor;
    dot.style.color = dotColor;
    infoBar.appendChild(dot);

    const agentName = document.createElement("span");
    agentName.className = "canvas-info-agent";
    agentName.textContent = card.agent_name || card.agent_id;
    infoBar.appendChild(agentName);

    const idEl = document.createElement("span");
    idEl.className = "canvas-info-id";
    idEl.textContent = card.agent_id;
    infoBar.appendChild(idEl);

    if (card.tags) {
      try {
        const tags = typeof card.tags === "string" ? JSON.parse(card.tags) : card.tags;
        if (Array.isArray(tags) && tags.length > 0) {
          const divider = document.createElement("span");
          divider.className = "canvas-info-divider";
          infoBar.appendChild(divider);
          const tagWrap = document.createElement("div");
          tagWrap.className = "canvas-info-tags";
          for (const t of tags) {
            const chip = document.createElement("span");
            chip.className = "tag-chip";
            chip.textContent = t;
            tagWrap.appendChild(chip);
          }
          infoBar.appendChild(tagWrap);
        }
      } catch { /* ignore */ }
    }

    const time = document.createElement("span");
    time.className = "canvas-info-time";
    time.textContent = formatTime(card.updated_at);
    infoBar.appendChild(time);

    const cardId = document.createElement("span");
    cardId.className = "canvas-info-card-id";
    cardId.textContent = card.card_id;
    infoBar.appendChild(cardId);
  }

  function markSpotlightSwap() {
    canvasSpotlight.classList.remove("spotlight-swap");
    void canvasSpotlight.offsetWidth;
    canvasSpotlight.classList.add("spotlight-swap");
    if (_spotlightSwapTimer) {
      window.clearTimeout(_spotlightSwapTimer);
    }
    _spotlightSwapTimer = window.setTimeout(() => {
      canvasSpotlight.classList.remove("spotlight-swap");
      _spotlightSwapTimer = 0;
    }, SPOTLIGHT_SWAP_DELAY);
  }

  // ----------------------------------------------------------------
  // Workflow View
  // ----------------------------------------------------------------
  var _workflowRunPollingTimer = 0;

  async function loadWorkflows() {
    try {
      var resp = await fetch("/api/workflow");
      var data = await resp.json();
      _workflowData = data.workflows || [];
      renderWorkflowList(_workflowData);
      loadWorkflowRuns();
    } catch (e) { /* ignore */ }
  }

  async function loadWorkflowRuns() {
    try {
      var resp = await fetch("/api/workflow/runs");
      var data = await resp.json();
      _workflowRuns = data.runs || [];
      if (_selectedWorkflow) renderWorkflowDetail(_selectedWorkflow);
    } catch (e) { /* ignore */ }
  }

  function renderWorkflowList(workflows) {
    if (!workflowListPanel) return;
    var existingWrap = workflowListPanel.querySelector(".workflow-list-table-wrap");
    if (existingWrap) existingWrap.remove();

    var wrap = document.createElement("div");
    wrap.className = "workflow-list-table-wrap";

    if (!workflows.length) {
      wrap.innerHTML = '<div class="workflow-empty">No workflows defined</div>';
      workflowListPanel.appendChild(wrap);
      return;
    }

    var table = document.createElement("table");
    table.className = "system-agents-table";
    var thead = document.createElement("thead");
    thead.innerHTML = "<tr><th>Name</th><th>Steps</th><th>Scope</th><th>Description</th></tr>";
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    workflows.forEach(function (wf) {
      var tr = document.createElement("tr");
      tr.style.cursor = "pointer";
      if (_selectedWorkflow && _selectedWorkflow.name === wf.name) {
        tr.classList.add("workflow-row-selected");
      }
      tr.innerHTML =
        "<td>" + escapeHtml(wf.name) + "</td>" +
        "<td>" + wf.step_count + "</td>" +
        "<td>" + escapeHtml(wf.scope) + "</td>" +
        "<td>" + escapeHtml(wf.description || "") + "</td>";
      tr.addEventListener("click", function () {
        _selectedWorkflow = wf;
        renderWorkflowList(workflows);
        renderWorkflowDetail(wf);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    workflowListPanel.appendChild(wrap);
  }

  function renderWorkflowDetail(wf) {
    if (!workflowDetailContent || !workflowDetailEmpty) return;
    workflowDetailEmpty.classList.add("view-hidden");
    workflowDetailContent.classList.remove("view-hidden");
    workflowDetailContent.innerHTML = "";

    // Header
    var header = document.createElement("div");
    header.style.marginBottom = "var(--sp-3)";
    header.innerHTML =
      "<h3 style='margin:0 0 var(--sp-1) 0;'>" + escapeHtml(wf.name) + "</h3>" +
      (wf.description ? "<p style='margin:0; color:var(--color-text-muted); font-size:var(--text-sm);'>" + escapeHtml(wf.description) + "</p>" : "");
    workflowDetailContent.appendChild(header);

    // Mermaid DAG
    if (wf.steps && wf.steps.length > 1) {
      var mermaidSrc = "graph TD\n";
      wf.steps.forEach(function (s, i) {
        mermaidSrc += '  S' + i + '["' + (i + 1) + ". " + escapeHtml(s.target) + '"]\n';
        if (i > 0) mermaidSrc += "  S" + (i - 1) + " --> S" + i + "\n";
      });
      var flowDiv = document.createElement("div");
      flowDiv.className = "workflow-step-flow";
      var mermaidDiv = document.createElement("pre");
      mermaidDiv.className = "mermaid-pending mermaid";
      mermaidDiv.dataset.mermaidSource = mermaidSrc;
      mermaidDiv.textContent = mermaidSrc;
      flowDiv.appendChild(mermaidDiv);
      workflowDetailContent.appendChild(flowDiv);
      runMermaid(".workflow-step-flow .mermaid-pending");
    }

    // Steps with status
    var activeRun = _workflowRuns.find(function (r) { return r.workflow_name === wf.name; });
    var stepsDiv = document.createElement("div");
    (wf.steps || []).forEach(function (s, i) {
      var stepStatus = "pending";
      var stepIcon = "\u23f3"; // ⏳
      if (activeRun && activeRun.steps[i]) {
        stepStatus = activeRun.steps[i].status;
        if (stepStatus === "running") stepIcon = "\ud83d\udd04"; // 🔄
        else if (stepStatus === "completed") stepIcon = "\u2705"; // ✅
        else if (stepStatus === "failed") stepIcon = "\u274c"; // ❌
      }
      var item = document.createElement("div");
      item.className = "workflow-step-item";
      item.innerHTML =
        '<span class="workflow-step-icon">' + stepIcon + "</span>" +
        '<span class="workflow-step-target">' + escapeHtml(s.target) + "</span>" +
        '<span class="workflow-step-message">' + escapeHtml(s.message) + "</span>" +
        '<span class="workflow-step-mode">' + escapeHtml(s.response_mode || "notify") + "</span>";
      stepsDiv.appendChild(item);
    });
    workflowDetailContent.appendChild(stepsDiv);

    // Run button
    var isRunning = activeRun && activeRun.status === "running";
    var runBtn = document.createElement("button");
    runBtn.className = "workflow-run-btn";
    runBtn.disabled = isRunning;
    runBtn.innerHTML = isRunning
      ? '<i class="ph ph-spinner"></i> Running...'
      : '<i class="ph ph-play"></i> Run';
    runBtn.addEventListener("click", function () {
      runWorkflow(wf.name);
    });
    workflowDetailContent.appendChild(runBtn);

    // Run history
    var relatedRuns = _workflowRuns.filter(function (r) { return r.workflow_name === wf.name; });
    if (relatedRuns.length > 0) {
      var histDiv = document.createElement("div");
      histDiv.className = "workflow-run-history";
      histDiv.innerHTML = '<div style="font-size:var(--text-xs); color:var(--color-muted); margin-bottom:var(--sp-1);">Recent runs</div>';
      relatedRuns.slice(0, 10).forEach(function (r) {
        var item = document.createElement("div");
        item.className = "workflow-run-item";
        var statusIcon = r.status === "completed" ? "\u2705" : r.status === "failed" ? "\u274c" : "\ud83d\udd04";
        var startTime = r.started_at ? new Date(r.started_at * 1000).toLocaleTimeString() : "";
        var duration = r.completed_at && r.started_at ? Math.round(r.completed_at - r.started_at) + "s" : "...";
        item.textContent = statusIcon + " " + startTime + " (" + duration + ")";
        histDiv.appendChild(item);
      });
      workflowDetailContent.appendChild(histDiv);
    }
  }

  async function runWorkflow(name) {
    try {
      var resp = await fetch("/api/workflow/run/" + encodeURIComponent(name), { method: "POST" });
      var data = await resp.json();
      if (data.run_id) {
        // Start polling for updates
        clearInterval(_workflowRunPollingTimer);
        _workflowRunPollingTimer = setInterval(function () {
          loadWorkflowRuns().then(function () {
            var run = _workflowRuns.find(function (r) { return r.run_id === data.run_id; });
            if (run && run.status !== "running") {
              clearInterval(_workflowRunPollingTimer);
              _workflowRunPollingTimer = 0;
            }
          });
        }, 2000);
        loadWorkflowRuns();
      }
    } catch (e) { /* ignore */ }
  }

  // ----------------------------------------------------------------
  // Admin View — Command Center
  // ----------------------------------------------------------------
  let _adminPollingTimers = [];

  async function loadAdminAgents() {
    try {
      const resp = await fetch("/api/admin/agents");
      const data = await resp.json();
      const agents = data.agents || [];
      renderAdminAgentsWidget(agents);
    } catch (e) {
      console.error("Failed to load admin agents:", e);
    }
  }

  function renderAdminAgentsWidget(agents) {
    if (!adminAgentsWidget) return;
    // Preserve the h3 title, remove only the table wrapper
    var existingWrap = adminAgentsWidget.querySelector(".admin-agents-table-wrap");
    if (existingWrap) existingWrap.remove();

    var content = renderSystemAgents(agents, {
      selectedId: _selectedAdminTarget,
      onRowClick: function(agent) {
        _selectedAdminTarget = agent.agent_id;
        _selectedAdminName = agent.name || agent.agent_id;
        if (adminTargetBadge) {
          adminTargetBadge.textContent = _selectedAdminName;
          adminTargetBadge.classList.add("has-target");
        }
        if (adminMessageInput) adminMessageInput.focus();
      },
      onRowDblClick: function(agent) {
        jumpToAgent(agent.agent_id);
      },
      onRowContextMenu: function(agent, e) {
        showAgentContextMenu(agent, e);
      }
    });
    content.className = "admin-agents-table-wrap";
    adminAgentsWidget.appendChild(content);
  }

  // ── Agent Context Menu ──────────────────────────
  var _agentContextMenu = null;
  var _contextMenuTarget = null;

  function createAgentContextMenu() {
    var menu = document.createElement("div");
    menu.className = "agent-context-menu";

    var killItem = document.createElement("div");
    killItem.className = "agent-context-menu-item danger";
    var icon = document.createElement("i");
    icon.className = "ph ph-trash";
    killItem.appendChild(icon);
    killItem.appendChild(document.createTextNode(" Kill Agent"));
    killItem.addEventListener("click", function(e) {
      e.stopPropagation();
      var target = _contextMenuTarget;
      hideAgentContextMenu();
      if (target) killAgent(target);
    });
    menu.appendChild(killItem);

    document.body.appendChild(menu);
    return menu;
  }

  function showAgentContextMenu(agent, e) {
    e.preventDefault();
    e.stopPropagation();
    if (!_agentContextMenu) _agentContextMenu = createAgentContextMenu();
    _contextMenuTarget = agent;

    var menu = _agentContextMenu;
    menu.style.display = "block";

    // Position with viewport boundary correction
    var menuRect = menu.getBoundingClientRect();
    var x = e.clientX;
    var y = e.clientY;
    if (x + menuRect.width > window.innerWidth) x = window.innerWidth - menuRect.width - 8;
    if (y + menuRect.height > window.innerHeight) y = window.innerHeight - menuRect.height - 8;
    if (x < 0) x = 8;
    if (y < 0) y = 8;
    menu.style.left = x + "px";
    menu.style.top = y + "px";
  }

  function hideAgentContextMenu() {
    if (!_agentContextMenu || _agentContextMenu.style.display === "none") return;
    _agentContextMenu.style.display = "none";
    _contextMenuTarget = null;
  }

  // Dismiss context menu on click-away, scroll, resize, Escape
  document.addEventListener("click", function() { hideAgentContextMenu(); });
  document.addEventListener("contextmenu", function() { hideAgentContextMenu(); });
  window.addEventListener("scroll", function() { hideAgentContextMenu(); }, true);
  window.addEventListener("resize", function() { hideAgentContextMenu(); });
  document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") hideAgentContextMenu();
  });

  // ── Confirm Modal ──────────────────────────────
  function showConfirmModal(options) {
    // options: { title, body, confirmLabel, cancelLabel, danger, onConfirm, onCancel }
    var overlay = document.createElement("div");
    overlay.className = "confirm-modal-overlay";

    var modal = document.createElement("div");
    modal.className = "confirm-modal";

    var title = document.createElement("div");
    title.className = "confirm-modal-title" + (options.danger ? " danger" : "");
    if (options.icon) {
      var icon = document.createElement("i");
      icon.className = options.icon;
      title.appendChild(icon);
    }
    title.appendChild(document.createTextNode(options.title || "Confirm"));
    modal.appendChild(title);

    var body = document.createElement("div");
    body.className = "confirm-modal-body";
    body.textContent = options.body || "";
    modal.appendChild(body);

    var actions = document.createElement("div");
    actions.className = "confirm-modal-actions";

    var cancelBtn = document.createElement("button");
    cancelBtn.className = "confirm-modal-btn cancel";
    cancelBtn.textContent = options.cancelLabel || "Cancel";

    var confirmBtn = document.createElement("button");
    confirmBtn.className = "confirm-modal-btn" + (options.danger ? " danger" : "");
    confirmBtn.textContent = options.confirmLabel || "OK";

    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);
    modal.appendChild(actions);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    function close() {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
    }
    function onKey(e) {
      if (e.key === "Escape") { e.stopImmediatePropagation(); close(); if (options.onCancel) options.onCancel(); }
    }
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", function(e) {
      if (e.target === overlay) { close(); if (options.onCancel) options.onCancel(); }
    });
    cancelBtn.addEventListener("click", function() { close(); if (options.onCancel) options.onCancel(); });
    confirmBtn.addEventListener("click", function() { close(); if (options.onConfirm) options.onConfirm(); });

    confirmBtn.focus();
  }

  function killAgent(agent) {
    var agentLabel = agent.name || agent.agent_id;
    showConfirmModal({
      title: "Kill Agent",
      body: "Are you sure you want to kill \"" + agentLabel + "\"? This will send SIGTERM to the agent process.",
      confirmLabel: "Kill",
      cancelLabel: "Cancel",
      danger: true,
      icon: "ph ph-trash",
      onConfirm: function() { executeKillAgent(agent); }
    });
  }

  function executeKillAgent(agent) {
    fetch("/api/admin/agents/" + encodeURIComponent(agent.agent_id), { method: "DELETE" })
      .then(function(resp) { return resp.json(); })
      .then(function(data) {
        if (data.status === "stopped") {
          showToast("Agent killed", agent.name || agent.agent_id);
          if (_selectedAdminTarget === agent.agent_id) {
            _selectedAdminTarget = null;
            _selectedAdminName = null;
            if (adminTargetBadge) {
              adminTargetBadge.textContent = "";
              adminTargetBadge.classList.remove("has-target");
            }
          }
          loadAdminAgents();
        } else {
          showToast("Kill failed: " + (data.status || data.error || "unknown"), agent.name || agent.agent_id);
        }
      })
      .catch(function() {
        showToast("Kill failed: network error", agent.name || agent.agent_id);
      });
  }

  function jumpToAgent(agentId) {
    fetch("/api/admin/jump/" + encodeURIComponent(agentId), { method: "POST" })
      .then(function(resp) { return resp.json(); })
      .then(function(data) {
        if (data.ok) {
          showToast("Jumped to terminal", agentId);
        } else {
          showToast("Jump failed: " + (data.error || "unknown"), agentId);
        }
      })
      .catch(function() {
        showToast("Jump failed: network error", agentId);
      });
  }

  function createAdminBubble(role, text, agentName) {
    var bubble = document.createElement("div");
    bubble.className = "admin-bubble admin-bubble-" + role;
    var header = document.createElement("div");
    header.className = "admin-bubble-header";
    var headerName = document.createElement("span");
    headerName.textContent = role === "user" ? "You" : (agentName || "Agent");
    header.appendChild(headerName);
    var time = document.createElement("span");
    time.className = "admin-bubble-time";
    time.textContent = new Date().toLocaleTimeString();
    header.appendChild(time);
    bubble.appendChild(header);
    var body = document.createElement("div");
    body.className = "admin-bubble-body";
    body.textContent = text;
    bubble.appendChild(body);
    bubble._adminBody = body;
    return bubble;
  }

  function addAdminBubble(role, text, agentName) {
    if (!adminFeed) return;
    var bubble = createAdminBubble(role, text, agentName);
    adminFeed.appendChild(bubble);
    adminFeed.scrollTop = adminFeed.scrollHeight;
  }

  function addAdminSpinner() {
    if (!adminFeed) return;
    var spinner = document.createElement("div");
    spinner.className = "admin-spinner";
    spinner.id = "admin-active-spinner";
    spinner.innerHTML = '<span class="admin-spinner-dot"></span> Waiting for response...';
    adminFeed.appendChild(spinner);
    adminFeed.scrollTop = adminFeed.scrollHeight;
    return spinner;
  }

  function removeAdminSpinner() {
    var el = document.getElementById("admin-active-spinner");
    if (el) el.remove();
  }

  let _adminSending = false;

  async function sendAdminCommand() {
    if (_adminSending) return;
    if (!adminMessageInput) return;
    var target = _selectedAdminTarget;
    var message = adminMessageInput.value.trim();
    if (!target || !message) return;

    _adminSending = true;
    if (adminSendBtn) adminSendBtn.disabled = true;

    var agentName = _selectedAdminName || target;

    // Clear input immediately
    adminMessageInput.value = "";
    adminMessageInput.style.height = "auto";

    addAdminBubble("user", message, null);
    addAdminSpinner();

    try {
      var resp = await fetch("/api/admin/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: target, message: message }),
      });
      var data = await resp.json();
      if (!resp.ok) {
        removeAdminSpinner();
        addAdminBubble("agent", "Error: " + (data.detail || "Failed to send"), agentName);
        return;
      }
      pollAdminTask(data.task_id, target, agentName);
    } catch (e) {
      removeAdminSpinner();
      addAdminBubble("agent", "Error: " + e.message, agentName);
    } finally {
      _adminSending = false;
      if (adminSendBtn) adminSendBtn.disabled = false;
    }
  }

  function pollAdminTask(taskId, target, agentName) {
    var attempts = 0;
    var maxAttempts = 150;
    var polling = true;

    async function poll() {
      if (!polling) return;
      attempts++;
      if (attempts > maxAttempts) {
        polling = false;
        removeAdminSpinner();
        addAdminBubble("agent", "Timeout: No response after 5 minutes", agentName);
        return;
      }
      try {
        var resp = await fetch("/api/admin/replies/" + encodeURIComponent(taskId));
        var data = await resp.json();
        if (data.status === "completed" || data.status === "DONE") {
          polling = false;
          removeAdminSpinner();
          var output = data.output || "Task completed";
          addAdminBubble("agent", output, agentName);
          return;
        } else if (data.status === "failed" || data.status === "error") {
          polling = false;
          removeAdminSpinner();
          addAdminBubble("agent", "Failed: " + (data.error || "Unknown error"), agentName);
          return;
        }
      } catch (e) {
        console.warn("[Admin] Poll error:", e);
      }
      // Adaptive interval: 1s for first 10, then 2s
      var delay = attempts < 10 ? 1000 : 2000;
      setTimeout(poll, delay);
    }

    // Start first poll quickly
    setTimeout(poll, 500);
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ----------------------------------------------------------------
  // Init
  // ----------------------------------------------------------------
  filterType.addEventListener("change", renderAll);
  filterAgent.addEventListener("change", renderAll);
  window.addEventListener("hashchange", navigate);
  if (adminSendBtn) adminSendBtn.addEventListener("click", sendAdminCommand);
  var _isComposing = false;
  function autoResizeAdminInput() {
    if (!adminMessageInput) return;
    adminMessageInput.style.height = "auto";
    adminMessageInput.style.height = Math.min(adminMessageInput.scrollHeight, 120) + "px";
  }
  if (adminMessageInput) {
    adminMessageInput.addEventListener("compositionstart", function() { _isComposing = true; });
    adminMessageInput.addEventListener("compositionend", function() { _isComposing = false; });
    adminMessageInput.addEventListener("input", autoResizeAdminInput);
    adminMessageInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && e.metaKey && !_isComposing) { e.preventDefault(); sendAdminCommand(); }
    });
  }

  /** Mermaid theme config keyed by canvas theme. */
  var MERMAID_THEMES = {
    dark: {
      theme: "base",
      themeVariables: {
        darkMode: true,
        background: "#0d1117",
        primaryColor: "#2d333b",
        primaryTextColor: "#e6edf3",
        primaryBorderColor: "#4051b5",
        secondaryColor: "#1c2333",
        secondaryTextColor: "#c9d1d9",
        secondaryBorderColor: "#6775c9",
        tertiaryColor: "#161b22",
        tertiaryTextColor: "#8b949e",
        tertiaryBorderColor: "#30363d",
        lineColor: "#6775c9",
        textColor: "#e6edf3",
        mainBkg: "#1c2333",
        nodeBorder: "#4051b5",
        clusterBkg: "#161b2266",
        clusterBorder: "#30363d",
        titleColor: "#e6edf3",
        edgeLabelBackground: "#0d1117",
        nodeTextColor: "#e6edf3",
        actorTextColor: "#e6edf3",
        actorBorder: "#4051b5",
        actorBkg: "#1c2333",
        actorLineColor: "#6775c9",
        signalColor: "#e6edf3",
        signalTextColor: "#0d1117",
        labelBoxBkgColor: "#1c2333",
        labelBoxBorderColor: "#4051b5",
        labelTextColor: "#e6edf3",
        loopTextColor: "#c9d1d9",
        noteBkgColor: "#2d333b",
        noteTextColor: "#e6edf3",
        noteBorderColor: "#6775c9",
        activationBkgColor: "#2d333b",
        activationBorderColor: "#4051b5",
        sequenceNumberColor: "#ffffff",
        sectionBkgColor: "#1c2333",
        altSectionBkgColor: "#161b22",
        sectionBkgColor2: "#2d333b",
        taskBkgColor: "#4051b5",
        taskTextColor: "#ffffff",
        taskTextLightColor: "#e6edf3",
        taskBorderColor: "#6775c9",
        taskTextOutsideColor: "#c9d1d9",
        activeTaskBkgColor: "#6775c9",
        activeTaskBorderColor: "#8b97db",
        doneTaskBkgColor: "#238636",
        doneTaskBorderColor: "#2ea043",
        critBkgColor: "#da3633",
        critBorderColor: "#f85149",
        todayLineColor: "#58a6ff",
        fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
        fontSize: "13px",
      },
    },
    light: {
      theme: "base",
      themeVariables: {
        darkMode: false,
        background: "#ffffff",
        primaryColor: "#eef0fb",
        primaryTextColor: "#24292f",
        primaryBorderColor: "#4051b5",
        secondaryColor: "#f3eefa",
        secondaryTextColor: "#24292f",
        secondaryBorderColor: "#7c4dff",
        tertiaryColor: "#eef8ee",
        tertiaryTextColor: "#24292f",
        tertiaryBorderColor: "#4caf50",
        lineColor: "#4051b5",
        textColor: "#24292f",
        mainBkg: "#eef0fb",
        nodeBorder: "#4051b5",
        clusterBkg: "#f8f9fc",
        clusterBorder: "#c5cae9",
        titleColor: "#24292f",
        edgeLabelBackground: "#ffffff",
        nodeTextColor: "#24292f",
        actorTextColor: "#24292f",
        actorBorder: "#4051b5",
        actorBkg: "#eef0fb",
        actorLineColor: "#4051b5",
        signalColor: "#24292f",
        signalTextColor: "#ffffff",
        labelBoxBkgColor: "#eef0fb",
        labelBoxBorderColor: "#4051b5",
        labelTextColor: "#24292f",
        loopTextColor: "#57606a",
        noteBkgColor: "#fff8e1",
        noteTextColor: "#24292f",
        noteBorderColor: "#f9a825",
        activationBkgColor: "#eef0fb",
        activationBorderColor: "#4051b5",
        sequenceNumberColor: "#ffffff",
        sectionBkgColor: "#eef0fb",
        altSectionBkgColor: "#f8f9fc",
        sectionBkgColor2: "#dde1f7",
        taskBkgColor: "#4051b5",
        taskTextColor: "#ffffff",
        taskTextLightColor: "#24292f",
        taskBorderColor: "#303f9f",
        taskTextOutsideColor: "#24292f",
        activeTaskBkgColor: "#6775c9",
        activeTaskBorderColor: "#4051b5",
        doneTaskBkgColor: "#c8e6c9",
        doneTaskBorderColor: "#4caf50",
        critBkgColor: "#ffcdd2",
        critBorderColor: "#e53935",
        todayLineColor: "#4051b5",
        fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
        fontSize: "13px",
      },
    },
  };

  function initMermaidTheme(theme) {
    if (typeof mermaid === "undefined") return;
    var config = MERMAID_THEMES[theme] || MERMAID_THEMES.dark;
    mermaid.initialize({
      startOnLoad: false,
      theme: config.theme,
      themeVariables: config.themeVariables,
    });
  }

  if (typeof hljs !== "undefined") {
    hljs.configure({ ignoreUnescapedHTML: true });
  }

  // Listen for resize messages from HTML artifact iframes (dashboard only)
  window.addEventListener("message", function(e) {
    if (!e.data || e.data.type !== "synapse-resize") return;
    var h = e.data.height;
    if (typeof h !== "number" || h <= 0 || h > 10000) return;
    var iframes = document.querySelectorAll(".format-html iframe, .format-artifact iframe");
    for (var i = 0; i < iframes.length; i++) {
      if (iframes[i].contentWindow === e.source) {
        // Skip canvas view iframes — they use CSS flex for sizing
        if (iframes[i].closest(".canvas-content")) break;
        iframes[i].style.height = h + "px";
        break;
      }
    }
  });

  // ── Admin splitter (drag-resize between agents widget and feed) ──
  function initAdminSplitter() {
    if (!adminSplitter || !adminAgentsWidget) return;
    var adminContainer = document.getElementById("admin-container");
    var adminInputBar = document.getElementById("admin-input-bar");
    var storageKey = "canvas-admin-agents-height";
    var minH = 80;

    // Restore saved height
    try {
      var saved = parseInt(localStorage.getItem(storageKey), 10);
      if (isFinite(saved)) {
        adminAgentsWidget.style.height = Math.max(minH, saved) + "px";
        adminAgentsWidget.classList.add("splitter-resized");
      }
    } catch (e) { /* ignore */ }

    var startY = 0;
    var startHeight = 0;

    function getMaxHeight() {
      if (!adminContainer) return 400;
      var inputH = adminInputBar ? adminInputBar.offsetHeight : 0;
      return adminContainer.clientHeight - inputH - adminSplitter.offsetHeight - minH;
    }

    function clamp(v) {
      return Math.max(minH, Math.min(v, getMaxHeight()));
    }

    function onMouseMove(e) {
      var delta = e.clientY - startY;
      var newH = clamp(startHeight + delta);
      adminAgentsWidget.style.height = newH + "px";
    }

    function onMouseUp() {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.classList.remove("splitter-dragging");
      adminSplitter.classList.remove("dragging");
      adminAgentsWidget.classList.add("splitter-resized");
      var h = clamp(parseInt(adminAgentsWidget.style.height, 10));
      if (isFinite(h)) { try { localStorage.setItem(storageKey, h); } catch (e) { /* ignore */ } }
    }

    adminSplitter.addEventListener("mousedown", function (e) {
      e.preventDefault();
      startY = e.clientY;
      startHeight = adminAgentsWidget.offsetHeight;
      document.body.classList.add("splitter-dragging");
      adminSplitter.classList.add("dragging");
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    // Keyboard support
    adminSplitter.addEventListener("keydown", function (e) {
      var step = e.shiftKey ? 20 : 5;
      var current = adminAgentsWidget.offsetHeight;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        adminAgentsWidget.style.height = clamp(current + step) + "px";
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        adminAgentsWidget.style.height = clamp(current - step) + "px";
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        adminAgentsWidget.classList.add("splitter-resized");
        var kh = clamp(parseInt(adminAgentsWidget.style.height, 10));
        if (isFinite(kh)) { try { localStorage.setItem(storageKey, kh); } catch (e2) { /* ignore */ } }
      }
    });
  }

  initTheme();
  loadCards();
  loadSystemPanel();
  connectSSE();
  window.setInterval(loadSystemPanel, 10000);
  initAdminSplitter();

  // Initial route
  navigate();
})();
