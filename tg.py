#!/usr/bin/env python3

import os
import requests
import time
import threading
import re
import sys
from typing import Optional, Dict, Any, List
from flask import Flask
from threading import Thread

# -------- Keep-Alive Server --------
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()

# -------- Bot Tokens from Environment --------
BOT_TOKENS = os.getenv("BOT_TOKENS", "").split(",")
if not BOT_TOKENS or BOT_TOKENS == [""]:
    print("No bot tokens found! Set BOT_TOKENS in Railway variables.")
    sys.exit()

# -------- Admin & Controller Setup --------
MAIN_ADMIN_ID = "8291330030"
controllers = set([MAIN_ADMIN_ID])

NC_EMOJI_SETS = [
    ["🙀","😹","🔥","❤️‍🔥","💔","⚡"],
    ["✨","🤩","🧊","🥤","🥃","🥂"],
    ["🧃","🛑","🎐","❤️","♨️","🔻"],
    ["🔸","🔺","♻️","👻","▫️","🍓"],
    ["🕷️","😁","❗","🥶","🕸️","💢"]
]

DEFAULT_RAID_TEXTS = [
    "😰😰𝗗𝗢𝗚𝗚𝗬 𝗦𝗛𝗛 𝗦𝗛𝗛 ",
    "𝘵𝘦𝘳𝘪 𝘮𝘢 𝘬𝘢𝘳𝘢𝘯 𝘈𝘶𝘫𝘭𝘢 𝘬𝘦 𝘨𝘢𝘯𝘦 𝘱𝘦 𝘤udengi ᵐᵃʰᵒˡ ᵖᵘʳᵃ ʷᵃᵛʸ 🎶😂👌🏻 ",
    "𝐂ʜᴀʟ  𝙆𝙐𝙏𝙏𝙄𝙔𝘼 ᴋɪ 𝑨𝑼𝑳𝑨𝐃 𝐏ᴀᴠ 👉🦵 ᴾᴬᴷᴬᴅ 🔥 ",
    "Try mom chudke bolti \"तितली बन उडु\" 🦋🦋🦋🦋🦋 ",
    "Tri mkc me short bottle silencer se patake phodunga tri ma ka bosda me bumbari hojayegi ✌🏻👏✌🏻👏✌🏻👏✌🏻👏✌🏻👏✌🏻👏 ",
    "𝘾𝙃𝘼𝙇 𝙍𝘼𝙉𝘿𝙄𝙆𝙀 𝙐𝙏𝙃𝘼𝙆 𝘽𝙀𝙏𝙃𝘼𝙆 𝙇𝘼𝙂𝘼😁🔥  "
]

chat_states: Dict[str, Dict[str, Any]] = {}
raids: Dict[str, Dict[str, Any]] = {}
stop_flags: Dict[str, threading.Event] = {}

HEADERS = {"User-Agent": "TelegramBot/5.0"}

# -------- Helper Functions --------
def api_post(token: str, method: str, data: Dict[str, Any]):
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        return requests.post(url, data=data, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"[ERROR] api_post {method}: {e}")
        return None

def send_message(token: str, chat_id: str, text: str, reply_to: Optional[int]=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    api_post(token, "sendMessage", data)

def set_chat_title(token: str, chat_id: str, title: str):
    return api_post(token, "setChatTitle", {"chat_id": chat_id, "title": title})

def mention_target(user: Dict[str, Any]) -> str:
    if not user:
        return "Unknown"
    if user.get('id'):
        name = user.get('name') or user.get('username') or user.get('id')
        return f"[{name}](tg://user?id={user.get('id')})"
    if user.get('username'):
        return user['username']
    return "Unknown"

def ensure_chat_state(chat_id: str) -> Dict[str, Any]:
    s = chat_states.get(chat_id)
    if not s:
        s = {
            'timing': {'reply': 1.0, 'nc': 0.1, 'fuck': 1.0},
            'replyOn': False,
            'replyText': '👋',
            'ncOn': False,
            'ncBase': '',
            'ncIndex': 0,
            'ncThread': None,
            'ncBackoff': None
        }
        chat_states[chat_id] = s
    return s

def parse_user_ref(arg: Optional[str], msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if arg:
        arg = arg.strip()
        if arg.startswith("@"): return {'username': arg}
        m = re.match(r"tg://user\?id=(\d+)", arg)
        if m: return {'id': m.group(1)}
        if arg.isdigit(): return {'id': arg}
    if msg.get('reply_to_message') and msg['reply_to_message'].get('from'):
        u = msg['reply_to_message']['from']
        return {'id': str(u.get('id')), 'username': ('@' + u.get('username')) if u.get('username') else None, 'name': u.get('first_name')}
    return None

def is_controller(user: Dict[str, Any]) -> bool:
    if not user: return False
    uid = str(user.get('id'))
    if uid == MAIN_ADMIN_ID: return True
    if uid in controllers: return True
    uname = user.get('username')
    if uname and ('@' + uname) in controllers: return True
    return False

def pick_raid_text(raid_info: Dict[str, Any]) -> str:
    return raid_info.get('raidText') or DEFAULT_RAID_TEXTS[int(time.time()) % len(DEFAULT_RAID_TEXTS)]

# -------- NC (Name Change) Functions --------
def start_nc(token: str, chat_id: str, base_text: str, emojis: List[str], speed: float = 0.1):
    s = ensure_chat_state(chat_id)
    if s.get('ncOn'):
        return
    s['ncOn'] = True
    s['ncBase'] = base_text
    s['ncIndex'] = 0
    stop_flags[chat_id] = threading.Event()

    def loop():
        while s['ncOn'] and not stop_flags[chat_id].is_set():
            try:
                emoji = emojis[s['ncIndex'] % len(emojis)]
                s['ncIndex'] += 1
                new_title = f"{s['ncBase']} {emoji}"
                resp = set_chat_title(token, chat_id, new_title)
                if resp is not None and not resp.ok:
                    print(f"[ERROR] Failed to set chat title: {resp.text}")
            except Exception as e:
                print(f"[ERROR] Exception in NC loop: {e}")
            for _ in range(int(speed * 10)):
                if stop_flags[chat_id].is_set():
                    break
                time.sleep(speed / 10)

    s['ncThread'] = threading.Thread(target=loop, daemon=True)
    s['ncThread'].start()

def stop_nc(chat_id: str):
    s = ensure_chat_state(chat_id)
    s['ncOn'] = False
    if chat_id in stop_flags:
        stop_flags[chat_id].set()
    if s.get('ncThread') and s['ncThread'].is_alive():
        s['ncThread'].join(timeout=1)

# -------- Raid Functions --------
def start_raid(token: str, msg: Dict[str, Any]):
    chat_id = str(msg['chat']['id'])
    r = raids.get(chat_id)
    if not r or not r.get('targets'):
        send_message(token, chat_id, "No targets set.")
        return
    r['mode'] = 'controller'
    r['raidIndex'] = 0
    send_message(token, chat_id, "Raid started.")

    stop_flags[chat_id] = threading.Event()

    def loop():
        while r.get('mode') == 'controller' and not stop_flags[chat_id].is_set():
            targets = r['targets']
            if targets:
                target = targets[r['raidIndex'] % len(targets)]
                r['raidIndex'] += 1
                body = f"{mention_target(target)} {pick_raid_text(r)}"
                send_message(token, chat_id, body)
            time.sleep(r.get('delay', 1.0))

    threading.Thread(target=loop, daemon=True).start()

def stop_raid(token: str, msg: Dict[str, Any]):
    chat_id = str(msg['chat']['id'])
    r = raids.get(chat_id)
    if r:
        r['mode'] = 'stopped'
        if chat_id in stop_flags:
            stop_flags[chat_id].set()
        send_message(token, chat_id, "Raid stopped.")

# -------- Auto Reply --------
def handle_auto_reply(token: str, msg: Dict[str, Any]):
    chat_id = str(msg['chat']['id'])
    s = ensure_chat_state(chat_id)
    if s.get('replyOn'):
        def do_reply():
            time.sleep(s['timing']['reply'])
            send_message(token, chat_id, s.get('replyText'), reply_to=msg.get('message_id'))
        threading.Thread(target=do_reply, daemon=True).start()

# -------- Command Handler --------
HELP_TEXT = (
    "*Bot Commands*\n"
    "!help — show this menu\n"
    "!sudo @user — add controller\n"
    "!rmsudo @user — remove controller\n"
    "!reply text — set auto reply\n"
    "!nc text — start NC (title animation)\n"
    "!dnc — stop NC\n"
    "!fuck @user — add raid target\n"
    "!raid — start raid\n"
    "!stop — stop raid\n"
    "!clear — clear raid targets\n"
    "!delay <mode> <sec> — set delay (reply/nc/raid)\n"
    "!restart — stop all & reset\n"
)

# -------- Command Processor --------
def handle_command(bot_index: int, token: str, msg: Dict[str, Any], text: str):
    chat_id = str(msg['chat']['id'])
    user = msg.get('from')

    def require_controller():
        if not is_controller(user):
            send_message(token, chat_id, "Controller-only.", reply_to=msg.get('message_id'))
            return False
        return True

    if text.lower() == "!help":
        send_message(token, chat_id, HELP_TEXT)

    elif text.startswith("!reply "):
        if not require_controller(): return
        s = ensure_chat_state(chat_id)
        s['replyOn'] = True
        s['replyText'] = text.split(" ", 1)[1].strip()
        send_message(token, chat_id, "Auto-reply enabled.")

    elif text.startswith("!sudo"):
        if not require_controller(): return
        arg = text.split(" ", 1)[1] if " " in text else None
        user_ref = parse_user_ref(arg, msg)
        if not user_ref:
            send_message(token, chat_id, "Provide @username, tg://user?id=... or reply.", reply_to=msg.get('message_id'))
            return
        key = user_ref.get('username') or str(user_ref.get('id'))
        controllers.add(key)
        send_message(token, chat_id, "Controller added.")

    elif text.startswith("!rmsudo"):
        if not require_controller(): return
        arg = text.split(" ", 1)[1] if " " in text else None
        user_ref = parse_user_ref(arg, msg)
        if not user_ref:
            send_message(token, chat_id, "Provide @username, tg://user?id=... or reply.", reply_to=msg.get('message_id'))
            return
        key = user_ref.get('username') or str(user_ref.get('id'))
        if key in controllers:
            controllers.discard(key)
            send_message(token, chat_id, "Controller removed.")
        else:
            send_message(token, chat_id, "Not in sudo list.")

    elif text.startswith("!fuck"):
        if not require_controller(): return
        arg = text.split(" ", 1)[1] if " " in text else None
        user_ref = parse_user_ref(arg, msg)
        if not user_ref:
            send_message(token, chat_id, "Provide @username, tg://user?id=... or reply.", reply_to=msg.get('message_id'))
            return
        target = {k:v for k,v in user_ref.items() if v}
        raids.setdefault(chat_id, {'targets': [], 'raidTexts': list(DEFAULT_RAID_TEXTS), 'delay': 1.0, 'mode': 'stopped', 'raidIndex': 0})['targets'].append(target)
        send_message(token, chat_id, "Raid target added.")

    elif text.lower() == "!raid":
        if not require_controller(): return
        start_raid(token, msg)

    elif text.lower() == "!stop":
        if not require_controller(): return
        stop_raid(token, msg)

    elif text.lower() == "!clear":
        if not require_controller(): return
        raids.pop(chat_id, None)
        send_message(token, chat_id, "Raid targets cleared.")

    elif text.startswith("!delay"):
        if not require_controller(): return
        parts = text.split()
        if len(parts) != 3:
            send_message(token, chat_id, "Usage: !delay <mode> <seconds>")
            return
        mode, sec_str = parts[1], parts[2]
        try:
            sec = float(sec_str)
        except ValueError:
            send_message(token, chat_id, "Invalid seconds.")
            return

        if mode == "raid":
            raids.setdefault(chat_id, {'targets': [], 'raidTexts': list(DEFAULT_RAID_TEXTS), 'delay': 1.0, 'mode': 'stopped', 'raidIndex': 0})['delay'] = sec
            send_message(token, chat_id, f"Raid delay set to {sec}s")
        elif mode in ["reply", "nc"]:
            s = ensure_chat_state(chat_id)
            s['timing'][mode] = sec
            send_message(token, chat_id, f"{mode.capitalize()} delay set to {sec}s")
        else:
            send_message(token, chat_id, "Modes: raid/reply/nc")

    elif text.lower() == "!restart":
        if not require_controller(): return
        # stop everything
        if chat_id in stop_flags:
            stop_flags[chat_id].set()
        raids.pop(chat_id, None)
        chat_states.pop(chat_id, None)
        stop_flags.pop(chat_id, None)
        send_message(token, chat_id, "Bot restarted.")

    elif text.startswith("!nc "):
        if not require_controller(): return
        arg = text.split(" ", 1)[1].strip()
        s = ensure_chat_state(chat_id)
        speed = s['timing'].get('nc', 0.1)
        start_nc(token, chat_id, arg, NC_EMOJI_SETS[bot_index % len(NC_EMOJI_SETS)], speed=speed)
        send_message(token, chat_id, f"NC started with speed {speed}s per update.")

    elif text.lower() == "!dnc":
        if not require_controller(): return
        stop_nc(chat_id)
        send_message(token, chat_id, "NC stopped.")


# -------- Polling Loop --------
def run_bot(bot_index: int, token: str, emoji_list: List[str]):
    print(f"[INFO] Starting bot {bot_index}...")
    last_update_id = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates?offset={last_update_id+1}&timeout=20", headers=HEADERS, timeout=30)
            data = r.json()
            for update in data.get('result', []):
                last_update_id = update['update_id']
                msg = update.get('message')
                if not msg:
                    continue
                text = msg.get('text') or ''
                if text.startswith('!'):
                    handle_command(bot_index, token, msg, text)
                else:
                    handle_auto_reply(token, msg)

                # Check for raid target interaction
                rinfo = raids.get(chat_id)
                if rinfo and rinfo.get('targets'):
                    for t in rinfo['targets']:
                        if (t.get('username') and msg.get('from',{}).get('username') and t['username'].lstrip('@') == msg['from']['username']) or \
                           (t.get('id') and str(t['id']) == str(msg.get('from',{}).get('id'))):
                            rinfo['mode'] = 'target'
                            stop_flags[chat_id] = threading.Event()
                            def loop_target():
                                while rinfo.get('mode') == 'target' and not stop_flags[chat_id].is_set():
                                    target = rinfo['targets'][rinfo['raidIndex'] % len(rinfo['targets'])]
                                    rinfo['raidIndex'] += 1
                                    send_message(token, chat_id, f"{mention_target(target)} {pick_raid_text(rinfo)}", reply_to=msg.get('message_id'))
                                    time.sleep(rinfo.get('delay', 1.0))
                            threading.Thread(target=loop_target, daemon=True).start()
                            break # Stop checking targets for this message
        except Exception as e:
            print(f"[ERROR] Bot {bot_index} polling error: {e}")
            time.sleep(1)

# -------- Start All Bots --------
for idx, tkn in enumerate(BOT_TOKENS):
    threading.Thread(target=run_bot, args=(idx, tkn, NC_EMOJI_SETS[idx % len(NC_EMOJI_SETS)]), daemon=True).start()

print("Bots started. Press Ctrl+C to exit.")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Exiting...")
    sys.exit(0)
