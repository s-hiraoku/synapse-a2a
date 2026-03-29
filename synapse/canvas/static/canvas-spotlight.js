(function(ns) {
  "use strict";

  const canvasSpotlight = ns.canvasSpotlight;
  const canvasView = ns.canvasView;
  const getSortedCards = ns.getSortedCards;
  const statusColor = ns.statusColor;
  const createDownloadButton = ns.createDownloadButton;
  const getTemplateBadgeLabel = ns.getTemplateBadgeLabel;
  const parseContent = ns.parseContent;
  const renderTemplateOrBlocks = function() { return ns.renderTemplateOrBlocks.apply(ns, arguments); };
  const formatTime = ns.formatTime;
  const runMermaid = function() { return ns.runMermaid.apply(ns, arguments); };
  const syncChildren = ns.syncChildren;

  function renderSpotlight() {
    if (!canvasSpotlight) return;

    const allCards = getSortedCards();
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
      ns._spotlightCardId = "";
      ns._spotlightManualIndex = -1;
      ns._spotlightManualCardId = "";
      ns._spotlightUpdatedAt = "";
      return;
    }

    // Re-resolve manual index by card_id to survive SSE reorder
    if (ns._spotlightManualIndex >= 0 && ns._spotlightManualCardId) {
      var resolved = allCards.findIndex(function (c) { return c.card_id === ns._spotlightManualCardId; });
      ns._spotlightManualIndex = resolved >= 0 ? resolved : 0;
    }
    if (ns._spotlightManualIndex >= allCards.length) {
      ns._spotlightManualIndex = allCards.length - 1;
    }
    const spotlightIndex = ns._spotlightManualIndex >= 0 ? ns._spotlightManualIndex : 0;
    const card = allCards[spotlightIndex];

    const previousCardId = ns._spotlightCardId;
    const isSameCard = card.card_id === previousCardId;

    // Skip rebuild if the same card version is already displayed
    if (isSameCard && card.updated_at === ns._spotlightUpdatedAt) {
      return;
    }

    const agentInfo = ns.systemAgents.find(a => a.agent_id === card.agent_id);
    const agentStatus = agentInfo ? agentInfo.status : "";

    // Set ambient glow color based on agent status
    canvasView.style.setProperty("--canvas-glow", statusColor(agentStatus));

    const frame = ensureSpotlightFrame();
    frame.titleText.textContent = card.title || "Untitled";
    frame.templateBadge.textContent = getTemplateBadgeLabel(card);
    frame.templateBadge.hidden = !frame.templateBadge.textContent;
    frame.navIndicator.hidden = ns._spotlightManualIndex < 0;
    frame.navIndicator.textContent = ns._spotlightManualIndex >= 0
      ? (spotlightIndex + 1) + " / " + allCards.length
      : "";
    renderSpotlightContent(frame.content, card);
    renderSpotlightInfo(frame.infoBar, card, agentStatus);

    if (previousCardId && !isSameCard) {
      markSpotlightSwap();
    }

    ns._spotlightCardId = card.card_id;
    ns._spotlightUpdatedAt = card.updated_at;

    // Re-run mermaid
    runMermaid("#canvas-spotlight .mermaid-pending");
  }

  function ensureSpotlightFrame() {
    let titleBar = canvasSpotlight.querySelector(".canvas-title-bar");
    let titleText = titleBar ? titleBar.querySelector(".canvas-title-text") : null;
    let titleMeta = titleBar ? titleBar.querySelector(".canvas-title-meta") : null;
    let templateBadge = titleMeta ? titleMeta.querySelector(".canvas-template-badge") : null;
    let navIndicator = titleMeta ? titleMeta.querySelector(".canvas-nav-indicator") : null;
    if (!titleBar) {
      titleBar = document.createElement("div");
      titleBar.className = "canvas-title-bar";
    }
    if (!titleText) {
      titleText = document.createElement("h2");
      titleText.className = "canvas-title-text";
    }
    if (!titleMeta) {
      titleMeta = document.createElement("div");
      titleMeta.className = "canvas-title-meta";
    }
    if (!templateBadge) {
      templateBadge = document.createElement("span");
      templateBadge.className = "canvas-template-badge";
      templateBadge.hidden = true;
    }
    if (!navIndicator) {
      navIndicator = document.createElement("span");
      navIndicator.className = "canvas-nav-indicator";
      navIndicator.hidden = true;
    }
    syncChildren(titleMeta, [templateBadge, navIndicator]);
    let dlBtn = titleBar.querySelector(".canvas-dl-btn");
    if (!dlBtn) {
      dlBtn = createDownloadButton(function () { return ns._spotlightCardId; });
    }
    syncChildren(titleBar, [titleText, titleMeta, dlBtn]);

    let content = canvasSpotlight.querySelector(".canvas-content");
    if (!content) {
      content = document.createElement("div");
      content.className = "canvas-content";
    }

    let infoBar = canvasSpotlight.querySelector(".canvas-info-bar");
    if (!infoBar) {
      infoBar = document.createElement("div");
      infoBar.className = "canvas-info-bar canvas-info-bar--minimal";
    }

    syncChildren(canvasSpotlight, [titleBar, content, infoBar]);
    return { titleBar, titleText, titleMeta, templateBadge, navIndicator, content, infoBar };
  }

  function renderSpotlightContent(content, card) {
    content.innerHTML = "";
    const parsed = parseContent(card.content);
    const blocks = Array.isArray(parsed) ? parsed : [parsed];
    renderTemplateOrBlocks(content, card, blocks, false, { inCanvasView: true });
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
  }

  function markSpotlightSwap() {
    canvasSpotlight.classList.remove("spotlight-swap");
    void canvasSpotlight.offsetWidth;
    canvasSpotlight.classList.add("spotlight-swap");
    if (ns._spotlightSwapTimer) {
      window.clearTimeout(ns._spotlightSwapTimer);
    }
    ns._spotlightSwapTimer = window.setTimeout(() => {
      canvasSpotlight.classList.remove("spotlight-swap");
      ns._spotlightSwapTimer = 0;
    }, ns.SPOTLIGHT_SWAP_DELAY);
  }

  ns.renderSpotlight = renderSpotlight;
})(window.SynapseCanvas);
