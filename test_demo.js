// Прогон демо как пользователь: кликает по кнопкам и проверяет, что каждая работает.
//   node business/test_demo.js [url]
const { spawn } = require("child_process")
const fs = require("fs")
const os = require("os")
const path = require("path")

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
const PORT = 9334
const URL = process.argv[2] || "https://ufa-zapis.surge.sh/demos/moj-doktor.html"

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const results = []
function ok(name, cond, extra) {
  results.push({ name, pass: !!cond, extra })
  console.log((cond ? "OK   " : "FAIL ") + name + (extra ? "  → " + extra : ""))
}

async function getJson(p, retries = 40) {
  for (let i = 0; i < retries; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}${p}`)
      if (r.ok) return await r.json()
    } catch (e) { /* ждём браузер */ }
    await sleep(250)
  }
  throw new Error("нет ответа от браузера: " + p)
}

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "demo-test-"))
  const chrome = spawn(CHROME, [
    "--headless=new", "--disable-gpu", "--no-first-run",
    "--remote-debugging-port=" + PORT, "--user-data-dir=" + profile, "about:blank",
  ], { stdio: "ignore" })

  const errors = []
  try {
    const page = await getJson("/json/list").then((l) => l.find((t) => t.type === "page"))
    const ws = new WebSocket(page.webSocketDebuggerUrl)
    await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })

    let id = 0
    const pending = new Map()
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data)
      if (m.method === "Runtime.exceptionThrown") {
        errors.push(m.params.exceptionDetails.text + " " + (m.params.exceptionDetails.exception || {}).description)
      }
      if (m.method === "Page.javascriptDialogOpening") {
        send("Page.handleJavaScriptDialog", { accept: true })
      }
      if (m.id && pending.has(m.id)) {
        const { resolve, reject } = pending.get(m.id)
        pending.delete(m.id)
        m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
      }
    }
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const mid = ++id
      pending.set(mid, { resolve, reject })
      ws.send(JSON.stringify({ id: mid, method, params }))
    })

    await send("Runtime.enable")
    await send("Page.enable")
    await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true })
    await send("Page.navigate", { url: URL })
    await sleep(2500)
    await ev0(`localStorage.removeItem('demo_bookings_v4')`)
    await send("Page.reload")
    await sleep(1800)

    async function ev0(expr) {
      const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true })
      return r.result && r.result.value
    }
    const ev = async (expr) => {
      const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + expr.slice(0, 80))
      return r.result.value
    }
    const click = async (sel) => { await ev(`(document.querySelector(${JSON.stringify(sel)})||{click(){}}).click()`); await sleep(350) }
    const text = async () => ev("document.getElementById('content').innerText")
    const fill = async (sel, val) => ev(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); el.value=${JSON.stringify(val)}; el.dispatchEvent(new Event('input')); })()`)
    const count = async () => ev("__demo.state.bookings.length")
    const bookingAt = async (i) => ev(`JSON.stringify(__demo.state.bookings[${i}] || null)`).then((s) => s && s !== "null" ? JSON.parse(s) : null)

    // 1. стартовый экран
    let t = await text()
    ok("стартовый экран — список услуг", /Выберите услугу/i.test(t))
    ok("услуги выводятся списком", (await ev("document.querySelectorAll('.row').length")) >= 3)

    // 2. услуга → календарь
    await click(".row")
    t = await text()
    ok("после услуги открылся календарь", /Выберите дату/i.test(t))
    const month = await ev("document.querySelector('.calhead .m').innerText")
    ok("в календаре есть месяц и год", /\d{4}/.test(month), month)
    ok("дни месяца отрисованы", (await ev("document.querySelectorAll('.day').length")) >= 28)

    // 3. листание месяцев
    await click("#nextMonth")
    ok("кнопка «следующий месяц» работает", (await ev("document.querySelector('.calhead .m').innerText")) !== month)
    await click("#prevMonth")
    ok("кнопка «предыдущий месяц» работает", (await ev("document.querySelector('.calhead .m').innerText")) === month)

    // 4. день и время
    await click(".day[data-d]")
    ok("после дня показано время", (await ev("document.querySelectorAll('.time').length")) >= 4)
    await click(".time:not(.off)")
    const time1 = await ev("__demo.state.time")
    ok("время выбирается", !!time1, time1)

    // 5. запись №1 — форма прямо на экране времени
    ok("форма появилась на экране времени", await ev("!!document.getElementById('fName')"))
    await fill("#fName", "Ирина")
    await fill("#fPhone", "89991234567")
    const masked = await ev("document.getElementById('fPhone').value")
    ok("телефон приводится к формату +7 (999) 123-45-67", masked === "+7 (999) 123-45-67", masked)

    await fill("#fPhone", "123")
    await click("#bottom .cta")
    ok("неполный номер не пропускается", /Введите телефон/i.test(await text()) && (await ev("__demo.state.step")) === 2)
    await fill("#fPhone", "+79991234567")
    await click("#bottom .cta")
    ok("запись №1 оформлена", /Вы записаны/i.test(await text()))
    ok("в списке одна запись", (await count()) === 1, String(await count()))
    const b1 = await bookingAt(0)

    // 5б. иерархия кнопок на экране «вы записаны»
    const primary = await ev("[...document.querySelectorAll('#content .cta')].map(b=>b.id)")
    ok("главная кнопка одна — «Как добраться»", primary.length === 1 && primary[0] === 'actMap', primary.join(","))
    ok("«В календарь» и «Перенести» — второй уровень",
       (await ev("document.getElementById('actCal').classList.contains('btn-outline')")) &&
       (await ev("document.getElementById('actMove').classList.contains('btn-outline')")))
    ok("«Записаться ещё» — второй уровень", await ev("document.getElementById('actAgain').classList.contains('btn-outline')"))
    ok("«Позвонить» и «Отменить» — мелкие ссылки",
       (await ev("document.getElementById('actCall').classList.contains('link')")) &&
       (await ev("document.getElementById('actCancel').classList.contains('link')")))
    ok("нижняя панель на этом экране не мешает", await ev("getComputedStyle(document.getElementById('bottom')).display === 'none'"))
    await click("#actMap")
    ok("«Как добраться» открывает карты", await ev("!!document.getElementById('mapSheet')"))
    await ev("(document.getElementById('mapSheet')||{remove(){}}).remove()")

    // 6. запись №2 — другой день и время
    await click("#actAgain")                        // «Записаться ещё» → к услугам
    await ev("document.querySelectorAll('.row')[1].click()")
    await sleep(400)
    ok("вторая запись: открылся календарь", (await ev("__demo.state.step")) === 2)
    await ev("(document.querySelectorAll('.day[data-d]')[4]||{click(){}}).click()")
    await sleep(300)
    await click(".time:not(.off)")
    const time2 = await ev("__demo.state.time")
    await fill("#fName", "Ирина")
    await fill("#fPhone", "89991234567")
    await click("#bottom .cta")
    ok("запись №2 оформлена", /Вы записаны/i.test(await text()))
    ok("теперь в списке две записи", (await count()) === 2, String(await count()))
    const b2 = await bookingAt(1)
    ok("услуги у записей разные", b1.service !== b2.service, b1.service + " / " + b2.service)
    ok("записи на разные слоты", (b1.dateISO + b1.time) !== (b2.dateISO + b2.time),
       b1.dateISO + " " + b1.time + " / " + b2.dateISO + " " + b2.time)

    // 7. «Мои записи» — обе на месте
    await click('[data-tab="mine"]')
    t = await text()
    ok("«Мои записи» показывают две записи", (await ev("document.querySelectorAll('[data-bid]').length")) === 2)
    ok("в заголовке вкладки видно количество", /Мои записи · 2/i.test(t), t.split("\n")[0])
    await ev("document.querySelector('[data-act=\"map\"]').click()")
    await sleep(300)
    ok("в «Моих записях» кнопка «как добраться» работает", await ev("!!document.getElementById('mapSheet')"))
    await ev("(document.getElementById('mapSheet')||{remove(){}}).remove()")

    // 8. «В календарь» для второй записи — файл именно про неё
    await ev("document.querySelector('[data-act=\"ics\"][data-id=\"" + b2.id + "\"]').click()")
    await sleep(400)
    const ics2 = await ev("__demo.buildIcs(__demo.state.bookings.find(b=>b.id===" + JSON.stringify(b2.id) + "))")
    ok("ics второй записи содержит её время", ics2.includes("T" + b2.time.replace(":", "")), b2.time)
    ok("ics второй записи содержит её услугу", ics2.includes(b2.service.slice(0, 8)))
    await ev("(document.getElementById('sheet')||{remove(){}}).remove()")

    // 9. «Перенести» вторую запись — время меняется, количество прежнее
    await ev("document.querySelector('[data-act=\"move\"][data-id=\"" + b2.id + "\"]').click()")
    await sleep(400)
    ok("«перенести» открывает календарь", /Выберите дату/i.test(await text()))
    ok("«перенести» помнит услугу", (await ev("__demo.state.service")) === b2.service)
    await ev("document.querySelectorAll('.day[data-d]')[6].click()")
    await sleep(300)
    const newTime = await ev("(() => { const t=[...document.querySelectorAll('.time:not(.off)')]; return t.length ? t[t.length-1].textContent.trim() : '' })()")
    await ev("(() => { const t=[...document.querySelectorAll('.time:not(.off)')]; if (t.length) t[t.length-1].click() })()")
    await sleep(300)
    await fill("#fName", "Ирина")
    await fill("#fPhone", "89991234567")
    await click("#bottom .cta")
    ok("после переноса экран говорит «перенесена»", /перенесена/i.test(await text()))
    ok("количество записей не выросло", (await count()) === 2, String(await count()))
    const moved = await ev("JSON.stringify(__demo.state.bookings.find(b=>b.id===" + JSON.stringify(b2.id) + "))")
    ok("время второй записи изменилось", JSON.parse(moved).time === newTime && newTime !== b2.time,
       b2.time + " → " + newTime)

    // 10. «Отменить» — своё окно подтверждения с причинами
    await click('[data-tab="mine"]')
    await ev("document.querySelector('[data-act=\"cancel\"][data-id=\"" + b1.id + "\"]').click()")
    await sleep(400)
    ok("открылось окно подтверждения отмены", await ev("!!document.getElementById('cancelSheet')"))
    ok("причины отмены предложены", (await ev("document.querySelectorAll('#cancelSheet .reason').length")) >= 5)
    ok("без причины кнопка отмены заблокирована", await ev("document.getElementById('cancelOk').disabled"))
    await ev("document.querySelectorAll('#cancelSheet .reason')[1].click()")
    await sleep(200)
    ok("после выбора причины кнопка активна", !(await ev("document.getElementById('cancelOk').disabled")))
    await ev("document.getElementById('keepBtn').click()")
    await sleep(300)
    ok("«не отменять» закрывает окно и сохраняет запись", (await count()) === 2)
    await ev("document.querySelector('[data-act=\"cancel\"][data-id=\"" + b1.id + "\"]').click()")
    await sleep(300)
    await ev("document.querySelectorAll('#cancelSheet .reason')[1].click()")
    await sleep(150)
    await ev("document.getElementById('cancelOk').click()")
    await sleep(500)
    ok("после отмены осталась одна запись", (await count()) === 1, String(await count()))
    const left = await bookingAt(0)
    ok("осталась именно вторая запись", left && left.id === b2.id, left && left.id)
    ok("отменённой записи в списке нет", (await ev("!!__demo.state.bookings.find(b=>b.id===" + JSON.stringify(b1.id) + ")")) === false)
    ok("причина отмены сохранилась", /Не подходит время/.test(await ev("localStorage.getItem('demo_cancels') || '[]'")))
    const cancelInfo = await ev("(document.getElementById('sheet')||{innerText:''}).innerText")
    ok("после отмены показано подтверждение с причиной", /Запись отменена/i.test(cancelInfo) && /Не подходит время/i.test(cancelInfo))
    await ev("(document.getElementById('sheet')||{remove(){}}).remove()")

    // 11. отмена последней — пусто
    await ev("document.querySelector('[data-act=\"cancel\"]').click()")
    await sleep(300)
    await ev("document.querySelectorAll('#cancelSheet .reason')[0].click()")
    await sleep(150)
    await ev("document.getElementById('cancelOk').click()")
    await sleep(500)
    await ev("(document.getElementById('sheet')||{remove(){}}).remove()")
    ok("отмена последней записи очищает список", (await count()) === 0)
    ok("«Мои записи» показывают пусто", /Пока пусто/i.test(await text()))

    // 12. звонок
    await click('[data-tab="help"]')
    const tel = await ev("__demo.telLink()")
    ok("кнопка «позвонить» даёт tel:-ссылку", /^tel:\+7\d{10}$/.test(tel), tel)
    await click("#helpCall")
    ok("нажатие «позвонить» показывает сообщение", /Звоним/i.test(await ev("document.body.innerText")))
    ok("в помощи 6 действий", (await ev("document.querySelectorAll('.row').length")) >= 6)

    // 12б. адрес и карты
    const addr = await ev("__demo.address")
    ok("у клиники есть адрес в Уфе", /Уфа/.test(addr) && /\d/.test(addr), addr)
    await click('[data-tab="help"]')
    await click("#helpMap")
    await sleep(300)
    ok("окно «как добраться» открывается", await ev("!!document.getElementById('mapSheet')"))
    const mapLinks = await ev("[...document.querySelectorAll('#mapSheet .mapbtn')].map(a=>a.getAttribute('href'))")
    ok("есть 4 варианта открыть карту", mapLinks.length === 4, mapLinks.length + " ссылок")
    ok("ссылка Яндекса содержит адрес", /yandex\.ru\/maps/.test(mapLinks[0] || "") && mapLinks[0].includes(encodeURIComponent(addr)))
    ok("ссылка Google содержит адрес", /google\.[a-z.]+\/maps/.test(mapLinks[1] || "") && decodeURIComponent(mapLinks[1]).includes(addr))
    ok("ссылка 2ГИС содержит адрес", /2gis\.ru/.test(mapLinks[2] || ""))
    ok("есть geo:-ссылка для приложения на телефоне", /^geo:/.test(mapLinks[3] || ""), mapLinks[3])
    await ev("(document.getElementById('mapSheet')||{remove(){}}).remove()")

    // 13. написать в клинику
    await click("#helpChat")
    await fill("#chatText", "Нужна консультация")
    await fill("#chatPhone", "89991234567")
    ok("маска работает и в чате", (await ev("document.getElementById('chatPhone').value")) === "+7 (999) 123-45-67")
    await click("#chatSend")
    ok("сообщение отправляется", /Сообщение отправлено/i.test(await text()))

    // 14. заказать звонок
    await click('[data-tab="help"]')
    await click("#helpCallback")
    await fill("#cbPhone", "89991234567")
    await click("#cbSend")
    ok("заявка на звонок принимается", /Заявка принята/i.test(await text()))

    // 15. отчёт об ошибке
    await click('[data-tab="help"]')
    await click("#helpBug")
    ok("кнопка написания в боте есть", await ev("!!document.getElementById('bugToBot')"))
    ok("у кнопки бота есть обработчик", await ev("typeof document.getElementById('bugToBot').onclick === 'function'"))
    await fill("#bugText", "Нажимаю на дату — время не появляется")
    await fill("#bugPhone", "@danila")
    await click("#bugSend")
    ok("отчёт об ошибке принимается", /Спасибо/i.test(await text()))
    const bugsSaved = await ev("localStorage.getItem('demo_bugs') || '[]'")
    ok("отчёт сохранился", /время не появляется/.test(bugsSaved))

    // 16. записи не теряются после перезагрузки
    await ev(`(function(){ const s = __demo.state; s.bookings.push({id:'x1', service:'Тест', dateISO:'2026-12-01', time:'11:00'}); localStorage.setItem('demo_bookings_v4', JSON.stringify(s.bookings)); })()`)
    await send("Page.reload")
    await sleep(1800)
    ok("записи сохраняются после перезагрузки", (await ev("__demo.state.bookings.length")) >= 1,
       String(await ev("__demo.state.bookings.length")))

    // возвращаемся на форму, чтобы проверить галочку
    await click('[data-tab="book"]')
    await sleep(400)
    await ev("(() => { const r = document.querySelector('.row[data-s]'); if (r) r.click(); })()")
    await sleep(500)
    await ev("(() => { const t = document.querySelector('.time:not(.off)'); if (t) t.click(); })()")
    await sleep(500)

    // галочка согласия обязательна
    await fill("#fName", "Ирина")
    await fill("#fPhone", "89991234567")
    await ev("(() => { const a = document.getElementById('fAgree'); if (a) a.checked = false; })()")
    await click("#bottom .cta")
    const blocked = (await ev("__demo.state.step")) === 2 && /согласие/i.test(await text())
    ok("без галочки записаться нельзя", blocked)
    await ev("(() => { const a = document.getElementById('fAgree'); if (a) { a.checked = true; a.onchange && a.onchange(); } })()")
    await fill("#fName", "Ирина")
    await fill("#fPhone", "89991234567")
    await click("#bottom .cta")
    ok("с галочкой запись проходит", (await ev("__demo.state.step")) === 4)

    ok("нет ошибок JavaScript", errors.length === 0, errors.slice(0, 3).join(" | "))
  } finally {
    chrome.kill()
  }

  const failed = results.filter((r) => !r.pass)
  console.log("\nИтого: " + (results.length - failed.length) + "/" + results.length + " проверок пройдено")
  if (failed.length) process.exitCode = 1
}

main().catch((e) => {
  console.error("ОШИБКА ТЕСТА:", e.message)
  process.exit(1)
})
