const vm = require("node:vm");
const { extractFunction, Document, assert } = require("./canvas_test_helpers");

function createEnvironment() {
  const document = new Document();
  return {
    document,
    canvasSpotlight: document.createElement("section"),
    canvasView: document.createElement("main"),
  };
}

function buildHarness(initialCards, systemAgents) {
  const env = createEnvironment();
  const helpers = `
    let document = globalThis.__env.document;
    let canvasSpotlight = globalThis.__env.canvasSpotlight;
    let canvasView = globalThis.__env.canvasView;
    let cards = new Map(globalThis.__cards.map((card) => [card.card_id, card]));
    let systemAgents = globalThis.__systemAgents;
    let _spotlightCardId = "";
    let _spotlightUpdatedAt = "";
    let _spotlightSwapTimer = 0;
    const SPOTLIGHT_SWAP_DELAY = 420;
    function parseContent(raw) { return JSON.parse(raw); }
    function renderTemplate() { return null; }
    function renderBlock(block) {
      const el = document.createElement("div");
      el.className = "content-block";
      el.textContent = block.body;
      return el;
    }
    function formatTime(value) { return value; }
    function statusColor(status) { return status || "#999"; }
    function runMermaid() {}
    function downloadCard() {}
    function createDownloadButton() { return document.createElement("button"); }
  `;

  const script = `
    ${helpers}
    ${extractFunction("syncChildren")}
    ${extractFunction("renderTemplateOrBlocks")}
    ${extractFunction("ensureSpotlightFrame")}
    ${extractFunction("renderSpotlightContent")}
    ${extractFunction("renderSpotlightInfo")}
    ${extractFunction("markSpotlightSwap")}
    ${extractFunction("renderSpotlight")}
    globalThis.__renderSpotlight = renderSpotlight;
    globalThis.__setCards = function (nextCards) {
      cards = new Map(nextCards.map((card) => [card.card_id, card]));
    };
  `;

  const sandbox = {
    console,
    JSON,
    Map,
    Set,
    Array,
    Object,
    __env: env,
    __cards: initialCards,
    __systemAgents: systemAgents,
    window: {
      setTimeout(fn) {
        return fn();
      },
      clearTimeout() {},
    },
  };
  sandbox.globalThis = sandbox;

  const compiled = new vm.Script(script, { filename: "canvas.js" });
  compiled.runInNewContext(sandbox, { timeout: 1000 });

  return {
    env,
    renderSpotlight: sandbox.__renderSpotlight,
    setCards: sandbox.__setCards,
  };
}

const initialCard = {
  card_id: "card-1",
  title: "Initial title",
  agent_id: "agent-1",
  agent_name: "Agent One",
  updated_at: "2026-03-08T10:00:00Z",
  tags: ["alpha"],
  content: JSON.stringify({ format: "markdown", body: "Initial body" }),
};

const updatedSameCard = {
  ...initialCard,
  title: "Updated title",
  updated_at: "2026-03-08T10:05:00Z",
  tags: ["beta"],
  content: JSON.stringify({ format: "markdown", body: "Updated body" }),
};

const replacementCard = {
  card_id: "card-2",
  title: "Replacement title",
  agent_id: "agent-2",
  agent_name: "Agent Two",
  updated_at: "2026-03-08T10:06:00Z",
  tags: ["gamma"],
  content: JSON.stringify({ format: "markdown", body: "Replacement body" }),
};

const agents = [
  { agent_id: "agent-1", status: "ready" },
  { agent_id: "agent-2", status: "processing" },
];

const { env, renderSpotlight, setCards } = buildHarness([initialCard], agents);

renderSpotlight();
const initialShell = env.canvasSpotlight;
const initialTitleBar = env.canvasSpotlight.querySelector(".canvas-title-bar");
const initialContent = env.canvasSpotlight.querySelector(".canvas-content");
const initialInfo = env.canvasSpotlight.querySelector(".canvas-info-bar");

setCards([updatedSameCard]);
renderSpotlight();

const updatedTitleBar = env.canvasSpotlight.querySelector(".canvas-title-bar");
const updatedContent = env.canvasSpotlight.querySelector(".canvas-content");
const updatedInfo = env.canvasSpotlight.querySelector(".canvas-info-bar");

assert(env.canvasSpotlight === initialShell, "spotlight root should be preserved");
assert(updatedTitleBar === initialTitleBar, "same-card updates should reuse the title bar");
assert(updatedContent === initialContent, "same-card updates should reuse the content container");
assert(updatedInfo === initialInfo, "same-card updates should reuse the info bar");
assert(updatedTitleBar.querySelector(".canvas-title-text").textContent === "Updated title", "title text should update in place");
assert(updatedContent.children[0].textContent === "Updated body", "content body should update in place");
assert(updatedInfo.querySelector(".canvas-info-agent").textContent === "Agent One", "agent label should remain available after in-place update");

setCards([replacementCard]);
renderSpotlight();

assert(
  env.canvasSpotlight.querySelector(".canvas-title-text").textContent === "Replacement title",
  "replacement card should render its title"
);
