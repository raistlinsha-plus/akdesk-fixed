import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../src/styles.css", import.meta.url), "utf8");
const definitions = new Set(
  [...source.matchAll(/(--[\w-]+)\s*:/g)].map((match) => match[1]),
);
const usages = new Set(
  [...source.matchAll(/var\((--[\w-]+)/g)].map((match) => match[1]),
);
const missing = [...usages].filter((name) => !definitions.has(name)).sort();

if (missing.length) {
  console.error(`Undefined CSS custom properties:\n${missing.join("\n")}`);
  process.exitCode = 1;
} else {
  console.log(`CSS custom properties: ${usages.size} usages resolved`);
}
