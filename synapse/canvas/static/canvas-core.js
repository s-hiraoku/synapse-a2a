window.SynapseCanvas = (function() {
  "use strict";

  const ns = {};

  function renderBlock() { return ns.renderBlock.apply(ns, arguments); }
  function broadcastThemeToIframes() { return ns.broadcastThemeToIframes.apply(ns, arguments); }
  function loadWorkflows() { return ns.loadWorkflows.apply(ns, arguments); }
  function loadPatterns() { return ns.loadPatterns.apply(ns, arguments); }
  function loadDatabaseList() { return ns.loadDatabaseList.apply(ns, arguments); }
  function loadKnowledgeView() { return ns.loadKnowledgeView.apply(ns, arguments); }

  var _dashExpandState = {};
  var _dashboardRendered = false;
  var _workflowRunPollingTimer = 0;

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
  const databaseView = document.getElementById("database-view");
  const adminFeed = document.getElementById("admin-feed");
  const adminTargetBadge = document.getElementById("admin-target-badge");
  const adminAgentsWidget = document.getElementById("admin-agents-widget");
  const adminMessageInput = document.getElementById("admin-message-input");
  const adminSendBtn = document.getElementById("admin-send-btn");
  const adminSplitter = document.getElementById("admin-splitter");
  const workflowView = document.getElementById("workflow-view");
  const workflowListPanel = document.getElementById("workflow-list-panel");
  const workflowSplitter = document.getElementById("workflow-splitter");
  const workflowDetailPanel = document.getElementById("workflow-detail-panel");
  const workflowDetailEmpty = document.getElementById("workflow-detail-empty");
  const workflowDetailContent = document.getElementById("workflow-detail-content");
  const multiagentView = document.getElementById("multiagent-view");
  const patternListPanel = document.getElementById("pattern-list-panel");
  const patternDetailEmpty = document.getElementById("pattern-detail-empty");
  const patternDetailContent = document.getElementById("pattern-detail-content");
  var _workflowData = [];
  var _workflowRuns = [];
  var _selectedWorkflow = null;
  var _workflowProjectDir = "";
  var _patternData = [];
  var _selectedPattern = null;
  var _patternProjectDir = "";
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
  var ROUTE_LABELS = { canvas: "Canvas", dashboard: "Dashboard", history: "Canvas / History", workflow: "Workflow", multiagent: "Patterns", knowledge: "Knowledge", system: "System", admin: "Agent Control", database: "Database" };

  // Current route
  let currentRoute = "canvas";
  // Track displayed card to skip redundant rebuilds
  let _spotlightCardId = "";
  let _spotlightManualIndex = -1;
  let _spotlightManualCardId = "";
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
  // Card export helpers (shared by download & copy-to-clipboard)
  // ----------------------------------------------------------------
  function fetchCardExport(cardId, format, label) {
    var url = "/api/cards/" + encodeURIComponent(cardId) + "/download";
    if (format) url += "?format=" + encodeURIComponent(format);
    return fetch(url).then(function (resp) {
      if (!resp.ok) {
        showToast(label + " failed: " + resp.status, "error");
        return null;
      }
      return resp;
    }).catch(function (err) {
      showToast(label + " failed: " + err.message, "error");
      return null;
    });
  }

  function downloadCard(cardId, format) {
    fetchCardExport(cardId, format, "Download").then(function (resp) {
      if (!resp) return;
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
    });
  }

  function copyCardToClipboard(cardId, format) {
    fetchCardExport(cardId, format || "md", "Copy").then(function (resp) {
      if (!resp) return;
      return resp.text().then(function (text) {
        return navigator.clipboard.writeText(text);
      }).then(function () {
        showToast("Copied to clipboard", "Copied");
      });
    });
  }

  function createActionButton(opts, getCardId) {
    var btn = document.createElement("button");
    btn.className = opts.className;
    btn.title = opts.title;
    btn.type = "button";
    btn.setAttribute("aria-label", opts.title);
    btn.innerHTML = '<i class="ph ' + opts.icon + '"></i>';
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var id = typeof getCardId === "function" ? getCardId() : getCardId;
      if (id) opts.action(id);
    });
    return btn;
  }

  function createDownloadButton(getCardId) {
    return createActionButton(
      { className: "canvas-dl-btn", title: "Download", icon: "ph-download-simple", action: downloadCard },
      getCardId
    );
  }

  function createCopyButton(getCardId) {
    return createActionButton(
      { className: "canvas-copy-btn", title: "Copy to clipboard", icon: "ph-copy", action: copyCardToClipboard },
      getCardId
    );
  }

  var _sortedCardsCache = null;
  function _invalidateSortedCards() { _sortedCardsCache = null; }
  function cardsByRecency(a, b) {
    return (b.updated_at || "").localeCompare(a.updated_at || "");
  }
  function getSortedCards() {
    if (!_sortedCardsCache) {
      _sortedCardsCache = [...cards.values()].sort(cardsByRecency);
    }
    return _sortedCardsCache;
  }

  function isEditableTarget(target) {
    if (!target || !(target instanceof HTMLElement)) return false;
    return Boolean(
      target.closest("input, textarea, select, [contenteditable='true']")
    );
  }

  function getTemplateBadgeLabel(card) {
    if (!card || !card.template) return "";
    return String(card.template).replace(/[-_]+/g, " ");
  }

  // ----------------------------------------------------------------
  // Initial load
  // ----------------------------------------------------------------
  function normalizeCard(card) {
    if (typeof card.template_data === "string") {
      try { card.template_data = JSON.parse(card.template_data); } catch (_) { card.template_data = {}; }
    }
    return card;
  }

  async function loadCards() {
    try {
      const resp = await fetch("/api/cards");
      const list = await resp.json();
      cards.clear();
      _invalidateSortedCards();
      for (const card of list) {
        normalizeCard(card);
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
      const card = normalizeCard(JSON.parse(e.data));
      cards.set(card.card_id, card);
      _invalidateSortedCards();
      trackAgent(card);
      renderCurrentView();
      showToast(card.title || "New card", card.agent_name || card.agent_id);
    });

    es.addEventListener("card_updated", (e) => {
      const card = normalizeCard(JSON.parse(e.data));
      cards.set(card.card_id, card);
      _invalidateSortedCards();
      trackAgent(card);
      renderCurrentView();
      showToast(card.title || "Card updated", card.agent_name || card.agent_id);
    });

    es.addEventListener("card_deleted", (e) => {
      const data = JSON.parse(e.data);
      const deleted = cards.get(data.card_id);
      cards.delete(data.card_id);
      _invalidateSortedCards();
      if (data.card_id === _spotlightCardId) {
        _spotlightCardId = "";
        _spotlightUpdatedAt = "";
      }
      renderCurrentView();
      showToast(deleted ? deleted.title : "Card deleted", "Removed");
    });

    es.addEventListener("system_update", () => {
      ns.loadSystemPanel();
      if (currentRoute === "admin") ns.loadAdminAgents();
    });

    es.addEventListener("workflow_update", () => {
      if (currentRoute === "workflow") ns.loadWorkflowRuns();
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
    ns.renderTemplateOrBlocks(item, card, blocks, true, null);
  }

  function renderCurrentView() {
    cancelAnimationFrame(_renderRAF);
    _renderRAF = requestAnimationFrame(() => {
      if (currentRoute === "canvas") {
        ns.renderSpotlight();
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
    filtered.sort(cardsByRecency);

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
    const byTime = allCards.sort(cardsByRecency);
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
    ns.runMermaid(".mermaid-pending");
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
    ns.runMermaid("#live-feed-list .mermaid-pending");
  }

  function createAgentPanel(group) {
    const panel = document.createElement("div");
    panel.className = "agent-panel";
    panel.dataset.agentKey = group.agentId || group.label;

    // Header
    const header = document.createElement("div");
    header.className = "agent-panel-header";
    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");

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
    header.setAttribute("aria-expanded", String(!isCollapsed));
    if (isCollapsed) arrow.classList.add("collapsed");
    arrow.textContent = "\u25BC";
    header.appendChild(arrow);

    panel.appendChild(header);

    // Body
    const body = document.createElement("div");
    body.className = "agent-panel-body";
    if (isCollapsed) body.classList.add("collapsed");

    const togglePanel = () => {
      body.classList.toggle("collapsed");
      arrow.classList.toggle("collapsed");
      header.setAttribute("aria-expanded", String(!body.classList.contains("collapsed")));
      localStorage.setItem(
        storageKey,
        body.classList.contains("collapsed") ? "collapsed" : "expanded"
      );
    };

    header.addEventListener("click", togglePanel);
    header.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        togglePanel();
      }
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

    header.appendChild(createCopyButton(card.card_id));
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
    ns.renderTemplateOrBlocks(el, card, blocks, false, null);

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
    ns.runMermaid(".mermaid-pending");
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
    if (hash === "#/knowledge") return "knowledge";
    if (hash === "#/admin") return "admin";
    if (hash === "#/database") return "database";
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
    var knowledgeView = document.getElementById("knowledge-view");

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
    if (multiagentView) multiagentView.classList.add("view-hidden");
    if (knowledgeView) knowledgeView.classList.add("view-hidden");
    if (adminView) adminView.classList.add("view-hidden");
    if (databaseView) databaseView.classList.add("view-hidden");

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
      ns.renderSpotlight();
    } else if (currentRoute === "dashboard") {
      if (dashboardView) dashboardView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      if (_lastSystemData) ns.renderDashboard(_lastSystemData);
      ns.loadSystemPanel();
    } else if (currentRoute === "system") {
      systemView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      if (_lastSystemData) ns.renderSystemPanel(_lastSystemData);
    } else if (currentRoute === "workflow") {
      if (workflowView) workflowView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      loadWorkflows();
    } else if (currentRoute === "multiagent") {
      if (multiagentView) multiagentView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      loadPatterns();
    } else if (currentRoute === "knowledge") {
      if (knowledgeView) knowledgeView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      loadKnowledgeView();
    } else if (currentRoute === "admin") {
      if (adminView) adminView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      ns.loadAdminAgents();
    } else if (currentRoute === "database") {
      if (databaseView) databaseView.classList.remove("view-hidden");
      filterBar.style.display = "none";
      loadDatabaseList();
    } else {
      historyView.classList.remove("view-hidden");
      filterBar.style.display = "";
      renderAll();
    }
  }

  filterType.addEventListener("change", renderAll);
  filterAgent.addEventListener("change", renderAll);
  window.addEventListener("hashchange", navigate);
  if (adminSendBtn) adminSendBtn.addEventListener("click", function() { ns.sendAdminCommand(); });
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
      if (e.key === "Enter" && e.metaKey && !_isComposing) { e.preventDefault(); ns.sendAdminCommand(); }
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

  ns.grid = grid;
  ns.filterType = filterType;
  ns.filterAgent = filterAgent;
  ns.cardCount = cardCount;
  ns.themeToggle = themeToggle;
  ns.filterBar = filterBar;
  ns.toastContainer = toastContainer;
  ns.systemPanel = systemPanel;
  ns.liveFeedList = liveFeedList;
  ns.canvasView = canvasView;
  ns.canvasSpotlight = canvasSpotlight;
  ns.dashboardView = dashboardView;
  ns.historyView = historyView;
  ns.systemView = systemView;
  ns.adminView = adminView;
  ns.databaseView = databaseView;
  ns.adminFeed = adminFeed;
  ns.adminTargetBadge = adminTargetBadge;
  ns.adminAgentsWidget = adminAgentsWidget;
  ns.adminMessageInput = adminMessageInput;
  ns.adminSendBtn = adminSendBtn;
  ns.adminSplitter = adminSplitter;
  ns.workflowView = workflowView;
  ns.workflowListPanel = workflowListPanel;
  ns.workflowSplitter = workflowSplitter;
  ns.workflowDetailPanel = workflowDetailPanel;
  ns.workflowDetailEmpty = workflowDetailEmpty;
  ns.workflowDetailContent = workflowDetailContent;
  ns.multiagentView = multiagentView;
  ns.patternListPanel = patternListPanel;
  ns.patternDetailEmpty = patternDetailEmpty;
  ns.patternDetailContent = patternDetailContent;
  ns.navLinks = navLinks;
  ns.sidebar = sidebar;
  ns.sidebarOverlay = sidebarOverlay;
  ns.sidebarToggle = sidebarToggle;
  ns.sidebarCollapseBtn = sidebarCollapseBtn;
  ns.topbarTitle = topbarTitle;
  ns.SPOTLIGHT_SWAP_DELAY = SPOTLIGHT_SWAP_DELAY;
  ns.ROUTE_LABELS = ROUTE_LABELS;
  ns.cards = cards;
  ns.knownAgents = knownAgents;
  ns._patternData = _patternData;
  ns._selectedPattern = _selectedPattern;
  ns._patternProjectDir = _patternProjectDir;

  Object.defineProperties(ns, {
    currentRoute: { get: function() { return currentRoute; }, set: function(v) { currentRoute = v; } },
    _spotlightCardId: { get: function() { return _spotlightCardId; }, set: function(v) { _spotlightCardId = v; } },
    _spotlightManualIndex: { get: function() { return _spotlightManualIndex; }, set: function(v) { _spotlightManualIndex = v; } },
    _spotlightManualCardId: { get: function() { return _spotlightManualCardId; }, set: function(v) { _spotlightManualCardId = v; } },
    _spotlightUpdatedAt: { get: function() { return _spotlightUpdatedAt; }, set: function(v) { _spotlightUpdatedAt = v; } },
    _spotlightSwapTimer: { get: function() { return _spotlightSwapTimer; }, set: function(v) { _spotlightSwapTimer = v; } },
    systemAgents: { get: function() { return systemAgents; }, set: function(v) { systemAgents = v; } },
    _lastSystemData: { get: function() { return _lastSystemData; }, set: function(v) { _lastSystemData = v; } },
    _systemPanelRendered: { get: function() { return _systemPanelRendered; }, set: function(v) { _systemPanelRendered = v; } },
    _lastSystemJSON: { get: function() { return _lastSystemJSON; }, set: function(v) { _lastSystemJSON = v; } },
    _workflowData: { get: function() { return _workflowData; }, set: function(v) { _workflowData = v; } },
    _workflowRuns: { get: function() { return _workflowRuns; }, set: function(v) { _workflowRuns = v; } },
    _selectedWorkflow: { get: function() { return _selectedWorkflow; }, set: function(v) { _selectedWorkflow = v; } },
    _workflowProjectDir: { get: function() { return _workflowProjectDir; }, set: function(v) { _workflowProjectDir = v; } },
    _selectedAdminTarget: { get: function() { return _selectedAdminTarget; }, set: function(v) { _selectedAdminTarget = v; } },
    _selectedAdminName: { get: function() { return _selectedAdminName; }, set: function(v) { _selectedAdminName = v; } },
    _dashExpandState: { get: function() { return _dashExpandState; }, set: function(v) { _dashExpandState = v; } },
    _dashboardRendered: { get: function() { return _dashboardRendered; }, set: function(v) { _dashboardRendered = v; } },
    _workflowRunPollingTimer: { get: function() { return _workflowRunPollingTimer; }, set: function(v) { _workflowRunPollingTimer = v; } },
  });

  ns.downloadCard = downloadCard;
  ns.createDownloadButton = createDownloadButton;
  ns.copyCardToClipboard = copyCardToClipboard;
  ns.createCopyButton = createCopyButton;
  ns.cardsByRecency = cardsByRecency;
  ns.getSortedCards = getSortedCards;
  ns.isEditableTarget = isEditableTarget;
  ns.renderBlock = renderBlock;
  ns.getTemplateBadgeLabel = getTemplateBadgeLabel;
  ns.normalizeCard = normalizeCard;
  ns.loadCards = loadCards;
  ns.connectSSE = connectSSE;
  ns.trackAgent = trackAgent;
  ns.getFilteredCards = getFilteredCards;
  ns.markAsNew = markAsNew;
  ns.syncChildren = syncChildren;
  ns.populateLiveFeedItem = populateLiveFeedItem;
  ns.renderCurrentView = renderCurrentView;
  ns.renderAll = renderAll;
  ns.renderLiveFeed = renderLiveFeed;
  ns.createAgentPanel = createAgentPanel;
  ns.updateAgentPanel = updateAgentPanel;
  ns.parseContent = parseContent;
  ns.parseBody = parseBody;
  ns.historyStatusColor = historyStatusColor;
  ns.formatTimeShort = formatTimeShort;
  ns.escapeHtml = escapeHtml;
  ns.inlineMarkdown = inlineMarkdown;
  ns.simpleMarkdown = simpleMarkdown;
  ns.formatTime = formatTime;
  ns.showToast = showToast;
  ns.setThemeLabel = setThemeLabel;
  ns.initTheme = initTheme;
  ns.reRenderMermaid = reRenderMermaid;
  ns.statusIcon = statusIcon;
  ns.statusColor = statusColor;
  ns.getRoute = getRoute;
  ns.openSidebar = openSidebar;
  ns.closeSidebar = closeSidebar;
  ns.navigate = navigate;
  ns.initMermaidTheme = initMermaidTheme;

  return ns;
})();
