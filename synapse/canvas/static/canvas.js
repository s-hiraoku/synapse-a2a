/* Synapse Canvas — browser-side card rendering with SSE live updates. */

(function () {
  "use strict";

  const grid = document.getElementById("canvas-grid");
  const filterType = document.getElementById("filter-type");
  const filterAgent = document.getElementById("filter-agent");
  const cardCount = document.getElementById("card-count");

  // Card cache: card_id -> card data
  const cards = new Map();
  // Known agents for filter dropdown
  const knownAgents = new Set();

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
      renderAll();
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
      renderAll();
    });

    es.addEventListener("card_updated", (e) => {
      const card = JSON.parse(e.data);
      cards.set(card.card_id, card);
      trackAgent(card);
      renderAll();
    });

    es.addEventListener("card_deleted", (e) => {
      const data = JSON.parse(e.data);
      cards.delete(data.card_id);
      renderAll();
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
  function renderAll() {
    const filtered = getFilteredCards();
    cardCount.textContent = `${filtered.length} card${filtered.length !== 1 ? "s" : ""}`;
    grid.innerHTML = "";

    // Sort: pinned first, then by updated_at desc
    filtered.sort((a, b) => {
      if (a.pinned && !b.pinned) return -1;
      if (!a.pinned && b.pinned) return 1;
      return (b.updated_at || "").localeCompare(a.updated_at || "");
    });

    for (const card of filtered) {
      grid.appendChild(createCardElement(card));
    }

    // Re-run mermaid on any new diagrams
    if (typeof mermaid !== "undefined") {
      mermaid.run({ querySelector: ".mermaid-pending" });
    }
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

    const badge = document.createElement("span");
    badge.className = "agent-badge";
    badge.textContent = card.agent_name || card.agent_id;
    header.appendChild(badge);

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
    iframe.style.border = "1px solid var(--border)";
    iframe.style.borderRadius = "4px";
    iframe.srcdoc = body;
    // Auto-resize
    iframe.onload = function () {
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

  function renderDiff(el, body) {
    const pre = document.createElement("pre");
    pre.className = "diff-view";
    const lines = body.split("\n");
    for (const line of lines) {
      const span = document.createElement("span");
      if (line.startsWith("+")) {
        span.className = "diff-add";
      } else if (line.startsWith("-")) {
        span.className = "diff-del";
      } else if (line.startsWith("@@")) {
        span.className = "diff-hunk";
      }
      span.textContent = line + "\n";
      pre.appendChild(span);
    }
    el.appendChild(pre);
  }

  function renderCode(el, body, lang) {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    if (lang) code.className = `language-${lang}`;
    code.textContent = body;
    pre.appendChild(code);
    el.appendChild(pre);
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

  // ----------------------------------------------------------------
  // Simple markdown parser (no external dependency)
  // ----------------------------------------------------------------
  function simpleMarkdown(text) {
    return text
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
      // Links
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
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
  // Init
  // ----------------------------------------------------------------
  filterType.addEventListener("change", renderAll);
  filterAgent.addEventListener("change", renderAll);

  if (typeof mermaid !== "undefined") {
    mermaid.initialize({ startOnLoad: false, theme: "default" });
  }

  loadCards();
  connectSSE();
})();
