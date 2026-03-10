const fs = require("fs");

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

class ClassList {
  constructor() {
    this.values = new Set();
  }
  add(...names) {
    names.forEach((name) => {
      this.values.add(name);
      return undefined;
    });
  }
  toggle(name) {
    if (this.values.has(name)) {
      this.values.delete(name);
      return false;
    }
    this.values.add(name);
    return true;
  }
  contains(name) {
    return this.values.has(name);
  }
}

class Element {
  constructor(tagName, document) {
    this.tagName = tagName.toUpperCase();
    this.document = document;
    this.children = [];
    this.parentNode = null;
    this.classList = new ClassList();
    this.dataset = {};
    this.textContent = "";
    this.id = "";
    this.className = "";
    this.style = {};
    this.listeners = {};
  }

  appendChild(child) {
    if (child == null) return child;
    child.parentNode = this;
    this.children.push(child);
    if (child.id) this.document.elementsById.set(child.id, child);
    return child;
  }

  addEventListener(type, handler) {
    this.listeners[type] = handler;
  }

  set innerHTML(value) {
    this.children = [];
    this.textContent = value;
  }

  get innerHTML() {
    return this.textContent;
  }

  get fullText() {
    let text = this.textContent || "";
    for (const child of this.children) {
      text += child.fullText || "";
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

function createEnvironment() {
  const document = new Document();
  const localStorageMap = new Map();
  return {
    document,
    localStorage: {
      getItem(key) {
        return localStorageMap.has(key) ? localStorageMap.get(key) : null;
      },
      setItem(key, value) {
        localStorageMap.set(key, String(value));
      },
      removeItem(key) {
        localStorageMap.delete(key);
      },
      key(index) {
        return Array.from(localStorageMap.keys())[index] || null;
      },
      get length() {
        return localStorageMap.size;
      },
    },
    systemPanel: document.createElement("div"),
  };
}

function buildHarness() {
  const env = createEnvironment();
  const headerCalls = [];
  const bodyCalls = [];

  const helpers = `
    let systemPanel = globalThis.__env.systemPanel;
    let localStorage = globalThis.__env.localStorage;
    let document = globalThis.__env.document;
    function statusColor() { return "#999"; }
    function renderAll() {}
    function emptyState(msg) {
      const el = document.createElement("div");
      el.className = "system-empty";
      el.textContent = msg;
      return el;
    }
    function renderSystemAgents(agents) {
      const el = document.createElement("div");
      el.textContent = "agents:" + agents.length;
      return el;
    }
    function renderSystemProfiles(profiles) {
      const el = document.createElement("div");
      el.textContent = "profiles:" + profiles.length;
      return el;
    }
    function renderSystemTasks(tasks) {
      const el = document.createElement("div");
      el.textContent = "tasks";
      return el;
    }
    function renderSystemFileLocks(locks) {
      const el = document.createElement("div");
      el.textContent = "locks:" + locks.length;
      return el;
    }
    function renderSystemMemories(memories) {
      const el = document.createElement("div");
      el.textContent = "memories:" + memories.length;
      return el;
    }
    function renderSystemWorktrees(worktrees) {
      const el = document.createElement("div");
      el.textContent = "worktrees:" + worktrees.length;
      return el;
    }
    function renderSystemHistory(history) {
      const el = document.createElement("div");
      el.textContent = "history:" + history.length;
      return el;
    }
    function renderSystemSkills(skills) {
      const el = document.createElement("div");
      el.textContent = "skills:" + skills.length;
      return el;
    }
    function renderSystemSkillSets(sets) {
      const el = document.createElement("div");
      el.textContent = "sets:" + (sets ? sets.length : 0);
      return el;
    }
    function renderSystemSessions(sessions) {
      const el = document.createElement("div");
      el.textContent = "sessions:" + (sessions ? sessions.length : 0);
      return el;
    }
    function renderSystemWorkflows(workflows) {
      const el = document.createElement("div");
      el.textContent = "workflows:" + (workflows ? workflows.length : 0);
      return el;
    }
    function renderSystemEnvironment(env) {
      const el = document.createElement("div");
      el.textContent = "env:" + Object.keys(env).length;
      return el;
    }
    function renderSystemTips(tips) {
      const el = document.createElement("div");
      el.textContent = "tips:" + tips.length;
      return el;
    }
    function fetch() { return Promise.resolve(); }
    function createSystemSection(key, title, bodyContent) {
      globalThis.__headerCalls.push(title);
      globalThis.__bodyCalls.push(bodyContent && bodyContent.fullText ? bodyContent.fullText : bodyContent.textContent || "");
      const section = document.createElement("section");
      const header = document.createElement("div");
      header.textContent = title;
      const body = document.createElement("div");
      body.appendChild(bodyContent);
      section.appendChild(header);
      section.appendChild(body);
      return section;
    }
  `;

  const script = `
    ${helpers}
    ${extractFunction("scopeBadge")}
    ${extractFunction("renderSystemPanel")}
    globalThis.__scopeBadge = scopeBadge;
    globalThis.__renderSystemPanel = renderSystemPanel;
  `;

  global.__env = env;
  global.__headerCalls = headerCalls;
  global.__bodyCalls = bodyCalls;
  // eslint-disable-next-line no-eval -- test harness executes extracted local canvas.js functions in isolation.
  eval(script);

  return {
    env,
    headerCalls,
    bodyCalls,
    renderSystemPanel: global.__renderSystemPanel,
    scopeBadge: global.__scopeBadge,
  };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function runCase(data) {
  const { env, headerCalls, bodyCalls, renderSystemPanel } = buildHarness();
  renderSystemPanel(data);
  return {
    text: env.systemPanel.fullText,
    headerCalls,
    bodyCalls,
    contentNode: env.document.getElementById("system-panel-content"),
  };
}

const zero = runCase({
  agents: [],
  tasks: {},
  file_locks: [],
  memories: [],
  worktrees: [],
  history: [],
  user_agent_profiles: [],
  active_project_agent_profiles: [],
  registry_errors: [],
});

assert(!zero.headerCalls.some((value) => value.includes("Registry Errors")), "zero-error render should not create registry errors section");
assert(zero.contentNode, "system-panel-content should be created");

// Registry errors have been moved to Dashboard view — System view should NOT render them
const nonZero = runCase({
  agents: [],
  tasks: {},
  file_locks: [],
  memories: [],
  worktrees: [],
  history: [],
  user_agent_profiles: [{ id: "global-checker" }],
  active_project_agent_profiles: [{ id: "repo-reviewer" }],
  registry_errors: [
    { source: "bad.json", message: "decode failed" },
    { source: "bad2.json", message: "parse failed" },
  ],
});

assert(!nonZero.headerCalls.some((value) => value.includes("Registry Errors")), "registry errors should not appear in System view (moved to Dashboard)");
assert(nonZero.headerCalls.includes("User Scope Saved Agents (1)"), "system view should render a user-scope saved agents section");
assert(nonZero.headerCalls.includes("Active-Project Saved Agents (1)"), "system view should render an active-project saved agents section");

const { scopeBadge } = buildHarness();
assert(scopeBadge("user").textContent === "User Scope", "user scope badge should use a readable label");
assert(scopeBadge("active-project").textContent === "Active Project", "active-project scope badge should use a readable label");
