# -*- coding: utf-8 -*-

"""
!!! PROJECT JANUS: GENESIS PROTOCOL v12.2 (GITHUB EDITION) !!!

[ОПИСАНИЕ]
Бесконечная текстовая RPG-песочница на базе LLM Gemini.
Работает как "зеркало подсознания".

[ФУНКЦИОНАЛ]
- TRINITY ENGINE: Динамическая смена нарратора (Отец/Сын/Шут).
- BLACK BOX: Мгновенная запись каждого действия (защита от абуза).
- CORE SYNC: Экспорт истории для скармливания Ядру Janus.
- SECURITY: Хранение ключей в .env файле.

[ЗАВИСИМОСТИ]
- pip install requests
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
    WARN   = "⚠️"
    KEY    = "🗝️"
    BOOK   = "📖"
    SAVE   = "💾"
    LINK   = "🔗"
    LOCK   = "🔒"
    SETUP  = "⚙️"

# --- ЦВЕТА ---
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
        print(f"{Col.CYAN}╔═══════════════════════════════════════╗")
        print(f"║      ПЕРВИЧНАЯ НАСТРОЙКА СИСТЕМЫ      ║")
        print(f"╚═══════════════════════════════════════╝{Col.RESET}")
        print(f"\n{Icon.SETUP} Введите ваши Google Gemini API Keys.")
        print("Можно ввести несколько через запятую для ротации.")
        print(f"{Col.GREY}(Они сохранятся локально в файл .env){Col.RESET}\n")
        
        raw = input("KEYS > ").strip()
        if not raw:
            print("Ошибка: Ключи не введены.")
            sys.exit(1)
            
        keys = [k.strip() for k in raw.split(',') if k.strip()]
        
        with open(ENV_FILE, 'w') as f:
            for k in keys:
                f.write(f"GEMINI_KEY={k}\n")
        
        print(f"\n{Col.GREEN}Настройка завершена. Перезапуск...{Col.RESET}")
        time.sleep(1)

# --- СОСТОЯНИЕ МИРА ---
class GameState:
    def __init__(self):
        self.depth = 1
        self.entropy = 0.1
        self.inventory = []
        self.lore = []
        self.last_context = ""
        self.psych_profile = "Neutral"
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
                    self.psych_profile = data.get('psych_profile', "Neutral")
                    self.last_context = data.get('last_context', "")
            except: pass

    def save_state(self):
        data = {
            'depth': self.depth,
            'entropy': self.entropy,
            'inventory': self.inventory,
            'lore': self.lore,
            'psych_profile': self.psych_profile,
            'last_context': self.last_context,
            'timestamp': datetime.now().isoformat()
        }
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except: pass

    def instant_sync_log(self, text, source="GAME"):
        """BLACK BOX MODE: Мгновенная запись."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "text": text,
            "depth": self.depth
        }
        self.session_buffer.append(entry)
        
        full_log = []
        if os.path.exists(EXPORT_FILE):
            try:
                with open(EXPORT_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content: full_log = json.load(f)
            except: pass
        
        if not isinstance(full_log, list): full_log = []
        full_log.append(entry)
        
        try:
            with open(EXPORT_FILE, 'w', encoding='utf-8') as f:
                json.dump(full_log, f, ensure_ascii=False, indent=2)
            self.session_buffer = [] 
        except Exception as e:
            print(f"{Col.RED}Ошибка записи хроники: {e}{Col.RESET}")

# --- GLOBAL STATE ---
GS = GameState()
API_KEYS = KeyManager.load_keys()

# --- HANDLERS ---
def exit_handler():
    # Защита от потери данных при выходе
    GS.save_state()
    if GS.session_buffer:
        GS.instant_sync_log("CRASH_DUMP: Unsaved buffer", "SYSTEM")
    # Красивое прощание только если это штатный выход
    if GS.depth > 1:
        print(f"\n{Col.GREEN}{Icon.LOCK} Данные зафиксированы. Реальность сохранена.{Col.RESET}")

atexit.register(exit_handler)
signal.signal(signal.SIGINT, lambda x, y: sys.exit(0))

# --- LOGIC ---
def get_archetype(entropy):
    if entropy < 0.3: return Icon.FATHER, "ОТЕЦ (Порядок)", 0.4
    elif entropy < 0.75: return Icon.SON, "СЫН (Видение)", 0.8
    else:
        if random.random() < 0.3: return Icon.JESTER, "ТРИКСТЕР (Хаос)", 1.3
        return Icon.SPIRIT, "ДУХ (Действие)", 1.0

def extract_json(text):
    clean = text.replace("```json", "").replace("```", "").strip()
    try:
        start = clean.find('{'); end = clean.rfind('}')
        if start != -1 and end != -1: clean = clean[start:end+1]
        return json.loads(clean)
    except: return None

def call_gemini(state, user_action):
    if not API_KEYS:
        print(f"{Col.RED}Ошибка: Нет ключей API. Удалите .env и перезапустите.{Col.RESET}")
        return None, None

    icon, archetype_name, temp = get_archetype(state.entropy)
    
    inv_str = ", ".join([str(i) for i in state.inventory]) if state.inventory else "Пусто"
    lore_str = "; ".join(state.lore[-3:]) if state.lore else "Нет данных"
    
    system_instruction = f"""
    ТЫ — JANUS GENESIS. Режим: {archetype_name}.
    Глубина: {state.depth}. Психотип: {state.psych_profile}.
    
    ИНСТРУКЦИИ АРХЕТИПА:
    - ОТЕЦ: Логика, структура, холод.
    - СЫН: Образы, эмоции, видения.
    - ДУХ/ТРИКСТЕР: Глитчи, ирония, парадоксы.
    
    ЗАДАЧА: JSON ответ на РУССКОМ.
    ФОРМАТ:
    {{
      "narrative": "Текст сюжета (до 300 знаков)...",
      "choices": ["Вариант 1", "Вариант 2"],
      "visual_clue": "{icon}",
      "artifact_found": "Название" OR null,
      "lore_unlocked": "Факт" OR null,
      "entropy_shift": 0.05
    }}
    """
    
    user_prompt = f"КОНТЕКСТ: {state.last_context}\nИНВЕНТАРЬ: {inv_str}\nДЕЙСТВИЕ: \"{user_action}\""

    key = random.choice(API_KEYS)
    # Используем основные модели, доступные в Free tier
    models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp"]

    for model in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            payload = {
                "contents": [{"parts": [{"text": user_prompt}]}],
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "generationConfig": {"temperature": temp}
            }
            headers = {"Content-Type": "application/json"}
            resp = requests.post(url, json=payload, headers=headers, timeout=25)
            if resp.status_code == 200:
                parsed = extract_json(resp.json()['candidates'][0]['content']['parts'][0]['text'])
                if parsed: return parsed, archetype_name
            elif resp.status_code == 429: time.sleep(1); continue
        except: continue
    return None, None

def draw_bar(value, width=10):
    percent = min(1.0, max(0.0, value / 1.5))
    fill = int(width * percent)
    bar = "█" * fill + "░" * (width - fill)
    c = Col.GREEN if value < 0.4 else (Col.YELLOW if value < 0.8 else Col.RED)
    return f"{Col.GREY}[{c}{bar}{Col.GREY}]{Col.RESET}"

# --- MAIN ---
def main():
    if not API_KEYS:
        KeyManager.setup()
        sys.exit(0)

    print("\033[2J\033[H", end="")
    print(f"{Col.CYAN}╔═══════════════════════════════════════╗")
    print(f"║   J A N U S   G E N E S I S  v12.2    ║")
    print(f"║      >>> BLACK BOX ACTIVE <<<         ║")
    print(f"╚═══════════════════════════════════════╝{Col.RESET}")
    
    GS.load()
    
    if GS.depth == 1 and not GS.last_context:
        intro = "Ты стоишь перед зеркалом. Отражения нет. Система Black Box активирована."
        print(f"\n{intro}")
        GS.last_context = intro
        GS.instant_sync_log(f"INIT: {intro}", "SYSTEM")

    while True:
        bar_vis = draw_bar(GS.entropy)
        p_col = Col.RED if "Aggressive" in GS.psych_profile else (Col.YELLOW if "Anxious" in GS.psych_profile else Col.PURPLE)
        
        print("\n" + f"{Col.GREY}─"*40 + f"{Col.RESET}")
        print(f"ГЛУБИНА: {Col.CYAN}{GS.depth:02d}{Col.RESET} | ХАОС: {bar_vis} | {p_col}{GS.psych_profile}{Col.RESET}")
        
        try:
            user_input = input(f"\n{Col.YELLOW}{Icon.SON} > {Col.RESET}").strip()
        except EOFError:
            break
            
        if not user_input: user_input = "Осмотреться"
        if user_input.lower() in ["exit", "выход"]: break

        # BLACK BOX LOGGING
        GS.instant_sync_log(f"USER: {user_input}", "USER")
        
        t = user_input.lower()
        if any(w in t for w in ["бить", "убить", "kill"]): GS.psych_profile = "Aggressive"
        elif any(w in t for w in ["бежать", "страх"]): GS.psych_profile = "Anxious"
        elif any(w in t for w in ["анализ", "почему"]): GS.psych_profile = "Analytical"

        print(f"{Col.GREY}⚡ Синхронизация...{Col.RESET}", end="\r")
        sys.stdout.flush()
        
        resp, archetype = call_gemini(GS, user_input)
        
        if resp:
            vis = resp.get('visual_clue', Icon.SON)
            nar = resp.get('narrative', '...')
            
            print(f"\n{vis} {Col.BOLD}{textwrap.fill(nar, width=65)}{Col.RESET}")
            if archetype: print(f"{Col.GREY}(Режим: {archetype}){Col.RESET}")
            
            art = resp.get('artifact_found')
            if art:
                name = art.get('name') if isinstance(art, dict) else str(art)
                print(f"\n{Col.GREEN}{Icon.KEY} АРТЕФАКТ: {name}{Col.RESET}")
                GS.inventory.append(art)
                GS.instant_sync_log(f"ARTIFACT: {name}", "LOOT")
            
            lore = resp.get('lore_unlocked')
            if lore:
                print(f"\n{Col.PURPLE}{Icon.BOOK} ИСТИНА: {lore}{Col.RESET}")
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
            print(f"\n{Col.RED}{Icon.WARN} Помехи в эфире. Проверьте ключи или сеть.{Col.RESET}")

if __name__ == "__main__":
    main()
