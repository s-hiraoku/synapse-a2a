const fs = require("fs");
const vm = require("node:vm");

const source = fs.readFileSync("synapse/canvas/static/canvas.js", "utf8");

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

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

module.exports = {
  source,
  extractFunction,
  Style,
  Element,
  TextNode,
  Document,
  assert,
};
