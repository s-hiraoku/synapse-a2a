const fs = require("fs");
const vm = require("node:vm");

const source = fs.readFileSync("synapse/canvas/static/canvas.js", "utf8");

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

class Element {
  constructor(tagName, document) {
    this.tagName = tagName.toUpperCase();
    this.document = document;
    this.children = [];
    this.parentNode = null;
    this.className = "";
    this.textContent = "";
    this.style = {};
    this.dataset = {};
    this._innerHTML = "";
    this.offsetWidth = 0;
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
    this._listeners = {};
  }

  addEventListener(event, handler) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(handler);
  }

  appendChild(child) {
    if (child == null) return child;
    child.parentNode = this;
    this.children.push(child);
    return child;
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

  removeChild(child) {
    const index = this.children.indexOf(child);
    if (index >= 0) {
      this.children.splice(index, 1);
      child.parentNode = null;
    }
    return child;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const results = [];
    const matcher = (node) => {
      if (!selector.startsWith(".")) return false;
      const target = selector.slice(1);
      return node.className.split(/\s+/).includes(target);
    };
    const walk = (node) => {
      for (const child of node.children) {
        if (matcher(child)) results.push(child);
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

class Document {
  createElement(tag) {
    return new Element(tag, this);
  }
}

function createEnvironment() {
  const document = new Document();
  return {
    document,
    grid: document.createElement("main"),
    cardCount: document.createElement("span"),
    liveFeedList: document.createElement("div"),
    filterAgent: { value: "Agent Two" },
  };
}

function buildHarness(allCards, filteredCards) {
  const env = createEnvironment();
  const helpers = `
    let document = globalThis.__env.document;
    let grid = globalThis.__env.grid;
    let cardCount = globalThis.__env.cardCount;
    let liveFeedList = globalThis.__env.liveFeedList;
    let filterAgent = globalThis.__env.filterAgent;
    let cards = new Map(globalThis.__allCards.map((card) => [card.card_id, card]));
    let systemAgents = globalThis.__systemAgents;
    let localStorage = { getItem() { return null; }, setItem() {} };
    const FORMAT_ICONS = {};
    function getFilteredCards() { return globalThis.__filteredCards; }
    function runMermaid() {}
    function statusColor() { return "#999"; }
    function formatTimeShort(value) { return value; }
    function formatTime(value) { return value; }
    function parseContent(raw) { return JSON.parse(raw); }
    function renderTemplate() { return null; }
    function renderBlock(block) {
      const el = document.createElement("div");
      el.className = "content-block";
      el.textContent = block.body;
      return el;
    }
  `;

  const script = `
    ${helpers}
    ${extractFunction("markAsNew")}
    ${extractFunction("syncChildren")}
    ${extractFunction("populateLiveFeedItem")}
    ${extractFunction("renderLiveFeed")}
    ${extractFunction("updateCardElement")}
    ${extractFunction("createCardElement")}
    ${extractFunction("updateAgentPanel")}
    ${extractFunction("createAgentPanel")}
    ${extractFunction("renderAll")}
    globalThis.__renderAll = renderAll;
  `;

  const sandbox = {
    console,
    JSON,
    Map,
    Set,
    Array,
    Object,
    __env: env,
    __allCards: allCards,
    __filteredCards: filteredCards,
    __systemAgents: allCards.map((card) => ({
      agent_id: card.agent_id,
      name: card.agent_name,
      status: "ready",
    })),
  };
  sandbox.globalThis = sandbox;

  const compiled = new vm.Script(script, { filename: "canvas.js" });
  compiled.runInNewContext(sandbox, { timeout: 1000 });

  return { env, renderAll: sandbox.__renderAll };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const cards = [
  {
    card_id: "oldest",
    title: "Oldest",
    agent_id: "agent-1",
    agent_name: "Agent One",
    updated_at: "2026-03-08T10:00:00Z",
    pinned: true,
    content: JSON.stringify({ format: "markdown", body: "Oldest body" }),
  },
  {
    card_id: "third",
    title: "Third",
    agent_id: "agent-2",
    agent_name: "Agent Two",
    updated_at: "2026-03-08T10:01:00Z",
    pinned: false,
    content: JSON.stringify({ format: "markdown", body: "Third body" }),
  },
  {
    card_id: "newest",
    title: "Newest",
    agent_id: "agent-3",
    agent_name: "Agent Three",
    updated_at: "2026-03-08T10:03:00Z",
    pinned: false,
    content: JSON.stringify({ format: "markdown", body: "Newest body" }),
  },
  {
    card_id: "second",
    title: "Second",
    agent_id: "agent-4",
    agent_name: "Agent Four",
    updated_at: "2026-03-08T10:02:00Z",
    pinned: false,
    content: JSON.stringify({ format: "markdown", body: "Second body" }),
  },
];

const filteredCards = cards.filter((card) => card.agent_name === "Agent Two");
const { env, renderAll } = buildHarness(cards, filteredCards);
renderAll();
const firstLiveFeedNode = env.liveFeedList.children[0];
const firstPanelNode = env.grid.children[0];
renderAll();

assert(env.cardCount.textContent === "1 card", "card count should reflect filtered agent messages");
assert(env.liveFeedList.children.length === 3, "live feed should render only the latest three cards");
assert(env.liveFeedList.children[0] === firstLiveFeedNode, "existing live feed nodes should be reused");
assert(env.grid.children[0] === firstPanelNode, "existing agent panels should be reused");

const titles = env.liveFeedList.children.map((item) => {
  const titleNode = item.children[0].children.find((child) => child.className === "live-feed-title");
  return titleNode ? titleNode.textContent : "";
});

assert(titles[0] === "Newest", "latest card should render first");
assert(titles[1] === "Second", "second latest card should render second");
assert(titles[2] === "Third", "third latest card should render third");
assert(!titles.includes("Oldest"), "oldest card should be excluded from the live feed");

const panelLabels = env.grid.children.map((panel) => {
  const nameNode = panel.querySelector(".agent-panel-name");
  return nameNode ? nameNode.textContent : panel.textContent;
});
assert(panelLabels.length === 1, "agent messages should render only one filtered agent panel");
assert(panelLabels[0] === "Agent Two", "filtered agent panel should match the selected agent");
assert(!panelLabels.includes("Agent One"), "filtered-out agent panels should be hidden");
assert(!panelLabels.includes("Agent Three"), "filtered-out agent panels should be hidden");
