(function(ns) {
  "use strict";

  const workflowListPanel = ns.workflowListPanel;
  const workflowDetailEmpty = ns.workflowDetailEmpty;
  const workflowDetailContent = ns.workflowDetailContent;
  const escapeHtml = ns.escapeHtml;
  const runMermaid = function() { return ns.runMermaid.apply(ns, arguments); };
  const showToast = ns.showToast;

  
  async function loadWorkflows() {
    try {
      var resp = await fetch("/api/workflow");
      var data = await resp.json();
      ns._workflowData = data.workflows || [];
      ns._workflowProjectDir = data.project_dir || "";
      renderWorkflowList(ns._workflowData);
      loadWorkflowRuns();
    } catch (e) { /* ignore */ }
  }

  async function loadWorkflowRuns() {
    try {
      var resp = await fetch("/api/workflow/runs");
      var data = await resp.json();
      ns._workflowRuns = data.runs || [];
      if (ns._selectedWorkflow) renderWorkflowDetail(ns._selectedWorkflow);
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
      if (ns._selectedWorkflow && ns._selectedWorkflow.name === wf.name) {
        tr.classList.add("workflow-row-selected");
      }
      tr.innerHTML =
        "<td>" + escapeHtml(wf.name) + "</td>" +
        "<td>" + wf.step_count + "</td>" +
        "<td>" + escapeHtml(wf.scope) + "</td>" +
        "<td>" + escapeHtml(wf.description || "") + "</td>";
      tr.addEventListener("click", function () {
        ns._selectedWorkflow = wf;
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
      function mermaidEscape(str) {
        // Escape characters that break Mermaid label parsing
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
      workflowDetailContent.appendChild(flowDiv);
      runMermaid(".workflow-step-flow .mermaid-pending");
    }

    // Steps with status
    var activeRun = ns._workflowRuns.find(function (r) { return r.workflow_name === wf.name; });
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
      var errorHtml = "";
      if (stepStatus === "failed" && activeRun && activeRun.steps[i] && activeRun.steps[i].error) {
        errorHtml = '<div class="workflow-step-error">' + escapeHtml(activeRun.steps[i].error) + "</div>";
      }
      var outputHtml = "";
      if (stepStatus === "completed" && activeRun && activeRun.steps[i] && activeRun.steps[i].output) {
        outputHtml = '<details class="workflow-step-output"><summary>Output</summary><pre>' + escapeHtml(activeRun.steps[i].output) + "</pre></details>";
      }
      var durationHtml = "";
      if (activeRun && activeRun.steps[i] && activeRun.steps[i].started_at && activeRun.steps[i].completed_at) {
        var dur = Math.round((activeRun.steps[i].completed_at - activeRun.steps[i].started_at) * 10) / 10;
        durationHtml = '<span class="workflow-step-duration">' + dur + "s</span>";
      }
      item.innerHTML =
        '<span class="workflow-step-icon">' + stepIcon + "</span>" +
        '<div class="workflow-step-body">' +
          '<div class="workflow-step-header">' +
            '<span class="workflow-step-target">' + escapeHtml(s.target) + "</span>" +
            '<span class="workflow-step-message">' + escapeHtml(s.message) + "</span>" +
            '<span class="workflow-step-mode">' + escapeHtml(s.response_mode || "notify") + "</span>" +
            durationHtml +
          "</div>" +
          errorHtml +
          outputHtml +
        "</div>";
      stepsDiv.appendChild(item);
    });
    workflowDetailContent.appendChild(stepsDiv);

    // Run bar (button + project context)
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
      runWorkflow(wf.name);
    });
    runBar.appendChild(runBtn);
    // Show execution context (scope + project dir)
    var ctxLabel = document.createElement("span");
    ctxLabel.className = "workflow-run-context";
    if (wf.scope === "project" && ns._workflowProjectDir) {
      var dirName = ns._workflowProjectDir.split("/").pop() || ns._workflowProjectDir;
      ctxLabel.innerHTML = '<i class="ph ph-folder-open"></i> ' + escapeHtml(dirName);
      ctxLabel.title = ns._workflowProjectDir;
    } else if (wf.scope === "user") {
      ctxLabel.innerHTML = '<i class="ph ph-user"></i> User scope';
      ctxLabel.title = "~/.synapse/workflows/";
    }
    runBar.appendChild(ctxLabel);
    workflowDetailContent.appendChild(runBar);

    // Run history
    var relatedRuns = ns._workflowRuns.filter(function (r) { return r.workflow_name === wf.name; });
    if (relatedRuns.length > 0) {
      var histDiv = document.createElement("div");
      histDiv.className = "workflow-run-history";
      histDiv.innerHTML = '<div style="font-size:var(--text-xs); color:var(--color-text-muted); margin-bottom:var(--sp-1);">Recent runs</div>';
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
      workflowDetailContent.appendChild(histDiv);
    }
  }

  async function runWorkflow(name) {
    try {
      var resp = await fetch("/api/workflow/run/" + encodeURIComponent(name), { method: "POST" });
      var data = await resp.json();
      if (data.run_id) {
        // Start polling for updates
        clearInterval(ns._workflowRunPollingTimer);
        ns._workflowRunPollingTimer = setInterval(function () {
          loadWorkflowRuns().then(function () {
            var run = ns._workflowRuns.find(function (r) { return r.run_id === data.run_id; });
            if (run && run.status !== "running") {
              clearInterval(ns._workflowRunPollingTimer);
              ns._workflowRunPollingTimer = 0;
              var label = run.status === "completed" ? "Workflow completed" : "Workflow failed";
              showToast(label, run.workflow_name);
            }
          });
        }, 2000);
        loadWorkflowRuns();
      }
    } catch (e) { /* ignore */ }
  }

  ns.loadWorkflows = loadWorkflows;
  ns.loadWorkflowRuns = loadWorkflowRuns;
  ns.renderWorkflowList = renderWorkflowList;
  ns.renderWorkflowDetail = renderWorkflowDetail;
})(window.SynapseCanvas);
