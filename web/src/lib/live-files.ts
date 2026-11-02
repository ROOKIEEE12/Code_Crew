/** Files inside a model's answer while it is still being written. */
export interface LiveFile {
  path: string;
  content: string;
  /** the model has finished this file (its END marker arrived) */
  done: boolean;
}

const START = /<<<FILE path="([^"]+)">>>\r?\n?/g;
const END = "<<<END FILE>>>";

/** Parses the file blocks of a partial answer. The last block may be unfinished;
 *  a half-arrived END marker at its tail is hidden so it never flickers on screen. */
export function parseLiveFiles(text: string): LiveFile[] {
  const starts = [...text.matchAll(START)];
  return starts.map((m, i) => {
    const from = (m.index ?? 0) + m[0].length;
    const until = i + 1 < starts.length ? starts[i + 1].index ?? text.length : text.length;
    let body = text.slice(from, until);
    const end = body.indexOf(END);
    const done = end >= 0;
    if (done) body = body.slice(0, end);
    else {
      for (let k = Math.min(END.length - 1, body.length); k > 0; k--) {
        if (END.startsWith(body.slice(-k))) {
          body = body.slice(0, -k);
          break;
        }
      }
    }
    return { path: m[1], content: body.replace(/\r?\n$/, ""), done };
  });
}
