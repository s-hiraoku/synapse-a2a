const vm = require("node:vm");
const { extractFunction, NS_STUB_CODE, Document, assert } = require("./canvas_test_helpers");

function buildHarness() {
  const document = new Document();
  const root = document.createElement("main");
  root.className = "format-mermaid";

  const valid = document.createElement("pre");
  valid.className = "mermaid-pending mermaid";
  valid.textContent = "flowchart TD\nA --> B";
  valid.dataset.mermaidSource = valid.textContent;

  const invalid = document.createElement("pre");
  invalid.className = "mermaid-pending mermaid";
  invalid.textContent = "flowchart TD\nA --> [[[unclosed";
  invalid.dataset.mermaidSource = invalid.textContent;

  root.appendChild(valid);
  root.appendChild(invalid);

  document.querySelectorAll = function (selector) {
    if (selector === ".mermaid-pending") {
      return root.querySelectorAll(".mermaid-pending");
    }
    if (selector.includes("svg")) {
      return root.children.filter((child) => child.innerHTML.includes("<svg"));
    }
    return root.querySelectorAll(selector);
  };

  const consoleErrors = [];
  const consoleWarnings = [];
  const sandboxConsole = {
    log: console.log,
    error(...args) {
      consoleErrors.push(args.join(" "));
    },
    warn(...args) {
      consoleWarnings.push(args.join(" "));
    },
  };

  const mermaid = {
    async parse(source) {
      return !source.includes("[[[");
    },
    async render(id, source) {
      if (source.includes("[[[")) {
        throw new Error("translate(undefined, NaN)");
      }
      return { svg: "<svg data-id=\"" + id + "\"></svg>" };
    },
    async run() {
      throw new Error("translate(undefined, NaN)");
    },
  };

  const script = `
    let document = globalThis.__document;
    let mermaid = globalThis.__mermaid;
    ${NS_STUB_CODE}
    ns.escapeHtml = function(value) {
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    };
    ${extractFunction("runMermaid")}
    globalThis.__runMermaid = runMermaid;
  `;

  const sandbox = {
    console: sandboxConsole,
    Promise,
    String,
    Array,
    Object,
    Error,
    __document: document,
    __mermaid: mermaid,
  };
  sandbox.globalThis = sandbox;

  const compiled = new vm.Script(script, { filename: "canvas.js" });
  compiled.runInNewContext(sandbox, { timeout: 1000 });

  return {
    valid,
    invalid,
    consoleErrors,
    consoleWarnings,
    runMermaid: sandbox.__runMermaid,
  };
}

(async () => {
  const { valid, invalid, consoleErrors, runMermaid } = buildHarness();

  await runMermaid(".mermaid-pending");

  assert(!valid.classList.contains("mermaid-pending"), "valid diagram should no longer be pending");
  assert(valid.innerHTML.includes("<svg"), "valid diagram should render as SVG");
  assert(invalid.innerHTML.includes("mermaid-error"), "invalid diagram should show fallback UI");
  assert(
    invalid.innerHTML.includes("flowchart TD\nA --&gt; [[[unclosed"),
    "invalid fallback should include escaped source"
  );
  assert(
    !consoleErrors.some((line) => line.includes("translate(undefined, NaN)")),
    "Mermaid layout exceptions should not be logged through console.error"
  );
})().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exitCode = 1;
});
