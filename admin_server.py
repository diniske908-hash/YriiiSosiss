"""Админка Зиныч IT: чаты клиентов, ошибки, задачи, спам.

    python business/admin_server.py --port 8765
"""
from __future__ import annotations
import os

import argparse
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVENTS = ROOT / "_events.jsonl"
FIXES = ROOT / "_fix_queue.json"
RESOLVED = ROOT / "_resolved.json"
SECTIONS = ROOT / "_sections.json"
CRM = ROOT / "_crm.json"
COLD = ROOT / "_cold_leads.json"
COLD_SCRIPT = ROOT / "_cold_script.json"
ARCHIVE = ROOT / "_archive.json"
MERGES = ROOT / "_merges.json"
NAMES = ROOT / "_names.json"
DEFAULT_COLD_SCRIPT = """Здравствуйте!

Пишу по «{name}» — у вас нет онлайн-записи, и вечером клиенты не дозваниваются.

Я сделал пример, как это выглядит:
{demo}

Запись за 40 секунд, заявка сразу администратору.
Бот в MAX или Telegram — 10 000 ₽, за 5–10 дней.

Заодно чиню компьютеры и настраиваю сеть.

Если не интересно — просто скажите, больше не напишу.

Зиныч"""
STAGES = [("new", "Новый"), ("contact", "Связались"), ("demo", "Демо"),
          ("offer", "Предложение"), ("paid", "Оплачено"), ("done", "Запущено")]
TG_TOKEN = os.environ.get("TG_TOKEN", "")

PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:,">
<title>Зиныч IT — диалоги</title>
<style>
  :root{
    --bg:#f7f8fb;--panel:#fff;--txt:#0d1520;--dim:#5f6975;--line:#e8edf3;--field:#8b97a6;
    --acc:#2f6bff;--acc-soft:#eef3ff;--ok:#0fa968;--ok-soft:#e9fbf1;
    --warn:#e08600;--warn-soft:#fff6e6;--bad:#e5484d;--bad-soft:#ffefef;
    --shadow:0 1px 2px rgba(13,21,32,.05),0 8px 26px rgba(13,21,32,.06);
  }
  *{box-sizing:border-box}
  input:focus-visible,textarea:focus-visible,select:focus-visible,
  .tab:focus-visible,.sec:focus-visible,.conv:focus-visible,.macro:focus-visible,
  .deal:focus-visible,.btn:focus-visible,.send:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
  html,body{height:100%;margin:0}
  body{background:var(--bg);color:var(--txt);
       font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
       display:flex;flex-direction:column;overflow:hidden}
  .gbar{flex:none;height:56px;display:flex;align-items:center;gap:18px;padding:0 16px;
        background:var(--panel);border-bottom:1px solid var(--line);z-index:5}
  .shell{flex:1;display:flex;min-height:0}
  aside{width:330px;flex:none;background:var(--panel);border-right:1px solid var(--line);
        display:flex;flex-direction:column;min-height:0}
  .brand{display:flex;align-items:center;gap:10px;padding:0;flex:none;cursor:pointer}
  .logo{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#2f6bff,#14b8a6);
        color:#fff;display:grid;place-items:center;font-weight:800;font-size:19px;flex:none}
  .brand b{font-size:14.5px;letter-spacing:-.01em}
  .brand small{display:block;color:var(--dim);font-size:11px;margin-top:1px}
  .tabs{display:flex;gap:3px;flex:1;overflow-x:auto;padding:0;flex-wrap:nowrap;scrollbar-width:none}
  .tabs::-webkit-scrollbar{display:none}
  .tab{flex:none;width:104px;text-align:center;font-size:13px;padding:8px 4px;border-radius:10px;
       color:var(--dim);cursor:pointer;border:1px solid transparent;white-space:nowrap}
  .tab:hover{background:#f2f5f9}
  .tab.on{background:var(--acc-soft);color:#1d4ed8;font-weight:600;border-color:#dbe6ff}
  body.wide aside{display:none}
  body.wide .search,body.wide .pulse,body.wide .secs,body.wide .list{display:none}
  body.wide .body{padding:18px 22px;display:block;overflow:auto}
  .board{display:flex;gap:10px;align-items:flex-start;min-height:100%}
  .col{width:195px;flex:none;background:#eef1f6;border:1px solid var(--line);border-radius:12px;padding:8px}
  .colhead{font-size:12px;font-weight:700;color:var(--dim);padding:4px 6px 8px;display:flex;justify-content:space-between}
  .col.over{background:#e3ecff}
  .cards{min-height:40px;display:flex;flex-direction:column;gap:7px}
  .deal{background:#fff;border:1px solid var(--line);border-radius:10px;padding:9px 10px;cursor:pointer;
        box-shadow:0 1px 2px rgba(13,21,32,.05)}
  .deal.drag{opacity:.45}
  .dname{font-weight:600;font-size:13px}
  .dmeta{font-size:11px;color:var(--dim);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .dsum{font-size:12px;font-weight:700;margin-top:5px}
  .dtags{display:flex;gap:3px;flex-wrap:wrap;margin-top:4px}
  .tag{font-size:10px;background:#eef3ff;color:var(--acc);padding:1px 6px;border-radius:999px}
  .colempty{font-size:11px;color:var(--dim);text-align:center;padding:8px}
  .calwrap{max-width:1100px;overflow-x:auto}
  .calgrid{min-width:760px}
  .calhead{display:flex;gap:10px;align-items:center;margin-bottom:12px}
  .calhead b{font-size:15px}
  .calgrid{display:grid;grid-template-columns:repeat(7,1fr);gap:8px}
  .calday{background:#fff;border:1px solid var(--line);border-radius:10px;min-height:130px;padding:6px}
  .calday.today{border-color:var(--acc);box-shadow:0 0 0 2px #dbe6ff}
  .caldate{font-size:11px;color:var(--dim);margin-bottom:6px}
  .calitem{font-size:11.5px;background:#eef3ff;border-radius:7px;padding:4px 6px;margin-bottom:4px;
           cursor:pointer;line-height:1.3}
  .calitem:hover{background:#dfe9ff}
  .sgrid{display:grid;grid-template-columns:repeat(3,minmax(150px,1fr));gap:10px;max-width:780px}
  .scard{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px}
  .snum{font-size:24px;font-weight:800;line-height:1.1}
  .slbl{font-size:12px;color:var(--dim);margin-top:3px}
  .spanel{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px;margin-top:12px;max-width:780px}
  .sth{font-weight:700;font-size:14px;margin-bottom:10px}
  .frow{display:flex;align-items:center;gap:10px;margin-bottom:7px;font-size:12.5px}
  .fname{width:110px;color:var(--dim)}
  .fbar{flex:1;height:8px;background:#eef1f6;border-radius:99px;overflow:hidden}
  .fbar i{display:block;height:100%;background:linear-gradient(90deg,#2f6bff,#1ac2b6)}
  .fnum{width:105px;text-align:right;font-weight:600}
  .coldwrap{max-width:1100px}
  .coldbar{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
  .coldbar input{flex:1;max-width:340px;padding:8px 12px;border:1px solid var(--field);
                 border-radius:10px;font:13px inherit;outline:none}
  .coldstat{font-size:12px;color:var(--dim)}
  .coldfilters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
  .coldfilters .pfilter{background:#f1f4f9;padding:4px 11px;border-radius:999px;margin-left:0}
  .coldfilters .pfilter.on{background:var(--acc-soft);color:#1d4ed8;font-weight:600}
  .coldtable{background:#fff;border:1px solid var(--line);border-radius:12px;overflow-x:auto}
  .ldrow{display:grid;grid-template-columns:1.4fr 1fr .6fr .95fr .7fr .55fr 165px;gap:8px;padding:10px 14px;
        border-bottom:1px solid var(--line);align-items:center;font-size:13px;cursor:pointer;min-width:930px}
  .sec .pencil{display:inline-block;margin-left:4px;opacity:.45;font-size:11px}
  .sec:hover .pencil{opacity:1}
  .rts{display:flex;gap:3px;flex-wrap:wrap}
  .rt{font-size:10px;font-weight:700;padding:1px 5px;border-radius:5px;white-space:nowrap}
  .rt.g{background:#e7f8ee;color:#0b7a4b}
  .rt.y{background:#ffefef;color:#b42318}
  .rt.no{background:#f1f4f9;color:#8a97a6}
  .ms{display:inline-block;font-size:10px;font-weight:700;padding:1px 5px;border-radius:5px;margin-right:2px}
  .ms.wa{background:#e7f8ee;color:#0b7a4b}
  .ms.tg{background:#e8f4ff;color:#14639c}
  .ms.max{background:#efe9ff;color:#5b3bb5}
  .ms.no{background:#f1f4f9;color:#8a97a6}
  .mchecks{display:flex;gap:14px;flex-wrap:wrap;font-size:13px}
  .mchecks label{display:flex;gap:5px;align-items:center;margin:0;color:var(--txt)}
  .ldrow:last-child{border-bottom:0}
  .ldrow:hover{background:#f7f9fd}
  .ldhead{font-size:11px;color:var(--dim);text-transform:uppercase;background:#f7f8fb;cursor:default}
  .chip.contacted{background:#fff4e6;color:#8a5300}
  .csub{font-size:11px;color:var(--dim);margin-top:2px}
  .tasks{max-width:760px}
  .th{font-weight:700;font-size:15px;margin-bottom:10px}
  .th span{font-weight:400;color:var(--dim);font-size:12px;margin-left:8px}
  .task{display:flex;gap:10px;align-items:center;background:#fff;border:1px solid var(--line);
        border-radius:10px;padding:10px 12px;margin-bottom:7px}
  .task.done .tt{text-decoration:line-through;color:var(--dim)}
  .task .tt{flex:1;font-size:13.5px}
  .task .tdate{font-size:11.5px;color:var(--dim)}
  .task.overdue .tdate{color:#b42318;font-weight:600}
  .tdel{cursor:pointer;color:#b9c4d0;padding:0 4px;font-size:12px}
  .tdel:hover{color:var(--bad)}
  .modal{position:fixed;inset:0;background:rgba(10,18,28,.4);display:grid;place-items:center;z-index:30}
  .mcard{background:#fff;border-radius:16px;padding:18px 20px;width:min(440px,92vw);max-height:90vh;overflow:auto;
         box-shadow:0 20px 60px rgba(0,0,0,.25)}
  .mh{display:flex;justify-content:space-between;align-items:center;font-weight:700;font-size:16px;margin-bottom:8px}
  .mh .x{cursor:pointer;color:var(--dim);font-weight:400}
  .mrow{display:flex;justify-content:space-between;font-size:13px;padding:3px 0;color:var(--dim)}
  .mrow b{color:var(--txt)}
  .mcard label{display:block;font-size:11.5px;color:var(--dim);margin:9px 0 4px}
  .mcard input,.mcard select,.mcard textarea{width:100%;padding:8px 10px;border:1px solid var(--field);
       border-radius:9px;font:13px inherit;outline:none}
  .mcard textarea{min-height:60px;resize:vertical}
  .pallist{max-height:320px;overflow:auto}
  .palitem{padding:9px 8px;border-radius:8px;cursor:pointer;display:flex;justify-content:space-between;
           gap:10px;font-size:13px}
  .palitem:hover{background:var(--acc-soft)}
  .palitem span{color:var(--dim);font-size:11.5px}
  .palempty{color:var(--dim);font-size:12px;padding:10px}
  #mSave{margin-top:10px}
  .mnotes{margin-top:10px;font-size:12px;color:var(--dim);border-top:1px dashed var(--line);padding-top:8px}
  .mnotes div{margin-bottom:4px}
  .search{padding:0 12px 10px}
  .search input{width:100%;padding:9px 12px 9px 32px;border:1px solid var(--field);border-radius:10px;
                font-size:13.5px;outline:none;background:#fbfcfe url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='15' height='15' fill='none' stroke='%237b8794' stroke-width='1.8'%3E%3Ccircle cx='6.5' cy='6.5' r='4.5'/%3E%3Cpath d='M10 10l3.5 3.5'/%3E%3C/svg%3E") no-repeat 10px 50%}
  .search input:focus{border-color:var(--acc);background-color:#fff}
  .pulse{font-size:12.5px;color:var(--dim);padding:0 14px 7px}
  .pulse b{color:var(--txt);font-weight:700}
  .pfilter{cursor:pointer;border-radius:999px;padding:1px 6px;margin-left:-6px}
  .pfilter.on{background:#fdecec;color:#d92d20}
  .chip.wait.late{background:#fde2e1;color:#b42318}
  .secs{display:flex;flex-wrap:wrap;gap:4px;padding:0 12px 9px;max-height:120px;overflow-y:auto;
        scrollbar-gutter:stable}
  .secs::-webkit-scrollbar{width:6px}
  .secs::-webkit-scrollbar-thumb{background:#d7dee8;border-radius:6px}
  .bulkbar{display:flex;gap:6px;align-items:center;padding:0 12px 8px}
  .bulkbar .btn{padding:5px 10px;font-size:12px}
  .selbox{width:18px;height:18px;border:1px solid var(--field);border-radius:5px;display:grid;
          place-items:center;flex:none;font-size:12px;color:#fff;background:#fff}
  .conv.sel{background:var(--acc-soft)}
  .conv.sel .selbox{background:var(--acc);border-color:var(--acc)}
  .sec{flex:none;font-size:11.5px;padding:4px 9px;border-radius:999px;background:#f1f4f9;color:var(--dim);
       cursor:pointer;border:1px solid transparent;white-space:nowrap}
  .sec:hover{background:#e9eef5}
  .sec.on{background:var(--acc-soft);color:var(--acc);border-color:#dbe6ff;font-weight:600}
  .sec.add{background:#fff;border:1px dashed #c9d3de;flex:none}
  .sec.drag{opacity:.45}
  .secs input{font:12px inherit;padding:4px 8px;border:1px solid var(--acc);border-radius:9px;
              outline:none;width:130px;background:#fff}
  .secsel{font:11.5px inherit;padding:4px 7px;border:1px solid var(--field);border-radius:9px;
          background:#fff;color:var(--txt);max-width:170px;outline:none}
  .pill.em{background:#fff4e6;color:#b25e09}
  .pill.wa{background:#e7f8ee;color:#0b7a4b}
  .chanlbl{font-weight:700;color:#1d4ed8}
  .ticks{font-weight:700;color:#dbeafe;margin-left:2px}
  .ticks.delivered{color:#dbeafe}
  .ticks.read{color:#ffffff}
  .ticks.failed{color:#fecaca}
  .list{flex:1;overflow-y:auto;padding:4px 8px 14px}
  .conv{display:flex;gap:11px;padding:11px;border-radius:12px;cursor:pointer;align-items:flex-start}
  .conv:hover{background:#f7f9fd}
  .conv.on{background:var(--acc-soft)}
  .ava{width:38px;height:38px;border-radius:50%;flex:none;display:grid;place-items:center;
       color:#fff;font-weight:700;font-size:15px;letter-spacing:0}
  .cinfo{flex:1;min-width:0}
  .crow{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
  .cname{font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .ctime{font-size:11px;color:var(--dim);flex:none}
  .csnip{font-size:12.5px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
  .chips{display:flex;gap:4px;margin-top:5px;flex-wrap:wrap}
  .chip{font-size:10px;font-weight:600;padding:1.5px 7px;border-radius:999px;letter-spacing:.01em;
        white-space:nowrap}
  .chip.app{background:var(--ok-soft);color:#0b7a4b}
  .chip.tech{background:var(--warn-soft);color:#8a5300}
  .chip.wait{background:#fdecec;color:#b42318}
  .chip.done{background:#eef3ff;color:#1d4ed8}
  .chip.muted{background:#f1f4f9;color:var(--dim)}
  main{flex:1;display:flex;flex-direction:column;min-width:0;background:var(--bg)}
  .topbar{height:64px;flex:none;background:var(--panel);border-bottom:1px solid var(--line);
          padding:0 22px;display:flex;align-items:center;justify-content:space-between;gap:14px}
  .who{display:flex;align-items:center;gap:11px;min-width:0}
  .who .t{font-weight:700;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .who .s{font-size:12px;color:var(--dim);margin-top:1px}
  .pill{font-size:11.5px;font-weight:600;padding:3px 9px;border-radius:999px;background:#f1f4f9;color:var(--dim)}
  .pill.tg{background:#e8f4ff;color:#14639c}
  .pill.max{background:#efe9ff;color:#5b3bb5}
  .body{flex:1;overflow-y:auto;padding:22px 26px;display:flex;flex-direction:column;gap:3px}
  .day{align-self:center;font-size:11.5px;color:var(--dim);background:#eef1f6;padding:3px 11px;border-radius:999px;margin:12px 0 8px}
  .line{display:flex;margin-bottom:7px}
  .line.me{justify-content:flex-end}
  .bub{max-width:min(72%,620px);padding:10px 14px;border-radius:16px;background:var(--panel);
       border:1px solid var(--line);font-size:14px;white-space:pre-wrap;word-wrap:break-word;box-shadow:0 1px 1px rgba(13,21,32,.03)}
  .line.me .bub{background:var(--acc);border-color:var(--acc);color:#fff;border-bottom-right-radius:6px}
  .line.me .bub.bot{background:#e8ecf3;border-color:#dbe1ea;color:#2a3441}
  .line.me .bub.owner{background:#1f6feb;border-color:#1f6feb}
  .who-lbl{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.04em;
           padding:1px 6px;border-radius:6px;margin-right:6px;background:rgba(0,0,0,.07);color:inherit;vertical-align:1px}
  .line.them .bub{border-bottom-left-radius:6px}
  .bub.tech{background:var(--warn-soft);border-color:#ffe0b0}
  .bub.srv{background:#f4f6f9;color:#6b7785;font-size:12.5px;border-style:dashed}
  .bub.app{background:var(--ok-soft);border-color:#bfeed6}
  .bub .meta{display:block;font-size:10.5px;opacity:.78;margin-top:4px}
  .composer{flex:none;background:var(--panel);border-top:1px solid var(--line);padding:12px 18px;
            display:flex;gap:10px;align-items:flex-end}
  .composer textarea{width:100%;flex:1;resize:none;min-height:44px;max-height:130px;padding:12px 14px;border:1px solid var(--field);
                     border-radius:13px;font:14px/1.45 inherit;outline:none;background:#fbfcfe}
  .macros{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}
  .macro{font:11.5px inherit;padding:4px 9px;border:1px solid var(--line);background:#f7f9fd;
         border-radius:999px;color:var(--dim);cursor:pointer;white-space:nowrap}
  .macro:hover{background:var(--acc-soft);border-color:#dbe6ff;color:var(--acc)}
  .composer textarea:focus{border-color:var(--acc);background:#fff}
  .send{width:44px;height:44px;border-radius:13px;border:0;background:var(--acc);color:#fff;cursor:pointer;
        display:grid;place-items:center;flex:none;transition:.15s}
  .send:hover{background:#245ae0}
  .send:disabled{opacity:.4;cursor:default}
  .empty{flex:1;display:grid;place-items:center;color:var(--dim);font-size:14px;text-align:center;padding:30px}
  .empty .ic{font-size:40px;margin-bottom:10px;opacity:.5}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px;
        box-shadow:var(--shadow);max-width:720px}
  .card h3{margin:0 0 6px;font-size:15.5px}
  .card .where{font-size:12px;color:var(--dim);margin-bottom:10px}
  .card p{margin:0;font-size:13.5px;color:#35414f;white-space:pre-wrap}
  .acts{display:flex;gap:8px;margin-top:16px}
  a.btn{display:inline-flex;align-items:center;justify-content:center;text-decoration:none}
  .btn{font:inherit;font-size:13.5px;font-weight:600;padding:9px 16px;border-radius:10px;cursor:pointer;
       border:1px solid var(--line);background:#fff;transition:.15s}
  .btn:hover{background:#f7f9fd}
  .btn.pri{background:var(--acc);border-color:var(--acc);color:#fff}
  .btn.pri:hover{background:#245ae0}
  .btn.ok{background:#0b7a4b;border-color:#0b7a4b;color:#fff}
  .btn.ok:hover{filter:brightness(.95)}
  .btn.no{color:#c0363b;border-color:#f6c9ca}
  .btn.no:hover{background:var(--bad-soft)}
  .btn:disabled{opacity:.5;cursor:default}
  .toast{position:fixed;left:50%;transform:translateX(-50%) translateY(20px);bottom:26px;background:#0d1520;color:#fff;
         padding:11px 20px;border-radius:12px;font-size:13.5px;opacity:0;transition:.2s;pointer-events:none;z-index:9}
  .toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
  ::-webkit-scrollbar{width:9px}
  ::-webkit-scrollbar-thumb{background:#d7dee8;border-radius:9px}
  ::-webkit-scrollbar-thumb:hover{background:#c3ccd9}
  /* ---- редизайн 11.11 ---- */
  :root{--bg:#eef2f8;--panel:#fff;--txt:#0f172a;--dim:#5b6775;--line:#e3e9f2;
        --acc:#2563eb;--acc-soft:#e8efff;--ok:#0b7a4b;--bad:#c0363b}
  body{background:var(--bg)}
  .gbar{height:64px;background:linear-gradient(120deg,#0f172a,#1e293b 60%,#312e81);
        border:0;box-shadow:0 4px 18px rgba(15,23,42,.28);padding:0 18px}
  .gbar .brand b{color:#fff}
  .gbar .brand small{color:#94a3b8}
  .gbar .logo{background:linear-gradient(135deg,#3b82f6,#8b5cf6);box-shadow:0 4px 14px rgba(59,130,246,.45)}
  .gbar .tab{color:#c7d2e3;border-color:transparent;border-radius:11px}
  .gbar .tab:hover{background:rgba(255,255,255,.09);color:#fff}
  .gbar .tab.on{background:#fff;color:#1d4ed8;border-color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.18)}
  .wa-link{margin-left:auto;color:#86efac;font-size:12px;font-weight:700;text-decoration:none;
           border:1px solid rgba(134,239,172,.45);padding:6px 11px;border-radius:9px}
  .wa-link:hover{background:rgba(134,239,172,.12)}
  aside{background:#fff;border-right:0;box-shadow:6px 0 24px rgba(15,23,42,.05)}
  .search input{background:#f3f6fb;border-color:#dbe3ee;border-radius:12px}
  .conv{border-radius:14px;padding:12px;margin-bottom:2px}
  .conv:hover{background:#f5f8ff}
  .conv.on{background:linear-gradient(90deg,#e8efff,#f7faff);box-shadow:inset 3px 0 0 #2563eb}
  .list{padding:4px 10px 14px}
  .topbar{height:70px;background:#fff;border-bottom:1px solid #eef2f8;box-shadow:0 2px 10px rgba(15,23,42,.04)}
  .body{background:linear-gradient(180deg,#f7f9fd,#eef2f8)}
  .bub{border-radius:18px;box-shadow:0 2px 12px rgba(15,23,42,.07)}
  .line.me .bub.owner{background:linear-gradient(135deg,#2563eb,#4f46e5);border:0}
  .line.me .bub.bot{background:#eef2f7;border:0}
  .composer{background:transparent;border:0;padding:8px 18px 14px}
  .composer textarea{background:#fff;border:1px solid #e3e9f2;border-radius:16px;
                     box-shadow:0 10px 34px rgba(15,23,42,.09)}
  .btn{border-radius:10px;border-color:#e3e9f2;background:#fff}
  .btn:hover{background:#f5f8ff}
  .btn.pri{background:linear-gradient(135deg,#2563eb,#4f46e5);border:0;color:#fff}
  .btn.pri:hover{filter:brightness(1.05)}
  .send{border-radius:14px;background:linear-gradient(135deg,#2563eb,#4f46e5)}
  .macro{border-radius:10px;background:#fff;border-color:#e3e9f2}
  .macro:hover{background:#eef3ff;color:#1d4ed8;border-color:#cddcff}
  .mcard{border-radius:20px;box-shadow:0 30px 80px rgba(15,23,42,.32);border:0}
  .mh{font-size:17px}
  .coldtable,.spanel,.scard,.tasks .task,.calday{border-color:#e3e9f2;border-radius:14px}
  .ldrow:hover{background:#f5f8ff}
  .snum{background:linear-gradient(135deg,#2563eb,#4f46e5);-webkit-background-clip:text;background-clip:text;color:transparent}
  .tab:focus-visible,.conv:focus-visible,.ldrow:focus-visible{outline-color:#2563eb}
  @media(max-width:1100px){ .col{width:150px} }
  @media(max-width:900px){
    .gbar{height:auto;padding:8px 12px;flex-wrap:wrap;gap:6px}
    .gbar .tabs{flex:1 0 100%;overflow-x:auto}
    .shell{flex-direction:column}
    aside{width:100%;max-height:42vh;border-right:0;border-bottom:1px solid var(--line)}
    main{min-height:58vh}
    .topbar{height:auto;padding:10px 14px;flex-wrap:wrap;gap:8px}
    .body{padding:12px}
    .bub{max-width:92%}
    .mcard{width:96vw;max-height:94vh}
    .board{min-width:0}
  }
</style></head>
<body>
<header class="gbar">
  <div class="brand" id="brand" title="К диалогам">
    <div class="logo">З</div>
    <div><b>Зиныч IT</b><small>диалоги и заявки</small></div>
  </div>
  <div class="tabs">
    <div class="tab on" role="tab" tabindex="0" data-sec="clients">Диалоги <span id="n-clients"></span></div>
    <div class="tab" role="tab" tabindex="0" data-sec="deals">Сделки</div>
    <div class="tab" role="tab" tabindex="0" data-sec="tasks">Дела <span id="n-tasks"></span></div>
    <div class="tab" role="tab" tabindex="0" data-sec="calendar">Календарь</div>
    <div class="tab" role="tab" tabindex="0" data-sec="errors">Проблемы <span id="n-errors"></span></div>
    <div class="tab" role="tab" tabindex="0" data-sec="stats">Сводка</div>
  </div>
  <a class="wa-link" href="http://127.0.0.1:8790/qr" target="_blank" rel="noopener"
     title="Подключить WhatsApp по QR">WhatsApp</a>
</header>
<div class="shell">
<aside>
  <div class="search"><input id="q" aria-label="Поиск по клиентам" placeholder="Поиск: имя, телефон, текст · Ctrl+K"></div>
  <div class="pulse" id="pulse"></div>
  <div class="secs" id="secs"></div>
  <div class="bulkbar" id="bulkbar"></div>
  <div class="list" id="list"></div>
</aside>

<main>
  <div class="topbar">
    <div class="who">
      <div class="ava" id="ava" style="display:none"></div>
      <div><div class="t" id="title">Диалоги</div><div class="s" id="sub">Выберите диалог слева</div></div>
    </div>
    <div id="badge"></div>
  </div>
  <div class="body" id="body">
    <div class="empty"><div><div class="ic">💬</div>Здесь появятся диалоги</div></div>
  </div>
  <div class="composer" id="composer" style="display:none">
    <div style="flex:1;min-width:0">
      <select id="replyChan" class="secsel" aria-label="Куда отправить ответ"
              style="display:none;margin-bottom:6px"></select>
      <div class="macros" id="macros"></div>
      <textarea id="text" aria-label="Текст ответа клиенту" placeholder="Написать клиенту… (Enter — отправить, Shift+Enter — новая строка)"></textarea>
    </div>
    <button class="send" id="send" title="Отправить">
      <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4Z"/></svg>
    </button>
  </div>
</main>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>

<script>
const COLORS = ['#2f6bff','#14b8a6','#f59e0b','#ef4444','#8b5cf6','#0ea5e9','#10b981','#f43f5e'];
let sec = 'clients', current = null, secFilter = null, firstLoad = true, calOffset = 0;
let onlyWaiting = false, dealsView = 'board', coldQ = '', showArchive = false;
let selectMode = false, coldStatus = 'all';
const selected = new Set();
const drafts = {};
let dragging = false, secDragId = null;

function saveDraft(){
  if (!current) return;
  const ta = document.getElementById('text');
  if (ta) drafts[current] = ta.value;
}
let cache = {clients:[],errors:[],fixes:[],spam:[],sections:{sections:[],map:{}}};
const TITLES = {clients:'Диалоги', deals:'Сделки', tasks:'Дела',
                errors:'Проблемы', stats:'Сводка', calendar:'Календарь', fixes:'Задачи', spam:'Спам'};

const esc = s => (s||'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const escAttr = s => esc(s).replace(/"/g, '&quot;');
const prettyText = t => (t||'').replace(/^\[ответ бота\]\s*/i, '')
  .replace(/^ОШИБКА ОТ КЛИЕНТА:\s*/i, 'Бот не понял сообщение: ');
const initial = n => (n||'?').trim().charAt(0).toUpperCase();
const color = n => COLORS[(n||'').split('').reduce((a,c)=>a+c.charCodeAt(0),0) % COLORS.length];
const api = (u, o) => fetch(u, o).then(r => r.json());
const secName = id => (((cache.sections||{}).sections||[]).find(s => s.id === id) || {}).name || '';
const chShort = ch => ch === 'max' ? 'MAX' : (ch === 'email' ? 'Почта' : (ch === 'whatsapp' ? 'WA' : 'TG'));
const fmtWait = m => m >= 1440 ? Math.floor(m/1440) + ' дн'
                             : (m >= 60 ? Math.floor(m/60) + ' ч' : (m ? m + ' мин' : 'только что'));

function toast(t){ const el = document.getElementById('toast'); el.textContent = t; el.classList.add('on');
  clearTimeout(el._t); el._t = setTimeout(()=>el.classList.remove('on'), 2000); }

function fmtTime(ts){ return (ts||'').slice(11,16); }
function fmtDay(ts){
  const d = (ts||'').slice(0,10);
  const today = todayISO();
  if (d === today) return 'Сегодня';
  const [y,m,dd] = d.split('-');
  return dd + '.' + m + '.' + y;
}

async function refresh(){
  if (dragging) return;
  if (document.querySelector('.modal') &&
      (sec === 'deals' || sec === 'tasks' || sec === 'stats' || sec === 'calendar')) return;
  const [clients, errors, fixes, spam, sections, crm, cold] = await Promise.all([
    api('/api/clients'), api('/api/errors'), api('/api/fixes'), api('/api/spam'),
    api('/api/sections'), api('/api/crm'), api('/api/cold')]);
  cache = {clients, errors, fixes, spam, sections, crm, cold};
  if (!document.getElementById('secName')) renderSecs();
  const active = clients.filter(c => !c.archived).length;
  document.getElementById('n-clients').textContent = active ? '('+active+')' : '';
  document.getElementById('n-errors').textContent = errors.length ? '('+errors.length+')' : '';
  const nt = document.getElementById('n-tasks');
  if (nt){ const open = (crm.tasks||[]).filter(t => !t.done).length; nt.textContent = open ? '('+open+')' : ''; }
  if (sec === 'errors') setErrorsHeader();
  if (sec === 'deals'){
    if (!dragging && document.activeElement.id !== 'coldQ') renderDealsView();
    return;
  }
  if (sec === 'tasks'){ renderTasks(); return; }
  if (sec === 'stats'){ renderStats(); return; }
  if (sec === 'calendar'){ renderCalendar(); return; }
  renderList();
  renderPulse();
  live();
  if (firstLoad && sec === 'clients' && clients.length){
    firstLoad = false;
    const first = clients.find(c => c.status === 'waiting' && !c.archived);
    if (first && !current) open(first.chat);
  }
  if (current && sec === 'clients' && !window.__busy) {
    window.__busy = true;
    openSilently(current).finally(() => { window.__busy = false; });
  }
}

async function openSilently(id){
  try {
    const d = await api('/api/client/' + id);
    const body = document.getElementById('body');
    if (body.dataset.count === String(d.total)) return;
    const atBottom = Math.abs(body.scrollHeight - body.scrollTop - body.clientHeight) < 80;
    let html = '', lastDay = '';
    d.messages.forEach(m => {
      const day = fmtDay(m.ts);
      if (day !== lastDay){ html += `<div class="day">${day}</div>`; lastDay = day; }
      const a = m.author || 'client';
      const cls = (a === 'bot' || a === 'owner') ? 'me' : 'them';
      const extra = a === 'bot' ? ' bot' : (a === 'owner' ? ' owner' : (m.tech ? ' tech' : (m.app ? ' app' : '')));
      const label = a === 'bot' ? '<span class="who-lbl">БОТ</span>'
                  : (a === 'owner' ? '<span class="who-lbl">ВЫ</span>' : '');
      const srv = /^\/(start|help|what|demo|price|order|bug)\b/i.test(m.text || '');
      const chan = (d.merged && m.channel) ? `<span class="chanlbl">${chShort(m.channel)}</span> · ` : '';
      const st = m.status || 'sent';
      const tick = a === 'owner'
        ? ` <span class="ticks ${st}" title="${st === 'read' ? 'Прочитано — клиент ответил после' : (st === 'delivered' ? 'Доставлено клиенту' : 'Отправлено')}">${st === 'read' || st === 'delivered' ? '✓✓' : (st === 'failed' ? '!' : '✓')}</span>`
        : '';
      html += `<div class="line ${cls}"><div class="bub${extra}${srv ? ' srv' : ''}">${label}${esc(prettyText(m.text))}<span class="meta">${chan}${fmtTime(m.ts)}${tick}</span></div></div>`;
    });
    body.innerHTML = html;
    body.dataset.count = String(d.total);
    if (atBottom) body.scrollTop = body.scrollHeight;
  } catch(e) {}
}

function renderList(){
  const q = (document.getElementById('q').value||'').toLowerCase();
  const list = document.getElementById('list');
  const rows = (cache[sec]||[]).filter(x => !q ||
      [x.who, x.summary, x.text, x.last, x.phone, x.chat].join(' ').toLowerCase().includes(q))
    .filter(x => sec !== 'clients' || secFilter === null || (x.section||'') === secFilter)
    .filter(x => sec !== 'clients' || !onlyWaiting || x.status === 'waiting')
    .filter(x => sec !== 'clients' || (showArchive ? x.archived : !x.archived));

  if (!rows.length){
    const msg = q ? `Ничего не найдено по «${esc(q)}»`
      : ((sec === 'clients' && (onlyWaiting || secFilter !== null)) ? 'В этом фильтре пусто' : 'Пусто');
    list.innerHTML = `<div class="empty" style="padding:28px 12px;font-size:13px">${msg}</div>`;
    return;
  }

  if (sec === 'clients'){
    list.innerHTML = rows.map(c => `
      <div class="conv ${current===c.chat?'on':''} ${selected.has(c.chat)?'sel':''}" role="button" tabindex="0" data-id="${c.chat}">
        ${selectMode ? `<span class="selbox">${selected.has(c.chat) ? '✓' : ''}</span>` : ''}
        <div class="ava" style="background:${color(c.who)}">${esc(initial(c.who))}</div>
        <div class="cinfo">
          <div class="crow"><span class="cname">${esc(c.who)}</span><span class="ctime">${fmtTime(c.last_ts)}</span></div>
          <div class="csnip">${esc(c.last.slice(0,48))}</div>
          <div class="chips">
            ${c.status === 'waiting' ? `<span class="chip wait${c.wait_min >= 1440 ? ' late' : ''}">ждёт ${fmtWait(c.wait_min || 0)}</span>`
                                     : '<span class="chip done">отвечено</span>'}
            ${c.bot_paused ? `<span class="chip muted">бот выкл${c.pause_until ? ' до ' + c.pause_until : ''}</span>` : ''}
            ${c.apps ? `<span class="chip app">заявка ${c.apps}</span>` : ''}
            ${c.tech ? `<span class="chip tech">сбоев ${c.tech}</span>` : ''}
            ${c.section ? `<span class="chip done">${esc(secName(c.section))}</span>` : ''}
            ${c.merged ? `<span class="chip done">${c.channels.length} канала</span>` : ''}
          </div>
        </div>
      </div>`).join('');
  } else if (sec === 'errors'){
    list.innerHTML = rows.map(e => `
      <div class="conv ${current===e.id?'on':''}" role="button" tabindex="0" data-id="${esc(e.id)}">
        <div class="ava" style="background:#e5484d">!</div>
        <div class="cinfo">
          <div class="crow"><span class="cname">${esc(e.where)}</span><span class="ctime">${fmtTime(e.ts)}</span></div>
          <div class="csnip">${esc(e.text.slice(0,48))}</div>
        </div>
      </div>`).join('');
  } else if (sec === 'fixes'){
    list.innerHTML = rows.map(f => `
      <div class="conv ${current===f.id?'on':''}" role="button" tabindex="0" data-id="${esc(f.id)}">
        <div class="ava" style="background:#f59e0b">🛠</div>
        <div class="cinfo">
          <div class="crow"><span class="cname">${esc(f.summary.slice(0,30))}</span><span class="ctime">${fmtTime(f.created)}</span></div>
          <div class="csnip">${esc((f.text||'').slice(0,48))}</div>
        </div>
      </div>`).join('');
  } else {
    list.innerHTML = rows.map(s => `
      <div class="conv ${current===s.id?'on':''}" role="button" tabindex="0" data-id="${esc(s.id)}">
        <div class="ava" style="background:#8b93a1">🚫</div>
        <div class="cinfo">
          <div class="crow"><span class="cname">${esc(s.who)}</span><span class="ctime">${fmtTime(s.ts)}</span></div>
          <div class="csnip">${esc(s.text.slice(0,48))}</div>
        </div>
      </div>`).join('');
  }

  list.querySelectorAll('.conv').forEach(el => {
    if (sec === 'clients' && selectMode){
      el.onclick = () => {
        const id = el.dataset.id;
        if (selected.has(id)) selected.delete(id); else selected.add(id);
        renderList();
      };
    } else {
      el.onclick = () => open(el.dataset.id);
    }
  });
  renderBulk();
}

function renderBulk(){
  const bar = document.getElementById('bulkbar');
  if (!bar) return;
  if (sec !== 'clients'){ bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  if (!selectMode){
    bar.innerHTML = '<button class="btn" id="selStart">☑ Выбрать несколько</button>';
    const b = document.getElementById('selStart');
    if (b) b.onclick = () => { selectMode = true; selected.clear(); renderList(); };
    return;
  }
  bar.innerHTML = `<button class="btn" id="selAll">Все</button>
    <button class="btn pri" id="selMerge" ${selected.size < 2 ? 'disabled' : ''}>Объединить (${selected.size})</button>
    <button class="btn no" id="selDel">Удалить (${selected.size})</button>
    <button class="btn" id="selCancel">Отмена</button>`;
  const all = document.getElementById('selAll');
  if (all) all.onclick = () => {
    document.querySelectorAll('#list .conv').forEach(el => selected.add(el.dataset.id));
    renderList();
  };
  const cancel = document.getElementById('selCancel');
  if (cancel) cancel.onclick = () => { selectMode = false; selected.clear(); renderList(); };
  const mg = document.getElementById('selMerge');
  if (mg) mg.onclick = async () => {
    if (selected.size < 2) return;
    const keys = [...selected].map(chat => {
      const c = (cache.clients || []).find(x => String(x.chat) === String(chat));
      return c ? c.key : '';
    }).filter(Boolean);
    if (keys.length < 2) return;
    if (!confirm(`Объединить диалоги (${keys.length}) в один контакт?`)) return;
    await api('/api/merge', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({keys})});
    selected.clear(); selectMode = false;
    toast('Диалоги объединены');
    await refresh();
  };
  const del = document.getElementById('selDel');
  if (del) del.onclick = async () => {
    if (!selected.size) return;
    if (!confirm(`Удалить диалогов: ${selected.size}? Сообщения будут стёрты.`)) return;
    const chats = [...selected];
    await api('/api/chat/delete', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({chats})});
    selected.clear(); selectMode = false;
    toast('Удалено диалогов: ' + chats.length);
    await refresh();
  };
}

function showClientsTab(){
  saveDraft();
  document.body.classList.remove('wide');
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.dataset.sec === 'clients'));
  sec = 'clients'; current = null;
  const sb = document.getElementById('secs');
  if (sb) sb.style.display = 'flex';
  setHeader('Диалоги', 'Выберите диалог слева', '');
  renderList();
}

function errorsEmpty(){
  document.getElementById('body').innerHTML =
    '<div class="empty"><div><div class="ic">👈</div>Выберите слева</div></div>';
}

function setErrorsHeader(){
  const nfix = (cache.fixes || []).length;
  const nspam = (cache.spam || []).length;
  setHeader('Проблемы', 'Что сломалось и требует решения',
    `<button class="btn" id="toFixes" style="padding:4px 10px;font-size:12px">В работе: ${nfix}</button>
     <button class="btn" id="toSpam" style="padding:4px 10px;font-size:12px">Спам: ${nspam}</button>`);
  const b = document.getElementById('toFixes');
  if (b) b.onclick = showFixes;
  const sp = document.getElementById('toSpam');
  if (sp) sp.onclick = showSpam;
}

function showErrors(){
  sec = 'errors'; current = null; renderList(); setErrorsHeader(); errorsEmpty();
}

function showFixes(){
  sec = 'fixes'; current = null; renderList();
  setHeader('Задачи', 'Принятые ошибки в работе',
    '<button class="btn" id="toErrors" style="padding:4px 10px;font-size:12px">← Ошибки</button>');
  errorsEmpty();
  const e = document.getElementById('toErrors');
  if (e) e.onclick = showErrors;
}

function showSpam(){
  sec = 'spam'; current = null; renderList();
  setHeader('Спам', 'Реклама от клиентов',
    '<button class="btn" id="toErrors3" style="padding:4px 10px;font-size:12px">← Ошибки</button>');
  errorsEmpty();
  const e = document.getElementById('toErrors3');
  if (e) e.onclick = showErrors;
}

const COLD_STATUS = {new: 'новый', contacted: 'написал', replied: 'ответил', refused: 'отказ'};
const onlyDigits = s => (String(s || '').split(/[;,/]/)[0] || '').replace(/\D/g, '').replace(/^8/, '7');

const COLD_DEMO = 'https://ufa-zapis.surge.sh/demos/moj-doktor.html';
const coldScript = l => {
  if (l.script) return l.script;
  const base = (cache.cold || {}).script || '';
  return base.replace(/\{name\}/g, l.name)
             .replace(/\{demo\}/g, COLD_DEMO)
             .replace(/\{niche\}/g, l.niche || 'клиники');
};

function showColdTemplate(){
  const base = (cache.cold || {}).script || '';
  const m = document.createElement('div');
  m.className = 'modal'; m.id = 'tplModal';
  m.innerHTML = `<div class="mcard" style="width:min(620px,94vw)">
    <div class="mh"><span>Базовый скрипт</span><span class="x" id="tClose">✕</span></div>
    <div class="mnotes">Вставки: {name} — клиника, {demo} — ссылка на демо, {niche} — ниша. Они заменятся сами.</div>
    <textarea id="tText" rows="14" aria-label="Базовый скрипт">${esc(base)}</textarea>
    <button class="btn pri" id="tSave" style="margin-top:10px;width:100%">Сохранить</button>
  </div>`;
  document.body.appendChild(m);
  const close = () => m.remove();
  m.querySelector('#tClose').onclick = close;
  m.onclick = e => { if (e.target === m) close(); };
  m.tabIndex = -1; m.focus();
  m.onkeydown = e => { if (e.key === 'Escape') close(); };
  m.querySelector('#tSave').onclick = async () => {
    const text = m.querySelector('#tText').value.trim();
    if (!text){ toast('Скрипт не может быть пустым'); return; }
    await api('/api/cold/script', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text})});
    close(); toast('Скрипт сохранён'); refresh();
  };
}

function renderDealsView(){
  const leads = (cache.cold || {}).leads || [];
  setHeader('Сделки', dealsView === 'board' ? 'Перетащите карточку по этапам'
                                            : 'Клиники без сайта и бота — готовый скрипт в один клик',
    `<button class="btn ${dealsView === 'board' ? 'pri' : ''}" id="dvBoard" style="padding:4px 12px;font-size:12px">Воронка</button>
     <button class="btn ${dealsView === 'cold' ? 'pri' : ''}" id="dvCold" style="padding:4px 12px;font-size:12px">Холодные лиды: ${leads.length}</button>`);
  const b = document.getElementById('dvBoard');
  if (b) b.onclick = () => { dealsView = 'board'; renderDealsView(); };
  const c = document.getElementById('dvCold');
  if (c) c.onclick = () => { dealsView = 'cold'; renderDealsView(); };
  if (dealsView === 'cold') renderCold(); else renderDeals();
}

function renderCold(){
  const all = (cache.cold || {}).leads || [];
  const q = coldQ.trim().toLowerCase();
  const leads = all.filter(l => (coldStatus === 'all' || (l.status || 'new') === coldStatus))
    .filter(l => !q || [l.name, l.phone, l.niche, l.city, l.address]
      .join(' ').toLowerCase().includes(q));
  const rows = leads.map(l => {
    const d = onlyDigits(l.phone);
    const hasWa = (l.messengers || []).includes('whatsapp');
    const wa = (hasWa && d) ? `https://wa.me/${d}?text=${encodeURIComponent(coldScript(l))}` : '';
    const call = (!hasWa && d) ? `tel:${d}` : '';
    const st = l.status || 'new';
    const stCls = st === 'replied' ? 'app' : (st === 'refused' ? 'tech' : (st === 'contacted' ? 'contacted' : 'done'));
    const ms = l.messengers || [];
    const msBadges = [
      ms.includes('whatsapp') ? '<span class="ms wa">WA</span>' : '',
      ms.includes('telegram') ? '<span class="ms tg">TG</span>' : '',
      ms.includes('max') ? '<span class="ms max">MAX</span>' : '',
    ].join('') || '<span class="ms no">?</span>';
    const r2 = l.rating_2gis ? Number(l.rating_2gis).toFixed(1) : '';
    const ry = l.rating_yandex ? Number(l.rating_yandex).toFixed(1) : '';
    const rtHtml = (r2 ? `<span class="rt g" title="2ГИС: ${l.reviews_2gis || 0} отзывов">2ГИС ${r2}</span>` : '') +
      (ry ? `<span class="rt y" title="Яндекс: ${l.reviews_yandex || 0} отзывов">Я ${ry}</span>` : '') ||
      '<span class="rt no">—</span>';
    return `
    <div class="ldrow" role="button" tabindex="0" data-id="${esc(l.id)}">
      <span><b>${esc(l.name)}</b><div class="csub">${esc(l.address || l.city || '')}</div></span>
      <span>${esc(l.phone || '—')}</span>
      <span>${msBadges}</span>
      <span class="rts">${rtHtml}</span>
      <span>${esc(l.niche || '')}</span>
      <span><span class="chip ${stCls}">${COLD_STATUS[st] || 'новый'}</span></span>
      <span style="display:flex;gap:5px">
        ${wa ? `<a class="btn pri" data-wa="${esc(l.id)}" data-st="${esc(st)}" href="${wa}"
                 target="_blank" rel="noopener" style="padding:6px 9px;font-size:12px"
                 title="Открыть WhatsApp с текстом">Написать</a>`
              : (call ? `<a class="btn" href="${call}" style="padding:6px 9px;font-size:12px">Позвонить</a>` : '')}
        <button class="btn" data-script="${esc(l.id)}" style="padding:6px 9px;font-size:12px">Текст</button>
      </span>
    </div>`;
  }).join('');
  const fresh = all.filter(l => l.status === 'new').length;
  document.getElementById('body').innerHTML = `<div class="coldwrap">
    <div class="coldbar">
      <input id="coldQ" aria-label="Поиск холодных лидов" placeholder="Поиск: клиника, телефон, адрес" value="${escAttr(coldQ)}">
      <button class="btn" id="coldTpl">Базовый скрипт</button>
      <button class="btn" id="coldScan">⟳ Найти ещё</button>
      <span class="coldstat">${leads.length} из ${all.length} · новых ${fresh}</span>
    </div>
    <div class="coldfilters">
      ${[['all', 'Все'], ['new', 'Новые'], ['contacted', 'Написал'], ['replied', 'Ответили'], ['refused', 'Отказ']]
        .map(([k, t]) => `<span class="pfilter ${coldStatus === k ? 'on' : ''}" data-cf="${k}">${t} ${k === 'all' ? all.length : all.filter(l => (l.status || 'new') === k).length}</span>`).join('')}
    </div>
    <div class="coldtable">
      <div class="ldrow ldhead"><span>Клиника</span><span>Телефон</span><span>Связь</span><span>Рейтинг</span><span>Ниша</span><span>Статус</span><span></span></div>
      ${rows || '<div class="empty" style="padding:30px">Ничего не найдено</div>'}
    </div></div>`;
  document.querySelectorAll('[data-cf]').forEach(el => el.onclick = () => {
    coldStatus = el.dataset.cf; renderCold();
  });
  const tpl = document.getElementById('coldTpl');
  if (tpl) tpl.onclick = showColdTemplate;
  const scan = document.getElementById('coldScan');
  if (scan) scan.onclick = async () => {
    scan.disabled = true; scan.textContent = 'Ищу…';
    try {
      const r = await api('/api/cold/scan', {method:'POST'});
      toast('Добавлено лидов: ' + (r.added || 0));
      await refresh();
    } catch (e) {
      toast('Не удалось найти — попробуйте ещё раз');
    } finally {
      scan.disabled = false; scan.textContent = '⟳ Найти ещё';
    }
  };
  const qi = document.getElementById('coldQ');
  if (qi) qi.oninput = () => {
    const pos = qi.selectionStart;
    coldQ = qi.value;
    renderCold();
    const n = document.getElementById('coldQ');
    if (n){ n.focus(); n.setSelectionRange(pos, pos); }
  };
  document.querySelectorAll('.ldrow[data-id]').forEach(row => row.onclick = () => showCold(row.dataset.id));
  document.querySelectorAll('[data-script]').forEach(b => b.onclick = e => {
    e.stopPropagation(); showCold(b.dataset.script);
  });
  document.querySelectorAll('[data-wa]').forEach(a => {
    a.onclick = e => {
      e.stopPropagation();
      if (a.dataset.st !== 'new') return;
      api('/api/cold/update', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({id: a.dataset.wa, status: 'contacted'})})
        .then(() => { toast('Отмечен: написал'); refresh(); });
    };
  });
}

function showCold(id){
  const l = ((cache.cold || {}).leads || []).find(x => x.id === id);
  if (!l){ toast('Лид не найден'); return; }
  const d = onlyDigits(l.phone);
  const script = coldScript(l);
  const ms = l.messengers || [];
  const hasWa = ms.includes('whatsapp'), hasTg = ms.includes('telegram'), hasMax = ms.includes('max');
  const rating2 = l.rating_2gis ? `★ ${Number(l.rating_2gis).toFixed(1)} · ${l.reviews_2gis || 0} отзывов` : '—';
  const ratingY = l.rating_yandex ? `★ ${Number(l.rating_yandex).toFixed(1)} · ${l.reviews_yandex || 0} отзывов` : '—';
  const waHref = (hasWa && d) ? `https://wa.me/${d}?text=${encodeURIComponent(script)}` : '';
  const tgHref = (hasTg && d) ? `https://t.me/+${d}` : '';
  const mailHref = l.email
    ? `mailto:${l.email}?subject=${encodeURIComponent('Бот записи для «' + l.name + '»')}` +
      `&body=${encodeURIComponent(script)}` : '';
  const m = document.createElement('div');
  m.className = 'modal'; m.id = 'coldModal';
  m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true');
  m.innerHTML = `<div class="mcard" style="width:min(620px,94vw)">
    <div class="mh"><span>${esc(l.name)}</span><span class="x" id="cClose">✕</span></div>
    <label>Название</label>
    <input id="cName" aria-label="Название лида" value="${escAttr(l.name)}" maxlength="120">
    <div class="mrow"><span>Телефон</span><b>${esc(l.phone || '—')}</b></div>
    <div class="mrow"><span>Почта</span><b>${esc(l.email || '—')}</b></div>
    <div class="mrow"><span>Адрес</span><b>${esc(l.address || l.city || '—')}</b></div>
    <div class="mrow"><span>Источник</span><b>${esc(l.source || '—')}</b></div>
    <div class="mrow"><span>Рейтинг 2ГИС</span><b>${rating2}</b></div>
    <div class="mrow"><span>Рейтинг Яндекс</span><b>${ratingY}</b></div>
    <label>Мессенджеры</label>
    <div class="mchecks">
      <label><input type="checkbox" id="mWa" ${(l.messengers || []).includes('whatsapp') ? 'checked' : ''}> WhatsApp</label>
      <label><input type="checkbox" id="mTg" ${(l.messengers || []).includes('telegram') ? 'checked' : ''}> Telegram</label>
      <label><input type="checkbox" id="mMax" ${(l.messengers || []).includes('max') ? 'checked' : ''}> MAX</label>
    </div>
    <div class="mnotes">WhatsApp — автоматом для мобильного. Проверить:
      ${d ? `<a href="https://wa.me/${d}" target="_blank" rel="noopener">WhatsApp</a> ·
             <a href="https://t.me/+${d}" target="_blank" rel="noopener">Telegram</a> ·
             <a href="https://max.ru/+${d}" target="_blank" rel="noopener">MAX</a>` : 'нет номера'}
    </div>
    <label>Статус</label>
    <select id="cStatus" aria-label="Статус лида">${Object.entries(COLD_STATUS).map(([k, v]) =>
      `<option value="${k}"${k === (l.status || 'new') ? ' selected' : ''}>${v}</option>`).join('')}</select>
    <label>Заметка</label>
    <textarea id="cNote" aria-label="Заметка по лиду">${esc(l.note || '')}</textarea>
    <label>Готовый скрипт</label>
    <textarea id="cScript" rows="7" aria-label="Скрипт для клиники">${esc(script)}</textarea>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
      ${waHref ? `<a class="btn pri" id="cWa" href="${waHref}" target="_blank" rel="noopener">WhatsApp</a>`
               : (d ? `<a class="btn" href="tel:${d}">Позвонить</a>` : '')}
      ${tgHref ? `<a class="btn" id="cTg" href="${tgHref}" target="_blank" rel="noopener">Telegram</a>`
               : '<span class="btn" style="opacity:.5" title="Не отмечен">Telegram?</span>'}
      ${(hasMax && d) ? `<a class="btn" href="https://max.ru/+${d}" target="_blank" rel="noopener">MAX</a>`
                      : '<span class="btn" style="opacity:.5" title="Не отмечен">MAX?</span>'}
      ${mailHref ? `<a class="btn" id="cMail" href="${mailHref}">Почта</a>`
                 : '<span class="btn" style="opacity:.5">Почта</span>'}
      <button class="btn" id="cCopy">Скопировать</button>
    </div>
    <div class="mnotes">Откроется чат с готовым текстом — останется нажать «Отправить».</div>
    <button class="btn pri" id="cSave" style="margin-top:10px;width:100%">Сохранить</button>
    <button class="btn no" id="cDel" style="margin-top:8px;width:100%">Удалить лид</button>
  </div>`;
  document.body.appendChild(m);
  let dirty = false;
  m.querySelectorAll('input,textarea,select').forEach(el => el.oninput = () => { dirty = true; });
  const close = () => {
    if (dirty && !confirm('Закрыть без сохранения?')) return;
    m.remove();
  };
  m.querySelector('#cClose').onclick = close;
  m.onclick = e => { if (e.target === m) close(); };
  m.tabIndex = -1; m.focus();
  m.onkeydown = e => { if (e.key === 'Escape') close(); };
  const text = () => m.querySelector('#cScript').value;
  const markContacted = async () => {
    if ((m.querySelector('#cStatus').value || 'new') !== 'new') return;
    await api('/api/cold/update', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id, status: 'contacted'})});
    m.querySelector('#cStatus').value = 'contacted';
  };
  ['cWa', 'cTg', 'cMail'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', () => markContacted());
  });
  m.querySelector('#cCopy').onclick = async () => {
    const txt = text();
    let ok = false;
    try { await navigator.clipboard.writeText(txt); ok = true; } catch (e) {}
    if (!ok){
      const ta = document.createElement('textarea');
      ta.value = txt; document.body.appendChild(ta); ta.select();
      try { ok = document.execCommand('copy'); } catch (e) {}
      ta.remove();
    }
    toast(ok ? 'Скрипт скопирован' : 'Не удалось скопировать');
  };
  m.querySelector('#cSave').onclick = async () => {
    await api('/api/cold/update', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id, name: m.querySelector('#cName').value.trim(),
        status: m.querySelector('#cStatus').value,
        messengers: ['whatsapp', 'telegram', 'max'].filter(k => m.querySelector(
          k === 'whatsapp' ? '#mWa' : (k === 'telegram' ? '#mTg' : '#mMax')).checked),
        note: m.querySelector('#cNote').value, script: text()})});
    dirty = false;
    close(); toast('Сохранено'); refresh();
  };
  m.querySelector('#cDel').onclick = async () => {
    if (!confirm('Удалить лид «' + l.name + '» из холодных?')) return;
    await api('/api/cold/delete', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id})});
    dirty = false;
    close(); toast('Лид удалён'); refresh();
  };
}

function renderDeals(){
  const deals = (cache.crm || {}).deals || [];
  const stages = (cache.crm || {}).stages || [];
  const board = stages.map(st => {
    const items = deals.filter(d => (d.stage || 'new') === st.id);
    const sum = items.reduce((n, d) => n + (Number(d.amount) || 0), 0);
    const cards = items.map(d => `
      <div class="deal" draggable="true" role="button" tabindex="0" data-key="${esc(d.key)}" data-chat="${esc(d.chat)}">
        <div class="dname">${esc(d.title || d.who)}</div>
        <div class="dmeta">${esc(d.phone || d.clinic || d.chat)}</div>
        ${(d.tags || []).length ? `<div class="dtags">${d.tags.map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : ''}
        ${Number(d.amount) ? `<div class="dsum">${Number(d.amount).toLocaleString('ru-RU')} ₽</div>` : ''}
      </div>`).join('') || '<div class="colempty">—</div>';
    return `<div class="col" data-stage="${st.id}">
      <div class="colhead"><span>${st.name}</span><span>${items.length}${sum ? ' · ' + sum.toLocaleString('ru-RU') + ' ₽' : ''}</span></div>
      <div class="cards">${cards}</div></div>`;
  }).join('');
  const body = document.getElementById('body');
  body.innerHTML = `<div class="board">${board}</div>`;
  body.querySelectorAll('.deal').forEach(el => {
    el.ondragstart = e => { dragging = true; e.dataTransfer.setData('text/plain', el.dataset.key); el.classList.add('drag'); };
    el.ondragend = () => { dragging = false; el.classList.remove('drag'); };
    el.onclick = () => { showClientsTab(); open(el.dataset.chat); };
  });
  body.querySelectorAll('.col').forEach(col => {
    col.ondragover = e => { e.preventDefault(); col.classList.add('over'); };
    col.ondragleave = () => col.classList.remove('over');
    col.ondrop = async e => {
      e.preventDefault(); col.classList.remove('over'); dragging = false;
      const key = e.dataTransfer.getData('text/plain');
      if (!key) return;
      await api('/api/crm/deal', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({key, stage: col.dataset.stage})});
      refresh();
    };
  });
}

const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

function fmtDate(s){
  if (!s) return '';
  const [y, m, d] = s.split('-');
  return d ? `${d}.${m}.${y}` : s;
}

function showTaskNew(){
  const clients = (cache.clients || []).filter(c => !c.archived);
  const m = document.createElement('div');
  m.className = 'modal'; m.id = 'taskModal';
  m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true');
  m.innerHTML = `<div class="mcard" style="width:min(420px,94vw)">
    <div class="mh"><span>Новое дело</span><span class="x" id="tnClose">✕</span></div>
    <label>Клиент</label>
    <select id="tnClient" aria-label="Клиент">${clients.map(c =>
      `<option value="${esc(c.key)}">${esc(c.who)}</option>`).join('')}</select>
    <label>Что сделать</label>
    <input id="tnText" aria-label="Что сделать" placeholder="Позвонить, отправить демо…">
    <label>Когда</label>
    <input id="tnAt" aria-label="Срок" type="date">
    <button class="btn pri" id="tnSave" style="margin-top:10px;width:100%">Сохранить</button>
  </div>`;
  document.body.appendChild(m);
  const close = () => m.remove();
  m.querySelector('#tnClose').onclick = close;
  m.onclick = e => { if (e.target === m) close(); };
  m.tabIndex = -1; m.focus();
  m.onkeydown = e => { if (e.key === 'Escape') close(); };
  m.querySelector('#tnSave').onclick = async () => {
    const text = m.querySelector('#tnText').value.trim();
    if (!text){ toast('Напишите, что сделать'); return; }
    await api('/api/crm/task', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key: m.querySelector('#tnClient').value, text,
        at: m.querySelector('#tnAt').value})});
    close(); toast('Дело добавлено'); refresh();
  };
}

function renderTasks(){
  const tasks = (cache.crm || {}).tasks || [];
  const today = todayISO();
  const rows = tasks.map(t => `
    <div class="task ${t.done ? 'done' : ''} ${(!t.done && t.at && t.at < today) ? 'overdue' : ''}">
      <input type="checkbox" ${t.done ? 'checked' : ''} data-task="${esc(t.id)}">
      <div class="tt"><b>${esc(t.who)}</b> — ${esc(t.text)}</div>
      <div class="tdate">${t.at ? fmtDate(t.at) : ''}</div>
      <span class="tdel" data-del="${esc(t.id)}" title="Удалить">✕</span>
    </div>`).join('');
  const open = tasks.filter(t => !t.done).length;
  document.getElementById('body').innerHTML =
    `<div class="tasks"><div class="th">Дела <span>${open} открытых · ${tasks.length - open} готово</span>
      <button class="btn" id="taskNew" style="float:right;padding:5px 12px;font-size:12px">＋ Дело</button></div>
     ${rows || '<div class="empty">Дел нет. Создайте в карточке клиента (📇 Карточка).</div>'}</div>`;
  const tn = document.getElementById('taskNew');
  if (tn) tn.onclick = showTaskNew;
  document.querySelectorAll('[data-task]').forEach(el => el.onchange = async () => {
    await api('/api/crm/task/done', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id: el.dataset.task})});
    refresh();
  });
  document.querySelectorAll('[data-del]').forEach(el => el.onclick = async () => {
    if (!confirm('Удалить дело?')) return;
    await api('/api/crm/task/delete', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id: el.dataset.del})});
    refresh();
  });
}

function renderCalendar(){
  const base = new Date(); base.setHours(0, 0, 0, 0);
  const dow = (base.getDay() + 6) % 7;
  const mon = new Date(base); mon.setDate(base.getDate() - dow + calOffset * 7);
  const days = [...Array(7)].map((_, i) => { const d = new Date(mon); d.setDate(mon.getDate() + i); return d; });
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const today = iso(new Date());
  const tasks = (cache.crm || {}).tasks || [];
  const cols = days.map((d, i) => {
    const key = iso(d);
    const items = tasks.filter(t => t.at === key && !t.done);
    return `<div class="calday ${key === today ? 'today' : ''}">
      <div class="caldate">${['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][i]} ${d.getDate()}.${String(d.getMonth() + 1).padStart(2, '0')}</div>
      ${items.map(t => `<div class="calitem" data-key="${esc(t.key)}">${esc(t.who)}: ${esc(t.text)}</div>`).join('')}
    </div>`;
  }).join('');
  const title = mon.toLocaleDateString('ru-RU', {month: 'long', year: 'numeric'});
  document.getElementById('body').innerHTML = `<div class="calwrap">
    <div class="calhead"><button class="btn" id="calPrev">‹</button><b>${esc(title)}</b>
      <button class="btn" id="calNext">›</button><button class="btn" id="calToday">Сегодня</button></div>
    <div class="calgrid">${cols}</div></div>`;
  document.getElementById('calPrev').onclick = () => { calOffset--; renderCalendar(); };
  document.getElementById('calNext').onclick = () => { calOffset++; renderCalendar(); };
  document.getElementById('calToday').onclick = () => { calOffset = 0; renderCalendar(); };
  document.querySelectorAll('.calitem').forEach(el => el.onclick = () => {
    const chat = el.dataset.key.split(':').slice(1).join(':');
    showClientsTab(); open(chat);
  });
}

function renderStats(){
  const cl = (cache.clients || []).filter(c => !c.archived), crm = cache.crm || {};
  const activeKeys = new Set(cl.map(c => c.key));
  const stages = crm.stages || [], tasks = crm.tasks || [];
  const deals = (crm.deals || []).filter(d => activeKeys.has(d.key));
  const today = todayISO();
  const waiting = cl.filter(c => c.status === 'waiting').length;
  const apps = cl.reduce((n, c) => n + (c.apps || 0), 0);
  const open = tasks.filter(t => !t.done).length;
  const over = tasks.filter(t => !t.done && t.at && t.at < today).length;
  const sum = deals.reduce((n, d) => n + (Number(d.amount) || 0), 0);
  const max = Math.max(1, ...stages.map(s => deals.filter(d => (d.stage || 'new') === s.id).length));
  const funnel = stages.map(s => {
    const arr = deals.filter(d => (d.stage || 'new') === s.id);
    const sm = arr.reduce((n, d) => n + (Number(d.amount) || 0), 0);
    return `<div class="frow"><span class="fname">${esc(s.name)}</span>
      <span class="fbar"><i style="width:${Math.round(arr.length / max * 100)}%"></i></span>
      <span class="fnum">${arr.length}${sm ? ' · ' + sm.toLocaleString('ru-RU') + ' ₽' : ''}</span></div>`;
  }).join('');
  const ch = {telegram: 0, max: 0, email: 0};
  cl.forEach(c => { ch[c.channel] = (ch[c.channel] || 0) + 1; });
  const channels = ['telegram', 'max', 'email'].map(k =>
    `<div class="frow"><span class="fname">${k === 'max' ? 'MAX' : (k === 'email' ? 'Почта' : 'Telegram')}</span>
      <span class="fbar"><i style="width:${Math.round((ch[k] || 0) / Math.max(1, cl.length) * 100)}%"></i></span>
      <span class="fnum">${ch[k] || 0}</span></div>`).join('');
  const card = (v, l) => `<div class="scard"><div class="snum">${v}</div><div class="slbl">${l}</div></div>`;
  document.getElementById('body').innerHTML = `<div>
    <div class="sgrid">
      ${card(waiting, 'ждут ответа')}${card(apps, 'заявок')}${card(deals.length, 'сделок')}
      ${card(sum.toLocaleString('ru-RU') + ' ₽', 'сумма в работе')}${card(open, 'открытых дел')}${card(over, 'просрочено')}
    </div>
    <div class="spanel"><div class="sth">Воронка</div>${funnel}</div>
    <div class="spanel"><div class="sth">Каналы</div>${channels}</div>
  </div>`;
}

function renderPulse(){
  const all = cache.clients || [];
  const cl = all.filter(c => !c.archived);
  const w = cl.filter(c => c.status === 'waiting').length;
  const apps = cl.reduce((n, c) => n + (c.apps || 0), 0);
  const narch = all.filter(c => c.archived).length;
  const el = document.getElementById('pulse');
  if (el){
    el.innerHTML = `<span class="pfilter ${onlyWaiting ? 'on' : ''}" id="pWait"><b>${w}</b> ждут ответа</span>
      · <b>${apps}</b> заявок · ${cl.length} диалогов
      · <span class="pfilter ${showArchive ? 'on' : ''}" id="pArch">архив ${narch}</span>`;
    const pw = document.getElementById('pWait');
    if (pw) pw.onclick = () => { onlyWaiting = !onlyWaiting; renderList(); renderPulse(); };
    const pa = document.getElementById('pArch');
    if (pa) pa.onclick = () => { showArchive = !showArchive; renderList(); renderPulse(); };
  }
}

function renderSecs(){
  const box = document.getElementById('secs');
  if (!box) return;
  const secs = (cache.sections || {}).sections || [];
  const counts = {};
  const activeClients = (cache.clients || []).filter(c => !c.archived);
  activeClients.forEach(c => { const k = c.section || ''; counts[k] = (counts[k] || 0) + 1; });
  let html = `<div class="sec ${secFilter === null ? 'on' : ''}" role="button" tabindex="0" data-sf="all">Все ${activeClients.length}</div>`;
  html += `<div class="sec ${secFilter === '' ? 'on' : ''}" role="button" tabindex="0" data-sf="">Без раздела${counts[''] ? ' ' + counts[''] : ''}</div>`;
  secs.forEach(s => {
    html += `<div class="sec ${secFilter === s.id ? 'on' : ''}" role="button" tabindex="0" data-sf="${s.id}" data-sec="${s.id}"
      title="Правый клик — удалить">${esc(s.name)}${counts[s.id] ? ' ' + counts[s.id] : ''}<span class="pencil" data-ren="${s.id}" title="Переименовать" role="button" tabindex="0">✏</span></div>`;
  });
  html += `<div class="sec add" role="button" tabindex="0" id="secAdd">＋ Раздел</div>`;
  html += `<div class="sec" role="button" tabindex="0" id="secManage" title="Управление разделами">⋯</div>`;
  box.innerHTML = html;
  box.querySelectorAll('[data-sf]').forEach(el => el.onclick = () => {
    secFilter = el.dataset.sf === 'all' ? null : el.dataset.sf;
    renderSecs(); renderList();
  });
  box.querySelectorAll('[data-ren]').forEach(el => {
    el.onclick = e => { e.stopPropagation(); renameSectionFlow(el.dataset.ren); };
  });
  box.querySelectorAll('[data-sec]').forEach(el => {
    el.draggable = true;
    el.ondragstart = e => {
      secDragId = el.dataset.sec;
      e.dataTransfer.setData('text/plain', secDragId);
      el.classList.add('drag');
    };
    el.ondragend = () => { secDragId = null; el.classList.remove('drag'); };
    el.ondragover = e => e.preventDefault();
    el.ondrop = async e => {
      e.preventDefault();
      const src = secDragId, dst = el.dataset.sec;
      el.classList.remove('drag');
      if (!src || src === dst) return;
      const ids = ((cache.sections || {}).sections || []).map(s => s.id);
      const from = ids.indexOf(src), to = ids.indexOf(dst);
      if (from < 0 || to < 0) return;
      ids.splice(to, 0, ids.splice(from, 1)[0]);
      await api('/api/sections/order', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ids})});
      await refresh();
    };
    el.ondblclick = e => { e.stopPropagation(); renameSectionFlow(el.dataset.sec); };
    el.oncontextmenu = e => { e.preventDefault(); removeSection(el.dataset.sec); };
  });
  const add = document.getElementById('secAdd');
  if (add) add.onclick = addSectionFlow;
  const manage = document.getElementById('secManage');
  if (manage) manage.onclick = manageSections;
}

function manageSections(){
  const secs = (cache.sections || {}).sections || [];
  const m = document.createElement('div');
  m.className = 'modal'; m.id = 'secModal';
  m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true');
  m.setAttribute('aria-label', 'Управление разделами');
  m.innerHTML = `<div class="mcard" style="width:min(400px,92vw)">
    <div class="mh"><span>Разделы</span><span class="x" id="smClose">✕</span></div>
    ${secs.map(s => `<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px">
      <input value="${esc(s.name)}" data-secname="${s.id}" style="flex:1">
      <button class="btn" data-secsave="${s.id}">OK</button>
      <button class="btn no" data-secdel="${s.id}">✕</button></div>`).join('')
      || '<div class="mnotes">Разделов пока нет</div>'}
  </div>`;
  document.body.appendChild(m);
  const close = () => m.remove();
  m.tabIndex = -1;
  m.focus();
  m.onkeydown = e => { if (e.key === 'Escape') close(); };
  m.querySelector('#smClose').onclick = close;
  m.onclick = e => { if (e.target === m) close(); };
  m.querySelectorAll('[data-secsave]').forEach(b => b.onclick = async () => {
    const id = b.dataset.secsave;
    const name = m.querySelector(`[data-secname="${id}"]`).value.trim();
    if (!name) return;
    await api('/api/sections/rename', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id, name})});
    close();
    await refresh();
  });
  m.querySelectorAll('[data-secdel]').forEach(b => b.onclick = async () => {
    if (!confirm('Удалить раздел? Диалоги останутся.')) return;
    await api('/api/sections/delete', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id: b.dataset.secdel})});
    close();
    secFilter = null;
    await refresh();
  });
}

function renameSectionFlow(sid){
  const box = document.getElementById('secs');
  const old = secName(sid);
  box.innerHTML = `<input id="secName" value="${esc(old)}" maxlength="40">
    <div class="sec" id="secOk">Сохранить</div>
    <div class="sec" id="secCancel">Отмена</div>`;
  const inp = document.getElementById('secName');
  inp.focus(); inp.select();
  const save = async () => {
    const name = inp.value.trim();
    if (!name) return;
    await api('/api/sections/rename', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id: sid, name})});
    document.getElementById('secs').innerHTML = '';
    await refresh();
  };
  document.getElementById('secOk').onclick = save;
  document.getElementById('secCancel').onclick = () => renderSecs();
  inp.onkeydown = e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') renderSecs(); };
}

async function removeSection(sid){
  if (!confirm('Удалить раздел «' + secName(sid) + '»? Диалоги останутся.')) return;
  await api('/api/sections/delete', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id: sid})});
  if (secFilter === sid) secFilter = null;
  await refresh();
}

function addSectionFlow(){
  const box = document.getElementById('secs');
  box.innerHTML = `<input id="secName" placeholder="Название раздела" maxlength="40">
    <div class="sec" id="secOk">Сохранить</div>
    <div class="sec" id="secCancel">Отмена</div>`;
  const inp = document.getElementById('secName');
  inp.focus();
  const save = async () => {
    const name = inp.value.trim();
    if (!name) return;
    await api('/api/sections/add', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name})});
    document.getElementById('secs').innerHTML = '';
    await refresh();
  };
  document.getElementById('secOk').onclick = save;
  document.getElementById('secCancel').onclick = () => renderSecs();
  inp.onkeydown = e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') renderSecs(); };
}

function renameDialog(key, currentName){
  const m = document.createElement('div');
  m.className = 'modal'; m.id = 'renameModal';
  m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true');
  m.setAttribute('aria-label', 'Переименовать');
  m.innerHTML = `<div class="mcard" style="width:min(420px,92vw)">
    <div class="mh"><span>Переименовать</span><span class="x" id="rnClose">✕</span></div>
    <label>Имя или название</label>
    <input id="rnName" maxlength="120" value="${escAttr(currentName || '')}" autocomplete="off">
    <div class="mnotes">Для объединённого клиента имя меняется сразу во всех каналах.</div>
    <button class="btn pri" id="rnSave" style="margin-top:10px;width:100%">Сохранить</button>
  </div>`;
  document.body.appendChild(m);
  const close = () => m.remove();
  const reopen = current;
  m.querySelector('#rnClose').onclick = close;
  m.onclick = e => { if (e.target === m) close(); };
  m.tabIndex = -1; m.focus();
  m.onkeydown = e => { if (e.key === 'Escape') close(); };
  const input = m.querySelector('#rnName');
  input.focus(); input.select();
  const save = async () => {
    const name = input.value.trim();
    if (!name){ toast('Введите имя'); return; }
    await api('/api/rename', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key, name})});
    close(); toast('Название сохранено');
    await refresh();
    if (reopen) open(reopen);
  };
  m.querySelector('#rnSave').onclick = save;
  input.onkeydown = e => { if (e.key === 'Enter') save(); };
}

async function showCard(key){
  let d = ((cache.crm || {}).deals || []).find(x => x.key === key);
  if (!d){
    try {
      cache.crm = await api('/api/crm');
      d = (cache.crm.deals || []).find(x => x.key === key);
    } catch (e) {}
  }
  if (!d){ toast('Карточка не загрузилась — обновите страницу'); return; }
  const stages = ((cache.crm || {}).stages || []).map(s =>
    `<option value="${s.id}"${s.id === d.stage ? ' selected' : ''}>${esc(s.name)}</option>`).join('');
  const notes = (d.notes || []).slice(-5).reverse()
    .map(n => `<div>${esc(n.ts)} — ${esc(n.text)}</div>`).join('');
  const m = document.createElement('div');
  m.className = 'modal'; m.id = 'cardModal';
  m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true');
  m.setAttribute('aria-label', 'Карточка клиента');
  m.innerHTML = `<div class="mcard">
    <div class="mh"><span>${esc(d.title || d.who)}</span><span class="x" id="mClose">✕</span></div>
    <label>Телефон</label><input id="mPhone" aria-label="Телефон" value="${esc(d.phone || '')}" placeholder="+7 (999) 123-45-67">
    <label>Клиника</label><input id="mClinic" aria-label="Клиника" value="${esc(d.clinic || '')}" placeholder="Название клиники">
    <div class="mrow"><span>Каналы</span><b>${(d.channels && d.channels.length ? d.channels : [d.channel]).map(ch => ch === 'max' ? 'MAX' : (ch === 'email' ? 'Почта' : (ch === 'whatsapp' ? 'WhatsApp' : 'Telegram'))).join(' + ')}</b></div>
    <div class="mrow"><span>Сообщений</span><b>${d.count || 0} · заявок ${d.apps || 0}</b></div>
    <div class="mrow"><span>Последнее</span><b>${esc(d.last_ts || '—')}</b></div>
    <label>Этап</label><select id="mStage" aria-label="Этап сделки">${stages}</select>
    <label>Сумма, ₽</label><input id="mAmount" aria-label="Сумма сделки" type="number" value="${Number(d.amount) || ''}" placeholder="например 10000">
    <label>Метки (через запятую)</label><input id="mTags" aria-label="Метки" value="${esc((d.tags || []).join(', '))}" placeholder="например: клиника, демо">
    <label>Заметка</label><textarea id="mNote" aria-label="Заметка о клиенте" placeholder="что обсудили">${esc(d.note || '')}</textarea>
    <label>Новое дело</label><input id="mTask" aria-label="Новое дело" placeholder="Позвонить, отправить демо…">
    <label>Когда</label><input id="mAt" aria-label="Срок дела" type="date">
    <label>История заметок</label>
    <div class="mnotes" id="mNotes">${notes || '<div>Пока нет</div>'}</div>
    <input id="mNoteNew" aria-label="Новая заметка" placeholder="Добавить заметку в историю">
    <button class="btn" id="mNoteAdd" style="margin-top:6px">＋ Добавить заметку</button>
    <button class="btn pri" id="mSave" style="margin-top:10px;width:100%">Сохранить</button>
  </div>`;
  document.body.appendChild(m);
  let dirty = false;
  m.querySelectorAll('input,textarea,select').forEach(el => el.oninput = () => { dirty = true; });
  const close = () => {
    if (dirty && !confirm('Закрыть карточку без сохранения?')) return;
    m.remove();
  };
  m.tabIndex = -1;
  m.focus();
  m.onkeydown = e => { if (e.key === 'Escape') close(); };
  m.querySelector('#mClose').onclick = close;
  m.onclick = e => { if (e.target === m) close(); };
  m.querySelector('#mNoteAdd').onclick = async () => {
    const txt = m.querySelector('#mNoteNew').value.trim();
    if (!txt) return;
    await api('/api/crm/note', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key, text: txt})});
    dirty = false;
    close();
    await refresh();
    showCard(key);
  };
  m.querySelector('#mSave').onclick = async () => {
    const tags = m.querySelector('#mTags').value.split(',').map(s => s.trim()).filter(Boolean);
    await api('/api/crm/deal', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key, stage: m.querySelector('#mStage').value,
        amount: Number(m.querySelector('#mAmount').value) || 0, tags,
        phone: m.querySelector('#mPhone').value.trim(),
        clinic: m.querySelector('#mClinic').value.trim(),
        note: m.querySelector('#mNote').value})});
    const task = m.querySelector('#mTask').value.trim();
    if (task) await api('/api/crm/task', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({key, text: task, at: m.querySelector('#mAt').value})});
    dirty = false;
    close();
    refresh();
  };
}

function setHeader(title, sub, badge, avatar){
  document.getElementById('title').textContent = title;
  document.getElementById('sub').textContent = sub;
  document.getElementById('badge').innerHTML = badge || '';
  const a = document.getElementById('ava');
  if (avatar){ a.style.display = 'grid'; a.textContent = avatar.t; a.style.background = avatar.c; }
  else a.style.display = 'none';
}

async function open(id){
  const ta = document.getElementById('text');
  if (current && current !== id) drafts[current] = ta.value;
  const same = current === id;
  current = id;
  renderList();
  const body = document.getElementById('body');
  const composer = document.getElementById('composer');

  if (sec === 'clients'){
    const d = await api('/api/client/' + id);
    const cl = (cache.clients || []).find(x => String(x.chat) === String(id)) || {};
    const chs = (d.channels && d.channels.length) ? d.channels : [d.channel];
    const chLabel = ch => ch === 'max' ? 'MAX' : (ch === 'email' ? 'Почта' : (ch === 'whatsapp' ? 'WhatsApp' : 'Telegram'));
    const chCls = ch => ch === 'max' ? 'max' : (ch === 'email' ? 'em' : (ch === 'whatsapp' ? 'wa' : 'tg'));
    let badge = chs.map(ch => `<span class="pill ${chCls(ch)}">${chLabel(ch)}</span>`).join(' ');
    if (d.merged && cl.keys && cl.keys.length > 1)
      badge += ` <span class="chip done" title="${esc(cl.keys.join(', '))}">объединён</span>`;
    badge += ` <button class="btn" id="btnRename" title="Переименовать" aria-label="Переименовать" style="padding:4px 8px">✏</button>`;
    const secs = (cache.sections || {}).sections || [];
    const curSec = cl.section || '';
    badge += ` <select class="secsel" id="secSel" aria-label="Раздел диалога" title="Раздел"><option value="">Без раздела</option>` +
      secs.map(s => `<option value="${s.id}"${s.id === curSec ? ' selected' : ''}>${esc(s.name)}</option>`).join('') +
      `</select>`;
    badge += ` <button class="btn" id="btnCard" style="padding:4px 10px;font-size:12px">📇 Карточка</button>`;
    badge += ` <button class="btn" id="btnArch" style="padding:4px 10px;font-size:12px">${cl.archived ? 'Вернуть' : '🗄 В архив'}</button>`;
    if (cl.bot_paused)
      badge += ` <span class="pill" style="background:#fff4e6;color:#b25e09">бот выкл до ${cl.pause_until||'—'}</span>
                 <button class="btn" style="padding:4px 10px;font-size:12px" data-act="resume" data-id="${encodeURIComponent(id)}">Вернуть бота</button>`;
    setHeader(d.who || id, d.messages.length + ' сообщений', badge,
      {t: initial(d.who), c: color(d.who)});
    const btnCard = document.getElementById('btnCard');
    if (btnCard) btnCard.onclick = () => showCard(cl.key || (d.channel + ':' + id));
    const btnRename = document.getElementById('btnRename');
    if (btnRename) btnRename.onclick = () => renameDialog(cl.key || (d.channel + ':' + id), d.who || id);
    const btnArch = document.getElementById('btnArch');
    if (btnArch) btnArch.onclick = async () => {
      const key = cl.key || (d.channel + ':' + id);
      await api('/api/archive', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({key, archived: !cl.archived})});
      toast(cl.archived ? 'Возвращён во входящие' : 'Убран в архив');
      await refresh();
      if (current) open(current);
    };
    const secSel = document.getElementById('secSel');
    if (secSel) secSel.onchange = async () => {
      const key = cl.key || (d.channel + ':' + id);
      await api('/api/sections/assign', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({key, section: secSel.value})});
      toast('Раздел сохранён');
      refresh();
    };
    let html = '', lastDay = '';
    d.messages.forEach(m => {
      const day = fmtDay(m.ts);
      if (day !== lastDay){ html += `<div class="day">${day}</div>`; lastDay = day; }
      const a = m.author || 'client';
      const cls = (a === 'bot' || a === 'owner') ? 'me' : 'them';
      const extra = a === 'bot' ? ' bot' : (a === 'owner' ? ' owner' : (m.tech ? ' tech' : (m.app ? ' app' : '')));
      const label = a === 'bot' ? '<span class="who-lbl">БОТ</span>'
                  : (a === 'owner' ? '<span class="who-lbl">ВЫ</span>' : '');
      const srv = /^\/(start|help|what|demo|price|order|bug)\b/i.test(m.text || '');
      const chan = (d.merged && m.channel) ? `<span class="chanlbl">${chShort(m.channel)}</span> · ` : '';
      const st = m.status || 'sent';
      const tick = a === 'owner'
        ? ` <span class="ticks ${st}" title="${st === 'read' ? 'Прочитано — клиент ответил после' : (st === 'delivered' ? 'Доставлено клиенту' : 'Отправлено')}">${st === 'read' || st === 'delivered' ? '✓✓' : (st === 'failed' ? '!' : '✓')}</span>`
        : '';
      html += `<div class="line ${cls}"><div class="bub${extra}${srv ? ' srv' : ''}">${label}${esc(prettyText(m.text))}<span class="meta">${chan}${fmtTime(m.ts)}${tick}</span></div></div>`;
    });
    body.innerHTML = html || '<div class="empty">Сообщений нет</div>';
    body.dataset.count = String(d.total);
    composer.style.display = 'flex';
    const rc = document.getElementById('replyChan');
    if (rc){
      if (d.merged && d.targets && d.targets.length > 1){
        rc.style.display = 'inline-block';
        rc.innerHTML = d.targets.map(t => `<option value="${escAttr(t.key)}">Куда: ${esc(t.label)}</option>`).join('');
      } else {
        rc.style.display = 'none';
      }
    }
    ta.value = same ? ta.value : (drafts[id] || '');
    ta.placeholder = (d.channel === 'max' ? 'Ответ в MAX' :
                      (d.channel === 'email' ? 'Ответ на почту' :
                       (d.channel === 'whatsapp' ? 'Ответ в WhatsApp' : 'Ответ в Telegram')))
                     + '… (Enter — отправить, Shift+Enter — новая строка)';
    requestAnimationFrame(() => { body.scrollTop = body.scrollHeight; });
    if (window.innerWidth > 900) ta.focus();
    bindActions();
  } else if (sec === 'errors'){
    const e = cache.errors.find(x => x.id === id) || {};
    setHeader('Ошибка', fmtDay(e.ts) + ' · ' + fmtTime(e.ts), '<span class="pill">требует решения</span>',
      {t:'!', c:'#e5484d'});
    body.innerHTML = `<div class="card">
        <h3>${esc(e.where || 'бот')}</h3>
        <div class="where">${esc(e.ts || '')}</div>
        <p>${esc(e.text || '')}</p>
        <div class="acts">
          <button class="btn pri" data-act="apply" data-id="${encodeURIComponent(id)}">Принять в работу</button>
          <button class="btn no" data-act="reject" data-id="${encodeURIComponent(id)}">Отклонить</button>
        </div></div>`;
    composer.style.display = 'none';
    bindActions();
  } else if (sec === 'fixes'){
    const f = cache.fixes.find(x => x.id === id) || {};
    setHeader('Задача', f.created || '', '<span class="pill">в работе</span>', {t:'🛠', c:'#f59e0b'});
    body.innerHTML = `<div class="card">
        <h3>${esc(f.summary || '')}</h3>
        <div class="where">${esc(f.created || '')}</div>
        <p>${esc(f.text || '')}${f.hint ? '\n\nЧто делать: ' + esc(f.hint) : ''}</p>
        <div class="acts"><button class="btn ok" data-act="done" data-id="${encodeURIComponent(id)}">Исправлено</button></div>
      </div>`;
    composer.style.display = 'none';
    bindActions();
  } else {
    const s = cache.spam.find(x => x.id === id) || {};
    setHeader('Спам', s.ts || '', '<span class="pill">реклама</span>', {t:'🚫', c:'#8b93a1'});
    body.innerHTML = `<div class="card"><h3>${esc(s.who||'—')}</h3><div class="where">${esc(s.ts||'')}</div><p>${esc(s.text||'')}</p></div>`;
    composer.style.display = 'none';
  }
}

function bindActions(){
  document.querySelectorAll('button[data-act]').forEach(btn => {
    btn.onclick = async () => {
      btn.disabled = true;
      const act = btn.dataset.act, id = decodeURIComponent(btn.dataset.id);
      if (act === 'reject' && !confirm('Отклонить ошибку? Она исчезнет из списка.')){ btn.disabled = false; return; }
      let r = {ok:false};
      try {
        if (act === 'apply')  r = await api('/api/errors/' + encodeURIComponent(id) + '/apply',  {method:'POST'});
        if (act === 'reject') r = await api('/api/errors/' + encodeURIComponent(id) + '/reject', {method:'POST'});
        if (act === 'done')   r = await api('/api/fixes/'  + encodeURIComponent(id) + '/done',   {method:'POST'});
        if (act === 'resume') r = await api('/api/resume/' + encodeURIComponent(id),             {method:'POST'});
      } catch(e) {}
      toast(r.ok ? 'Готово' : 'Не получилось');
      current = null;
      await refresh();
      if (sec === 'errors'){ setErrorsHeader(); errorsEmpty(); }
      else if (sec === 'fixes'){ showFixes(); }
      else {
        document.getElementById('body').innerHTML =
          '<div class="empty"><div><div class="ic">✓</div>Готово</div></div>';
        setHeader(TITLES[sec] || 'Диалоги', 'Выберите слева', '');
      }
    };
  });
}

async function send(){
  if (window.__sending) return;
  const box = document.getElementById('text');
  const text = box.value.trim();
  if (!text || !current) return;
  window.__sending = true;
  const btn = document.getElementById('send');
  if (btn) btn.disabled = true;
  try {
    const r = await api('/api/reply', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({chat: current, text,
        channel: (document.getElementById('replyChan') || {}).value || ''})});
    if (r.ok){
      box.value = ''; box.style.height = 'auto';
      delete drafts[current];
    } else {
      box.value = text;
      box.style.height = 'auto';
      box.style.height = Math.min(box.scrollHeight, 130) + 'px';
      saveDraft();
    }
    toast(r.ok ? 'Отправлено' : 'Не ушло — текст сохранён');
    if (r.ok) open(current);
  } finally {
    window.__sending = false;
    if (btn) btn.disabled = false;
  }
}

document.getElementById('send').onclick = send;
document.getElementById('text').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); send(); }
});
document.getElementById('text').addEventListener('input', function(){
  this.style.height = 'auto'; this.style.height = Math.min(this.scrollHeight, 130) + 'px';
});
document.getElementById('q').oninput = renderList;

document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
  t.classList.add('on');
  saveDraft();
  sec = t.dataset.sec; current = null;
  const sbox = document.getElementById('secs');
  if (sbox) sbox.innerHTML = '';
  renderSecs();
  const board = sec === 'deals' || sec === 'tasks' || sec === 'stats' || sec === 'calendar';
  document.body.classList.toggle('wide', board);
  const secsBox = document.getElementById('secs');
  if (secsBox) secsBox.style.display = sec === 'clients' ? 'flex' : 'none';
  document.getElementById('composer').style.display = 'none';
  document.getElementById('badge').innerHTML = '';
  const subs = {clients:'Выберите диалог слева', deals:'Перетащите карточку по этапам',
                tasks:'Что нужно сделать и когда', errors:'Что сломалось и требует решения',
                fixes:'Принятые ошибки в работе', spam:'Реклама от клиентов'};
  setHeader(TITLES[sec], subs[sec], '');
  if (sec === 'errors') setErrorsHeader();
  if (sec === 'deals'){ renderDealsView(); return; }
  if (sec === 'tasks'){ renderTasks(); return; }
  if (sec === 'stats'){ renderStats(); return; }
  if (sec === 'calendar'){ renderCalendar(); return; }
  document.getElementById('body').innerHTML = '<div class="empty"><div><div class="ic">👈</div>' + subs[sec] + '</div></div>';
  renderList();
});

const MACROS = [
  {t: 'Цены', s: 'Бот записи — 10 000 ₽, запуск 5–10 дней. Оплата 50/50. Могу показать демо.'},
  {t: 'Демо', s: 'Вот как это выглядит: https://ufa-zapis.surge.sh/demos/moj-doktor.html'},
  {t: 'Перезвоню', s: 'Спасибо! Перезвоню в течение часа.'},
  {t: 'Записал', s: 'Записал. Администратор подтвердит запись в течение 15 минут.'},
  {t: 'Спасибо', s: 'Спасибо за обращение! Если будут вопросы — пишите.'}
];
function renderMacros(){
  const box = document.getElementById('macros');
  if (!box) return;
  box.innerHTML = MACROS.map((m, i) => `<div class="macro" role="button" tabindex="0" data-m="${i}">${esc(m.t)}</div>`).join('')
    + `<div class="macro" role="button" tabindex="0" id="aiDraft">✨ Предложить</div>`;
  box.querySelectorAll('[data-m]').forEach(el => el.onclick = () => {
    const ta = document.getElementById('text');
    const txt = MACROS[+el.dataset.m].s;
    ta.value = ta.value.trim() ? ta.value.replace(/\s+$/, '') + ' ' + txt : txt;
    ta.focus();
    ta.dispatchEvent(new Event('input'));
  });
  const ai = document.getElementById('aiDraft');
  ai.onclick = async () => {
    if (!current) return;
    ai.textContent = 'Думаю…';
    const r = await api('/api/ai_draft', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({chat: current})});
    ai.textContent = '✨ Предложить';
    if (r.ok && r.text){
      const ta = document.getElementById('text');
      ta.value = r.text;
      ta.focus();
      ta.dispatchEvent(new Event('input'));
    } else {
      toast('Нейросеть не ответила');
    }
  };
}

// живые уведомления
let lastTotal = null;
function live(){
  const total = cache.clients.reduce((n,c)=>n+(c.in_count||0), 0);
  if (lastTotal !== null && total > lastTotal){
    const c = cache.clients.reduce((a,b) => (!a || (b.last_ts || '') > (a.last_ts || '')) ? b : a, null);
    toast('Новое сообщение' + (c ? ': ' + c.who : ''));
    try {
      const ctx = new (window.AudioContext||window.webkitAudioContext)();
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.connect(g); g.connect(ctx.destination); o.frequency.value = 720; g.gain.value = .05;
      o.start(); setTimeout(()=>{o.stop();ctx.close();}, 150);
    } catch(e) {}
    if (window.Notification && Notification.permission === 'granted')
      new Notification('Зиныч IT', {body: c ? (c.who + ': ' + c.last.slice(0,70)) : 'Новое сообщение'});
  }
  lastTotal = total;
}
if (window.Notification && Notification.permission === 'default')
  document.body.addEventListener('click', () => Notification.requestPermission(), {once:true});

function openPalette(){
  if (document.getElementById('palette')) return;
  const m = document.createElement('div');
  m.className = 'modal'; m.id = 'palette';
  m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true');
  m.setAttribute('aria-label', 'Быстрый поиск');
  m.innerHTML = `<div class="mcard" style="width:min(520px,92vw);padding:12px">
    <input id="palQ" aria-label="Поиск клиента или раздела" placeholder="Клиент, телефон или имя…" autocomplete="off">
    <div class="pallist" id="palList" style="margin-top:8px"></div></div>`;
  document.body.appendChild(m);
  const inp = document.getElementById('palQ'), list = document.getElementById('palList');
  const close = () => m.remove();
  m.onclick = e => { if (e.target === m) close(); };
  m.onkeydown = e => { if (e.key === 'Escape') close(); };
  const draw = () => {
    const q = inp.value.trim().toLowerCase();
    const cmds = [['Диалоги', 'clients'], ['Сделки', 'deals'], ['Дела', 'tasks'],
                  ['Календарь', 'calendar'], ['Сводка', 'stats'], ['Проблемы', 'errors']]
      .filter(([t]) => !q || t.toLowerCase().includes(q));
    const items = (cache.clients || []).filter(c =>
      !q || (c.who + ' ' + c.chat + ' ' + (c.phone || '')).toLowerCase().includes(q)).slice(0, 8);
    list.innerHTML = cmds.map(([t, s]) => `<div class="palitem" data-tab="${s}">
        <b>${t}</b><span>перейти</span></div>`).join('') +
      items.map(c => `<div class="palitem" data-chat="${esc(c.chat)}">
        <b>${esc(c.who)}</b><span>${c.channel === 'max' ? 'MAX' : (c.channel === 'email' ? 'Почта' : 'Telegram')}
        · ${esc(c.phone || c.chat)}</span></div>`).join('') ||
      '<div class="palempty">Ничего не найдено</div>';
    list.querySelectorAll('[data-tab]').forEach(el => el.onclick = () => {
      close();
      const tab = document.querySelector(`[data-sec="${el.dataset.tab}"]`);
      if (tab) tab.click();
    });
    list.querySelectorAll('[data-chat]').forEach(el => el.onclick = () => {
      close(); showClientsTab(); open(el.dataset.chat);
    });
  };
  inp.oninput = draw;
  draw();
  inp.focus();
  inp.onkeydown = e => {
    if (e.key === 'Escape') close();
    if (e.key === 'Enter'){ const f = list.querySelector('.palitem'); if (f) f.click(); }
  };
}
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k'){ e.preventDefault(); openPalette(); }
  if (e.altKey && /^[1-6]$/.test(e.key)){
    const t = document.querySelectorAll('.tab')[+e.key - 1];
    if (t){ e.preventDefault(); t.click(); }
  }
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('.tab,.sec,.conv,.macro,.deal,.ldrow')){
    e.preventDefault();
    e.target.click();
  }
});
document.getElementById('brand').onclick = () => document.querySelector('[data-sec="clients"]').click();

renderMacros();
refresh();
setInterval(refresh, 5000);
</script></body></html>"""


# ------------------------------------------------------------------ данные

def read_events() -> list[dict]:
    if not EVENTS.exists():
        return []
    out = []
    for line in EVENTS.read_text(encoding="utf-8").splitlines()[-1200:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def event_key(e: dict) -> str:
    return f"{e.get('ts')}|{e.get('source')}|{(e.get('text') or '')[:80]}"


# ------------------------------------------------------------------ разделы

def sections_state() -> dict:
    data = load_json(SECTIONS, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("sections", [])
    data.setdefault("map", {})
    return data


def save_sections(data: dict) -> None:
    SECTIONS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def add_section(name: str) -> dict:
    name = (name or "").strip()[:40]
    if not name:
        return {}
    data = sections_state()
    sid = "s" + str(int(time.time() * 1000))
    data["sections"].append({"id": sid, "name": name})
    save_sections(data)
    return {"id": sid, "name": name}


def rename_section(sid: str, name: str) -> bool:
    name = (name or "").strip()[:40]
    if not name:
        return False
    data = sections_state()
    for s in data["sections"]:
        if s["id"] == sid:
            s["name"] = name
            save_sections(data)
            return True
    return False


def reorder_sections(ids: list[str]) -> bool:
    data = sections_state()
    order = {sid: i for i, sid in enumerate(ids)}
    data["sections"].sort(key=lambda s: order.get(s["id"], 999))
    save_sections(data)
    return True


def delete_section(sid: str) -> bool:
    data = sections_state()
    data["sections"] = [s for s in data["sections"] if s["id"] != sid]
    data["map"] = {k: v for k, v in data["map"].items() if v != sid}
    save_sections(data)
    return True


def assign_section(key: str, sid: str) -> bool:
    data = sections_state()
    if sid and not any(s["id"] == sid for s in data["sections"]):
        return False
    if sid:
        data["map"][key] = sid
    else:
        data["map"].pop(key, None)
    save_sections(data)
    return True


# ------------------------------------------------------------------ CRM

def crm_state() -> dict:
    data = load_json(CRM, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("deals", {})
    data.setdefault("tasks", [])
    data.setdefault("notes", {})
    return data


def save_crm(data: dict) -> None:
    CRM.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def crm_deal(key: str, **fields) -> bool:
    data = crm_state()
    deal = data["deals"].setdefault(key, {"stage": "new", "amount": 0, "tags": [],
                                          "note": "", "title": ""})
    if "stage" in fields and fields["stage"] not in dict(STAGES):
        return False
    for name in ("stage", "amount", "tags", "note", "title", "phone", "clinic"):
        if name in fields and fields[name] is not None:
            deal[name] = fields[name]
    deal["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_crm(data)
    return True


def crm_task_add(key: str, text: str, at: str = "") -> dict:
    text = (text or "").strip()[:200]
    if not text:
        return {}
    data = crm_state()
    tid = "t" + str(int(time.time() * 1000))
    task = {"id": tid, "key": key, "text": text, "at": at or "",
            "done": False, "notified": False, "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    data["tasks"].append(task)
    save_crm(data)
    return task


def crm_task_done(tid: str) -> bool:
    data = crm_state()
    for t in data["tasks"]:
        if t["id"] == tid:
            t["done"] = not t["done"]
            save_crm(data)
            return True
    return False


def crm_task_delete(tid: str) -> bool:
    data = crm_state()
    before = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != tid]
    if len(data["tasks"]) != before:
        save_crm(data)
        return True
    return False


def reminder_check() -> None:
    """Раз в минуту: дела со сроком «сегодня/просрочено» — владельцу в Telegram, один раз."""
    data = crm_state()
    today = time.strftime("%Y-%m-%d")
    due = []
    for t in data["tasks"]:
        if not t.get("done") and not t.get("notified") and t.get("at") and t["at"] <= today:
            t["notified"] = True
            due.append(t)
    if not due:
        return
    save_crm(data)
    import relay
    for t in due:
        try:
            relay.send_reply("tg", relay.OWNER_TG,
                             f"⏰ Дело: {t['text']}\nСрок: {t.get('at', '')}")
        except Exception:  # noqa: BLE001
            pass


def crm_note_add(key: str, text: str) -> bool:
    text = (text or "").strip()[:1000]
    if not text:
        return False
    data = crm_state()
    data["notes"].setdefault(key, []).append(
        {"ts": time.strftime("%Y-%m-%d %H:%M"), "text": text})
    save_crm(data)
    return True


def cold_script_text() -> str:
    data = load_json(COLD_SCRIPT, {})
    return (data.get("text") if isinstance(data, dict) else "") or DEFAULT_COLD_SCRIPT


def cold_state() -> dict:
    data = load_json(COLD, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("leads", [])
    data["script"] = cold_script_text()
    return data


def archive_state() -> dict:
    data = load_json(ARCHIVE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("keys", {})
    return data


def set_archived(key: str, on: bool) -> bool:
    data = archive_state()
    if on:
        data["keys"][key] = time.strftime("%Y-%m-%d %H:%M:%S")
    else:
        data["keys"].pop(key, None)
    ARCHIVE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def merge_groups() -> tuple[list[dict], dict[str, dict]]:
    data = load_json(MERGES, {})
    groups = data.get("groups") if isinstance(data, dict) else []
    if not isinstance(groups, list):
        groups = []
    by_key: dict[str, dict] = {}
    for g in groups:
        for k in g.get("keys") or []:
            by_key[str(k)] = g
    return groups, by_key


def names_state() -> dict:
    data = load_json(NAMES, {})
    names = data.get("names") if isinstance(data, dict) else {}
    return names if isinstance(names, dict) else {}


def set_client_name(key: str, name: str) -> str:
    """Переименовать клиента/контакт; для объединённого — имя всей группы."""
    key = str(key or "").strip()
    if not key:
        return ""
    groups, by_key = merge_groups()
    if ":" not in key:
        found = next((c for c in clients() if str(c.get("chat")) == key), None)
        key = (found or {}).get("key", key)
    group = by_key.get(key)
    if group:
        group["name"] = name.strip()
        MERGES.write_text(json.dumps({"groups": groups}, ensure_ascii=False, indent=1), encoding="utf-8")
        key = group.get("primary", key)
    data = load_json(NAMES, {})
    names = data.get("names") if isinstance(data.get("names"), dict) else {}
    if name.strip():
        names[key] = name.strip()
    else:
        names.pop(key, None)
    NAMES.write_text(json.dumps({"names": names}, ensure_ascii=False, indent=1), encoding="utf-8")
    return key


def merge_clients(keys: list[str]) -> dict:
    keys = [str(k) for k in keys if ":" in str(k)]
    if len(keys) < 2:
        return {}
    groups, by_key = merge_groups()
    merged_keys: list[str] = []
    for g in groups:
        if any(k in (g.get("keys") or []) for k in keys):
            merged_keys.extend(g.get("keys") or [])
    all_keys = list(dict.fromkeys(keys + merged_keys))
    primary = all_keys[0]
    names = []
    for c in clients():
        if c.get("key") in all_keys and c.get("who") and not str(c["who"]).isdigit():
            names.append(str(c["who"]))
    name = max(names, key=len) if names else ""
    groups = [g for g in groups if not any(k in (g.get("keys") or []) for k in keys)]
    groups.append({"primary": primary, "keys": all_keys, "name": name})
    MERGES.write_text(json.dumps({"groups": groups}, ensure_ascii=False, indent=1), encoding="utf-8")

    # переносим разделы, архив, сделки, дела и заметки на главный ключ
    secs = sections_state()
    for k in all_keys[1:]:
        if k in secs["map"]:
            secs["map"].setdefault(primary, secs["map"][k])
            secs["map"].pop(k, None)
    save_sections(secs)

    arch = archive_state()
    at = next((arch["keys"][k] for k in all_keys if k in arch["keys"]), None)
    if at:
        arch["keys"][primary] = at
        for k in all_keys:
            arch["keys"].pop(k, None)
        ARCHIVE.write_text(json.dumps(arch, ensure_ascii=False, indent=1), encoding="utf-8")

    crm = crm_state()
    base = dict(crm["deals"].get(primary) or {})
    for k in all_keys[1:]:
        other = crm["deals"].pop(k, None)
        if other:
            for f, v in other.items():
                if f not in base or base[f] in ("", 0, [], None):
                    base[f] = v
    if base:
        crm["deals"][primary] = base
    crm["tasks"] = [dict(t, key=primary) if t.get("key") in all_keys else t for t in crm["tasks"]]
    for k in all_keys[1:]:
        if k in crm["notes"]:
            crm["notes"].setdefault(primary, []).extend(crm["notes"].pop(k))
    save_crm(crm)
    return {"primary": primary, "keys": all_keys, "name": name}


def delete_chats(chats: list[str]) -> int:
    targets = {str(c) for c in chats if str(c)}
    if not targets:
        return 0
    groups, _ = merge_groups()
    for g in groups:
        if g.get("primary", "").split(":", 1)[-1] in targets:
            for k in g.get("keys") or []:
                targets.add(str(k).split(":", 1)[-1])
    lines = EVENTS.read_text(encoding="utf-8").splitlines() if EVENTS.exists() else []
    keep, removed = [], 0
    for line in lines:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            keep.append(line)
            continue
        if str((e.get("extra") or {}).get("chat_id")) in targets:
            removed += 1
            continue
        keep.append(line)
    EVENTS.write_text("\n".join(keep) + "\n", encoding="utf-8")

    data = crm_state()
    for key in list(data["deals"]):
        if key.split(":", 1)[-1] in targets:
            data["deals"].pop(key, None)
    data["tasks"] = [t for t in data["tasks"]
                     if str(t.get("key", "")).split(":", 1)[-1] not in targets]
    for key in list(data["notes"]):
        if key.split(":", 1)[-1] in targets:
            data["notes"].pop(key, None)
    save_crm(data)

    secs = sections_state()
    secs["map"] = {k: v for k, v in secs["map"].items()
                   if k.split(":", 1)[-1] not in targets}
    save_sections(secs)

    groups, _ = merge_groups()
    groups = [g for g in groups
              if not any(str(k).split(":", 1)[-1] in targets for k in g.get("keys") or [])]
    MERGES.write_text(json.dumps({"groups": groups}, ensure_ascii=False, indent=1), encoding="utf-8")
    return removed


def cold_scan() -> dict:
    import lead_scanner
    return lead_scanner.scan()


def cold_delete(lid: str) -> bool:
    data = cold_state()
    before = len(data["leads"])
    data["leads"] = [l for l in data["leads"] if l.get("id") != lid]
    if len(data["leads"]) == before:
        return False
    COLD.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def cold_update(lid: str, **fields) -> bool:
    data = cold_state()
    for lead in data["leads"]:
        if lead.get("id") != lid:
            continue
        for name in ("name", "status", "note", "phone", "email", "script", "messengers"):
            if name in fields and fields[name] is not None:
                lead[name] = fields[name]
        COLD.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return True
    return False


def deals_view() -> list[dict]:
    data = crm_state()
    out = []
    for c in clients():
        d = data["deals"].get(c["key"], {})
        out.append({**c, "stage": d.get("stage", "new"), "amount": d.get("amount", 0),
                    "tags": d.get("tags", []), "title": d.get("title") or c["who"],
                    "phone": d["phone"] if "phone" in d else c.get("phone", ""),
                    "clinic": d["clinic"] if "clinic" in d else c.get("clinic", ""),
                    "note": d.get("note", ""),
                    "notes": data["notes"].get(c["key"], [])})
    return out


def tasks_view() -> list[dict]:
    names = {c["key"]: c["who"] for c in clients()}
    out = []
    for t in crm_state()["tasks"]:
        out.append({**t, "who": names.get(t.get("key", ""), t.get("key", ""))})
    return sorted(out, key=lambda x: (x["done"], x.get("at") or "9999", x["created"]))


def clients() -> list[dict]:
    data: dict = {}
    groups, by_key = merge_groups()
    for e in read_events():
        extra = e.get("extra") or {}
        chat = extra.get("chat_id")
        if not chat:
            continue
        channel = extra.get("channel", "telegram")
        raw_key = f"{channel}:{chat}"
        g = by_key.get(raw_key)
        ckey = g["primary"] if g else raw_key
        pchan, pchat = ckey.split(":", 1) if ":" in ckey else (channel, str(chat))
        c = data.setdefault(ckey, {
            "chat": pchat, "key": ckey, "who": "", "count": 0, "in_count": 0,
            "last_client_ts": "", "phone": "", "clinic": "",
            "last": "", "last_ts": "", "tech": 0, "apps": 0, "channel": pchan,
        })
        name = (e.get("who") or "").strip()
        # старое MAX-событие писало вместо имени числовой id — не затираем им имя,
        # которое пришло в другом событии (например, в заявке)
        if extra.get("from") != "owner" and name and name != str(chat) and not name.isdigit():
            c["who"] = name
        text = e.get("text") or ""
        c["count"] += 1
        if extra.get("from") != "owner" and not text.startswith("[ответ бота]"):
            c["in_count"] += 1
            if e["ts"] >= c.get("last_client_ts", ""):
                c["last_client_ts"] = e["ts"]
        if text.startswith("ЗАЯВКА"):
            c["apps"] += 1
            parts = [p.strip() for p in text.split("|")]
            if len(parts) >= 2:
                c["phone"] = parts[1]
            c["clinic"] = parts[0].replace("ЗАЯВКА:", "").strip()
        if (e.get("extra") or {}).get("tech"):
            c["tech"] += 1
        if e["ts"] >= c["last_ts"]:
            c["last_ts"] = e["ts"]
            c["last"] = text
            extra = e.get("extra") or {}
            c["last_author"] = ("owner" if extra.get("from") == "owner"
                                else ("bot" if text.startswith("[ответ бота]") else "client"))

    import handoff

    secs = sections_state()
    arch = archive_state()["keys"]
    arch_changed = False
    by_primary = {g["primary"]: g for g in groups}
    names = names_state()
    for c in data.values():
        g = by_primary.get(c["key"])
        if g:
            c["keys"] = list(g.get("keys") or [])
            c["channels"] = sorted({k.split(":", 1)[0] for k in c["keys"]})
            if g.get("name"):
                c["who"] = g["name"]
        else:
            c["keys"] = [c["key"]]
            c["channels"] = [c.get("channel") or "telegram"]
        c["merged"] = len(c["keys"]) > 1
        if names.get(c["key"]):
            c["who"] = names[c["key"]]
        c["who"] = c["who"] or c["chat"]
        ch = ("max" if c.get("channel") == "max"
              else ("email" if c.get("channel") == "email"
                    else ("whatsapp" if c.get("channel") == "whatsapp" else "tg")))
        c["section"] = secs["map"].get(c["key"], "")
        c["last_author"] = c.get("last_author", "client")
        c["status"] = "waiting" if c["last_author"] == "client" else "pending"
        c["status_label"] = "ждёт ответа" if c["status"] == "waiting" else "отвечено"
        c["bot_paused"] = handoff.is_muted(ch, c["chat"])
        info = handoff.info(ch, c["chat"])
        c["pause_until"] = (time.strftime("%H:%M", time.localtime(info["until"]))
                            if info.get("until") else "")
        c["wait_min"] = 0
        if c["status"] == "waiting" and c["last_ts"]:
            try:
                started = time.mktime(time.strptime(c["last_ts"], "%Y-%m-%d %H:%M:%S"))
                c["wait_min"] = max(0, int((time.time() - started) / 60))
            except ValueError:
                pass
        c["archived"] = False
        at = arch.get(c["key"])
        if at:
            # клиент написал после архивации — возвращаем во входящие
            if c.get("last_client_ts", "") > at:
                arch.pop(c["key"], None)
                arch_changed = True
            else:
                c["archived"] = True

    if arch_changed:
        state = archive_state()
        state["keys"] = arch
        ARCHIVE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    waiting = sorted((c for c in data.values() if c["status"] == "waiting"),
                     key=lambda x: x["last_ts"])              # кто дольше ждёт — выше
    other = sorted((c for c in data.values() if c["status"] != "waiting"),
                   key=lambda x: x["last_ts"], reverse=True)  # отвеченные — свежие выше
    return waiting + other


def thread(chat: str) -> dict:
    groups, _ = merge_groups()
    chat_s = str(chat)
    group = next((g for g in groups
                  if g.get("primary") == chat_s
                  or g.get("primary", "").split(":", 1)[-1] == chat_s), None)
    keys = set(group.get("keys") or []) if group else None
    msgs, who, channel, targets = [], chat_s, "telegram", {}
    for e in read_events():
        extra = e.get("extra") or {}
        cid = str(extra.get("chat_id"))
        ch = extra.get("channel", "telegram")
        key = f"{ch}:{cid}"
        if keys:
            if key not in keys:
                continue
        elif cid != chat_s:
            continue
        text = e.get("text") or ""
        name = (e.get("who") or "").strip()
        if extra.get("from") != "owner" and name and name != cid and not name.isdigit():
            who = name
        channel = ch
        targets[key] = {"key": key, "channel": ch, "chat": cid,
                        "label": ("MAX" if ch == "max" else ("Почта" if ch == "email"
                                  else ("WhatsApp" if ch == "whatsapp" else "Telegram")))}
        msgs.append({
            "ts": e["ts"], "text": text, "channel": ch,
            "author": ("owner" if extra.get("from") == "owner"
                       else ("bot" if text.startswith("[ответ бота]") else "client")),
            "status": (extra.get("status") or ("sent" if extra.get("from") == "owner" else "")),
            "tech": bool(extra.get("tech")),
            "app": text.startswith("ЗАЯВКА"),
        })
    # прочитано = после нашего сообщения клиент написал ещё раз;
    # доставлено = канал принял сообщение (Telegram/MAX/почта)
    seen_client = False
    for m in reversed(msgs):
        if m["author"] == "client":
            seen_client = True
        elif m["author"] == "owner":
            if seen_client:
                m["status"] = "read"
            elif m.get("status") != "failed":
                m["status"] = "delivered"
    if group and group.get("name"):
        who = group["name"]
    tlist = list(targets.values())
    if group:
        tlist.sort(key=lambda t: 0 if t["key"] == group.get("primary") else 1)
    channels = sorted({t["channel"] for t in tlist}) or [channel]
    name_key = tlist[0]["key"] if tlist else f"{channel}:{chat_s}"
    who = names_state().get(name_key) or (group.get("name") if group else "") or who
    return {"who": who, "channel": (tlist[0]["channel"] if tlist else channel),
            "channels": channels, "targets": tlist, "merged": bool(group),
            "messages": msgs[-200:], "total": len(msgs)}


def errors() -> list[dict]:
    done = set(load_json(RESOLVED, {}).keys())
    out, seen = [], set()
    for e in read_events():
        is_error = e.get("kind") == "error"
        is_tech = (e.get("extra") or {}).get("tech") and e.get("kind") == "message"
        if not (is_error or is_tech):
            continue
        key = event_key(e)
        if key in done:
            continue
        sig = (e.get("text") or "")[:200]
        if sig in seen:
            continue          # одинаковый текст не показываем дважды
        seen.add(sig)
        who = e.get("who") or ""
        out.append({"id": key, "ts": e["ts"],
                    "where": (who or e.get("source", "бот")) + (" · жалоба" if is_tech else " · сбой"),
                    "text": e.get("text") or ""})
    return out[::-1]


def fixes() -> list[dict]:
    data = load_json(FIXES, {})
    return [dict(id=tid, **v) for tid, v in data.items() if v.get("status") != "done"][::-1]


def spam() -> list[dict]:
    out = [{"id": f"{e['ts']}|spam", "ts": e["ts"], "who": e.get("who") or "—", "text": e.get("text") or ""}
           for e in read_events() if e.get("kind") == "spam"]
    return out[::-1][:80]


# ------------------------------------------------------------------ действия

def reply(chat: str, text: str, channel: str = "") -> bool:
    import handoff
    import relay
    from events import log as ev_log

    info = thread(chat)
    targets = info.get("targets") or []
    target = None
    if channel:
        target = next((t for t in targets
                       if t.get("key") == channel or t.get("channel") == channel), None)
    if not target:
        target = targets[0] if targets else {"channel": info.get("channel", "telegram"), "chat": chat}
    ch = target.get("channel", "telegram")
    cid = str(target.get("chat", chat))
    if relay.send_reply(ch, cid, text):
        ev_log("whatsapp" if ch == "whatsapp" else ("max" if ch == "max" else ("email" if ch == "email" else "telegram")),
               "message", text, "владелец",
               {"chat_id": cid if ch == "email" else int(cid),
                "channel": ch, "from": "owner", "status": "delivered"})
        handoff.mute(ch, cid, 6)
        return True
    return False


def ai_draft(chat: str) -> str:
    """Черновик ответа нейросетью (Gonka) по последним сообщениям диалога."""
    import llm

    msgs = thread(chat).get("messages", [])[-6:]
    convo = "\n".join(("Клиент: " if m["author"] == "client" else "Мы: ")
                       + (m["text"] or "")[:400] for m in msgs)
    prompt = (
        "Ты — владелец небольшой IT-компании «Зиныч IT» (Уфа): делаем боты записи для клиник. "
        "Напиши короткий ответ клиенту: 2–4 предложения, простым русским языком, без официоза. "
        "Цены: бот 10 000 ₽, бот с сайтом 20 000 ₽, запуск 5–10 дней. "
        "Демо: https://ufa-zapis.surge.sh/demos/moj-doktor.html\n\n"
        f"Переписка:\n{convo}\n\nОтвет:"
    )
    return llm.chat([{"role": "user", "content": prompt}], max_tokens=220, temperature=0.5).strip()


def _find_event(key: str):
    for e in read_events():
        if event_key(e) == key:
            return e
    return None


def apply_error(key: str) -> bool:
    import fix_done
    import resolve

    event = _find_event(key)
    if not event:
        return False
    resolve.mark_resolved([event], "принято из админки")
    fix_done.add((event.get("text") or "")[:120], "разобрать и исправить", (event.get("text") or "")[:300])
    threading.Thread(
        target=fix_done.notify,
        args=(f"✅ Ошибка принята в работу\n\n{(event.get('text') or '')[:300]}",),
        daemon=True,
    ).start()
    return True


def reject_error(key: str) -> bool:
    import resolve

    event = _find_event(key)
    if not event:
        return False
    resolve.mark_resolved([event], "отклонено")
    return True


def resume_bot(chat: str) -> bool:
    import handoff

    info = thread(chat)
    channel = "max" if info.get("channel") == "max" else ("email" if info.get("channel") == "email" else "tg")
    handoff.resume(channel, chat)
    return True


def close_fix(tid: str) -> bool:
    import fix_done

    data = fix_done.load()
    if tid not in data:
        return False
    data[tid]["status"] = "done"
    data[tid]["closed"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data[tid]["note"] = "исправлено"
    fix_done.save(data)
    return True


# ------------------------------------------------------------------ сервер

class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/clients":
            self._json(clients())
        elif path.startswith("/api/client/"):
            self._json(thread(path.rsplit("/", 1)[-1]))
        elif path == "/api/errors":
            self._json(errors())
        elif path == "/api/fixes":
            self._json(fixes())
        elif path == "/api/spam":
            self._json(spam())
        elif path == "/api/sections":
            self._json(sections_state())
        elif path == "/api/crm":
            self._json({"deals": deals_view(), "tasks": tasks_view(),
                        "stages": [{"id": k, "name": v} for k, v in STAGES]})
        elif path == "/api/cold":
            self._json(cold_state())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"

        if path == "/api/reply":
            payload = json.loads(raw or b"{}")
            self._json({"ok": reply(str(payload.get("chat", "")),
                                    (payload.get("text") or "").strip(),
                                    str(payload.get("channel", "")))})
        elif path == "/api/ai_draft":
            payload = json.loads(raw or b"{}")
            try:
                self._json({"ok": True, "text": ai_draft(str(payload.get("chat", "")))})
            except Exception as exc:  # noqa: BLE001
                self._json({"ok": False, "error": str(exc)[:200]})
        elif path == "/api/sections/add":
            payload = json.loads(raw or b"{}")
            section = add_section(payload.get("name", ""))
            self._json({"ok": bool(section), "section": section})
        elif path == "/api/sections/rename":
            payload = json.loads(raw or b"{}")
            self._json({"ok": rename_section(payload.get("id", ""), payload.get("name", ""))})
        elif path == "/api/sections/delete":
            payload = json.loads(raw or b"{}")
            self._json({"ok": delete_section(payload.get("id", ""))})
        elif path == "/api/sections/order":
            payload = json.loads(raw or b"{}")
            self._json({"ok": reorder_sections(payload.get("ids") or [])})
        elif path == "/api/sections/assign":
            payload = json.loads(raw or b"{}")
            self._json({"ok": assign_section(payload.get("key", ""), payload.get("section", ""))})
        elif path == "/api/crm/deal":
            payload = json.loads(raw or b"{}")
            key = payload.pop("key", "")
            self._json({"ok": crm_deal(key, **payload)})
        elif path == "/api/crm/task":
            payload = json.loads(raw or b"{}")
            task = crm_task_add(payload.get("key", ""), payload.get("text", ""), payload.get("at", ""))
            self._json({"ok": bool(task), "task": task})
        elif path == "/api/crm/task/done":
            payload = json.loads(raw or b"{}")
            self._json({"ok": crm_task_done(payload.get("id", ""))})
        elif path == "/api/crm/task/delete":
            payload = json.loads(raw or b"{}")
            self._json({"ok": crm_task_delete(payload.get("id", ""))})
        elif path == "/api/crm/note":
            payload = json.loads(raw or b"{}")
            self._json({"ok": crm_note_add(payload.get("key", ""), payload.get("text", ""))})
        elif path == "/api/cold/scan":
            self._json({"ok": True, **cold_scan()})
        elif path == "/api/wa/incoming":
            payload = json.loads(raw or b"{}")
            chat = re.sub(r"\D", "", str(payload.get("chat") or ""))
            text = (payload.get("text") or "").strip()
            if chat and text:
                from events import log as ev_log
                ev_log("whatsapp", "message", text, (payload.get("name") or chat).strip(),
                       {"chat_id": chat, "channel": "whatsapp"})
            self._json({"ok": bool(chat and text)})
        elif path == "/api/rename":
            payload = json.loads(raw or b"{}")
            key = set_client_name(str(payload.get("key") or payload.get("chat") or ""),
                                  str(payload.get("name") or ""))
            self._json({"ok": bool(key), "key": key})
        elif path == "/api/merge":
            payload = json.loads(raw or b"{}")
            self._json({"ok": True, "merge": merge_clients(payload.get("keys") or [])})
        elif path == "/api/archive":
            payload = json.loads(raw or b"{}")
            self._json({"ok": set_archived(payload.get("key", ""), bool(payload.get("archived")))})
        elif path == "/api/chat/delete":
            payload = json.loads(raw or b"{}")
            self._json({"ok": True, "removed": delete_chats(payload.get("chats") or [])})
        elif path == "/api/cold/script":
            payload = json.loads(raw or b"{}")
            text = (payload.get("text") or "").strip()
            if not text:
                self._json({"ok": False})
            else:
                COLD_SCRIPT.write_text(json.dumps({"text": text}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
                self._json({"ok": True})
        elif path == "/api/cold/update":
            payload = json.loads(raw or b"{}")
            lid = payload.pop("id", "")
            self._json({"ok": cold_update(lid, **payload)})
        elif path == "/api/cold/delete":
            payload = json.loads(raw or b"{}")
            self._json({"ok": cold_delete(payload.get("id", ""))})
        elif path.startswith("/api/errors/") and path.endswith("/apply"):
            key = urllib.parse.unquote(path[len("/api/errors/"):-len("/apply")])
            self._json({"ok": apply_error(key)})
        elif path.startswith("/api/errors/") and path.endswith("/reject"):
            key = urllib.parse.unquote(path[len("/api/errors/"):-len("/reject")])
            self._json({"ok": reject_error(key)})
        elif path.startswith("/api/resume/"):
            self._json({"ok": resume_bot(urllib.parse.unquote(path[len("/api/resume/"):]))})
        elif path.startswith("/api/fixes/") and path.endswith("/done"):
            tid = urllib.parse.unquote(path[len("/api/fixes/"):-len("/done")])
            self._json({"ok": close_fix(tid)})
        else:
            self._json({"error": "not found"}, 404)

    def log_message(self, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    from lock import acquire
    acquire("admin")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)

    def _remind() -> None:
        while True:
            try:
                reminder_check()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(60)

    threading.Thread(target=_remind, daemon=True).start()
    print(f"Админка: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
