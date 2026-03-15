const vm = require("node:vm");
const { extractFunction, assert } = require("./canvas_test_helpers");

// Extract formatCanvasHTMLDocument and run it in a sandbox
function runFormatCanvasHTMLDocument(body) {
  const script = `
    ${extractFunction("formatCanvasHTMLDocument")}
    globalThis.__result = formatCanvasHTMLDocument(globalThis.__body);
  `;
  const sandbox = { globalThis: { __body: body, __result: "" } };
  vm.createContext(sandbox);
  new vm.Script(script).runInContext(sandbox);
  return sandbox.globalThis.__result;
}

// --- Test 1: synapse-theme listener script is injected ---
(function test_theme_listener_injected() {
  const result = runFormatCanvasHTMLDocument("<p>Hello</p>");
  assert(
    result.includes("synapse-theme"),
    "Output should contain synapse-theme message listener"
  );
  assert(
    result.includes('data-theme'),
    "Output should set data-theme attribute"
  );
  console.log("PASS: theme listener script injected");
})();

// --- Test 2: synapse-resize ResizeObserver script is injected ---
(function test_resize_observer_injected() {
  const result = runFormatCanvasHTMLDocument("<p>Hello</p>");
  assert(
    result.includes("synapse-resize"),
    "Output should contain synapse-resize message"
  );
  assert(
    result.includes("ResizeObserver"),
    "Output should use ResizeObserver"
  );
  console.log("PASS: resize observer script injected");
})();

// --- Test 3: Full document (<!doctype html>) gets scripts in <head> ---
(function test_full_document_injection() {
  const fullDoc =
    '<!doctype html><html><head><title>Test</title></head><body><p>Content</p></body></html>';
  const result = runFormatCanvasHTMLDocument(fullDoc);
  // Scripts should be injected before </head>
  const headEnd = result.indexOf("</head>");
  assert(headEnd > -1, "Output should have </head>");
  const themePos = result.indexOf("synapse-theme");
  const resizePos = result.indexOf("synapse-resize");
  assert(
    themePos > -1 && themePos < headEnd,
    "synapse-theme script should be in <head>"
  );
  assert(
    resizePos > -1 && resizePos < headEnd,
    "synapse-resize script should be in <head>"
  );
  console.log("PASS: full document gets scripts in <head>");
})();

// --- Test 4: Default CSS variables (--bg, --fg) are included ---
(function test_css_variables_included() {
  const result = runFormatCanvasHTMLDocument("<div>Test</div>");
  assert(result.includes("--bg:"), "Output should contain --bg CSS variable");
  assert(result.includes("--fg:"), "Output should contain --fg CSS variable");
  assert(
    result.includes("--border:"),
    "Output should contain --border CSS variable"
  );
  console.log("PASS: default CSS variables included");
})();

// --- Test 5: HTML with <html> but no <head> gets head + scripts ---
(function test_html_without_head() {
  const htmlNoHead = "<html><body><p>No head</p></body></html>";
  const result = runFormatCanvasHTMLDocument(htmlNoHead);
  assert(
    result.includes("<head>"),
    "Should inject <head> when not present"
  );
  assert(
    result.includes("synapse-theme"),
    "Should include theme script even without existing <head>"
  );
  console.log("PASS: HTML without <head> gets injected head + scripts");
})();

console.log("All canvas artifact tests passed.");
