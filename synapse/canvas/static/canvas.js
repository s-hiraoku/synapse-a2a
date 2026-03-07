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
  const navLinks = document.querySelectorAll(".nav-link");

  // Current route
  let currentRoute = "canvas";
  // Track displayed card to skip redundant rebuilds
  let _spotlightCardId = "";
  let _spotlightUpdatedAt = "";

  // Card cache: card_id -> card data
  const cards = new Map();
  // Known agents for filter dropdown
  const knownAgents = new Set();
  // System agents cache for panel rendering
  let systemAgents = [];

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
    });

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
  function renderCurrentView() {
    cancelAnimationFrame(_renderRAF);
    _renderRAF = requestAnimationFrame(() => {
      if (currentRoute === "canvas") {
        renderSpotlight();
      } else {
        renderAll();
      }
    });
  }

  function renderAll() {
    const filtered = getFilteredCards();
    const countText = `${filtered.length} card${filtered.length !== 1 ? "s" : ""}`;
    cardCount.textContent = countText;
    grid.innerHTML = "";

    // Sort: pinned first, then by updated_at desc
    filtered.sort((a, b) => {
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      return (b.updated_at || "").localeCompare(a.updated_at || "");
    });

    // Group cards by agent
    const agentGroups = new Map();

    // Seed panels from system agents (so empty agents get a panel)
    for (const agent of systemAgents) {
      const label = agent.name || agent.agent_id;
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

    // Live Feed (latest 3 by time, ignoring pin order)
    const byTime = [...filtered].sort((a, b) =>
      (b.updated_at || "").localeCompare(a.updated_at || "")
    );
    renderLiveFeed(byTime.slice(0, 3));

    // Render each agent panel
    for (const group of agentGroups.values()) {
      grid.appendChild(createAgentPanel(group));
    }

    // Re-run mermaid on any new diagrams
    if (typeof mermaid !== "undefined") {
      mermaid.run({ querySelector: ".mermaid-pending" });
    }
  }

  function renderLiveFeed(recentCards) {
    if (!liveFeedList) return;
    liveFeedList.innerHTML = "";

    if (recentCards.length === 0) {
      const empty = document.createElement("div");
      empty.className = "live-feed-empty";
      empty.textContent = "Waiting for agent messages...";
      liveFeedList.appendChild(empty);
      return;
    }

    for (const card of recentCards) {
      const item = document.createElement("div");
      item.className = "live-feed-item";

      // Header row: badge + title + time
      const header = document.createElement("div");
      header.className = "live-feed-item-header";

      // Status dot from systemAgents
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

      // Content preview: render actual card content
      const content = parseContent(card.content);
      const blocks = Array.isArray(content) ? content : [content];
      for (const block of blocks) {
        item.appendChild(renderBlock(block));
      }

      liveFeedList.appendChild(item);
    }

    // Re-run mermaid on live feed diagrams
    if (typeof mermaid !== "undefined") {
      mermaid.run({ querySelector: "#live-feed-list .mermaid-pending" });
    }
  }

  function createAgentPanel(group) {
    const panel = document.createElement("div");
    panel.className = "agent-panel";

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

    if (group.cards.length === 0) {
      const empty = document.createElement("div");
      empty.className = "agent-panel-empty";
      empty.textContent = "No messages";
      body.appendChild(empty);
    } else {
      for (const card of group.cards) {
        body.appendChild(createCardElement(card));
      }
    }

    panel.appendChild(body);
    return panel;
  }

  function createCardElement(card) {
    const el = document.createElement("article");
    el.className = "canvas-card";
    if (card.pinned) el.classList.add("pinned");
    el.dataset.cardId = card.card_id;

    // Header
    const header = document.createElement("header");
    const title = document.createElement("h2");
    title.textContent = card.title || "Untitled";
    header.appendChild(title);

    if (card.pinned) {
      const pin = document.createElement("span");
      pin.className = "pin-icon";
      pin.textContent = "\u{1F4CC}";
      header.appendChild(pin);
    }

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

    // Content blocks
    const content = parseContent(card.content);
    const blocks = Array.isArray(content) ? content : [content];
    for (const block of blocks) {
      el.appendChild(renderBlock(block));
    }

    // Footer
    const footer = document.createElement("footer");
    footer.textContent = formatTime(card.updated_at);
    el.appendChild(footer);

    return el;
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
  function renderBlock(block) {
    const wrap = document.createElement("div");
    wrap.className = `content-block format-${block.format}`;

    switch (block.format) {
      case "mermaid":
        renderMermaid(wrap, block.body);
        break;
      case "markdown":
        renderMarkdown(wrap, block.body);
        break;
      case "html":
        renderHTML(wrap, block.body);
        break;
      case "table":
        renderTable(wrap, block.body);
        break;
      case "json":
        renderJSON(wrap, block.body);
        break;
      case "diff":
        renderDiff(wrap, block.body);
        break;
      case "code":
        renderCode(wrap, block.body, block.lang);
        break;
      case "image":
        renderImage(wrap, block.body);
        break;
      case "chart":
        renderChart(wrap, block.body);
        break;
      case "log":
        renderLog(wrap, block.body);
        break;
      case "status":
        renderStatus(wrap, block.body);
        break;
      case "metric":
        renderMetric(wrap, block.body);
        break;
      case "checklist":
        renderChecklist(wrap, block.body);
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
        renderTrace(wrap, block.body);
        break;
      case "task-board":
        renderTaskBoard(wrap, block.body);
        break;
      default:
        wrap.textContent = block.body;
    }

    return wrap;
  }

  function renderMermaid(el, body) {
    const pre = document.createElement("pre");
    pre.className = "mermaid-pending mermaid";
    pre.textContent = body;
    el.appendChild(pre);
  }

  function renderMarkdown(el, body) {
    // Simple markdown: headings, bold, italic, code, links, lists
    const html = simpleMarkdown(body);
    el.innerHTML = html;
  }

  function renderHTML(el, body) {
    // Sandboxed iframe for raw HTML
    const iframe = document.createElement("iframe");
    iframe.sandbox = "allow-scripts";
    iframe.style.width = "100%";
    iframe.style.minHeight = "200px";
    iframe.style.border = "1px solid var(--color-border)";
    iframe.style.borderRadius = "4px";
    // In canvas view, fill the available content area
    const isCanvasView = el.closest(".canvas-content") !== null;
    if (isCanvasView) {
      iframe.style.height = "100%";
      iframe.style.minHeight = "0";
    }
    iframe.srcdoc = body;
    // Auto-resize (dashboard only — canvas uses CSS flex)
    iframe.onload = function () {
      if (isCanvasView) return;
      try {
        iframe.style.height = iframe.contentDocument.body.scrollHeight + 20 + "px";
      } catch { /* cross-origin fallback */ }
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

  function renderJSON(el, body) {
    const pre = document.createElement("pre");
    pre.className = "json-view";
    try {
      const obj = typeof body === "string" ? JSON.parse(body) : body;
      pre.textContent = JSON.stringify(obj, null, 2);
    } catch {
      pre.textContent = body;
    }
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

  function renderCode(el, body, lang) {
    const pre = document.createElement("pre");
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
    canvas.style.maxHeight = "400px";
    el.appendChild(canvas);
    new Chart(canvas, config);
  }

  function renderLog(el, body) {
    const entries = Array.isArray(body) ? body : [];
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

  function renderChecklist(el, body) {
    const items = Array.isArray(body) ? body : [];
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

  function renderTrace(el, body) {
    const spans = Array.isArray(body) ? body : [];
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

  // ----------------------------------------------------------------
  // System Panel
  // ----------------------------------------------------------------
  async function loadSystemPanel() {
    if (!systemPanel) return;
    try {
      const resp = await fetch("/api/system");
      if (!resp.ok) return;
      const data = await resp.json();
      systemAgents = Array.isArray(data.agents) ? data.agents : [];
      renderSystemPanel(data);
      renderAll();
    } catch (e) {
      console.error("Failed to load system panel:", e);
    }
  }

  function renderSystemPanel(data) {
    if (!systemPanel) return;
    systemPanel.innerHTML = "";

    // Panel toggle header
    const toggle = document.createElement("button");
    toggle.id = "system-panel-toggle";
    const arrow = document.createElement("span");
    arrow.className = "toggle-arrow";
    // One-time reset of all collapsed states after redesign
    if (!localStorage.getItem("canvas-layout-v3")) {
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith("system-panel") || key.startsWith("agent-panel")) {
          localStorage.removeItem(key);
        }
      }
      localStorage.setItem("canvas-layout-v3", "1");
    }
    const isCollapsedPanel = localStorage.getItem("system-panel-main") === "collapsed";
    if (isCollapsedPanel) arrow.classList.add("collapsed");
    arrow.textContent = "\u25BC";
    toggle.appendChild(arrow);

    const agentCount = Array.isArray(data.agents) ? data.agents.length : 0;
    const taskCount = Object.values(data.tasks || {}).reduce((s, a) => s + (Array.isArray(a) ? a.length : 0), 0);
    const lockCount = Array.isArray(data.file_locks) ? data.file_locks.length : 0;
    const memoryCount = Array.isArray(data.memories) ? data.memories.length : 0;
    const worktreeCount = Array.isArray(data.worktrees) ? data.worktrees.length : 0;
    const historyCount = Array.isArray(data.history) ? data.history.length : 0;
    const profileCount = Array.isArray(data.agent_profiles) ? data.agent_profiles.length : 0;
    toggle.appendChild(document.createTextNode(
      `System  \u2014  ${agentCount} agents \u00B7 ${profileCount} profiles \u00B7 ${taskCount} tasks \u00B7 ${memoryCount} memories \u00B7 ${historyCount} history`
    ));
    systemPanel.appendChild(toggle);

    // Content wrapper
    const content = document.createElement("div");
    content.id = "system-panel-content";
    if (isCollapsedPanel) content.classList.add("collapsed");

    toggle.addEventListener("click", () => {
      content.classList.toggle("collapsed");
      arrow.classList.toggle("collapsed");
      localStorage.setItem(
        "system-panel-main",
        content.classList.contains("collapsed") ? "collapsed" : "expanded"
      );
    });

    content.appendChild(
      createSystemSection(
        "agents",
        "Agents (" + agentCount + ")",
        renderSystemAgents(Array.isArray(data.agents) ? data.agents : [])
      )
    );
    if (profileCount > 0) {
      content.appendChild(
        createSystemSection(
          "agent-profiles",
          "Saved Agents (" + profileCount + ")",
          renderSystemProfiles(data.agent_profiles)
        )
      );
    }
    content.appendChild(
      createSystemSection(
        "tasks",
        "Tasks (" + taskCount + ")",
        renderSystemTasks(data.tasks || {})
      )
    );
    content.appendChild(
      createSystemSection(
        "file-locks",
        "File Locks (" + lockCount + ")",
        renderSystemFileLocks(Array.isArray(data.file_locks) ? data.file_locks : [])
      )
    );
    content.appendChild(
      createSystemSection(
        "memories",
        "Shared Memory (" + memoryCount + ")",
        renderSystemMemories(Array.isArray(data.memories) ? data.memories : [])
      )
    );
    if (worktreeCount > 0) {
      content.appendChild(
        createSystemSection(
          "worktrees",
          "Worktrees (" + worktreeCount + ")",
          renderSystemWorktrees(data.worktrees)
        )
      );
    }
    content.appendChild(
      createSystemSection(
        "history",
        "Recent History (" + historyCount + ")",
        renderSystemHistory(Array.isArray(data.history) ? data.history : [])
      )
    );
    systemPanel.appendChild(content);
  }

  function createSystemSection(key, title, bodyContent) {
    const section = document.createElement("section");
    section.className = "system-section";

    const header = document.createElement("div");
    header.className = "system-section-header";
    header.textContent = title;

    const body = document.createElement("div");
    body.className = "system-section-body";
    const collapsed = localStorage.getItem(`system-panel-${key}`) === "collapsed";
    if (collapsed) body.classList.add("collapsed");
    body.appendChild(bodyContent);

    header.addEventListener("click", () => {
      body.classList.toggle("collapsed");
      localStorage.setItem(
        `system-panel-${key}`,
        body.classList.contains("collapsed") ? "collapsed" : "expanded"
      );
    });

    section.appendChild(header);
    section.appendChild(body);
    return section;
  }

  function renderSystemAgents(agents) {
    const wrap = document.createElement("div");
    if (agents.length === 0) {
      wrap.textContent = "No agents";
      return wrap;
    }

    const table = document.createElement("table");
    table.className = "system-agents-table";

    // Header
    const thead = document.createElement("thead");
    const hrow = document.createElement("tr");
    for (const col of ["", "TYPE", "NAME", "ROLE", "SKILL SET", "STATUS", "PORT", "DIR", "CURRENT"]) {
      const th = document.createElement("th");
      th.textContent = col;
      hrow.appendChild(th);
    }
    thead.appendChild(hrow);
    table.appendChild(thead);

    // Body
    const tbody = document.createElement("tbody");
    for (const agent of agents) {
      const tr = document.createElement("tr");

      // Status dot
      const tdDot = document.createElement("td");
      tdDot.className = "agent-dot-cell";
      const dot = document.createElement("span");
      dot.className = "system-status-dot";
      dot.style.background = statusColor(agent.status);
      tdDot.appendChild(dot);
      tr.appendChild(tdDot);

      // Type
      const tdType = document.createElement("td");
      tdType.textContent = agent.agent_type || "";
      tr.appendChild(tdType);

      // Name
      const tdName = document.createElement("td");
      tdName.className = "agent-name-cell";
      tdName.textContent = agent.name || "-";
      tr.appendChild(tdName);

      // Role
      const tdRole = document.createElement("td");
      tdRole.className = "agent-role-cell";
      tdRole.textContent = agent.role || "-";
      tr.appendChild(tdRole);

      // Skill Set
      const tdSkill = document.createElement("td");
      tdSkill.className = "agent-role-cell";
      tdSkill.textContent = agent.skill_set || "-";
      tr.appendChild(tdSkill);

      // Status
      const tdStatus = document.createElement("td");
      tdStatus.className = "agent-status-cell";
      tdStatus.textContent = agent.status || "-";
      tdStatus.style.color = statusColor(agent.status);
      tr.appendChild(tdStatus);

      // Port
      const tdPort = document.createElement("td");
      tdPort.className = "agent-port-cell";
      tdPort.textContent = agent.port || "-";
      tr.appendChild(tdPort);

      // Working dir
      const tdDir = document.createElement("td");
      tdDir.className = "agent-dir-cell";
      tdDir.textContent = agent.working_dir || "-";
      tr.appendChild(tdDir);

      // Current task
      const tdCurrent = document.createElement("td");
      tdCurrent.className = "agent-current-cell";
      const preview = agent.current_task_preview || "-";
      if (preview !== "-" && agent.task_received_at) {
        const elapsed = Math.floor((Date.now() / 1000) - agent.task_received_at);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        const elapsedStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
        tdCurrent.textContent = `${preview} (${elapsedStr})`;
      } else {
        tdCurrent.textContent = preview;
      }
      tr.appendChild(tdCurrent);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);

    wrap.appendChild(table);
    return wrap;
  }

  function renderSystemTasks(tasks) {
    const board = document.createElement("div");
    board.className = "task-board";
    for (const name of ["pending", "in_progress", "completed"]) {
      const column = document.createElement("div");
      column.className = "task-column";

      const header = document.createElement("div");
      header.className = "task-column-header";
      header.textContent = name.replace("_", " ");
      column.appendChild(header);

      for (const item of tasks[name] || []) {
        const card = document.createElement("div");
        card.className = "task-item";
        card.textContent = `${item.id || ""} ${item.subject || ""}`.trim();
        if (item.assignee) {
          const assignee = document.createElement("div");
          assignee.className = "task-assignee";
          assignee.textContent = item.assignee;
          card.appendChild(assignee);
        }
        column.appendChild(card);
      }

      board.appendChild(column);
    }
    return board;
  }

  function renderSystemFileLocks(locks) {
    const wrap = document.createElement("div");
    if (locks.length === 0) {
      wrap.textContent = "No active locks";
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
      wrap.textContent = "No shared memories";
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
      wrap.textContent = "No active worktrees";
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
      wrap.textContent = "No history";
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
      wrap.textContent = "No saved agents";
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
      tdScope.className = "agent-port-cell";
      tdScope.textContent = p.scope;
      tr.appendChild(tdScope);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
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

  function simpleMarkdown(text) {
    return escapeHtml(text)
      // Code blocks
      .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
      // Inline code
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      // Headings
      .replace(/^### (.+)$/gm, "<h4>$1</h4>")
      .replace(/^## (.+)$/gm, "<h3>$1</h3>")
      .replace(/^# (.+)$/gm, "<h2>$1</h2>")
      // Bold + italic
      .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      // Links (only allow safe URL schemes; input is already HTML-escaped)
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, function(_, text, href) {
        if (/^(https?:|mailto:|#)/i.test(href) && !/^javascript:/i.test(href)) {
          return '<a href="' + href + '" target="_blank" rel="noopener">' + text + '</a>';
        }
        return text;
      })
      // Unordered list
      .replace(/^[-*] (.+)$/gm, "<li>$1</li>")
      // Line breaks
      .replace(/\n/g, "<br>");
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
  function showToast(title, agentLabel) {
    const toast = document.createElement("div");
    toast.className = "toast";
    const titleEl = document.createElement("div");
    titleEl.className = "toast-title";
    titleEl.textContent = title || "Card updated";
    toast.appendChild(titleEl);
    if (agentLabel) {
      const agentEl = document.createElement("div");
      agentEl.className = "toast-agent";
      agentEl.textContent = agentLabel;
      toast.appendChild(agentEl);
    }
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }

  // ----------------------------------------------------------------
  // Theme Toggle
  // ----------------------------------------------------------------
  function initTheme() {
    const saved = localStorage.getItem("canvas-theme") || "dark";
    document.documentElement.setAttribute("data-theme", saved);
    themeToggle.textContent = saved === "dark" ? "Light" : "Dark";
  }

  themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("canvas-theme", next);
    themeToggle.textContent = next === "dark" ? "Light" : "Dark";
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
      case "success":
        return "var(--color-success)";
      case "processing":
      case "running":
        return "var(--color-accent)";
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
    return "canvas";
  }

  function navigate() {
    currentRoute = getRoute();

    // Update nav links
    navLinks.forEach(link => {
      link.classList.toggle("active", link.dataset.route === currentRoute);
    });

    // Toggle views
    if (currentRoute === "canvas") {
      canvasView.classList.remove("view-hidden");
      dashboardView.classList.add("view-hidden");
      filterBar.style.display = "none";
      renderSpotlight();
    } else {
      canvasView.classList.add("view-hidden");
      dashboardView.classList.remove("view-hidden");
      filterBar.style.display = "";
      renderAll();
    }
  }

  // ----------------------------------------------------------------
  // Canvas View — full-viewport projection of latest card
  // ----------------------------------------------------------------
  function renderSpotlight() {
    if (!canvasSpotlight) return;
    canvasSpotlight.innerHTML = "";

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
      canvasSpotlight.appendChild(empty);
      canvasView.style.removeProperty("--canvas-glow");
      return;
    }

    // Find the most recently updated card (O(n) instead of sorting)
    const card = allCards.reduce((latest, c) =>
      (c.updated_at || "") > (latest.updated_at || "") ? c : latest
    );

    // Skip rebuild if the same card version is already displayed
    if (card.card_id === _spotlightCardId && card.updated_at === _spotlightUpdatedAt) {
      return;
    }
    _spotlightCardId = card.card_id;
    _spotlightUpdatedAt = card.updated_at;

    const agentInfo = systemAgents.find(a => a.agent_id === card.agent_id);
    const agentStatus = agentInfo ? agentInfo.status : "";

    // Set ambient glow color based on agent status
    canvasView.style.setProperty("--canvas-glow", statusColor(agentStatus));

    // Title bar
    const titleBar = document.createElement("div");
    titleBar.className = "canvas-title-bar";
    const titleText = document.createElement("h2");
    titleText.className = "canvas-title-text";
    titleText.textContent = card.title || "Untitled";
    titleBar.appendChild(titleText);
    canvasSpotlight.appendChild(titleBar);

    // Content — fills the viewport
    const content = document.createElement("div");
    content.className = "canvas-content";
    const parsed = parseContent(card.content);
    const blocks = Array.isArray(parsed) ? parsed : [parsed];
    for (const block of blocks) {
      content.appendChild(renderBlock(block));
    }
    canvasSpotlight.appendChild(content);

    // Info bar — floating at bottom
    const infoBar = document.createElement("div");
    infoBar.className = "canvas-info-bar";

    // Status dot with glow
    const dot = document.createElement("span");
    dot.className = "canvas-info-dot";
    const dotColor = statusColor(agentStatus);
    dot.style.background = dotColor;
    dot.style.color = dotColor;
    infoBar.appendChild(dot);

    // Agent name
    const agentName = document.createElement("span");
    agentName.className = "canvas-info-agent";
    agentName.textContent = card.agent_name || card.agent_id;
    infoBar.appendChild(agentName);

    // Agent ID
    const idEl = document.createElement("span");
    idEl.className = "canvas-info-id";
    idEl.textContent = card.agent_id;
    infoBar.appendChild(idEl);

    // Tags
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

    // Time
    const time = document.createElement("span");
    time.className = "canvas-info-time";
    time.textContent = formatTime(card.updated_at);
    infoBar.appendChild(time);

    // Card ID
    const cardId = document.createElement("span");
    cardId.className = "canvas-info-card-id";
    cardId.textContent = card.card_id;
    infoBar.appendChild(cardId);

    canvasSpotlight.appendChild(infoBar);

    // Re-run mermaid
    if (typeof mermaid !== "undefined") {
      mermaid.run({ querySelector: "#canvas-spotlight .mermaid-pending" });
    }
  }

  // ----------------------------------------------------------------
  // Init
  // ----------------------------------------------------------------
  filterType.addEventListener("change", renderAll);
  filterAgent.addEventListener("change", renderAll);
  window.addEventListener("hashchange", navigate);

  if (typeof mermaid !== "undefined") {
    mermaid.initialize({ startOnLoad: false, theme: "default" });
  }
  if (typeof hljs !== "undefined") {
    hljs.configure({ ignoreUnescapedHTML: true });
  }

  initTheme();
  loadCards();
  loadSystemPanel();
  connectSSE();
  window.setInterval(loadSystemPanel, 10000);

  // Initial route
  navigate();
})();
