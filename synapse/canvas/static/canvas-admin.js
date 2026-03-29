(function(ns) {
  "use strict";

  const adminView = ns.adminView;
  const adminFeed = ns.adminFeed;
  const adminTargetBadge = ns.adminTargetBadge;
  const adminAgentsWidget = ns.adminAgentsWidget;
  const adminMessageInput = ns.adminMessageInput;
  const adminSendBtn = ns.adminSendBtn;
  const showToast = ns.showToast;
  const statusColor = ns.statusColor;
  const renderSpotlight = function() { return ns.renderSpotlight.apply(ns, arguments); };
  const renderSystemAgents = ns.renderSystemAgents;
  const escapeHtml = ns.escapeHtml;
  const canvasView = ns.canvasView;
  const isEditableTarget = ns.isEditableTarget;
  const getSortedCards = ns.getSortedCards;
  let _adminSending = false;

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
      selectedId: ns._selectedAdminTarget,
      onRowClick: function(agent) {
        ns._selectedAdminTarget = agent.agent_id;
        ns._selectedAdminName = agent.name || agent.agent_id;
        if (adminTargetBadge) {
          adminTargetBadge.textContent = ns._selectedAdminName;
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
    // Escape: dismiss context menu first, then spotlight nav
    if (e.key === "Escape") {
      hideAgentContextMenu();
      if (
        ns.currentRoute === "canvas" && canvasView &&
        !canvasView.classList.contains("view-hidden") &&
        ns._spotlightManualIndex >= 0
      ) {
        ns._spotlightManualIndex = -1;
        ns._spotlightManualCardId = "";
        e.preventDefault();
        renderSpotlight();
      }
      return;
    }

    if (
      ns.currentRoute !== "canvas" ||
      !canvasView ||
      canvasView.classList.contains("view-hidden") ||
      isEditableTarget(document.activeElement)
    ) {
      return;
    }

    const sortedCards = getSortedCards();
    if (sortedCards.length <= 1) return;

    if (e.key === "ArrowRight") {
      var nextIndex = ns._spotlightManualIndex < 0 ? 1 : ns._spotlightManualIndex + 1;
      if (nextIndex < sortedCards.length) {
        ns._spotlightManualIndex = nextIndex;
        ns._spotlightManualCardId = sortedCards[nextIndex].card_id;
        e.preventDefault();
        renderSpotlight();
      }
    } else if (e.key === "ArrowLeft") {
      if (ns._spotlightManualIndex > 0) {
        ns._spotlightManualIndex -= 1;
        ns._spotlightManualCardId = sortedCards[ns._spotlightManualIndex].card_id;
        e.preventDefault();
        renderSpotlight();
      } else if (ns._spotlightManualIndex < 0) {
        // Enter manual mode at current card (index 0)
        ns._spotlightManualIndex = 0;
        ns._spotlightManualCardId = sortedCards[0].card_id;
        e.preventDefault();
        renderSpotlight();
      }
    }
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
          if (ns._selectedAdminTarget === agent.agent_id) {
            ns._selectedAdminTarget = null;
            ns._selectedAdminName = null;
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

  async function sendAdminCommand() {
    if (_adminSending) return;
    if (!adminMessageInput) return;
    var target = ns._selectedAdminTarget;
    var message = adminMessageInput.value.trim();
    if (!target || !message) return;

    _adminSending = true;
    if (adminSendBtn) adminSendBtn.disabled = true;

    var agentName = ns._selectedAdminName || target;

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

  ns.loadAdminAgents = loadAdminAgents;
  ns.sendAdminCommand = sendAdminCommand;
})(window.SynapseCanvas);
