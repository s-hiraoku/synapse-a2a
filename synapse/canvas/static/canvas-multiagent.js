(function(ns) {
  "use strict";

  const patternListPanel = ns.patternListPanel;
  const patternDetailEmpty = ns.patternDetailEmpty;
  const patternDetailContent = ns.patternDetailContent;
  const escapeHtml = ns.escapeHtml;
  const runMermaid = function() { return ns.runMermaid.apply(ns, arguments); };

  async function loadPatterns() {
    try {
      var resp = await fetch("/api/multiagent");
      var data = await resp.json();
      ns._patternData = data.patterns || [];
      ns._patternProjectDir = data.project_dir || "";
      renderPatternList(ns._patternData);
      if (ns._selectedPattern) {
        var selected = ns._patternData.find(function(pattern) {
          return pattern.name === ns._selectedPattern.name;
        });
        if (selected) renderPatternDetail(selected);
      }
    } catch (e) { /* ignore */ }
  }

  function renderPatternList(patterns) {
    if (!patternListPanel) return;
    var existingWrap = patternListPanel.querySelector(".workflow-list-table-wrap");
    if (existingWrap) existingWrap.remove();

    var wrap = document.createElement("div");
    wrap.className = "workflow-list-table-wrap";

    if (!patterns.length) {
      wrap.innerHTML = '<div class="workflow-empty">No multi agent patterns defined</div>';
      patternListPanel.appendChild(wrap);
      return;
    }

    var table = document.createElement("table");
    table.className = "system-agents-table";
    var thead = document.createElement("thead");
    thead.innerHTML = "<tr><th>Name</th><th>Pattern Type</th><th>Description</th><th>Scope</th></tr>";
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    patterns.forEach(function(pattern) {
      var tr = document.createElement("tr");
      tr.style.cursor = "pointer";
      if (ns._selectedPattern && ns._selectedPattern.name === pattern.name) {
        tr.classList.add("workflow-row-selected");
      }
      tr.innerHTML =
        "<td>" + escapeHtml(pattern.name || "") + "</td>" +
        "<td>" + escapeHtml(pattern.pattern || "") + "</td>" +
        "<td>" + escapeHtml(pattern.description || "") + "</td>" +
        "<td>" + escapeHtml(pattern.scope || "") + "</td>";
      tr.addEventListener("click", function() {
        ns._selectedPattern = pattern;
        renderPatternList(patterns);
        renderPatternDetail(pattern);
      });
      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    wrap.appendChild(table);
    patternListPanel.appendChild(wrap);
  }

  function renderPatternDetail(pattern) {
    if (!patternDetailContent || !patternDetailEmpty) return;
    patternDetailEmpty.classList.add("view-hidden");
    patternDetailContent.classList.remove("view-hidden");
    patternDetailContent.innerHTML = "";

    var header = document.createElement("div");
    header.style.marginBottom = "var(--sp-3)";
    header.innerHTML =
      "<h3 style='margin:0 0 var(--sp-1) 0;'>" + escapeHtml(pattern.name || "") + "</h3>" +
      (pattern.description
        ? "<p style='margin:0; color:var(--color-text-muted); font-size:var(--text-sm);'>" + escapeHtml(pattern.description) + "</p>"
        : "");
    patternDetailContent.appendChild(header);

    var meta = document.createElement("div");
    meta.className = "workflow-run-bar";
    meta.style.marginBottom = "var(--sp-2)";
    meta.innerHTML =
      '<span class="workflow-run-context"><i class="ph ph-graph"></i> ' + escapeHtml(pattern.pattern || "unknown") + "</span>";
    if (pattern.scope) {
      var scope = document.createElement("span");
      scope.className = "workflow-run-context";
      if (pattern.scope === "project" && ns._patternProjectDir) {
        var dirName = ns._patternProjectDir.split("/").pop() || ns._patternProjectDir;
        scope.innerHTML = '<i class="ph ph-folder-open"></i> ' + escapeHtml(dirName);
        scope.title = ns._patternProjectDir;
      } else {
        scope.innerHTML = '<i class="ph ph-user"></i> ' + escapeHtml(pattern.scope);
      }
      meta.appendChild(scope);
    }
    patternDetailContent.appendChild(meta);

    var mermaidWrap = document.createElement("div");
    mermaidWrap.className = "workflow-step-flow";
    var mermaidDiv = document.createElement("pre");
    var mermaidSource = generateMermaid(pattern);
    mermaidDiv.className = "mermaid-pending mermaid";
    mermaidDiv.dataset.mermaidSource = mermaidSource;
    mermaidDiv.textContent = mermaidSource;
    mermaidWrap.appendChild(mermaidDiv);
    patternDetailContent.appendChild(mermaidWrap);
    runMermaid(".workflow-step-flow .mermaid-pending");

    var configWrap = document.createElement("div");
    configWrap.className = "workflow-run-history";
    configWrap.innerHTML =
      '<div style="font-size:var(--text-xs); color:var(--color-text-muted); margin-bottom:var(--sp-1);">Configuration</div>' +
      "<pre style='margin:0; white-space:pre-wrap; word-break:break-word;'>" +
      escapeHtml(JSON.stringify(pattern, null, 2)) +
      "</pre>";
    patternDetailContent.appendChild(configWrap);
  }

  function generateMermaid(pattern) {
    var type = pattern.pattern || "";
    switch (type) {
      case "generator-verifier":
        return generateGVMermaid(pattern);
      case "orchestrator-subagent":
        return generateOSMermaid(pattern);
      case "agent-teams":
        return generateATMermaid(pattern);
      case "message-bus":
        return generateMBMermaid(pattern);
      case "shared-state":
        return generateSSMermaid(pattern);
      default:
        return "graph TD\n  A[Unknown Pattern]";
    }
  }

  function generateGVMermaid(pattern) {
    var generatorName = (pattern.generator && pattern.generator.name) || "Generator";
    var verifierName = (pattern.verifier && pattern.verifier.name) || "Verifier";
    var maxIterations = pattern.max_iterations || 3;
    return "graph LR\n" +
      '  Task["Task"] --> Gen["' + escapeHtml(generatorName) + '"]\n' +
      '  Gen -->|output| Ver["' + escapeHtml(verifierName) + '"]\n' +
      '  Ver -->|pass| Result["Result"]\n' +
      '  Ver -->|"feedback (' + maxIterations + ' max)"| Gen\n' +
      '  style Gen fill:#4a9eff,color:#fff\n' +
      '  style Ver fill:#ff6b6b,color:#fff\n';
  }

  function generateOSMermaid(pattern) {
    var orchestratorName = (pattern.orchestrator && pattern.orchestrator.name) || "Orchestrator";
    var subtasks = pattern.subtasks || [];
    var lines = "graph TD\n";
    lines += '  Task["Task"] --> Orch["' + escapeHtml(orchestratorName) + '"]\n';
    subtasks.forEach(function(subtask, i) {
      var name = subtask.name || ("Subtask " + (i + 1));
      lines += '  Orch -->|delegate| S' + i + '["' + escapeHtml(name) + '"]\n';
      lines += '  S' + i + ' -->|result| Orch\n';
    });
    lines += '  Orch --> Synth["Synthesis"]\n';
    lines += '  style Orch fill:#4a9eff,color:#fff\n';
    return lines;
  }

  function generateATMermaid(pattern) {
    var team = pattern.team || {};
    var count = team.count || 3;
    var members = team.members || [];
    var lines = "graph LR\n";
    lines += '  Queue["Task Queue"]\n';
    lines += '  Results["Results"]\n';
    for (var i = 0; i < count; i++) {
      var member = members[i] || {};
      var name = member.name || ("Worker " + (i + 1));
      lines += '  Queue --> W' + i + '["' + escapeHtml(name) + '"]\n';
      lines += '  W' + i + ' -->|done| Results\n';
    }
    lines += '  style Queue fill:#ffa726,color:#fff\n';
    return lines;
  }

  function generateMBMermaid(pattern) {
    var topics = pattern.topics || [];
    var routerName = (pattern.router && pattern.router.name) || "Router";
    var lines = "graph TD\n";
    lines += '  Event["Event"] --> Router["' + escapeHtml(routerName) + '"]\n';
    topics.forEach(function(topic, i) {
      var subscribers = topic.subscribers || [];
      subscribers.forEach(function(subscriber, j) {
        var name = subscriber.name || ("Agent " + (i + 1) + "-" + (j + 1));
        var nodeId = "A" + i + "_" + j;
        lines += '  Router -->|' + escapeHtml(topic.name || "topic") + '| ' + nodeId + '["' + escapeHtml(name) + '"]\n';
        lines += '  ' + nodeId + ' -.->|publish| Router\n';
      });
    });
    lines += '  style Router fill:#ab47bc,color:#fff\n';
    return lines;
  }

  function generateSSMermaid(pattern) {
    var agents = pattern.agents || [];
    var store = pattern.shared_store || "wiki";
    var storeLabel = store === "wiki" ? "Wiki" : "Shared Memory";
    var lines = "graph TD\n";
    lines += '  Store["' + escapeHtml(storeLabel) + '"]\n';
    agents.forEach(function(agent, i) {
      var name = agent.name || ("Agent " + (i + 1));
      lines += '  A' + i + '["' + escapeHtml(name) + '"] <-->|read/write| Store\n';
    });
    if (pattern.termination && pattern.termination.mode) {
      lines += '  Store --> Term["Termination: ' + escapeHtml(pattern.termination.mode) + '"]\n';
    }
    lines += '  style Store fill:#66bb6a,color:#fff\n';
    return lines;
  }

  ns.loadPatterns = loadPatterns;
  ns.renderPatternList = renderPatternList;
  ns.renderPatternDetail = renderPatternDetail;
})(window.SynapseCanvas);
