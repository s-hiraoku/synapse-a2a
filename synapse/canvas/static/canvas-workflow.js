window.SynapseCanvas = window.SynapseCanvas || {};

(function (ns) {
  "use strict";

  ns._workflowData = ns._workflowData || [];
  ns._workflowRuns = ns._workflowRuns || [];
  ns._selectedWorkflow = ns._selectedWorkflow || null;
  ns._workflowProjectDir = ns._workflowProjectDir || "";
  ns._workflowRunPollingTimer = ns._workflowRunPollingTimer || 0;
  ns._workflowInitialized = ns._workflowInitialized || false;

  ns.workflowListPanel = ns.workflowListPanel || document.getElementById("workflow-list-panel");
  ns.workflowSplitter = ns.workflowSplitter || document.getElementById("workflow-splitter");
  ns.workflowDetailPanel = ns.workflowDetailPanel || document.getElementById("workflow-detail-panel");
  ns.workflowDetailEmpty = ns.workflowDetailEmpty || document.getElementById("workflow-detail-empty");
  ns.workflowDetailContent = ns.workflowDetailContent || document.getElementById("workflow-detail-content");

  ns.loadWorkflows = async function loadWorkflows() {
    try {
      var resp = await fetch("/api/workflow");
      var data = await resp.json();
      ns._workflowData = data.workflows || [];
      ns._workflowProjectDir = data.project_dir || "";
      ns.renderWorkflowList(ns._workflowData);
      ns.loadWorkflowRuns();
    } catch (e) {
      // ignore
    }
  };

  ns.loadWorkflowRuns = async function loadWorkflowRuns() {
    try {
      var resp = await fetch("/api/workflow/runs");
      var data = await resp.json();
      ns._workflowRuns = data.runs || [];
      if (ns._selectedWorkflow) ns.renderWorkflowDetail(ns._selectedWorkflow);
    } catch (e) {
      // ignore
    }
  };

  ns.renderWorkflowList = function renderWorkflowList(workflows) {
    if (!ns.workflowListPanel) return;

    var existingWrap = ns.workflowListPanel.querySelector(".workflow-list-table-wrap");
    if (existingWrap) existingWrap.remove();

    var wrap = document.createElement("div");
    wrap.className = "workflow-list-table-wrap";

    if (!workflows.length) {
      wrap.innerHTML = '<div class="workflow-empty">No workflows defined</div>';
      ns.workflowListPanel.appendChild(wrap);
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
      if (ns._selectedWorkflow && ns._selectedWorkflow.name === wf.name) {
        tr.classList.add("workflow-row-selected");
      }
      tr.innerHTML =
        "<td>" + ns.escapeHtml(wf.name) + "</td>" +
        "<td>" + wf.step_count + "</td>" +
        "<td>" + ns.escapeHtml(wf.scope) + "</td>" +
        "<td>" + ns.escapeHtml(wf.description || "") + "</td>";
      tr.addEventListener("click", function () {
        ns._selectedWorkflow = wf;
        ns.renderWorkflowList(workflows);
        ns.renderWorkflowDetail(wf);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    ns.workflowListPanel.appendChild(wrap);
  };

  ns.renderWorkflowDetail = function renderWorkflowDetail(wf) {
    if (!ns.workflowDetailContent || !ns.workflowDetailEmpty) return;

    ns.workflowDetailEmpty.classList.add("view-hidden");
    ns.workflowDetailContent.classList.remove("view-hidden");
    ns.workflowDetailContent.innerHTML = "";

    var header = document.createElement("div");
    header.style.marginBottom = "var(--sp-3)";
    header.innerHTML =
      "<h3 style='margin:0 0 var(--sp-1) 0;'>" + ns.escapeHtml(wf.name) + "</h3>" +
      (wf.description
        ? "<p style='margin:0; color:var(--color-text-muted); font-size:var(--text-sm);'>" +
          ns.escapeHtml(wf.description) +
          "</p>"
        : "");
    ns.workflowDetailContent.appendChild(header);

    if (wf.steps && wf.steps.length > 1) {
      function mermaidEscape(str) {
        return str.replace(/"/g, "#quot;").replace(/[[\](){}]/g, " ").replace(/\//g, "#sol;");
      }

      var mermaidSrc = "graph TD\n";
      wf.steps.forEach(function (s, i) {
        var msg = s.message.length > 30 ? s.message.substring(0, 30) + "…" : s.message;
        var label = "Step " + (i + 1) + ": " + mermaidEscape(s.target) + "<br/>" + mermaidEscape(msg);
        mermaidSrc += '  S' + i + '["' + label + '"]\n';
        if (i > 0) {
          var mode = s.response_mode || "notify";
          mermaidSrc += "  S" + (i - 1) + " -->|" + mode + "| S" + i + "\n";
        }
      });

      var flowDiv = document.createElement("div");
      flowDiv.className = "workflow-step-flow";
      var mermaidDiv = document.createElement("pre");
      mermaidDiv.className = "mermaid-pending mermaid";
      mermaidDiv.dataset.mermaidSource = mermaidSrc;
      mermaidDiv.textContent = mermaidSrc;
      flowDiv.appendChild(mermaidDiv);
      ns.workflowDetailContent.appendChild(flowDiv);
      ns.runMermaid(".workflow-step-flow .mermaid-pending");
    }

    var activeRun = ns._workflowRuns.find(function (r) {
      return r.workflow_name === wf.name;
    });
    var stepsDiv = document.createElement("div");
    (wf.steps || []).forEach(function (s, i) {
      var stepStatus = "pending";
      var stepIcon = "\u23f3";
      if (activeRun && activeRun.steps[i]) {
        stepStatus = activeRun.steps[i].status;
        if (stepStatus === "running") stepIcon = "\ud83d\udd04";
        else if (stepStatus === "completed") stepIcon = "\u2705";
        else if (stepStatus === "failed") stepIcon = "\u274c";
      }
      var item = document.createElement("div");
      item.className = "workflow-step-item";
      var errorHtml = "";
      if (stepStatus === "failed" && activeRun && activeRun.steps[i] && activeRun.steps[i].error) {
        errorHtml = '<div class="workflow-step-error">' + ns.escapeHtml(activeRun.steps[i].error) + "</div>";
      }
      var outputHtml = "";
      if (
        stepStatus === "completed" &&
        activeRun &&
        activeRun.steps[i] &&
        activeRun.steps[i].output
      ) {
        outputHtml =
          '<details class="workflow-step-output"><summary>Output</summary><pre>' +
          ns.escapeHtml(activeRun.steps[i].output) +
          "</pre></details>";
      }
      var durationHtml = "";
      if (
        activeRun &&
        activeRun.steps[i] &&
        activeRun.steps[i].started_at &&
        activeRun.steps[i].completed_at
      ) {
        var dur = Math.round((activeRun.steps[i].completed_at - activeRun.steps[i].started_at) * 10) / 10;
        durationHtml = '<span class="workflow-step-duration">' + dur + "s</span>";
      }
      item.innerHTML =
        '<span class="workflow-step-icon">' + stepIcon + "</span>" +
        '<div class="workflow-step-body">' +
          '<div class="workflow-step-header">' +
            '<span class="workflow-step-target">' + ns.escapeHtml(s.target) + "</span>" +
            '<span class="workflow-step-message">' + ns.escapeHtml(s.message) + "</span>" +
            '<span class="workflow-step-mode">' + ns.escapeHtml(s.response_mode || "notify") + "</span>" +
            durationHtml +
          "</div>" +
          errorHtml +
          outputHtml +
        "</div>";
      stepsDiv.appendChild(item);
    });
    ns.workflowDetailContent.appendChild(stepsDiv);

    var runBar = document.createElement("div");
    runBar.className = "workflow-run-bar";
    var isRunning = activeRun && activeRun.status === "running";
    var runBtn = document.createElement("button");
    runBtn.className = "workflow-run-btn";
    runBtn.disabled = isRunning;
    runBtn.innerHTML = isRunning
      ? '<i class="ph ph-spinner"></i> Running...'
      : '<i class="ph ph-play"></i> Run';
    runBtn.addEventListener("click", function () {
      if (runBtn.disabled) return;
      runBtn.disabled = true;
      runBtn.innerHTML = '<i class="ph ph-spinner"></i> Starting...';
      ns.runWorkflow(wf.name);
    });
    runBar.appendChild(runBtn);

    var ctxLabel = document.createElement("span");
    ctxLabel.className = "workflow-run-context";
    if (wf.scope === "project" && ns._workflowProjectDir) {
      var dirName = ns._workflowProjectDir.split("/").pop() || ns._workflowProjectDir;
      ctxLabel.innerHTML = '<i class="ph ph-folder-open"></i> ' + ns.escapeHtml(dirName);
      ctxLabel.title = ns._workflowProjectDir;
    } else if (wf.scope === "user") {
      ctxLabel.innerHTML = '<i class="ph ph-user"></i> User scope';
      ctxLabel.title = "~/.synapse/workflows/";
    }
    runBar.appendChild(ctxLabel);
    ns.workflowDetailContent.appendChild(runBar);

    var relatedRuns = ns._workflowRuns.filter(function (r) {
      return r.workflow_name === wf.name;
    });
    if (relatedRuns.length > 0) {
      var histDiv = document.createElement("div");
      histDiv.className = "workflow-run-history";
      histDiv.innerHTML =
        '<div style="font-size:var(--text-xs); color:var(--color-text-muted); margin-bottom:var(--sp-1);">Recent runs</div>';
      relatedRuns.slice(0, 10).forEach(function (r) {
        var item = document.createElement("div");
        item.className = "workflow-run-item";
        var statusIcon = r.status === "completed" ? "\u2705" : r.status === "failed" ? "\u274c" : "\ud83d\udd04";
        var startTime = r.started_at ? new Date(r.started_at * 1000).toLocaleTimeString() : "";
        var duration = r.completed_at && r.started_at ? Math.round(r.completed_at - r.started_at) + "s" : "...";
        var stepsCompleted = r.steps ? r.steps.filter(function (s) { return s.status === "completed"; }).length : 0;
        var stepsTotal = r.steps ? r.steps.length : 0;
        var failedStep = r.steps ? r.steps.find(function (s) { return s.status === "failed"; }) : null;
        var summary = statusIcon + " " + startTime + " (" + duration + ") — " + stepsCompleted + "/" + stepsTotal + " steps";
        if (failedStep && failedStep.error) {
          summary += " — " + failedStep.target + ": " + failedStep.error;
        }
        item.textContent = summary;
        if (r.status === "failed") item.style.color = "var(--color-danger)";
        histDiv.appendChild(item);
      });
      ns.workflowDetailContent.appendChild(histDiv);
    }
  };

  ns.runWorkflow = async function runWorkflow(name) {
    try {
      var resp = await fetch("/api/workflow/run/" + encodeURIComponent(name), { method: "POST" });
      var data = await resp.json();
      if (data.run_id) {
        clearInterval(ns._workflowRunPollingTimer);
        ns._workflowRunPollingTimer = setInterval(function () {
          ns.loadWorkflowRuns().then(function () {
            var run = ns._workflowRuns.find(function (r) {
              return r.run_id === data.run_id;
            });
            if (run && run.status !== "running") {
              clearInterval(ns._workflowRunPollingTimer);
              ns._workflowRunPollingTimer = 0;
              var label = run.status === "completed" ? "Workflow completed" : "Workflow failed";
              ns.showToast(label, run.workflow_name);
            }
          });
        }, 2000);
        ns.loadWorkflowRuns();
      }
    } catch (e) {
      // ignore
    }
  };

  ns.initWorkflowView = function initWorkflowView() {
    if (ns._workflowInitialized) return;
    ns._workflowInitialized = true;

    if (!ns.workflowSplitter || !ns.workflowListPanel) return;

    var wfContainer = document.getElementById("workflow-container");
    var storageKey = "canvas-workflow-list-height";
    var minH = 60;

    try {
      var saved = parseInt(localStorage.getItem(storageKey), 10);
      if (isFinite(saved)) {
        ns.workflowListPanel.style.height = Math.max(minH, saved) + "px";
        ns.workflowListPanel.classList.add("splitter-resized");
      }
    } catch (e) {
      // ignore
    }

    var startY = 0;
    var startHeight = 0;

    function getMaxHeight() {
      if (!wfContainer) return 400;
      return wfContainer.clientHeight - ns.workflowSplitter.offsetHeight - minH;
    }

    function clamp(v) {
      return Math.max(minH, Math.min(v, getMaxHeight()));
    }

    function onMouseMove(e) {
      var delta = e.clientY - startY;
      ns.workflowListPanel.style.height = clamp(startHeight + delta) + "px";
    }

    function onMouseUp() {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      document.body.classList.remove("splitter-dragging");
      ns.workflowSplitter.classList.remove("dragging");
      ns.workflowListPanel.classList.add("splitter-resized");
      var h = clamp(parseInt(ns.workflowListPanel.style.height, 10));
      if (isFinite(h)) {
        try {
          localStorage.setItem(storageKey, h);
        } catch (e) {
          // ignore
        }
      }
    }

    ns.workflowSplitter.addEventListener("mousedown", function (e) {
      e.preventDefault();
      startY = e.clientY;
      startHeight = ns.workflowListPanel.offsetHeight;
      document.body.classList.add("splitter-dragging");
      ns.workflowSplitter.classList.add("dragging");
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    ns.workflowSplitter.addEventListener("keydown", function (e) {
      var step = e.shiftKey ? 20 : 5;
      var current = ns.workflowListPanel.offsetHeight;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        ns.workflowListPanel.style.height = clamp(current + step) + "px";
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        ns.workflowListPanel.style.height = clamp(current - step) + "px";
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        ns.workflowListPanel.classList.add("splitter-resized");
        var kh = clamp(parseInt(ns.workflowListPanel.style.height, 10));
        if (isFinite(kh)) {
          try {
            localStorage.setItem(storageKey, kh);
          } catch (e2) {
            // ignore
          }
        }
      }
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ns.initWorkflowView, { once: true });
  } else {
    ns.initWorkflowView();
  }
})(window.SynapseCanvas);
