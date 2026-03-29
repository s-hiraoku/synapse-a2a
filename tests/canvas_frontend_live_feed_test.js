const vm = require("node:vm");
const { extractFunction, Document, assert } = require("./canvas_test_helpers");

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
    function cardsByRecency(a, b) { return (b.updated_at || "").localeCompare(a.updated_at || ""); }
    function getFilteredCards() { return globalThis.__filteredCards; }
    function runMermaid() {}
    function downloadCard() {}
    function createDownloadButton() { return document.createElement("button"); }
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
    ${extractFunction("renderTemplateOrBlocks")}
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
