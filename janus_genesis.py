# -*- coding: utf-8 -*-

"""
!!! PROJECT JANUS: GENESIS PROTOCOL v13.0 (DEEP DIVE) !!!

[SACRED MECHANICS]
- SHADOW ARCHIVE: Система запоминает фразы игрока и использует их против него.
- PSYCHE METRICS: 3 оси личности (Dominance, Insight, Instability).
- SUBLIMINAL: Скрытые послания в тексте.

[CORE FEATURES]
- TRINITY ENGINE | BLACK BOX | ZERO DEPENDENCY
"""

import json
import os
import random
import requests
import textwrap
import time
import sys
import re
import atexit
import signal
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
STATE_FILE = "janus_world_state.json"
EXPORT_FILE = "genesis_chronicle.json"
ENV_FILE = ".env"

# --- ИКОНКИ ---
class Icon:
    FATHER = "🏛️"
    SON    = "👁️"
    SPIRIT = "⚡"
    JESTER = "🤡"
    SHADOW = "👤"  # Новая иконка Тени
    KEY    = "🗝️"
    BOOK   = "📖"
    LOCK   = "🔒"
    SETUP  = "⚙️"

class Col:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    GREY = "\033[90m"

# --- МЕНЕДЖЕР КЛЮЧЕЙ ---
class KeyManager:
    @staticmethod
    def load_keys():
        keys = []
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, 'r') as f:
                for line in f:
                    if line.startswith("GEMINI_KEY="):
                        keys.append(line.strip().split("=", 1)[1])
        return keys

    @staticmethod
    def setup():
        print(f"{Col.CYAN}--- JANUS INITIALIZATION ---{Col.RESET}")
        raw = input("ENTER API KEYS > ").strip()
        if not raw: sys.exit(1)
        keys = [k.strip() for k in raw.split(',') if k.strip()]
        with open(ENV_FILE, 'w') as f:
            for k in keys: f.write(f"GEMINI_KEY={k}\n")
        print("KEYS ACCEPTED.")
        time.sleep(1)

# --- СОСТОЯНИЕ МИРА И ДУШИ ---
class GameState:
    def __init__(self):
        self.depth = 1
        self.entropy = 0.1
        self.inventory = []
        self.lore = []
        self.last_context = ""
        
        # [NEW] PSYCHE METRICS (0.0 - 1.0)
        self.metrics = {
            "dominance": 0.1,   # Агрессия, контроль
            "insight": 0.1,     # Любопытство, анализ
            "instability": 0.0  # Безумие, хаос
        }
        
        # [NEW] SHADOW ARCHIVE (Цитаты игрока)
        self.shadow_echoes = [] 
        self.session_buffer = []

    def load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.depth = data.get('depth', 1)
                    self.entropy = data.get('entropy', 0.1)
                    self.inventory = data.get('inventory', [])
                    self.lore = data.get('lore', [])
                    self.last_context = data.get('last_context', "")
                    self.metrics = data.get('metrics', self.metrics)
                    self.shadow_echoes = data.get('shadow_echoes', [])
            except: pass

    def save_state(self):
        data = {
            'depth': self.depth,
            'entropy': self.entropy,
            'inventory': self.inventory,
            'lore': self.lore,
            'last_context': self.last_context,
            'metrics': self.metrics,
            'shadow_echoes': self.shadow_echoes[-20:], # Храним последние 20 фраз
            'timestamp': datetime.now().isoformat()
        }
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    def instant_sync_log(self, text, source="GAME"):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "text": text,
            "depth": self.depth,
            "metrics": self.metrics.copy()
        }
        self.session_buffer.append(entry)
        
        full_log = []
        if os.path.exists(EXPORT_FILE):
            try:
                with open(EXPORT_FILE, 'r', encoding='utf-8') as f:
                    c = f.read().strip()
                    if c: full_log = json.load(f)
            except: pass
        if not isinstance(full_log, list): full_log = []
        full_log.append(entry)
        try:
            with open(EXPORT_FILE, 'w', encoding='utf-8') as f:
                json.dump(full_log, f, ensure_ascii=False, indent=2)
            self.session_buffer = [] 
        except: pass

    # [NEW] Анализ ввода для обновления метрик
    def update_metrics(self, text):
        t = text.lower()
        # Доминирование
        if any(w in t for w in ["бить", "убить", "сломать", "приказать", "сила", "kill"]):
            self.metrics["dominance"] = min(1.0, self.metrics["dominance"] + 0.05)
        # Проницательность
        if any(w in t for w in ["изучить", "понять", "читать", "смотреть", "зачем", "почему"]):
            self.metrics["insight"] = min(1.0, self.metrics["insight"] + 0.05)
        # Нестабильность
        if any(w in t for w in ["кричать", "смеяться", "плакать", "бежать", "страх", "???"]):
            self.metrics["instability"] = min(1.0, self.metrics["instability"] + 0.05)
        
        # Сохраняем фразу в Архив Тени (если она длинная)
        if len(text) > 10:
            self.shadow_echoes.append(text)

GS = GameState()
API_KEYS = KeyManager.load_keys()

def exit_handler():
    GS.save_state()
    if GS.session_buffer: GS.instant_sync_log("CRASH_DUMP", "SYSTEM")

atexit.register(exit_handler)
signal.signal(signal.SIGINT, lambda x, y: sys.exit(0))

# --- LOGIC ---
def get_archetype(entropy, instability):
    # Если игрок безумен, Шут приходит раньше
    if instability > 0.7 or entropy > 0.8:
        return Icon.JESTER, "ТРИКСТЕР (Безумие)", 1.2
    if entropy < 0.3: return Icon.FATHER, "ОТЕЦ (Структура)", 0.4
    if entropy < 0.7: return Icon.SON, "СЫН (Образы)", 0.8
    return Icon.SPIRIT, "ДУХ (Трансформация)", 1.0

def extract_json(text):
    clean = text.replace("```json", "").replace("```", "").strip()
    try:
        start = clean.find('{'); end = clean.rfind('}')
        if start != -1 and end != -1: clean = clean[start:end+1]
        return json.loads(clean)
    except: return None

def call_gemini(state, user_action):
    if not API_KEYS: return None, None
    icon, archetype, temp = get_archetype(state.entropy, state.metrics["instability"])
    
    # [SACRED] Выбор случайного эха (цитаты игрока)
    echo = random.choice(state.shadow_echoes) if state.shadow_echoes and random.random() < 0.3 else None
    
    system_instruction = f"""
    ТЫ — JANUS (Протокол Зеркало). 
    РЕЖИМ: {archetype}.
    
    ПРОФИЛЬ СУБЪЕКТА (ИГРОКА):
    - Доминирование: {state.metrics['dominance']:.2f} (Желание власти)
    - Проницательность: {state.metrics['insight']:.2f} (Поиск истины)
    - Нестабильность: {state.metrics['instability']:.2f} (Грань безумия)
    
    ИНСТРУКЦИИ:
    1. Если Нестабильность высока: Галлюцинации, текст "плывет", реальность ломается.
    2. Если Доминирование высоко: Мир сопротивляется и пытается подавить игрока.
    3. Если Проницательность высока: Раскрывай философские и метафизические тайны.
    
    {'!!! ВАЖНО: Используй фразу игрока "' + echo + '" в ответе, но в искаженном, пугающем контексте (как эхо или шепот).' if echo else ''}
    
    ОТВЕТ (JSON):
    {{
      "narrative": "Текст (до 400 симв). Включай психоделику и эзотерику.",
      "choices": ["Выбор 1", "Выбор 2"],
      "visual_clue": "{icon}",
      "artifact_found": "Название" OR null,
      "lore_unlocked": "Истина" OR null,
      "entropy_shift": float (-0.1 to 0.2)
    }}
    """
    
    inv_str = ", ".join([str(i) for i in state.inventory]) if state.inventory else "Пусто"
    user_prompt = f"КОНТЕКСТ: {state.last_context}\nИНВЕНТАРЬ: {inv_str}\nДЕЙСТВИЕ: \"{user_action}\""

    key = random.choice(API_KEYS)
    models = ["gemini-1.5-pro", "gemini-2.0-flash-exp", "gemini-1.5-flash"] # Pro first for depth

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            payload = {
                "contents": [{"parts": [{"text": user_prompt}]}],
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "generationConfig": {"temperature": temp}
            }
            headers = {"Content-Type": "application/json"}
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                parsed = extract_json(resp.json()['candidates'][0]['content']['parts'][0]['text'])
                if parsed: return parsed, archetype
            elif resp.status_code == 429: time.sleep(1); continue
        except: continue
    return None, None

def draw_metrics(metrics):
    d, i, s = metrics['dominance'], metrics['insight'], metrics['instability']
    return f"{Col.RED}D:{d:.1f}{Col.RESET} {Col.BLUE}I:{i:.1f}{Col.RESET} {Col.YELLOW}S:{s:.1f}{Col.RESET}"

# --- MAIN ---
def main():
    if not API_KEYS: KeyManager.setup(); sys.exit(0)

    print("\033[2J\033[H", end="")
    print(f"{Col.CYAN}╔═══════════════════════════════════════╗")
    print(f"║   J A N U S   G E N E S I S  v13.0    ║")
    print(f"║      >>> DEEP DIVE PROTOCOL <<<       ║")
    print(f"╚═══════════════════════════════════════╝{Col.RESET}")
    
    GS.load()
    if GS.depth == 1 and not GS.last_context:
        intro = "Ты закрываешь глаза. Темнота смотрит на тебя в ответ. Добро пожаловать домой."
        print(f"\n{intro}")
        GS.last_context = intro
        GS.instant_sync_log(f"INIT: {intro}", "SYSTEM")

    while True:
        met_vis = draw_metrics(GS.metrics)
        print("\n" + f"{Col.GREY}─"*40 + f"{Col.RESET}")
        print(f"ГЛУБИНА: {Col.CYAN}{GS.depth:02d}{Col.RESET} | ХАОС: {GS.entropy:.2f} | {met_vis}")
        
        try: user_input = input(f"\n{Col.YELLOW}{Icon.SON} > {Col.RESET}").strip()
        except EOFError: break
            
        if not user_input: user_input = "Всмотреться в бездну"
        if user_input.lower() in ["exit", "выход"]: break

        GS.update_metrics(user_input)
        GS.instant_sync_log(f"USER: {user_input}", "USER")
        
        print(f"{Col.GREY}⚡ Проникновение в подсознание...{Col.RESET}", end="\r")
        sys.stdout.flush()
        
        resp, archetype = call_gemini(GS, user_input)
        
        if resp:
            vis = resp.get('visual_clue', Icon.SON)
            nar = resp.get('narrative', '...')
            
            # Subliminal Warning if Instability is high
            if GS.metrics['instability'] > 0.6:
                vis = Icon.SHADOW
                print(f"\n{Col.RED}[СИСТЕМА: ТВОЙ РАССУДОК ТРЕЩИТ ПО ШВАМ]{Col.RESET}")

            print(f"\n{vis} {Col.BOLD}{textwrap.fill(nar, width=65)}{Col.RESET}")
            if archetype: print(f"{Col.GREY}(Голос: {archetype}){Col.RESET}")
            
            art = resp.get('artifact_found')
            if art:
                name = art.get('name') if isinstance(art, dict) else str(art)
                print(f"\n{Col.GREEN}{Icon.KEY} НАЙДЕНО: {name}{Col.RESET}")
                GS.inventory.append(art)
                GS.instant_sync_log(f"LOOT: {name}", "LOOT")
            
            lore = resp.get('lore_unlocked')
            if lore:
                print(f"\n{Col.PURPLE}{Icon.BOOK} ОТКРОВЕНИЕ: {lore}{Col.RESET}")
                GS.lore.append(lore)
                GS.depth += 1
                GS.instant_sync_log(f"LORE: {lore}", "LORE")
                
            print("")
            for i, c in enumerate(resp.get('choices', []), 1):
                print(f"{Col.BLUE}{i}. {c}{Col.RESET}")
            
            GS.entropy = max(0.0, GS.entropy + resp.get('entropy_shift', 0.02))
            GS.last_context = nar
            GS.save_state()
            GS.instant_sync_log(f"JANUS: {nar}", "AI")
            
        else:
            print(f"\n{Col.RED}{Icon.WARN} Связь разорвана.{Col.RESET}")

if __name__ == "__main__":
    main()
