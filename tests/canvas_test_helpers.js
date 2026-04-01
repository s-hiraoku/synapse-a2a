const fs = require("fs");
const vm = require("node:vm");

const _JS_FILES = [
  "canvas-core.js",
  "canvas-renderers.js",
  "canvas-system.js",
  "canvas-spotlight.js",
  "canvas-admin.js",
  "canvas-workflow.js",
  "canvas-database.js",
  "canvas-init.js",
];
const source = _JS_FILES
  .map((f) => fs.readFileSync("synapse/canvas/static/" + f, "utf8"))
  .join("\n");

// This simple brace-counting extractor assumes the target function body does not
// contain unmatched braces inside strings, template literals, or comments.
// That is acceptable for the current canvas.js helpers, but it may fail on other
// inputs with braces in single-line or multi-line comments or embedded strings.
// A robust fix would require a real parser or tokenizer.
function extractFunction(name) {
  const start = source.indexOf(`function ${name}(`);
  if (start === -1) {
    throw new Error(`Function not found: ${name}`);
  }
  let braceIndex = source.indexOf("{", start);
  let depth = 0;
  for (let i = braceIndex; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "{") depth += 1;
    if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        return source.slice(start, i + 1);
      }
    }
  }
  throw new Error(`Unbalanced function: ${name}`);
}

class Style {
  constructor() {
    this._values = {};
  }

  setProperty(name, value) {
    this._values[name] = value;
  }

  removeProperty(name) {
    delete this._values[name];
  }
}

class Element {
  constructor(tagName, document) {
    this.tagName = tagName.toUpperCase();
    this.document = document;
    this.children = [];
    this.parentNode = null;
    this.className = "";
    this.textContent = "";
    this.id = "";
    this.style = new Style();
    this.dataset = {};
    this._innerHTML = "";
    this.offsetWidth = 0;
    this._listeners = {};
    this.classList = {
      add: (...names) => {
        const set = new Set(this.className.split(/\s+/).filter(Boolean));
        for (const name of names) set.add(name);
        this.className = Array.from(set).join(" ");
      },
      remove: (...names) => {
        const set = new Set(this.className.split(/\s+/).filter(Boolean));
        for (const name of names) set.delete(name);
        this.className = Array.from(set).join(" ");
      },
      toggle: (name, force) => {
        const set = new Set(this.className.split(/\s+/).filter(Boolean));
        const shouldAdd = force === undefined ? !set.has(name) : force;
        if (shouldAdd) set.add(name);
        else set.delete(name);
        this.className = Array.from(set).join(" ");
      },
      contains: (name) => this.className.split(/\s+/).includes(name),
    };
  }

  setAttribute(name, value) {
    this.dataset["_attr_" + name] = String(value);
    if (name === "id") this.id = value;
  }

  getAttribute(name) {
    return this.dataset["_attr_" + name] || null;
  }

  removeAttribute(name) {
    delete this.dataset["_attr_" + name];
  }

  addEventListener(event, handler) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(handler);
  }

  appendChild(child) {
    if (child == null) return child;
    if (child.parentNode && child.parentNode !== this) {
      child.parentNode.removeChild(child);
    } else if (child.parentNode === this) {
      this.removeChild(child);
    }
    child.parentNode = this;
    this.children.push(child);
    if (child.id && this.document && this.document.elementsById) {
      this.document.elementsById.set(child.id, child);
    }
    return child;
  }

  insertBefore(child, reference) {
    if (child == null) return child;
    if (child.parentNode && child.parentNode !== this) {
      child.parentNode.removeChild(child);
    } else if (child.parentNode === this) {
      this.removeChild(child);
    }
    child.parentNode = this;
    if (reference == null) {
      this.children.push(child);
      return child;
    }
    const index = this.children.indexOf(reference);
    if (index === -1) {
      this.children.push(child);
    } else {
      this.children.splice(index, 0, child);
    }
    return child;
  }

  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) {
      this.children.splice(index, 1);
      child.parentNode = null;
    }
    return child;
  }

  replaceChildren(...nodes) {
    for (const child of [...this.children]) {
      child.parentNode = null;
    }
    this.children = [];
    for (const node of nodes) {
      this.appendChild(node);
    }
  }

  set innerHTML(value) {
    this.children = [];
    this.textContent = value;
    this._innerHTML = value;
  }

  get innerHTML() {
    return this._innerHTML;
  }

  get firstChild() {
    return this.children[0] || null;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const results = [];
    const match = (node) => {
      if (!selector.startsWith(".")) return false;
      const target = selector.slice(1);
      return node.className.split(/\s+/).includes(target);
    };
    const walk = (node) => {
      for (const child of node.children) {
        if (match(child)) results.push(child);
        walk(child);
      }
    };
    walk(this);
    return results;
  }

  get fullText() {
    let text = this.textContent || "";
    for (const child of this.children) {
      text += child.fullText || child.textContent || "";
    }
    return text;
  }
}

class TextNode {
  constructor(text) {
    this.textContent = text;
    this.fullText = text;
    this.id = "";
  }
}

class Document {
  constructor() {
    this.elementsById = new Map();
  }

  createElement(tag) {
    return new Element(tag, this);
  }

  createTextNode(text) {
    return new TextNode(text);
  }

  getElementById(id) {
    return this.elementsById.get(id) || null;
  }
}

// Stub for the SynapseCanvas namespace used by split JS modules.
// Tests that extract individual functions via extractFunction() need this
// object in scope so that `ns.*` references inside those functions resolve.
const NS_STUB_CODE = `
  var ns = {
    _systemPanelRendered: false, _lastSystemData: null, _lastSystemJSON: null,
    _dashboardRendered: false, _dashExpandState: {},
    _spotlightCardId: null, _spotlightManualIndex: -1, _spotlightManualCardId: null,
    _spotlightUpdatedAt: null, _spotlightSwapTimer: null,
    _selectedAdminTarget: null, _selectedAdminName: null, _adminPollingTimers: {},
    _adminSending: false, _workflowData: null, _workflowRuns: null,
    _selectedWorkflow: null, _workflowRunPollingTimer: null,
    _dbCurrentDb: "", _dbCurrentTable: "", _dbCurrentScope: "project",
    _dbOffset: 0, _dbLimit: 50, _dbTotal: 0,
    cards: new Map(), knownAgents: new Set(), systemAgents: [],
    currentRoute: "canvas", _sortedCardsCache: null,
    renderTemplateOrBlocks: function() {},
    renderBlock: function() { return document.createElement("div"); },
    showToast: function() {}, formatTime: function(v) { return v; },
    statusColor: function() { return "#999"; }, escapeHtml: function(s) { return s; },
    navigate: function() {}, renderAll: function() {},
    loadSystemPanel: function() {}, connectSSE: function() {},
    runMermaid: function() {}, downloadCard: function() {},
    createDownloadButton: function() { return document.createElement("button"); },
    copyCardToClipboard: function() {},
    createCopyButton: function() { var btn = document.createElement("button"); btn.className = "canvas-copy-btn"; return btn; },
    renderLiveFeed: function() {}, trackAgent: function() {},
    getFilteredCards: function() { return []; },
    getSortedCards: function() { return []; },
    cardsByRecency: function(a, b) { return 0; },
    parseContent: function(raw) { try { return JSON.parse(raw); } catch(e) { return raw; } },
    renderTemplate: function() { return null; },
    getTemplateBadgeLabel: function(card) { return ""; },
    markAsNew: function() {},
  };
`;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

module.exports = {
  source,
  extractFunction,
  NS_STUB_CODE,
  Style,
  Element,
  TextNode,
  Document,
  assert,
};
