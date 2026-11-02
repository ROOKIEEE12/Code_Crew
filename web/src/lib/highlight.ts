// A deliberately small syntax highlighter for the live "typing" pane.
// The Code tab uses the full Monaco editor; this only needs to look right
// while text streams in, so it works line by line with no parser state.

const KEYWORDS: Record<string, string[]> = {
  python: ["def", "class", "return", "if", "elif", "else", "for", "while", "in", "not", "and", "or", "is", "import", "from", "as",
    "raise", "try", "except", "finally", "with", "lambda", "yield", "pass", "break", "continue", "None", "True", "False", "self"],
  javascript: ["function", "const", "let", "var", "return", "if", "else", "for", "while", "of", "in", "new", "class", "throw",
    "try", "catch", "finally", "import", "export", "from", "default", "typeof", "null", "undefined", "true", "false", "this", "async", "await"],
};

export function langOf(path: string): "python" | "javascript" | "html" | "css" | "text" {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "py") return "python";
  if (["js", "mjs", "cjs", "ts"].includes(ext)) return "javascript";
  if (["html", "htm"].includes(ext)) return "html";
  if (ext === "css") return "css";
  return "text";
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** Returns HTML for one line of code. Input is escaped before any markup is added. */
export function highlightLine(line: string, lang: ReturnType<typeof langOf>): string {
  if (lang === "text") return esc(line);
  const commentStart = lang === "python" ? "#" : lang === "css" ? "/*" : lang === "html" ? "<!--" : "//";
  if (line.trimStart().startsWith(commentStart)) return `<span class="hl-cm">${esc(line)}</span>`;

  if (lang === "html") {
    return esc(line)
      .replace(/(&lt;\/?)([a-zA-Z0-9-]+)/g, '$1<span class="hl-kw">$2</span>')
      .replace(/([a-zA-Z-]+)=(&quot;|")([^"]*)"/g, '<span class="hl-fn">$1</span>=<span class="hl-st">"$3"</span>');
  }
  if (lang === "css") {
    return esc(line)
      .replace(/^(\s*)([.#]?[a-zA-Z][\w-]*)(\s*\{)/, '$1<span class="hl-fn">$2</span>$3')
      .replace(/([a-z-]+)(\s*:)/g, '<span class="hl-kw">$1</span>$2')
      .replace(/\b(\d+(?:\.\d+)?)(px|rem|em|%|s|ms)?\b/g, '<span class="hl-nu">$1$2</span>');
  }

  // Tokenise strings first so keywords inside them stay uncoloured.
  const parts = line.split(/("(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)*'?|`(?:[^`\\]|\\.)*`?)/);
  const words = new RegExp(`\\b(${KEYWORDS[lang].join("|")})\\b`, "g");
  return parts
    .map((part, i) => {
      if (i % 2 === 1) return `<span class="hl-st">${esc(part)}</span>`;
      return esc(part)
        .replace(words, '<span class="hl-kw">$1</span>')
        .replace(/\b([A-Za-z_]\w*)(?=\()/g, '<span class="hl-fn">$1</span>')
        .replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="hl-nu">$1</span>');
    })
    .join("");
}

/** Test names declared in a test file, in order (pytest functions or node:test calls). */
export function testNames(content: string): string[] {
  const out: string[] = [];
  for (const m of content.matchAll(/^\s*(?:async\s+)?def\s+(test_\w+)\s*\(/gm)) out.push(m[1]);
  for (const m of content.matchAll(/\b(?:test|it)\(\s*(["'`])(.+?)\1/g)) out.push(m[2]);
  return out;
}
