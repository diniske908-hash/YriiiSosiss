// Мост WhatsApp Web <-> админка. Запуск: node wa_bridge.js
// При первом запуске открыть http://127.0.0.1:8790/qr и отсканировать QR
// в WhatsApp на телефоне (Связанные устройства).
const http = require("http");
const path = require("path");
const QRCode = require("qrcode");
const { Client, LocalAuth } = require("whatsapp-web.js");

const PORT = Number(process.env.WA_PORT || 8790);
const ADMIN = process.env.WA_ADMIN || "http://127.0.0.1:8765";
const CHROME = process.env.WA_CHROME || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";

let qrData = "";
let ready = false;
let me = "";
let lastError = "";

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: path.join(__dirname, "_session") }),
  puppeteer: {
    executablePath: CHROME,
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
  },
});

client.on("qr", async (qr) => {
  qrData = await QRCode.toDataURL(qr, { margin: 1, width: 320 });
  console.log("QR готов: http://127.0.0.1:" + PORT + "/qr");
});

client.on("ready", () => {
  ready = true;
  qrData = "";
  me = (client.info && (client.info.pushname || client.info.wid.user)) || "";
  console.log("WhatsApp подключён:", me);
});

client.on("disconnected", (reason) => {
  ready = false;
  lastError = String(reason || "disconnected");
  console.log("WhatsApp отключён:", lastError);
});

client.on("auth_failure", (msg) => {
  lastError = String(msg || "auth_failure");
  console.log("Ошибка авторизации WhatsApp:", lastError);
});

client.on("message", async (msg) => {
  try {
    if (msg.fromMe || msg.isStatus || msg.broadcast) return;
    if (!msg.from || !msg.from.endsWith("@c.us")) return;
    const chat = msg.from.split("@")[0].replace(/\D/g, "");
    if (!chat) return;
    let name = "";
    try {
      const contact = await msg.getContact();
      name = contact.pushname || contact.name || contact.shortName || "";
    } catch (_) {}
    const text = msg.body || (msg.hasMedia ? "[медиа]" : "");
    if (!text) return;
    await fetch(ADMIN + "/api/wa/incoming", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat, name, text }),
    });
  } catch (e) {
    console.log("ошибка входящего:", e.message);
  }
});

async function send(chat, text) {
  const digits = String(chat).replace(/\D/g, "");
  if (!digits) throw new Error("нет номера");
  const target = digits + "@c.us";
  await client.sendMessage(target, text);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  const json = (code, data) => {
    res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" });
    res.end(JSON.stringify(data));
  };
  if (url.pathname === "/status") {
    return json(200, { ready, me, error: lastError, has_qr: !!qrData });
  }
  if (url.pathname === "/qr") {
    if (ready) {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      return res.end("<h2>WhatsApp уже подключён</h2><p>" + me + "</p>");
    }
    if (!qrData) {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      return res.end("<h2>Ждём QR…</h2><p>Обновите через 2–3 секунды.</p>");
    }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    return res.end("<h2>Сканируйте QR в WhatsApp → Связанные устройства</h2><img src='" + qrData + "'>");
  }
  if (url.pathname === "/send" && req.method === "POST") {
    let body = "";
    for await (const chunk of req) body += chunk;
    try {
      const data = JSON.parse(body || "{}");
      if (!data.chat || !data.text) return json(400, { ok: false, error: "chat/text" });
      await send(data.chat, data.text);
      return json(200, { ok: true });
    } catch (e) {
      return json(500, { ok: false, error: e.message });
    }
  }
  json(404, { ok: false });
});

server.listen(PORT, "127.0.0.1", () => console.log("WA bridge: http://127.0.0.1:" + PORT));
client.initialize().catch((e) => {
  lastError = e.message;
  console.log("не удалось запустить WhatsApp:", e.message);
});
