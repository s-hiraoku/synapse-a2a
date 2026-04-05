(function(ns) {
  "use strict";

  var wikiEnabledState = null;
  var pagesCache = {};
  var statsCache = {};
  var pageCache = {};

  var knowledgeState = {
    scope: "project",
    type: "",
    search: "",
    sort: "updated",
    pages: [],
    stats: null,
    selectedSlug: "",
  };

  var TYPE_ICONS = {
    entity: "\ud83c\udff7",
    concept: "\ud83d\udca1",
    decision: "\u2696",
    comparison: "\ud83d\udd04",
    synthesis: "\ud83d\udcca",
  };

  function ensureKnowledgeShell() {
    var existing = document.getElementById("knowledge-view");
    if (existing) return existing;

    var section = document.createElement("section");
    section.id = "knowledge-view";
    section.className = "view-hidden knowledge-view";
    var shell = document.createElement("div");
    shell.className = "knowledge-shell";
    section.appendChild(shell);

    var mainContent = document.getElementById("main-content");
    var before = document.getElementById("database-view")
      || document.getElementById("admin-view")
      || null;
    if (mainContent) {
      mainContent.insertBefore(section, before);
    }
    return section;
  }

  function getKnowledgeShell() {
    var view = ensureKnowledgeShell();
    return view ? view.firstElementChild : null;
  }

  function getKnowledgeNavLink() {
    return document.querySelector('.nav-link[data-route="knowledge"]');
  }

  async function fetchJSON(url) {
    var resp = await fetch(url);
    if (!resp.ok) {
      throw new Error("Request failed: " + resp.status);
    }
    return resp.json();
  }

  function normalizeBooleanEnabled(data) {
    if (typeof data === "boolean") return data;
    if (data && typeof data.enabled === "boolean") return data.enabled;
    return Boolean(data);
  }

  async function checkWikiEnabled() {
    if (wikiEnabledState !== null) return wikiEnabledState;
    try {
      var data = await fetchJSON("/api/wiki/enabled");
      wikiEnabledState = normalizeBooleanEnabled(data);
    } catch (err) {
      wikiEnabledState = false;
      if (ns.showToast) ns.showToast("Knowledge unavailable", err.message);
    }
    syncKnowledgeNav();
    return wikiEnabledState;
  }

  function syncKnowledgeNav() {
    var link = getKnowledgeNavLink();
    if (!link) return;
    if (wikiEnabledState === false) link.classList.add("knowledge-nav-hidden");
    else link.classList.remove("knowledge-nav-hidden");
  }

  function getPagesPayload(data) {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.pages)) return data.pages;
    return [];
  }

  async function fetchWikiPages(scope) {
    if (pagesCache[scope]) return pagesCache[scope];
    var data = await fetchJSON("/api/wiki?scope=" + encodeURIComponent(scope));
    var pages = getPagesPayload(data);
    pagesCache[scope] = pages;
    return pages;
  }

  async function fetchWikiStats(scope) {
    if (statsCache[scope]) return statsCache[scope];
    var stats = await fetchJSON("/api/wiki/stats?scope=" + encodeURIComponent(scope));
    statsCache[scope] = stats || {};
    return statsCache[scope];
  }

  async function fetchWikiPage(scope, slug) {
    var key = scope + ":" + slug;
    if (pageCache[key]) return pageCache[key];
    var data = await fetchJSON("/api/wiki/" + encodeURIComponent(scope) + "/pages/" + encodeURIComponent(slug));
    pageCache[key] = data || {};
    return pageCache[key];
  }

  function getPageType(page) {
    return String(page.page_type || page.type || "entity").toLowerCase();
  }

  function getPageTitle(page) {
    if (page.title) return String(page.title);
    if (page.filename) return String(page.filename).replace(/\.[^.]+$/, "");
    if (page.slug) return String(page.slug).replace(/[-_]+/g, " ");
    return "Untitled";
  }

  function getPageSummary(page) {
    var body = String(page.body || page.content || "");
    var firstLine = body.split("\n").find(function(line) { return line.trim(); });
    return firstLine || "No summary available.";
  }

  function getRelativeTime(ts) {
    if (!ts) return "";
    return ns.formatTimeShort ? ns.formatTimeShort(String(ts)) : String(ts);
  }

  function getAbsoluteTime(ts) {
    if (!ts) return "";
    return ns.formatTime ? ns.formatTime(String(ts)) : String(ts);
  }

  function getPageSlug(page) {
    if (page.slug) return String(page.slug);
    return getPageTitle(page).trim().toLowerCase().replace(/\s+/g, "-");
  }

  function sortPages(pages, sort) {
    var list = pages.slice();
    list.sort(function(a, b) {
      if (sort === "title") {
        return getPageTitle(a).localeCompare(getPageTitle(b));
      }
      if (sort === "links") {
        return Number(b.link_count || 0) - Number(a.link_count || 0);
      }
      if (sort === "sources") {
        return Number(b.source_count || 0) - Number(a.source_count || 0);
      }
      return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
    });
    return list;
  }

  function renderEmptyState(title, detail) {
    var empty = document.createElement("div");
    empty.className = "knowledge-panel knowledge-empty";
    empty.innerHTML = "<strong>" + ns.escapeHtml(title) + "</strong><span>" + ns.escapeHtml(detail) + "</span>";
    return empty;
  }

  function buildFilterControl(className, tagName) {
    var wrap = document.createElement("label");
    wrap.className = "knowledge-filter-control " + className;
    var control = document.createElement(tagName);
    wrap.appendChild(control);
    return { wrap: wrap, control: control };
  }

  function renderKnowledgeView(pages, stats, scope) {
    var shell = getKnowledgeShell();
    if (!shell) return;
    shell.innerHTML = "";

    var tabs = document.createElement("div");
    tabs.className = "knowledge-panel knowledge-tabs";
    ["project", "global"].forEach(function(tabScope) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "knowledge-tab" + (tabScope === scope ? " active" : "");
      btn.textContent = tabScope.charAt(0).toUpperCase() + tabScope.slice(1);
      btn.addEventListener("click", function() {
        if (knowledgeState.scope === tabScope) return;
        knowledgeState.scope = tabScope;
        knowledgeState.selectedSlug = "";
        loadKnowledgeView();
      });
      tabs.appendChild(btn);
    });
    shell.appendChild(tabs);

    var statsRow = document.createElement("div");
    statsRow.className = "knowledge-panel knowledge-stats";
    [
      { label: "Pages", value: String(stats.page_count != null ? stats.page_count : pages.length) },
      { label: "Sources", value: String(stats.source_count != null ? stats.source_count : sumCounts(pages, "source_count")) },
      { label: "Updated", value: getRelativeTime(stats.last_updated || stats.updated_at) || "No activity" },
    ].forEach(function(item) {
      var stat = document.createElement("div");
      stat.className = "knowledge-stat-item";
      stat.innerHTML =
        '<span class="knowledge-stat-label">' + ns.escapeHtml(item.label) + "</span>" +
        '<span class="knowledge-stat-value">' + ns.escapeHtml(item.value) + "</span>";
      statsRow.appendChild(stat);
    });
    shell.appendChild(statsRow);

    var filters = document.createElement("div");
    filters.className = "knowledge-panel knowledge-filters";

    var typeFilter = buildFilterControl("knowledge-type-filter", "select");
    [
      { value: "", label: "All types" },
      { value: "entity", label: "Entity" },
      { value: "concept", label: "Concept" },
      { value: "decision", label: "Decision" },
      { value: "comparison", label: "Comparison" },
      { value: "synthesis", label: "Synthesis" },
    ].forEach(function(optionData) {
      var option = document.createElement("option");
      option.value = optionData.value;
      option.textContent = optionData.label;
      if (knowledgeState.type === optionData.value) option.selected = true;
      typeFilter.control.appendChild(option);
    });
    typeFilter.control.addEventListener("change", function() {
      knowledgeState.type = this.value;
      knowledgeState.selectedSlug = "";
      renderKnowledgeView(knowledgeState.pages, knowledgeState.stats || {}, knowledgeState.scope);
    });
    filters.appendChild(typeFilter.wrap);

    var searchFilter = buildFilterControl("knowledge-search", "input");
    searchFilter.control.type = "search";
    searchFilter.control.placeholder = "Search pages";
    searchFilter.control.value = knowledgeState.search;
    searchFilter.control.addEventListener("input", function() {
      knowledgeState.search = this.value;
      knowledgeState.selectedSlug = "";
      renderKnowledgeView(knowledgeState.pages, knowledgeState.stats || {}, knowledgeState.scope);
    });
    filters.appendChild(searchFilter.wrap);

    var sortFilter = buildFilterControl("knowledge-sort", "select");
    [
      { value: "updated", label: "Recently updated" },
      { value: "title", label: "Title" },
      { value: "links", label: "Most links" },
      { value: "sources", label: "Most sources" },
    ].forEach(function(optionData) {
      var option = document.createElement("option");
      option.value = optionData.value;
      option.textContent = optionData.label;
      if (knowledgeState.sort === optionData.value) option.selected = true;
      sortFilter.control.appendChild(option);
    });
    sortFilter.control.addEventListener("change", function() {
      knowledgeState.sort = this.value;
      knowledgeState.selectedSlug = "";
      renderKnowledgeView(knowledgeState.pages, knowledgeState.stats || {}, knowledgeState.scope);
    });
    filters.appendChild(sortFilter.wrap);

    shell.appendChild(filters);

    if (!pages.length) {
      shell.appendChild(renderEmptyState("No knowledge pages", "The selected scope does not have any indexed wiki pages yet."));
      return;
    }

    var main = document.createElement("div");
    main.className = "knowledge-main";
    main.appendChild(renderPageList(pages, knowledgeState.type, knowledgeState.search, knowledgeState.sort));
    main.appendChild(renderActivityLog(stats.recent_activity || []));
    shell.appendChild(main);
  }

  function renderPageList(pages, filter, search, sort) {
    var panel = document.createElement("div");
    panel.className = "knowledge-panel knowledge-page-list";

    var normalizedSearch = String(search || "").trim().toLowerCase();
    var filtered = pages.filter(function(page) {
      var matchesType = !filter || getPageType(page) === filter;
      if (!matchesType) return false;
      if (!normalizedSearch) return true;
      var haystack = [
        getPageTitle(page),
        getPageSummary(page),
        String(page.slug || ""),
      ].join("\n").toLowerCase();
      return haystack.indexOf(normalizedSearch) !== -1;
    });

    var sorted = sortPages(filtered, sort);
    if (!sorted.length) {
      panel.appendChild(renderEmptyState("No matching pages", "Adjust the type filter or search query to see more results."));
      return panel;
    }

    sorted.forEach(function(page) {
      var card = document.createElement("button");
      card.type = "button";
      card.className = "knowledge-page-card";
      var type = getPageType(page);
      var slug = getPageSlug(page);
      card.innerHTML =
        '<span class="knowledge-page-type-icon">' + (TYPE_ICONS[type] || TYPE_ICONS.entity) + "</span>" +
        '<div class="knowledge-page-copy">' +
          '<h3 class="knowledge-page-title">' + ns.escapeHtml(getPageTitle(page)) + "</h3>" +
          '<div class="knowledge-page-summary">' + ns.escapeHtml(getPageSummary(page)) + "</div>" +
          '<div class="knowledge-page-meta">' +
            "<span>" + ns.escapeHtml(String(page.link_count || 0)) + " links</span>" +
            "<span>" + ns.escapeHtml(String(page.source_count || 0)) + " sources</span>" +
            "<span>" + ns.escapeHtml(getRelativeTime(page.updated_at || page.modified_at) || "Unknown") + "</span>" +
          "</div>" +
        "</div>";
      card.addEventListener("click", function() {
        openKnowledgePage(slug);
      });
      panel.appendChild(card);
    });

    return panel;
  }

  function normalizeSources(pageData) {
    if (Array.isArray(pageData.sources)) return pageData.sources;
    if (pageData.metadata && Array.isArray(pageData.metadata.sources)) return pageData.metadata.sources;
    return [];
  }

  function normalizeWikiLinks(pageData) {
    if (Array.isArray(pageData.wikilinks)) return pageData.wikilinks;
    if (Array.isArray(pageData.links)) return pageData.links;
    return [];
  }

  function linkifyWikiNodes(root) {
    if (!root || typeof NodeFilter === "undefined") return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    var replacements = [];
    while (walker.nextNode()) {
      var node = walker.currentNode;
      if (node.nodeValue && node.nodeValue.indexOf("[[") !== -1) replacements.push(node);
    }
    replacements.forEach(function(node) {
      var parts = String(node.nodeValue).split(/(\[\[[^[\]]+\]\])/g);
      if (parts.length === 1) return;
      var fragment = document.createDocumentFragment();
      parts.forEach(function(part) {
        var match = part.match(/^\[\[([^[\]]+)\]\]$/);
        if (!match) {
          fragment.appendChild(document.createTextNode(part));
          return;
        }
        var label = match[1];
        var link = document.createElement("a");
        link.href = "#";
        link.className = "wiki-link";
        link.dataset.slug = label.trim();
        link.textContent = label;
        link.addEventListener("click", function(ev) {
          ev.preventDefault();
          openKnowledgePage(this.dataset.slug);
        });
        fragment.appendChild(link);
      });
      node.parentNode.replaceChild(fragment, node);
    });
  }

  function renderPageDetail(pageData) {
    var shell = getKnowledgeShell();
    if (!shell) return;
    var main = shell.querySelector(".knowledge-main");
    if (!main) return;
    main.className = "knowledge-main knowledge-main-single";
    main.innerHTML = "";

    var panel = document.createElement("div");
    panel.className = "knowledge-panel knowledge-detail";

    var back = document.createElement("button");
    back.type = "button";
    back.className = "knowledge-detail-back";
    back.textContent = "\u2190 Back to list";
    back.addEventListener("click", function() {
      knowledgeState.selectedSlug = "";
      renderKnowledgeView(knowledgeState.pages, knowledgeState.stats || {}, knowledgeState.scope);
    });
    panel.appendChild(back);

    var header = document.createElement("div");
    header.className = "knowledge-detail-header";
    header.innerHTML =
      '<div><div class="knowledge-type-badge">' +
        (TYPE_ICONS[getPageType(pageData)] || TYPE_ICONS.entity) + " " +
        ns.escapeHtml(getPageType(pageData)) +
      '</div><h2 class="knowledge-detail-title">' + ns.escapeHtml(getPageTitle(pageData)) + "</h2></div>";
    panel.appendChild(header);

    var body = document.createElement("div");
    body.className = "knowledge-detail-body";
    body.appendChild(ns.renderBlock({ format: "markdown", body: String(pageData.body || pageData.content || "") }));
    linkifyWikiNodes(body);
    panel.appendChild(body);

    var wikilinks = normalizeWikiLinks(pageData);
    if (wikilinks.length) {
      var linksSection = document.createElement("div");
      linksSection.className = "knowledge-detail-links";
      linksSection.innerHTML = '<h3 class="knowledge-section-title">Wikilinks</h3>';
      var list = document.createElement("ul");
      list.className = "knowledge-links-list";
      wikilinks.forEach(function(item) {
        var slug = typeof item === "string" ? item : String(item.slug || item.title || "");
        var label = typeof item === "string" ? item : String(item.title || item.slug || "");
        var li = document.createElement("li");
        li.className = "knowledge-link-item";
        var link = document.createElement("a");
        link.href = "#";
        link.className = "wiki-link";
        link.dataset.slug = slug;
        link.textContent = label;
        link.addEventListener("click", function(ev) {
          ev.preventDefault();
          openKnowledgePage(this.dataset.slug);
        });
        li.appendChild(link);
        list.appendChild(li);
      });
      linksSection.appendChild(list);
      panel.appendChild(linksSection);
    }

    var sources = normalizeSources(pageData);
    if (sources.length) {
      var sourcesSection = document.createElement("div");
      sourcesSection.className = "knowledge-detail-sources";
      sourcesSection.innerHTML = '<h3 class="knowledge-section-title">Sources</h3>';
      var sourceList = document.createElement("ul");
      sourceList.className = "knowledge-source-list";
      sources.forEach(function(source) {
        var li = document.createElement("li");
        li.className = "knowledge-source-item";
        if (typeof source === "string") {
          li.textContent = source;
        } else {
          var label = String(source.title || source.url || source.path || "Source");
          if (source.url) {
            var anchor = document.createElement("a");
            anchor.href = source.url;
            anchor.target = "_blank";
            anchor.rel = "noopener";
            anchor.textContent = label;
            li.appendChild(anchor);
          } else {
            li.textContent = label;
          }
        }
        sourceList.appendChild(li);
      });
      sourcesSection.appendChild(sourceList);
      panel.appendChild(sourcesSection);
    }

    var metadata = pageData.metadata || {};
    var footer = document.createElement("div");
    footer.className = "knowledge-detail-footer";
    [
      ["Confidence", metadata.confidence || pageData.confidence],
      ["Author", metadata.author || pageData.author],
      ["Created", getAbsoluteTime(metadata.created_at || pageData.created_at)],
      ["Updated", getAbsoluteTime(metadata.updated_at || pageData.updated_at)],
    ].forEach(function(item) {
      if (!item[1]) return;
      var span = document.createElement("span");
      span.textContent = item[0] + ": " + item[1];
      footer.appendChild(span);
    });
    if (footer.childNodes.length) panel.appendChild(footer);

    main.appendChild(panel);
  }

  function renderActivityLog(activities) {
    var panel = document.createElement("div");
    panel.className = "knowledge-panel knowledge-activity";

    var title = document.createElement("h3");
    title.className = "knowledge-section-title";
    title.textContent = "Recent Activity";
    panel.appendChild(title);

    if (!activities.length) {
      panel.appendChild(renderEmptyState("No recent activity", "Updates from the knowledge log will appear here."));
      return panel;
    }

    activities.forEach(function(activity) {
      var item = document.createElement("div");
      item.className = "knowledge-activity-item";

      var timestamp = document.createElement("span");
      timestamp.className = "knowledge-activity-timestamp";
      timestamp.textContent = getRelativeTime(activity.timestamp || activity.updated_at || activity.created_at) || "Unknown";
      item.appendChild(timestamp);

      var op = document.createElement("span");
      op.className = "knowledge-activity-op";
      op.textContent = String(activity.operation || activity.op || "update");
      item.appendChild(op);

      var detail = document.createElement("div");
      detail.className = "knowledge-activity-detail";
      detail.textContent = String(activity.detail || activity.message || activity.path || "");
      item.appendChild(detail);

      panel.appendChild(item);
    });

    return panel;
  }

  async function openKnowledgePage(slug) {
    try {
      knowledgeState.selectedSlug = slug;
      var page = await fetchWikiPage(knowledgeState.scope, slug);
      renderPageDetail(page);
    } catch (err) {
      if (ns.showToast) ns.showToast("Knowledge page failed", err.message);
    }
  }

  async function loadKnowledgeView() {
    ensureKnowledgeShell();
    var shell = getKnowledgeShell();
    if (!shell) return;

    shell.innerHTML = "";
    var enabled = await checkWikiEnabled();
    if (!enabled) {
      shell.appendChild(renderEmptyState("Wiki is not enabled", "Enable the wiki backend to browse project and global knowledge pages."));
      return;
    }

    try {
      var scope = knowledgeState.scope || "project";
      var results = await Promise.all([
        fetchWikiPages(scope),
        fetchWikiStats(scope),
      ]);
      knowledgeState.pages = results[0];
      knowledgeState.stats = results[1] || {};
      renderKnowledgeView(knowledgeState.pages, knowledgeState.stats, scope);
      if (knowledgeState.selectedSlug) {
        openKnowledgePage(knowledgeState.selectedSlug);
      }
    } catch (err) {
      shell.appendChild(renderEmptyState("Knowledge failed to load", err.message));
      if (ns.showToast) ns.showToast("Knowledge failed to load", err.message);
    }
  }

  function sumCounts(items, key) {
    return items.reduce(function(total, item) {
      return total + Number(item[key] || 0);
    }, 0);
  }

  ensureKnowledgeShell();
  checkWikiEnabled();

  ns.fetchWikiPages = fetchWikiPages;
  ns.fetchWikiStats = fetchWikiStats;
  ns.fetchWikiPage = fetchWikiPage;
  ns.loadKnowledgeView = loadKnowledgeView;
  ns.renderKnowledgeView = renderKnowledgeView;
  ns.renderPageList = renderPageList;
  ns.renderPageDetail = renderPageDetail;
  ns.renderActivityLog = renderActivityLog;
})(window.SynapseCanvas);
