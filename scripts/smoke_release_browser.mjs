// Exercise the shipped browser UI and real downloads through a temporary Chrome profile.
// Invoked by smoke_local_release.py --browser (Node.js >= 22; no npm dependencies).
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const [base, workspace] = process.argv.slice(2);
assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
const profile = join(workspace, "chrome-profile");
const downloads = join(workspace, "downloads");
await mkdir(downloads);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless", "--disable-gpu", "--disable-background-networking", "--no-proxy-server",
  "--disable-sync", "--disable-component-update", "--no-first-run",
  "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
  "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
  `--user-data-dir=${profile}`, base + "/#/help?q=start",
], { stdio: "ignore" });
const exited = once(chrome, "exit");
let socket;

async function until(operation, message) {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    const result = await operation();
    if (result) return result;
    await delay(100);
  }
  throw Error(message);
}

try {
  const port = await until(async () => {
    const value = await readFile(join(profile, "DevToolsActivePort"), "utf-8").catch(() => "");
    return value.split("\n")[0];
  }, "Chrome debugging port not available");
  const target = await until(async () => {
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    return targets.find(item => item.type === "page" && item.url.startsWith(base));
  }, "Chrome target did not load the local app");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  let sequence = 0;
  const requests = new Map();
  socket.addEventListener("message", ({ data }) => {
    const response = JSON.parse(data);
    requests.get(response.id)?.(response);
  });
  async function cdp(method, params = {}) {
    const id = ++sequence;
    const response = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => { requests.delete(id); reject(Error(method + " timed out")); }, 8_000);
      requests.set(id, result => { clearTimeout(timeout); requests.delete(id); resolve(result); });
      socket.send(JSON.stringify({ id, method, params }));
    });
    if (response.error) throw Error(method + ": " + response.error.message);
    return response.result;
  }
  async function evaluate(expression) {
    const result = await cdp("Runtime.evaluate", { expression, returnByValue: true });
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || "Browser JS failed");
    return result.result.value;
  }
  const go = async route => evaluate(`setTimeout(() => { location.href = ${JSON.stringify(base + route)}; }, 0); true`);
  const contains = async text => {
    try {
      await until(() => evaluate(`document.body?.textContent.includes(${JSON.stringify(text)})`), `Missing UI text: ${text}`);
    } catch (error) {
      console.error(await evaluate("({ title: document.title, route: location.hash, text: document.body?.textContent.slice(0, 180) })"));
      throw error;
    }
  };
  const click = async text => assert(await evaluate(`(() => { const button = [...document.querySelectorAll("button")].find(b => b.textContent.trim() === ${JSON.stringify(text)}); if (!button || button.disabled) return false; button.click(); return true; })()`), `Cannot click: ${text}`);
  async function writeNote(text) {
    assert(await evaluate(`(() => {
      const area = document.querySelector("textarea");
      if (!area) return false;
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set.call(area, ${JSON.stringify(text)});
      area.dispatchEvent(new Event("input", {bubbles: true}));
      return true;
    })()`));
  }
  async function downloaded(suffix) {
    const file = await until(async () => (await readdir(downloads)).find(name => name.endsWith(suffix)), `No download: ${suffix}`);
    return readFile(join(downloads, file), "utf-8");
  }
  await cdp("Page.enable");
  await cdp("Runtime.enable");
  await cdp("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });
  await contains("带走一份股债金汇观察底稿");
  await click("核验样例依据");
  assert(await evaluate(`(() => {
    const checkbox = document.querySelector(".first-task input[type=checkbox]");
    if (!checkbox) return false; checkbox.click(); return true;
  })()`));
  await click("写下我的判断");
  await writeNote("实测首任务底稿");
  await click("下载合成底稿");
  assert.match(await downloaded("首任务-合成底稿.md"), /实测首任务底稿/);
  await cdp("Emulation.setDeviceMetricsOverride", { width: 430, height: 900, deviceScaleFactor: 1, mobile: false });
  await go("/#/cross-asset-week?q=sample");
  await contains("-3.00 BP");
  await contains("前期观测 缺失");
  await writeNote("实测周复盘底稿");
  await click("下载合成周复盘");
  const note = await downloaded("2026-07-31-合成样例.md");
  assert.match(note, /固定合成样例/);
  assert.match(note, /实测周复盘底稿/);
  await click("返回本地真实数据入口");
  await contains("最近已过周五");
  await click("前一周");
  const date = await evaluate('document.querySelector(".asset-week input[type=date]").value');
  assert.match(date, /^\d{4}-\d{2}-\d{2}$/);
  await click("读取本周");
  await contains("当前服务为演示模式");
  await writeNote("核验后保留的人工备注");
  assert(await evaluate(`(() => {
    const card = [...document.querySelectorAll(".asset-week-card")].find(item => item.querySelector("h2").textContent === "10年期国债收益率");
    const button = card?.querySelector(".asset-week-link");
    if (!button) return false;
    button.click();
    return true;
  })()`));
  await contains("返回周复盘 · " + date);
  await click("← 返回周复盘 · " + date);
  await contains("仅重读10年期国债收益率");
  assert.equal(await evaluate('document.querySelector(".asset-week textarea").value'), "核验后保留的人工备注");
  assert.equal(await evaluate('document.querySelector(".asset-week input[type=date]").value'), date);
  await click("仅重读10年期国债收益率");
  await contains("3 项尚未读取");
  await until(() => evaluate(`[...document.querySelectorAll("button")].some(button => button.textContent.trim() === "下载查询引用底稿" && !button.disabled)`),
    "Single-series read did not finish");
  await click("下载查询引用底稿");
  const reference = await downloaded(date + "-查询引用.md");
  assert.match(reference, /核验后保留的人工备注/);
  assert.match(reference, /查询引用版/);
  assert.doesNotMatch(reference, /-3\.00 BP|\+1\.00%|固定合成样例/);
  console.log("PASS browser: first task, sample download, source return, single read and reference download");
} finally {
  socket?.close();
  chrome.kill("SIGTERM");
  await Promise.race([exited, delay(4000)]);
}
