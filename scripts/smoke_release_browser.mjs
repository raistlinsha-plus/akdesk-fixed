// Exercise the shipped browser UI and real downloads through a temporary Chrome profile.
// Invoked by smoke_local_release.py --browser (Node.js >= 22; no npm dependencies).
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const [base, workspace, mode, screenshot] = process.argv.slice(2);
const live = mode === "--live";
const demoPath = live ? undefined : mode;
assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
assert(!demoPath || /^\/[^?#]*\/$/.test(demoPath));
const profile = join(workspace, "chrome-profile");
const downloads = join(workspace, "downloads");
await mkdir(downloads);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless", "--disable-gpu", "--disable-background-networking", "--no-proxy-server",
  "--disable-sync", "--disable-component-update", "--no-first-run",
  "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
  "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
  `--user-data-dir=${profile}`, base + (demoPath || "/"),
], { stdio: "ignore" });
const exited = once(chrome, "exit");
let socket;

async function until(operation, message, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
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
  async function writeNote(text, label) {
    assert(await evaluate(`(() => {
      const label = ${JSON.stringify(label ?? "")};
      const area = label
        ? [...document.querySelectorAll("label")].find(item => item.textContent.startsWith(label))?.querySelector("textarea")
        : document.querySelector("textarea");
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
  if (demoPath) {
    await cdp("Emulation.setDeviceMetricsOverride", { width: 1280, height: 1200, deviceScaleFactor: 1, mobile: false });
    await contains("带走一份复盘底稿");
    await click("在线做一份周复盘");
    await contains("固定合成样例 · 非真实行情");
    await click("读取本周");
    await contains("前期观测 缺失");
    assert(await evaluate(`document.querySelector(".asset-week-draft button").disabled`));
    await writeNote("股指上涨与长端收益率下行是两条独立观察。人民币参考价缺前期观测，下周先核验原始来源。");
    await click("下载合成周复盘");
    const note = await downloaded("2026-07-31-合成样例.md");
    assert.match(note, /固定合成样例 · 非真实行情/);
    assert.match(note, /人民币参考价缺前期观测/);
    assert.match(note, /区间观测不足/);
    await go(demoPath + "#/week-story");
    await contains("用两周做一次连续复盘");
    await writeNote("资金与曲线变化分开看，先观察长端。", "第一周判断");
    await writeNote("下一周长端收益率是否继续下行？", "下一周要核验什么？");
    await click("保存样例并进入下一周");
    await contains("上周待核验：下一周长端收益率是否继续下行？");
    await writeNote("长端方向可继续观察，汇率缺数不能支持跨资产结论。", "第二周判断");
    await click("下载两周合成底稿");
    assert.match(await downloaded("两周合成样例.md"), /固定合成样例.*非真实行情/);
    if (screenshot) {
      await evaluate("window.scrollTo(0, 0)");
      const clip = await evaluate(`(() => {
        const section = document.querySelector(".asset-week").getBoundingClientRect();
        return { x: Math.max(0, Math.floor(section.x + scrollX - 16)), y: Math.max(0, Math.floor(section.y + scrollY - 16)),
          width: Math.ceil(section.width + 32), height: Math.ceil(section.height + 32), scale: 1 };
      })()`);
      const image = await cdp("Page.captureScreenshot", { format: "png", clip, captureBeyondViewport: true });
      await writeFile(screenshot, Buffer.from(image.data, "base64"));
    }
    await cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
    assert(await evaluate("document.querySelector('.asset-week').scrollWidth <= document.querySelector('.asset-week').clientWidth + 1"));
    console.log("PASS browser: static Pages layout, original and two-week samples, Markdown and narrow viewport");
  } else if (live) {
    await contains("股债金汇周复盘");
    await contains("最近已过周五");
    assert.equal(await evaluate('document.querySelector(".workspace-onboarding")'), null);
    assert.equal(await evaluate('document.querySelector(".asset-week-card")'), null);
    const date = await evaluate('document.querySelector(".asset-week input[type=date]").value');
    await contains("尚无上周复盘");
    await click("前一周");
    await contains("尚无上周复盘");
    await writeNote("第一周：保留当时的观察。", "本周判断");
    await writeNote("下一周回看利率的方向。", "下周待核验事项");
    await click("保存到本机");
    await contains("已保存到本机。");
    await click("后一周");
    await contains("下一周回看利率的方向。");
    await click("读取本周");
    await until(() => evaluate(`(() => {
      const cards = [...document.querySelectorAll(".asset-week-card")];
      return cards.length === 4 && cards.every(card => card.getAttribute("aria-busy") === "false");
    })()`), "Real reads did not settle", 42_000);
    const states = await evaluate(`[...document.querySelectorAll(".asset-week-card")].map(card =>
      [card.querySelector("h2").textContent, card.querySelector("small").textContent, card.querySelector("strong").textContent !== "—"])`);
    assert(states.every(([, state]) => !/演示|合成/.test(state)), "Unexpected demo values in real app");
    await writeNote("冷启动验收：记录缺项并保留查询线索。", "本周判断");
    await click("保存到本机");
    await contains("已保存到本机。");
    await evaluate("window.akdeskSmokeBeforeReload = true; true");
    await cdp("Page.reload");
    await until(() => evaluate("!window.akdeskSmokeBeforeReload"), "New document did not load");
    await contains("下一周回看利率的方向。");
    assert.equal(await evaluate('document.querySelector(".asset-week textarea").value'), "冷启动验收：记录缺项并保留查询线索。");
    await click("导出已保存底稿");
    const markdown = await downloaded(date + "-查询引用.md");
    assert.match(markdown, /冷启动验收/);
    assert.match(markdown, /用户自撰记录与查询引用/);
    assert.match(markdown, /第一周：保留当时的观察/);
    assert.doesNotMatch(markdown, /固定合成样例|前期观测|本期观测/);
    console.log("PASS cold real-mode: two weeks, restart recovery, market reads and reference export", JSON.stringify(states));
  } else {
  await contains("股债金汇周复盘");
  await contains("最近已过周五");
  assert.equal(await evaluate('document.querySelector(".workspace-onboarding")'), null);
  assert.equal(await evaluate('localStorage.getItem("akdesk.experience-profile.v1")'), null);
  await go("/#/help?q=start");
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
  await contains("固定合成样例 · 非真实行情");
  await click("读取本周");
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
  await contains("本地演示模式不保存个人周复盘");
  assert(await evaluate('[...document.querySelectorAll("button")].find(button => button.textContent === "保存到本机")?.disabled'));
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
  assert.equal(await evaluate('document.querySelector(".asset-week input[type=date]").value'), date);
  await click("仅重读10年期国债收益率");
  await contains("3 项尚未读取");
  await evaluate(`localStorage.setItem("akdesk.experience-profile.v1", "rates"); true`);
  await evaluate(`history.replaceState(null, "", "/"); setTimeout(() => location.reload(), 0); true`);
  await until(() => evaluate(`document.querySelector("main h1")?.textContent === "宏观固收投研工作台"`),
    "Saved research profile did not keep its normal landing page");
  console.log("PASS browser: fresh entry, legacy ETF task, weekly sample, source return and demo journal isolation");
  }
} finally {
  socket?.close();
  chrome.kill("SIGTERM");
  await Promise.race([exited, delay(4000)]);
}
