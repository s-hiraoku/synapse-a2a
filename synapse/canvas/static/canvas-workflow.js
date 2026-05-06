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
    var existingToolbar = workflowListPanel.querySelector(".workflow-toolbar");
    if (existingToolbar) existingToolbar.remove();
    var existingWrap = workflowListPanel.querySelector(".workflow-list-table-wrap");
    if (existingWrap) existingWrap.remove();

    workflowListPanel.appendChild(buildWorkflowToolbar());

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

  function buildWorkflowToolbar() {
    var toolbar = document.createElement("div");
    toolbar.className = "workflow-toolbar";

    var createBtn = document.createElement("button");
    createBtn.className = "workflow-run-btn workflow-create-btn";
    createBtn.innerHTML = '<i class="ph ph-plus"></i> New';
    createBtn.addEventListener("click", function () {
      showWorkflowEditor(null);
    });
    toolbar.appendChild(createBtn);

    var importBtn = document.createElement("button");
    importBtn.className = "workflow-run-btn workflow-import-btn";
    importBtn.innerHTML = '<i class="ph ph-upload-simple"></i> Import YAML';
    importBtn.addEventListener("click", function () {
      showWorkflowImportEditor();
    });
    toolbar.appendChild(importBtn);

    return toolbar;
  }

  function renderWorkflowDetail(wf) {
    if (!workflowDetailContent || !workflowDetailEmpty) return;
    workflowDetailEmpty.classList.add("view-hidden");
    workflowDetailContent.classList.remove("view-hidden");
    workflowDetailContent.innerHTML = "";

    var header = document.createElement("div");
    header.className = "workflow-detail-header";
    header.style.marginBottom = "var(--sp-3)";
    var titleWrap = document.createElement("div");
    titleWrap.innerHTML =
      "<h3 style='margin:0 0 var(--sp-1) 0;'>" + escapeHtml(wf.name) + "</h3>" +
      (wf.description ? "<p style='margin:0; color:var(--color-text-muted); font-size:var(--text-sm);'>" + escapeHtml(wf.description) + "</p>" : "");
    header.appendChild(titleWrap);
    header.appendChild(buildWorkflowDetailActions(wf));
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
        var nodeId = s.id || ("S" + i);
        var label = (s.id || ("Step " + (i + 1))) + ": " + mermaidEscape(s.target) + "<br/>" + mermaidEscape(msg);
        mermaidSrc += '  S' + i + '["' + label + '"]\n';
        if (Array.isArray(s.depends_on) && s.depends_on.length) {
          s.depends_on.forEach(function (dep) {
            var depIndex = wf.steps.findIndex(function (candidate, candidateIndex) {
              return (candidate.id || ("S" + candidateIndex)) === dep;
            });
            if (depIndex >= 0) {
              var condition = s.condition || "all_success";
              mermaidSrc += "  S" + depIndex + " -->|" + condition + "| S" + i + "\n";
            }
          });
        } else if (i > 0 && !nodeId) {
          var mode = s.response_mode || "notify";
          mermaidSrc += "  S" + (i - 1) + " -->|" + mode + "| S" + i + "\n";
        } else if (i > 0 && !wf.steps.some(function (step) { return Array.isArray(step.depends_on) && step.depends_on.length; })) {
          var linearMode = s.response_mode || "notify";
          mermaidSrc += "  S" + (i - 1) + " -->|" + linearMode + "| S" + i + "\n";
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

  function buildWorkflowDetailActions(wf) {
    var actions = document.createElement("div");
    actions.className = "workflow-detail-actions";

    var editBtn = document.createElement("button");
    editBtn.className = "workflow-run-btn workflow-edit-btn";
    editBtn.innerHTML = '<i class="ph ph-pencil-simple"></i> Edit';
    editBtn.addEventListener("click", function () {
      showWorkflowEditor(wf);
    });
    actions.appendChild(editBtn);

    var exportBtn = document.createElement("button");
    exportBtn.className = "workflow-run-btn workflow-export-btn";
    exportBtn.innerHTML = '<i class="ph ph-download-simple"></i> Export YAML';
    exportBtn.addEventListener("click", function () {
      downloadWorkflowYaml(wf);
    });
    actions.appendChild(exportBtn);

    var deleteBtn = document.createElement("button");
    deleteBtn.className = "workflow-run-btn workflow-delete-btn";
    deleteBtn.innerHTML = '<i class="ph ph-trash"></i> Delete';
    deleteBtn.addEventListener("click", async function () {
      if (!confirm("Delete workflow '" + wf.name + "'?")) return;
      var resp = await fetch("/api/workflow/" + encodeURIComponent(wf.name), {
        method: "DELETE",
      });
      if (resp.ok) {
        ns._selectedWorkflow = null;
        if (workflowDetailContent) workflowDetailContent.classList.add("view-hidden");
        if (workflowDetailEmpty) workflowDetailEmpty.classList.remove("view-hidden");
        showToast("Workflow deleted", wf.name);
        await loadWorkflows();
      }
    });
    actions.appendChild(deleteBtn);

    return actions;
  }

  function showWorkflowEditor(wf) {
    if (!workflowDetailContent || !workflowDetailEmpty) return;
    workflowDetailEmpty.classList.add("view-hidden");
    workflowDetailContent.classList.remove("view-hidden");
    workflowDetailContent.innerHTML = "";

    var isEdit = !!wf;
    var editor = document.createElement("div");
    editor.className = "workflow-editor";

    var heading = document.createElement("h3");
    heading.textContent = isEdit ? "Edit Workflow" : "New Workflow";
    editor.appendChild(heading);

    var nameLabel = document.createElement("label");
    nameLabel.className = "workflow-editor-field";
    nameLabel.textContent = "Name";
    var nameInput = document.createElement("input");
    nameInput.className = "workflow-editor-name";
    nameInput.value = wf ? wf.name : "";
    nameInput.disabled = isEdit;
    nameLabel.appendChild(nameInput);
    editor.appendChild(nameLabel);

    var descLabel = document.createElement("label");
    descLabel.className = "workflow-editor-field";
    descLabel.textContent = "Description";
    var descInput = document.createElement("textarea");
    descInput.className = "workflow-editor-description";
    descInput.value = wf ? (wf.description || "") : "";
    descLabel.appendChild(descInput);
    editor.appendChild(descLabel);

    var stepsContainer = document.createElement("div");
    stepsContainer.className = "workflow-step-editor-list";
    var steps = wf && wf.steps && wf.steps.length ? wf.steps : [{ response_mode: "notify" }];
    steps.forEach(function (step) {
      addWorkflowStepEditorRow(stepsContainer, step);
    });
    editor.appendChild(stepsContainer);

    var addStepBtn = document.createElement("button");
    addStepBtn.className = "workflow-run-btn workflow-add-step-btn";
    addStepBtn.innerHTML = '<i class="ph ph-plus"></i> Add step';
    addStepBtn.addEventListener("click", function () {
      addWorkflowStepEditorRow(stepsContainer, { response_mode: "notify" });
    });
    editor.appendChild(addStepBtn);

    var actions = document.createElement("div");
    actions.className = "workflow-editor-actions";
    var saveBtn = document.createElement("button");
    saveBtn.className = "workflow-run-btn workflow-save-btn";
    saveBtn.innerHTML = '<i class="ph ph-floppy-disk"></i> Save';
    saveBtn.addEventListener("click", async function () {
      var payload = collectWorkflowEditorPayload(editor);
      if (!payload.name || !payload.steps.length) {
        showToast("Workflow requires a name and at least one step", "");
        return;
      }
      var url = isEdit ? "/api/workflow/" + encodeURIComponent(wf.name) : "/api/workflow";
      var method = isEdit ? "PUT" : "POST";
      var resp = await fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (resp.ok) {
        var data = await resp.json();
        ns._selectedWorkflow = data.workflow || payload;
        showToast(isEdit ? "Workflow updated" : "Workflow created", payload.name);
        await loadWorkflows();
        renderWorkflowDetail(ns._selectedWorkflow);
      }
    });
    actions.appendChild(saveBtn);

    var cancelBtn = document.createElement("button");
    cancelBtn.className = "workflow-run-btn workflow-cancel-btn";
    cancelBtn.textContent = "Cancel";
    cancelBtn.addEventListener("click", function () {
      if (wf) renderWorkflowDetail(wf);
      else {
        workflowDetailContent.classList.add("view-hidden");
        workflowDetailEmpty.classList.remove("view-hidden");
      }
    });
    actions.appendChild(cancelBtn);
    editor.appendChild(actions);

    workflowDetailContent.appendChild(editor);
  }

  function addWorkflowStepEditorRow(container, step) {
    var row = document.createElement("div");
    row.className = "workflow-step-editor-row";

    var idInput = document.createElement("input");
    idInput.className = "workflow-step-id-input";
    idInput.placeholder = "id";
    idInput.value = step.id || "";
    row.appendChild(idInput);

    var targetInput = document.createElement("input");
    targetInput.className = "workflow-step-target-input";
    targetInput.placeholder = "target";
    targetInput.value = step.target || "";
    row.appendChild(targetInput);

    var messageInput = document.createElement("textarea");
    messageInput.className = "workflow-step-message-input";
    messageInput.placeholder = "message";
    messageInput.value = step.message || "";
    row.appendChild(messageInput);

    var modeInput = document.createElement("select");
    modeInput.className = "workflow-step-mode-input";
    ["notify", "wait", "silent"].forEach(function (mode) {
      var opt = document.createElement("option");
      opt.value = mode;
      opt.textContent = mode;
      if ((step.response_mode || "notify") === mode) opt.selected = true;
      modeInput.appendChild(opt);
    });
    modeInput.value = step.response_mode || "notify";
    row.appendChild(modeInput);

    var dependsInput = document.createElement("input");
    dependsInput.className = "workflow-step-depends-input";
    dependsInput.placeholder = "depends_on";
    dependsInput.value = Array.isArray(step.depends_on) ? step.depends_on.join(",") : "";
    row.appendChild(dependsInput);

    var removeBtn = document.createElement("button");
    removeBtn.className = "workflow-run-btn workflow-remove-step-btn";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", function () {
      if (container.children.length > 1) row.remove();
    });
    row.appendChild(removeBtn);

    container.appendChild(row);
  }

  function collectWorkflowEditorPayload(editor) {
    var rows = editor.querySelectorAll(".workflow-step-editor-row");
    var steps = [];
    rows.forEach(function (row) {
      var target = row.querySelector(".workflow-step-target-input").value.trim();
      var message = row.querySelector(".workflow-step-message-input").value.trim();
      var step = {
        id: row.querySelector(".workflow-step-id-input").value.trim(),
        target: target,
        message: message,
        response_mode: row.querySelector(".workflow-step-mode-input").value || "notify",
        depends_on: row.querySelector(".workflow-step-depends-input").value
          .split(",")
          .map(function (v) { return v.trim(); })
          .filter(Boolean),
      };
      if (target || message) steps.push(step);
    });
    return {
      name: editor.querySelector(".workflow-editor-name").value.trim(),
      description: editor.querySelector(".workflow-editor-description").value.trim(),
      steps: steps,
    };
  }

  function showWorkflowImportEditor() {
    if (!workflowDetailContent || !workflowDetailEmpty) return;
    workflowDetailEmpty.classList.add("view-hidden");
    workflowDetailContent.classList.remove("view-hidden");
    workflowDetailContent.innerHTML = "";

    var editor = document.createElement("div");
    editor.className = "workflow-editor workflow-import-editor";
    var title = document.createElement("h3");
    title.textContent = "Import Workflow YAML";
    editor.appendChild(title);
    var textarea = document.createElement("textarea");
    textarea.className = "workflow-import-yaml";
    textarea.placeholder = "name: review\nsteps:\n  - target: claude\n    message: Review the patch";
    editor.appendChild(textarea);
    var saveBtn = document.createElement("button");
    saveBtn.className = "workflow-run-btn workflow-import-save-btn";
    saveBtn.textContent = "Import";
    saveBtn.addEventListener("click", async function () {
      var payload = parseWorkflowText(textarea.value);
      var resp = await fetch("/api/workflow", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (resp.ok) {
        var data = await resp.json();
        ns._selectedWorkflow = data.workflow || payload;
        showToast("Workflow imported", payload.name);
        await loadWorkflows();
        renderWorkflowDetail(ns._selectedWorkflow);
      }
    });
    editor.appendChild(saveBtn);
    workflowDetailContent.appendChild(editor);
  }

  function parseWorkflowText(text) {
    var trimmed = String(text || "").trim();
    if (trimmed.charAt(0) === "{") return JSON.parse(trimmed);
    var payload = { name: "", description: "", steps: [] };
    var currentStep = null;
    trimmed.split(/\r?\n/).forEach(function (line) {
      var m;
      if ((m = line.match(/^name:\s*(.*)$/))) payload.name = unquoteYaml(m[1]);
      else if ((m = line.match(/^description:\s*(.*)$/))) payload.description = unquoteYaml(m[1]);
      else if ((m = line.match(/^\s*-\s*target:\s*(.*)$/))) {
        currentStep = { target: unquoteYaml(m[1]), message: "", response_mode: "notify" };
        payload.steps.push(currentStep);
      } else if (currentStep && (m = line.match(/^\s*message:\s*(.*)$/))) currentStep.message = unquoteYaml(m[1]);
      else if (currentStep && (m = line.match(/^\s*response_mode:\s*(.*)$/))) currentStep.response_mode = unquoteYaml(m[1]);
      else if (currentStep && (m = line.match(/^\s*id:\s*(.*)$/))) currentStep.id = unquoteYaml(m[1]);
    });
    return payload;
  }

  function unquoteYaml(value) {
    return String(value || "").trim().replace(/^['"]|['"]$/g, "");
  }

  function workflowToYaml(wf) {
    var lines = ["name: " + wf.name];
    if (wf.description) lines.push("description: " + wf.description);
    lines.push("steps:");
    (wf.steps || []).forEach(function (step) {
      if (step.id) lines.push("  - id: " + step.id);
      else lines.push("  - target: " + (step.target || ""));
      if (step.id) lines.push("    target: " + (step.target || ""));
      lines.push("    message: " + (step.message || ""));
      lines.push("    response_mode: " + (step.response_mode || "notify"));
      if (Array.isArray(step.depends_on) && step.depends_on.length) {
        lines.push("    depends_on: [" + step.depends_on.join(", ") + "]");
      }
    });
    return lines.join("\n") + "\n";
  }

  function downloadWorkflowYaml(wf) {
    var blob = new Blob([workflowToYaml(wf)], { type: "text/yaml" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = wf.name + ".yaml";
    if (a.click) a.click();
    URL.revokeObjectURL(url);
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
