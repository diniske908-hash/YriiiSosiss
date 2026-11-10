// Снимок страницы в мобильном размере через Chrome DevTools Protocol.
//
//   node business/shot.js <url> <out.png> [--wait 5000] [--click "текст кнопки"] [--full]
//
// Умеет: подождать реальное время, нажать кнопку по тексту, снять длинную страницу.
const { spawn } = require("child_process")
const fs = require("fs")
const os = require("os")
const path = require("path")

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
const PORT = Number(process.env.SHOT_PORT) || (9300 + Math.floor(Math.random() * 600))

const args = process.argv.slice(2)
const url = args[0]
const out = args[1]
const waitIdx = args.indexOf("--wait")
const waitMs = waitIdx >= 0 ? parseInt(args[waitIdx + 1], 10) : 2500
const clickIdx = args.indexOf("--click")
const clickText = clickIdx >= 0 ? args[clickIdx + 1] : null
const full = args.includes("--full")
const heightIdx = args.indexOf("--height")
const height = heightIdx >= 0 ? parseInt(args[heightIdx + 1], 10) : 900

if (!url || !out) {
  console.error("usage: node shot.js <url> <out.png> [--wait ms] [--click text] [--full] [--height px]")
  process.exit(2)
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function getJson(pathname, retries = 40) {
  for (let i = 0; i < retries; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}${pathname}`)
      if (r.ok) return await r.json()
    } catch (e) { /* браузер ещё поднимается */ }
    await sleep(250)
  }
  throw new Error("браузер не ответил на " + pathname)
}

async function main() {
  const profileIdx = args.indexOf("--profile")
  const profile = profileIdx >= 0 ? args[profileIdx + 1]
    : fs.mkdtempSync(path.join(os.tmpdir(), "shot-"))
  const chrome = spawn(CHROME, [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-default-browser-check",
    "--remote-debugging-port=" + PORT,
    ...(profileIdx >= 0 ? ["--profile-directory=Default"] : []),
    "--user-data-dir=" + profile,
    "about:blank",
  ], { stdio: "ignore" })

  try {
    const target = await getJson("/json/new?about:blank", 1).catch(() => null)
    let page = target
    if (!page) {
      const list = await getJson("/json/list")
      page = list.find((t) => t.type === "page")
    }
    const ws = new WebSocket(page.webSocketDebuggerUrl)
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })

    let id = 0
    const pending = new Map()
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.id && pending.has(msg.id)) {
        const { resolve, reject } = pending.get(msg.id)
        pending.delete(msg.id)
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
      }
    }
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const mid = ++id
      pending.set(mid, { resolve, reject })
      ws.send(JSON.stringify({ id: mid, method, params }))
    })

    await send("Page.enable")
    const widthIdx = args.indexOf("--width")
    const width = widthIdx >= 0 ? parseInt(args[widthIdx + 1], 10) : 390
    await send("Emulation.setDeviceMetricsOverride", {
      width, height, deviceScaleFactor: 2, mobile: width < 600,
    })
    await send("Page.navigate", { url })
    await sleep(waitMs)

    const evalIdx = args.indexOf("--eval")
    if (evalIdx >= 0) {
      const code = args[evalIdx + 1]
      const r = await send("Runtime.evaluate", { expression: code, returnByValue: true, awaitPromise: true })
      if (r.exceptionDetails) console.log("EXC:", JSON.stringify(r.exceptionDetails).slice(0, 400))
      console.log("eval:", JSON.stringify(r.result && r.result.value))
      await sleep(600)
    }

    if (clickText) {
      const expr = `(() => {
        const btns = [...document.querySelectorAll('button')];
        const b = btns.find(x => x.textContent.trim() === ${JSON.stringify(clickText)}
                              || x.textContent.includes(${JSON.stringify(clickText)}));
        if (b) { b.click(); return 'ok'; }
        return 'нет кнопки';
      })()`
      const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true })
      console.log("нажатие:", r.result && r.result.value)
      await sleep(1200)
    }

    const shot = await send("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: full,
      fromSurface: true,
    })
    fs.writeFileSync(out, Buffer.from(shot.data, "base64"))
    console.log("сохранено:", out)
    ws.close()
  } finally {
    chrome.kill()
  }
}

main().catch((e) => {
  console.error("ОШИБКА:", e.message)
  process.exit(1)
})
