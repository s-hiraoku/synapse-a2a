window.SynapseCanvas = window.SynapseCanvas || {};

(function (ns) {
  "use strict";

  ns._adminPollingTimers = ns._adminPollingTimers || [];
  ns._agentContextMenu = ns._agentContextMenu || null;
  ns._contextMenuTarget = ns._contextMenuTarget || null;
  ns._adminSending = ns._adminSending || false;
  ns._isComposing = ns._isComposing || false;
  ns._selectedAdminTarget = ns._selectedAdminTarget || "";
  ns._selectedAdminName = ns._selectedAdminName || "";
  ns._adminInitialized = ns._adminInitialized || false;

  ns.adminFeed = ns.adminFeed || document.getElementById("admin-feed");
  ns.adminTargetBadge = ns.adminTargetBadge || document.getElementById("admin-target-badge");
  ns.adminAgentsWidget = ns.adminAgentsWidget || document.getElementById("admin-agents-widget");
  ns.adminMessageInput = ns.adminMessageInput || document.getElementById("admin-message-input");
  ns.adminSendBtn = ns.adminSendBtn || document.getElementById("admin-send-btn");
  ns.adminSplitter = ns.adminSplitter || document.getElementById("admin-splitter");

  ns.loadAdminAgents = async function loadAdminAgents() {
    try {
      var resp = await fetch("/api/admin/agents");
      var data = await resp.json();
      var agents = data.agents || [];
      ns.renderAdminAgentsWidget(agents);
    } catch (e) {
      console.error("Failed to load admin agents:", e);
    }
  };

  ns.renderAdminAgentsWidget = function renderAdminAgentsWidget(agents) {
    if (!ns.adminAgentsWidget) return;

    var existingWrap = ns.adminAgentsWidget.querySelector(".admin-agents-table-wrap");
    if (existingWrap) existingWrap.remove();

    var content = ns.renderSystemAgents(agents, {
      selectedId: ns._selectedAdminTarget,
      onRowClick: function (agent) {
        ns._selectedAdminTarget = agent.agent_id;
        ns._selectedAdminName = agent.name || agent.agent_id;
        if (ns.adminTargetBadge) {
          ns.adminTargetBadge.textContent = ns._selectedAdminName;
          ns.adminTargetBadge.classList.add("has-target");
        }
        if (ns.adminMessageInput) ns.adminMessageInput.focus();
      },
      onRowDblClick: function (agent) {
        ns.jumpToAgent(agent.agent_id);
      },
      onRowContextMenu: function (agent, e) {
        ns.showAgentContextMenu(agent, e);
      },
    });
    content.className = "admin-agents-table-wrap";
    ns.adminAgentsWidget.appendChild(content);
  };

  ns.createAgentContextMenu = function createAgentContextMenu() {
    var menu = document.createElement("div");
    menu.className = "agent-context-menu";

    var killItem = document.createElement("div");
    killItem.className = "agent-context-menu-item danger";
    var icon = document.createElement("i");
    icon.className = "ph ph-trash";
    killItem.appendChild(icon);
    killItem.appendChild(document.createTextNode(" Kill Agent"));
    killItem.addEventListener("click", function (e) {
      e.stopPropagation();
      var target = ns._contextMenuTarget;
      ns.hideAgentContextMenu();
      if (target) ns.killAgent(target);
    });
    menu.appendChild(killItem);

    document.body.appendChild(menu);
    return menu;
  };

  ns.showAgentContextMenu = function showAgentContextMenu(agent, e) {
    e.preventDefault();
    e.stopPropagation();
    if (!ns._agentContextMenu) ns._agentContextMenu = ns.createAgentContextMenu();
    ns._contextMenuTarget = agent;

    var menu = ns._agentContextMenu;
    menu.style.display = "block";

    var menuRect = menu.getBoundingClientRect();
    var x = e.clientX;
    var y = e.clientY;
    if (x + menuRect.width > window.innerWidth) x = window.innerWidth - menuRect.width - 8;
    if (y + menuRect.height > window.innerHeight) y = window.innerHeight - menuRect.height - 8;
    if (x < 0) x = 8;
    if (y < 0) y = 8;
    menu.style.left = x + "px";
    menu.style.top = y + "px";
  };

  ns.hideAgentContextMenu = function hideAgentContextMenu() {
    if (!ns._agentContextMenu || ns._agentContextMenu.style.display === "none") return;
    ns._agentContextMenu.style.display = "none";
    ns._contextMenuTarget = null;
  };

  ns.showConfirmModal = function showConfirmModal(options) {
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
      if (e.key === "Escape") {
        e.stopImmediatePropagation();
        close();
        if (options.onCancel) options.onCancel();
      }
    }
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) {
        close();
        if (options.onCancel) options.onCancel();
      }
    });
    cancelBtn.addEventListener("click", function () {
      close();
      if (options.onCancel) options.onCancel();
    });
    confirmBtn.addEventListener("click", function () {
      close();
      if (options.onConfirm) options.onConfirm();
    });

    confirmBtn.focus();
  };

  ns.killAgent = function killAgent(agent) {
    var agentLabel = agent.name || agent.agent_id;
    ns.showConfirmModal({
      title: "Kill Agent",
      body:
        'Are you sure you want to kill "' +
        agentLabel +
        '"? This will send SIGTERM to the agent process.',
      confirmLabel: "Kill",
      cancelLabel: "Cancel",
      danger: true,
      icon: "ph ph-trash",
      onConfirm: function () {
        ns.executeKillAgent(agent);
      },
    });
  };

  ns.executeKillAgent = function executeKillAgent(agent) {
    fetch("/api/admin/agents/" + encodeURIComponent(agent.agent_id), { method: "DELETE" })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        if (data.status === "stopped") {
          ns.showToast("Agent killed", agent.name || agent.agent_id);
          if (ns._selectedAdminTarget === agent.agent_id) {
            ns._selectedAdminTarget = "";
            ns._selectedAdminName = "";
            if (ns.adminTargetBadge) {
              ns.adminTargetBadge.textContent = "";
              ns.adminTargetBadge.classList.remove("has-target");
            }
          }
          ns.loadAdminAgents();
        } else {
          ns.showToast("Kill failed: " + (data.status || data.error || "unknown"), agent.name || agent.agent_id);
        }
      })
      .catch(function () {
        ns.showToast("Kill failed: network error", agent.name || agent.agent_id);
      });
  };

  ns.jumpToAgent = function jumpToAgent(agentId) {
    fetch("/api/admin/jump/" + encodeURIComponent(agentId), { method: "POST" })
      .then(function (resp) {
        return resp.json();
      })
      .then(function (data) {
        if (data.ok) {
          ns.showToast("Jumped to terminal", agentId);
        } else {
          ns.showToast("Jump failed: " + (data.error || "unknown"), agentId);
        }
      })
      .catch(function () {
        ns.showToast("Jump failed: network error", agentId);
      });
  };

  ns.createAdminBubble = function createAdminBubble(role, text, agentName) {
    var bubble = document.createElement("div");
    bubble.className = "admin-bubble admin-bubble-" + role;
    var header = document.createElement("div");
    header.className = "admin-bubble-header";
    var headerName = document.createElement("span");
    headerName.textContent = role === "user" ? "You" : agentName || "Agent";
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
  };

  ns.addAdminBubble = function addAdminBubble(role, text, agentName) {
    if (!ns.adminFeed) return;
    var bubble = ns.createAdminBubble(role, text, agentName);
    ns.adminFeed.appendChild(bubble);
    ns.adminFeed.scrollTop = ns.adminFeed.scrollHeight;
  };

  ns.addAdminSpinner = function addAdminSpinner() {
    if (!ns.adminFeed) return null;
    var spinner = document.createElement("div");
    spinner.className = "admin-spinner";
    spinner.id = "admin-active-spinner";
    spinner.innerHTML = '<span class="admin-spinner-dot"></span> Waiting for response...';
    ns.adminFeed.appendChild(spinner);
    ns.adminFeed.scrollTop = ns.adminFeed.scrollHeight;
    return spinner;
  };

  ns.removeAdminSpinner = function removeAdminSpinner() {
    var el = document.getElementById("admin-active-spinner");
    if (el) el.remove();
  };

  ns.pollAdminTask = function pollAdminTask(taskId, target, agentName) {
    var attempts = 0;
    var maxAttempts = 150;
    var polling = true;

    async function poll() {
      if (!polling) return;
      attempts++;
      if (attempts > maxAttempts) {
        polling = false;
        ns.removeAdminSpinner();
        ns.addAdminBubble("agent", "Timeout: No response after 5 minutes", agentName);
        return;
      }
      try {
        var resp = await fetch("/api/admin/replies/" + encodeURIComponent(taskId));
        var data = await resp.json();
        if (data.status === "completed" || data.status === "DONE") {
          polling = false;
          ns.removeAdminSpinner();
          ns.addAdminBubble("agent", data.output || "Task completed", agentName);
          return;
        } else if (data.status === "failed" || data.status === "error") {
          polling = false;
          ns.removeAdminSpinner();
          ns.addAdminBubble("agent", "Failed: " + (data.error || "Unknown error"), agentName);
          return;
        }
      } catch (e) {
        console.warn("[Admin] Poll error:", e);
      }
      var delay = attempts < 10 ? 1000 : 2000;
      setTimeout(poll, delay);
    }

    setTimeout(poll, 500);
  };

  ns.sendAdminCommand = async function sendAdminCommand() {
    if (ns._adminSending) return;
    if (!ns.adminMessageInput) return;

    var target = ns._selectedAdminTarget;
    var message = ns.adminMessageInput.value.trim();
    if (!target || !message) return;

    ns._adminSending = true;
    if (ns.adminSendBtn) ns.adminSendBtn.disabled = true;

    var agentName = ns._selectedAdminName || target;

    ns.adminMessageInput.value = "";
    ns.adminMessageInput.style.height = "auto";

    ns.addAdminBubble("user", message, null);
    ns.addAdminSpinner();

    try {
      var resp = await fetch("/api/admin/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: target, message: message }),
      });
      var data = await resp.json();
      if (!resp.ok) {
        ns.removeAdminSpinner();
        ns.addAdminBubble("agent", "Error: " + (data.detail || "Failed to send"), agentName);
        return;
      }
      ns.pollAdminTask(data.task_id, target, agentName);
    } catch (e) {
      ns.removeAdminSpinner();
      ns.addAdminBubble("agent", "Error: " + e.message, agentName);
    } finally {
      ns._adminSending = false;
      if (ns.adminSendBtn) ns.adminSendBtn.disabled = false;
    }
  };

  ns.initAdminView = function initAdminView() {
    if (ns._adminInitialized) return;
    ns._adminInitialized = true;

    if (!ns.adminSplitter || !ns.adminAgentsWidget) return;

    var adminContainer = document.getElementById("admin-container");
    var adminInputBar = document.getElementById("admin-input-bar");
    var storageKey = "canvas-admin-agents-height";
    var minH = 80;

    try {
      var saved = parseInt(localStorage.getItem(storageKey), 10);
      if (isFinite(saved)) {
        ns.adminAgentsWidget.style.height = Math.max(minH, saved) + "px";
        ns.adminAgentsWidget.classList.add("splitter-resized");
      }
    } catch (e) {
      // ignore
    }

    var startY = 0;
    var startHeight = 0;

    function getMaxHeight() {
      if (!adminContainer) return 400;
      var inputH = adminInputBar ? adminInputBar.offsetHeight : 0;
      return adminContainer.clientHeight - inputH - ns.adminSplitter.offsetHeight - minH;
    }

    function clamp(v) {
      return Math.max(minH, Math.min(v, getMaxHeight()));
    }

    function onMouseMove(e) {
      var delta = e.clientY - startY;
      ns.adminAgentsWidget.style.height = clamp(startHeight + delta) + "px";
    }

    function onMouseUp() {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.classList.remove("splitter-dragging");
      ns.adminSplitter.classList.remove("dragging");
      ns.adminAgentsWidget.classList.add("splitter-resized");
      var h = clamp(parseInt(ns.adminAgentsWidget.style.height, 10));
      if (isFinite(h)) {
        try {
          localStorage.setItem(storageKey, h);
        } catch (e) {
          // ignore
        }
      }
    }

    ns.adminSplitter.addEventListener("mousedown", function (e) {
      e.preventDefault();
      startY = e.clientY;
      startHeight = ns.adminAgentsWidget.offsetHeight;
      document.body.classList.add("splitter-dragging");
      ns.adminSplitter.classList.add("dragging");
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    ns.adminSplitter.addEventListener("keydown", function (e) {
      var step = e.shiftKey ? 20 : 5;
      var current = ns.adminAgentsWidget.offsetHeight;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        ns.adminAgentsWidget.style.height = clamp(current + step) + "px";
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        ns.adminAgentsWidget.style.height = clamp(current - step) + "px";
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        ns.adminAgentsWidget.classList.add("splitter-resized");
        var kh = clamp(parseInt(ns.adminAgentsWidget.style.height, 10));
        if (isFinite(kh)) {
          try {
            localStorage.setItem(storageKey, kh);
          } catch (e2) {
            // ignore
          }
        }
      }
    });

    document.addEventListener("click", function () {
      ns.hideAgentContextMenu();
    });
    document.addEventListener("contextmenu", function () {
      ns.hideAgentContextMenu();
    });
    window.addEventListener(
      "scroll",
      function () {
        ns.hideAgentContextMenu();
      },
      true
    );
    window.addEventListener("resize", function () {
      ns.hideAgentContextMenu();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        ns.hideAgentContextMenu();
      }
    });

    if (ns.adminSendBtn) ns.adminSendBtn.addEventListener("click", ns.sendAdminCommand);

    function autoResizeAdminInput() {
      if (!ns.adminMessageInput) return;
      ns.adminMessageInput.style.height = "auto";
      ns.adminMessageInput.style.height = Math.min(ns.adminMessageInput.scrollHeight, 120) + "px";
    }

    if (ns.adminMessageInput) {
      ns.adminMessageInput.addEventListener("compositionstart", function () {
        ns._isComposing = true;
      });
      ns.adminMessageInput.addEventListener("compositionend", function () {
        ns._isComposing = false;
      });
      ns.adminMessageInput.addEventListener("input", autoResizeAdminInput);
      ns.adminMessageInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && e.metaKey && !ns._isComposing) {
          e.preventDefault();
          ns.sendAdminCommand();
        }
      });
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ns.initAdminView, { once: true });
  } else {
    ns.initAdminView();
  }
})(window.SynapseCanvas);
