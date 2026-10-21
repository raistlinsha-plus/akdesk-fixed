import { readFile, readdir } from "node:fs/promises";

async function cssFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = new URL(entry.name + (entry.isDirectory() ? "/" : ""), directory);
    return entry.isDirectory() ? cssFiles(path) : entry.name.endsWith(".css") ? [path] : [];
  }));
  return nested.flat();
}

const files = await cssFiles(new URL("../src/", import.meta.url));
const source = (await Promise.all(files.map((path) => readFile(path, "utf8")))).join("\n");
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
  console.log(`CSS custom properties: ${usages.size} usages resolved across ${files.length} stylesheets`);
}
