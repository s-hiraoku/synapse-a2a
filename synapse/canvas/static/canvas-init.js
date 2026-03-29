(function(ns) {
  "use strict";

  const adminSplitter = ns.adminSplitter;
  const adminAgentsWidget = ns.adminAgentsWidget;
  const workflowSplitter = ns.workflowSplitter;
  const workflowListPanel = ns.workflowListPanel;

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

  function initWorkflowSplitter() {
    if (!workflowSplitter || !workflowListPanel) return;
    var wfContainer = document.getElementById("workflow-container");
    var storageKey = "canvas-workflow-list-height";
    var minH = 60;

    // Restore saved height
    try {
      var saved = parseInt(localStorage.getItem(storageKey), 10);
      if (isFinite(saved)) {
        workflowListPanel.style.height = Math.max(minH, saved) + "px";
        workflowListPanel.classList.add("splitter-resized");
      }
    } catch (e) { /* ignore */ }

    var startY = 0;
    var startHeight = 0;

    function getMaxHeight() {
      if (!wfContainer) return 400;
      return wfContainer.clientHeight - workflowSplitter.offsetHeight - minH;
    }

    function clamp(v) {
      return Math.max(minH, Math.min(v, getMaxHeight()));
    }

    function onMouseMove(e) {
      var delta = e.clientY - startY;
      workflowListPanel.style.height = clamp(startHeight + delta) + "px";
    }

    function onMouseUp() {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.classList.remove("splitter-dragging");
      workflowSplitter.classList.remove("dragging");
      workflowListPanel.classList.add("splitter-resized");
      var h = clamp(parseInt(workflowListPanel.style.height, 10));
      if (isFinite(h)) { try { localStorage.setItem(storageKey, h); } catch (e) { /* ignore */ } }
    }

    workflowSplitter.addEventListener("mousedown", function (e) {
      e.preventDefault();
      startY = e.clientY;
      startHeight = workflowListPanel.offsetHeight;
      document.body.classList.add("splitter-dragging");
      workflowSplitter.classList.add("dragging");
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    // Keyboard support
    workflowSplitter.addEventListener("keydown", function (e) {
      var step = e.shiftKey ? 20 : 5;
      var current = workflowListPanel.offsetHeight;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        workflowListPanel.style.height = clamp(current + step) + "px";
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        workflowListPanel.style.height = clamp(current - step) + "px";
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        workflowListPanel.classList.add("splitter-resized");
        var kh = clamp(parseInt(workflowListPanel.style.height, 10));
        if (isFinite(kh)) { try { localStorage.setItem(storageKey, kh); } catch (e2) { /* ignore */ } }
      }
    });
  }


  ns.initAdminSplitter = initAdminSplitter;
  ns.initWorkflowSplitter = initWorkflowSplitter;

  ns.initTheme();
  ns.loadCards();
  ns.loadSystemPanel();
  ns.connectSSE();
  window.setInterval(ns.loadSystemPanel, 10000);
  initAdminSplitter();
  initWorkflowSplitter();
  ns.navigate();
})(window.SynapseCanvas);
