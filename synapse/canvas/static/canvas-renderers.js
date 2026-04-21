(function(ns) {
  "use strict";

  const parseBody = ns.parseBody;
  const simpleMarkdown = ns.simpleMarkdown;
  const escapeHtml = ns.escapeHtml;
  const showToast = ns.showToast;
  const statusColor = ns.statusColor;
  const statusIcon = ns.statusIcon;
  const formatTime = ns.formatTime;

  function formatNumber(n) {
    if (n == null) return "-";
    return Number(n).toLocaleString();
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

  function renderTemplateOrBlocks(parent, card, blocks, compact, renderOptions) {
    if (card.template && card.template_data && Object.keys(card.template_data).length > 0) {
      const td = card.template_data;
      const rendered = renderTemplate(card.template, blocks, td, compact, renderOptions);
      if (rendered) {
        parent.appendChild(rendered);
        return;
      }
    }
    for (const block of blocks) {
      parent.appendChild(renderBlock(block, renderOptions));
    }
  }

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
    if (typeof mermaid === "undefined") return Promise.resolve();
    const target = selector || ".mermaid-pending";
    const nodes = Array.prototype.slice.call(document.querySelectorAll(target));

    function renderError(el, source) {
      const escaped = (ns.escapeHtml || escapeHtml)(source || "");
      el.classList.remove("mermaid-pending");
      el.innerHTML = [
        '<div class="mermaid-error" role="note">',
        "<strong>Diagram could not be rendered</strong>",
        "<details><summary>Show source</summary><pre>",
        escaped,
        "</pre></details>",
        "</div>",
      ].join("");
    }

    function normalizeSvg(svg) {
      // Mermaid sets inline style="max-width: XXXpx" based on diagram complexity.
      // Preserve it but cap at container width. Only override height.
      svg.removeAttribute("height");
      svg.removeAttribute("width");
      svg.style.height = "auto";
      svg.style.display = "block";
      svg.style.maxWidth = "100%";
      svg.style.margin = "0 auto";
    }

    const jobs = nodes.map(function (el) {
      const source = el.dataset.mermaidSource || el.textContent || "";
      return Promise.resolve()
        .then(function () {
          return Promise.resolve(mermaid.parse(source, { suppressErrors: true }));
        })
        .then(function (valid) {
          if (valid === false) {
            throw new Error("Mermaid parse returned false");
          }
          runMermaid._counter = (runMermaid._counter || 0) + 1;
          return mermaid.render("mermaid-diagram-" + runMermaid._counter, source);
        })
        .then(function (result) {
          el.classList.remove("mermaid-pending");
          el.innerHTML = result && result.svg ? result.svg : "";
          if (typeof el.querySelectorAll === "function") {
            el.querySelectorAll("svg").forEach(normalizeSvg);
          }
        })
        .catch(function (err) {
          console.warn("Mermaid diagram could not be rendered", { source: source, error: err });
          renderError(el, source);
        });
    });

    return Promise.all(jobs);
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

    // Only allow http/https URLs to prevent XSS via javascript: or data: URIs
    var safeUrl = url && /^https?:\/\//i.test(url) ? url : "";

    var card = document.createElement(safeUrl ? "a" : "div");
    card.className = "link-preview-card";
    if (safeUrl) {
      card.href = safeUrl;
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


  ns.renderTemplateOrBlocks = renderTemplateOrBlocks;
  ns.renderBlock = renderBlock;
  ns.runMermaid = runMermaid;
  ns.broadcastThemeToIframes = broadcastThemeToIframes;
  ns.renderHTML = renderHTML;
  ns.renderMermaid = renderMermaid;
})(window.SynapseCanvas);
