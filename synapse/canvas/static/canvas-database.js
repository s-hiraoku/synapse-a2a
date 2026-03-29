(function(ns) {
  "use strict";

  ns._dbCurrentDb = ns._dbCurrentDb || "";
  ns._dbCurrentTable = ns._dbCurrentTable || "";
  ns._dbOffset = ns._dbOffset || 0;
  ns._dbLimit = ns._dbLimit || 50;
  ns._dbTotal = ns._dbTotal || 0;

  async function loadDatabaseList() {
    var tree = document.getElementById("db-tree");
    if (!tree) return;
    try {
      var resp = await fetch("/api/db/list");
      var dbs = await resp.json();
      tree.innerHTML = "";
      for (var i = 0; i < dbs.length; i++) {
        var db = dbs[i];
        var group = document.createElement("div");
        group.className = "db-tree-group";

        var label = document.createElement("div");
        label.className = "db-tree-db";
        var icon = document.createElement("i");
        icon.className = "ph ph-hard-drives";
        label.appendChild(icon);
        var nameSpan = document.createElement("span");
        nameSpan.textContent = db.name;
        label.appendChild(nameSpan);
        if (db.scope === "global") {
          var scopeBadge = document.createElement("span");
          scopeBadge.className = "db-tree-scope";
          scopeBadge.textContent = "global";
          label.appendChild(scopeBadge);
        }
        var sizeSpan = document.createElement("span");
        sizeSpan.className = "db-tree-size";
        sizeSpan.textContent = formatBytes(db.size);
        label.appendChild(sizeSpan);
        group.appendChild(label);

        for (var j = 0; j < db.tables.length; j++) {
          var tbl = db.tables[j];
          var tblLink = document.createElement("a");
          tblLink.className = "db-tree-table";
          tblLink.href = "#";
          tblLink.dataset.db = db.name;
          tblLink.dataset.table = tbl;
          tblLink.dataset.scope = db.scope || "project";
          var tblIcon = document.createElement("i");
          tblIcon.className = "ph ph-table";
          tblLink.appendChild(tblIcon);
          tblLink.appendChild(document.createTextNode(tbl));
          tblLink.addEventListener("click", function (ev) {
            ev.preventDefault();
            var allLinks = tree.querySelectorAll(".db-tree-table");
            for (var k = 0; k < allLinks.length; k++) allLinks[k].classList.remove("active");
            this.classList.add("active");
            loadDbTable(this.dataset.db, this.dataset.table, 0, this.dataset.scope);
          });
          group.appendChild(tblLink);
        }
        tree.appendChild(group);
      }
    } catch (e) {
      tree.innerHTML = "<div class='workflow-empty'>Failed to load databases</div>";
    }
  }

  async function loadDbTable(dbName, tableName, offset, scope) {
    ns._dbCurrentDb = dbName;
    ns._dbCurrentTable = tableName;
    ns._dbCurrentScope = scope || "project";
    ns._dbOffset = offset || 0;
    var emptyEl = document.getElementById("db-empty");
    var tableView = document.getElementById("db-table-view");
    if (emptyEl) emptyEl.classList.add("view-hidden");
    if (tableView) tableView.classList.remove("view-hidden");

    var titleEl = document.getElementById("db-table-title");
    if (titleEl) titleEl.textContent = dbName + " / " + tableName;

    try {
      var resp = await fetch("/api/db/" + encodeURIComponent(dbName) + "/" + encodeURIComponent(tableName) + "?limit=" + ns._dbLimit + "&offset=" + ns._dbOffset + "&scope=" + encodeURIComponent(ns._dbCurrentScope));
      var data = await resp.json();
      ns._dbTotal = data.total;

      var countEl = document.getElementById("db-table-count");
      if (countEl) countEl.textContent = data.total + " rows";

      var thead = document.getElementById("db-table-head");
      if (thead) {
        thead.innerHTML = "";
        var hrow = document.createElement("tr");
        for (var c = 0; c < data.columns.length; c++) {
          var th = document.createElement("th");
          th.textContent = data.columns[c];
          hrow.appendChild(th);
        }
        thead.appendChild(hrow);
      }

      var tbody = document.getElementById("db-table-body");
      if (tbody) {
        tbody.innerHTML = "";
        for (var r = 0; r < data.rows.length; r++) {
          var tr = document.createElement("tr");
          for (var c2 = 0; c2 < data.columns.length; c2++) {
            var td = document.createElement("td");
            var val = data.rows[r][data.columns[c2]];
            var text = val === null ? "" : String(val);
            td.textContent = text.length > 100 ? text.slice(0, 100) + "\u2026" : text;
            if (text.length > 100) td.title = text;
            tr.appendChild(td);
          }
          tbody.appendChild(tr);
        }
      }

      // Pagination
      var pageInfo = document.getElementById("db-page-info");
      var prevBtn = document.getElementById("db-prev-btn");
      var nextBtn = document.getElementById("db-next-btn");
      var startRow = ns._dbOffset + 1;
      var endRow = Math.min(ns._dbOffset + data.rows.length, ns._dbTotal);
      if (pageInfo) pageInfo.textContent = startRow + "-" + endRow + " / " + ns._dbTotal;
      if (prevBtn) prevBtn.disabled = ns._dbOffset <= 0;
      if (nextBtn) nextBtn.disabled = ns._dbOffset + ns._dbLimit >= ns._dbTotal;
    } catch (e) {
      var tbody2 = document.getElementById("db-table-body");
      if (tbody2) tbody2.innerHTML = "<tr><td colspan='99'>Error loading data</td></tr>";
    }
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  // Pagination buttons
  var dbPrevBtn = document.getElementById("db-prev-btn");
  var dbNextBtn = document.getElementById("db-next-btn");
  if (dbPrevBtn) dbPrevBtn.addEventListener("click", function () {
    if (ns._dbOffset > 0) loadDbTable(ns._dbCurrentDb, ns._dbCurrentTable, Math.max(0, ns._dbOffset - ns._dbLimit), ns._dbCurrentScope);
  });
  if (dbNextBtn) dbNextBtn.addEventListener("click", function () {
    if (ns._dbOffset + ns._dbLimit < ns._dbTotal) loadDbTable(ns._dbCurrentDb, ns._dbCurrentTable, ns._dbOffset + ns._dbLimit, ns._dbCurrentScope);
  });

  ns.loadDatabaseList = loadDatabaseList;
  ns.loadDbTable = loadDbTable;
})(window.SynapseCanvas);
