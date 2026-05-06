const fs = require("node:fs");
const vm = require("node:vm");
const { Document, assert } = require("./canvas_test_helpers");

function click(element) {
  const handlers = element._listeners.click || [];
  assert(handlers.length > 0, "element should have a click listener");
  return handlers[0]({ preventDefault() {} });
}

function buildHarness() {
  const document = new Document();
  const listPanel = document.createElement("div");
  listPanel.id = "workflow-list-panel";
  document.elementsById.set(listPanel.id, listPanel);

  const title = document.createElement("h3");
  title.className = "admin-section-title";
  title.textContent = "Workflows";
  listPanel.appendChild(title);

  const empty = document.createElement("div");
  empty.id = "workflow-detail-empty";
  empty.className = "workflow-empty";
  document.elementsById.set(empty.id, empty);

  const detail = document.createElement("div");
  detail.id = "workflow-detail-content";
  detail.className = "view-hidden";
  document.elementsById.set(detail.id, detail);

  const calls = [];
  const fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      ok: true,
      async json() {
        return { workflow: { name: "created", steps: [] } };
      },
      async text() {
        return "name: exported\nsteps: []\n";
      },
    };
  };

  const ns = {
    workflowListPanel: listPanel,
    workflowDetailEmpty: empty,
    workflowDetailContent: detail,
    _workflowData: [],
    _workflowRuns: [],
    _selectedWorkflow: null,
    _workflowProjectDir: "/tmp/project",
    escapeHtml(value) {
      return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    },
    runMermaid() {},
    showToast() {},
  };

  const sandbox = {
    document,
    window: { SynapseCanvas: ns },
    console,
    fetch,
    confirm: () => true,
    URL: { createObjectURL: () => "blob:workflow", revokeObjectURL() {} },
    Blob: function Blob(parts, options) {
      this.parts = parts;
      this.options = options;
    },
    setInterval: () => 1,
    clearInterval() {},
    encodeURIComponent,
    setTimeout,
  };
  sandbox.globalThis = sandbox;

  const source = fs.readFileSync("synapse/canvas/static/canvas-workflow.js", "utf8");
  new vm.Script(source, { filename: "canvas-workflow.js" }).runInNewContext(sandbox);

  return { document, ns, listPanel, empty, detail, calls };
}

(async () => {
  const { ns, listPanel, detail, calls } = buildHarness();

  ns.renderWorkflowList([]);
  const createButton = listPanel.querySelector(".workflow-create-btn");
  const importButton = listPanel.querySelector(".workflow-import-btn");
  assert(createButton, "workflow list should render a New button");
  assert(importButton, "workflow list should render an Import YAML button");

  await click(createButton);
  const editor = detail.querySelector(".workflow-editor");
  assert(editor, "New button should open the workflow editor");

  const nameInput = detail.querySelector(".workflow-editor-name");
  const targetInput = detail.querySelector(".workflow-step-target-input");
  const messageInput = detail.querySelector(".workflow-step-message-input");
  const saveButton = detail.querySelector(".workflow-save-btn");
  nameInput.value = "browser-flow";
  targetInput.value = "claude";
  messageInput.value = "Review the patch";
  await click(saveButton);

  const createCall = calls.find((call) => call.url === "/api/workflow");
  assert(createCall, "saving a new workflow should POST /api/workflow");
  assert(createCall.options.method === "POST", "new workflow save should use POST");
  const payload = JSON.parse(createCall.options.body);
  assert(payload.name === "browser-flow", "POST payload should include workflow name");
  assert(payload.steps[0].target === "claude", "POST payload should include step target");
  assert(payload.steps[0].message === "Review the patch", "POST payload should include step message");

  const workflow = {
    name: "existing-flow",
    description: "Existing",
    scope: "project",
    steps: [{ id: "s1", target: "codex", message: "Implement", response_mode: "wait" }],
  };
  ns.renderWorkflowDetail(workflow);
  assert(detail.querySelector(".workflow-edit-btn"), "detail should render an Edit button");
  assert(detail.querySelector(".workflow-export-btn"), "detail should render an Export YAML button");
  const deleteButton = detail.querySelector(".workflow-delete-btn");
  assert(deleteButton, "detail should render a Delete button");
  await click(deleteButton);

  const deleteCall = calls.find((call) => call.url === "/api/workflow/existing-flow");
  assert(deleteCall, "delete should call workflow detail endpoint");
  assert(deleteCall.options.method === "DELETE", "delete should use DELETE");
})().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
