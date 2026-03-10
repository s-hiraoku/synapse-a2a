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

class Style {
  constructor() {
    this.values = {};
  }

  setProperty(name, value) {
    this.values[name] = value;
  }

  removeProperty(name) {
    delete this.values[name];
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
    this.style = new Style();
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
    canvasSpotlight: document.createElement("section"),
    canvasView: { style: new Style() },
  };
}

function buildHarness(allCards) {
  const env = createEnvironment();
  const helpers = `
    let document = globalThis.__env.document;
    let canvasSpotlight = globalThis.__env.canvasSpotlight;
    let canvasView = globalThis.__env.canvasView;
    let cards = new Map(globalThis.__cards.map((card) => [card.card_id, card]));
    let systemAgents = globalThis.__systemAgents;
    let _spotlightCardId = "";
    let _spotlightUpdatedAt = "";
    function statusColor() { return "#999"; }
    function formatTime(value) { return value; }
    function runMermaid() {}
    function renderBlock(block) {
      const el = document.createElement("div");
      el.className = "content-block";
      el.textContent = block.body;
      return el;
    }
    function renderTemplate(templateName, blocks) {
      const el = document.createElement("div");
      el.className = "template-render";
      el.textContent = templateName + ":" + blocks.map((block) => block.body).join(" ");
      return el;
    }
  `;

  const script = `
    ${helpers}
    ${extractFunction("parseContent")}
    ${extractFunction("renderSpotlight")}
    globalThis.__renderSpotlight = renderSpotlight;
  `;

  const sandbox = {
    __env: env,
    __cards: allCards,
    __systemAgents: allCards.map((card) => ({
      agent_id: card.agent_id,
      status: "ready",
    })),
  };
  vm.createContext(sandbox);
  const compiled = new vm.Script(script, { filename: "canvas.js" });
  compiled.runInContext(sandbox, { timeout: 1000 });

  return { env, renderSpotlight: sandbox.__renderSpotlight };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const cards = [
  {
    card_id: "stable",
    title: "Stable Card",
    agent_id: "agent-1",
    agent_name: "Agent One",
    updated_at: "2026-03-10T10:01:00Z",
    content: JSON.stringify({ format: "markdown", body: "stable body" }),
  },
  {
    card_id: "broken",
    title: "Broken Card",
    agent_id: "agent-2",
    agent_name: "Agent Two",
    updated_at: "2026-03-10T10:02:00Z",
    template: "briefing",
    template_data: "{broken-json",
    content: JSON.stringify({ format: "markdown", body: "broken body" }),
  },
];

const { env, renderSpotlight } = buildHarness(cards);
renderSpotlight();

assert(env.canvasSpotlight.children.length > 0, "spotlight should not become empty when the latest card is malformed");
assert(env.canvasSpotlight.fullText.includes("Stable Card"), "spotlight should fall back to the latest renderable card");
assert(!env.canvasSpotlight.fullText.includes("Broken Card"), "spotlight should skip the malformed latest card");
