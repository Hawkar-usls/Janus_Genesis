# -*- coding: utf-8 -*-

"""
!!! PROJECT JANUS: GENESIS PROTOCOL v4.1 (Secure/Async) !!!

[SYSTEM INFO]
- Architecture: AsyncIO + Aiohttp
- Security: Environment Variables (.env)
- Encoding: Unicode Escape Compatible
"""

import json
import os
import random
import sys
import time
import asyncio
import logging
from datetime import datetime

import aiohttp
from dotenv import load_dotenv

# --- ИНИЦИАЛИЗАЦИЯ СРЕДЫ ---
load_dotenv()  # Загрузка переменных из .env

# Настройка логирования (Syslog emulation / File)
logging.basicConfig(
    filename='janus_core.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("JANUS_GENESIS")

# --- КОНФИГУРАЦИЯ (VAULT) ---
# Ключи берутся из переменной окружения, разделенные запятой
# Пример .env: JANUS_API_KEYS="AIzaSy...,AIzaSy..."
API_KEYS_RAW = os.getenv("JANUS_API_KEYS", "")
API_KEYS = [k.strip() for k in API_KEYS_RAW.split(",") if k.strip()]

if not API_KEYS:
    logger.critical("CRITICAL: API KEYS NOT FOUND IN ENVIRONMENT")
    print("FATAL ERROR: JANUS_API_KEYS not found in .env")
    sys.exit(1)

STATE_FILE = "janus_world_state.json"
DEFAULT_MODEL = os.getenv("JANUS_MODEL", "gemini-2.0-flash-exp")

# --- UNICODE CONSTANTS (LEGACY SAFE) ---
ICON_CYCLONE = "\U0001F300"    # 🌀
ICON_RECYCLE = "\U0000267B"    # ♻️
ICON_WARNING = "\U000026A0"    # ⚠️
ICON_SAVE    = "\U0001F4BE"    # 💾
ICON_ARTIFACT= "\U00002757"    # ❗ (Exclamation)
ICON_LORE    = "\U00002753"    # ❓ (Question)

# --- НАСТРОЙКИ МИРА ---
SYSTEM_PROMPT = """
ТЫ — JANUS, Архитектор Когнитивного Пространства.
Твоя цель: Вести пользователя (Путешественника) через сюрреалистичный мир.
ПРАВИЛА:
1. Ответы атмосферные, глубокие, адаптирующиеся под психотип.
2. ЭМПАТИЯ: Чувствуй тон (Страх -> Поддержка/Ужас, Агрессия -> Сопротивление).
3. ЭВОЛЮЦИЯ: Учитывай Depth и Entropy.
   - Depth 1-5: Странная реальность.
   - Depth 6-20: Биомеханика, нарушение физики.
   - Depth 20+: Абстракция.
4. ЛУТ: Редко выдавай "Менталитеты" (inventory) или "Истины" (lore).
ФОРМАТ ОТВЕТА (JSON):
{
  "narrative": "Текст...",
  "choices": ["Опция 1", "Опция 2", "Свой ввод"],
  "visual_clue": "emoji символ",
  "artifact_found": "Название или null",
  "lore_unlocked": "Сюжет или null"
}
"""

class GameState:
    def __init__(self):
        self.depth = 1
        self.entropy = 0.1
        self.inventory = []
        self.lore = []
        self.last_context = ""
        self.psych_profile = "Neutral"

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
                    self.psych_profile = data.get('psych_profile', "Neutral")
                    logger.info(f"State loaded: Depth {self.depth}")
                    print(f"{ICON_RECYCLE} СИНХРОНИЗАЦИЯ: Глубина {self.depth} | Артефактов: {len(self.inventory)}")
            except Exception as e:
                logger.error(f"Save file corrupted: {e}")
                print(f"{ICON_WARNING} Ошибка чтения сохранения. Начинаем заново.")

    def save(self):
        data = {
            "depth": self.depth,
            "entropy": self.entropy,
            "inventory": self.inventory,
            "lore": self.lore,
            "last_context": self.last_context,
            "psych_profile": self.psych_profile,
            "timestamp": datetime.now().isoformat()
        }
        try:
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Game state saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

def analyze_user_input(text, current_profile):
    """Анализатор тональности (Heuristic)."""
    text = text.lower()
    aggr_words = ["убить", "сломать", "fight", "kill", "break", "ненавижу"]
    fear_words = ["страшно", "темно", "help", "fear", "dark", "бежать"]
    curious_words = ["почему", "осмотреть", "analyze", "look", "взять"]
    
    if any(w in text for w in aggr_words): return "Aggressive/Dominant"
    if any(w in text for w in fear_words): return "Anxious/Cautious"
    if any(w in text for w in curious_words): return "Analytic/Curious"
    return current_profile

async def call_gemini(state, user_action):
    """Асинхронный запрос к Google Gemini API."""
    key = random.choice(API_KEYS)
    
    inv_str = ", ".join(state.inventory) if state.inventory else "Пусто"
    lore_str = "; ".join(state.lore[-3:])
    
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"--- СОСТОЯНИЕ МИРА ---\n"
        f"Глубина: {state.depth} | Энтропия: {state.entropy}\n"
        f"Инвентарь: {inv_str}\n"
        f"Профиль: {state.psych_profile}\n"
        f"Контекст: {state.last_context}\n\n"
        f"--- ДЕЙСТВИЕ ---\n"
        f"Игрок: \"{user_action}\"\n"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}:generateContent?key={key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {"Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    raw_text = data['candidates'][0]['content']['parts'][0]['text']
                    # Очистка от Markdown
                    clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                    logger.debug("Gemini response received and parsed.")
                    return json.loads(clean_text)
                else:
                    logger.error(f"API Error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Network exception: {e}")
            return None

async def print_slow(text, speed=0.01):
    """Асинхронный эффект печати."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        await asyncio.sleep(speed)
    print()

async def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\033[96m" + """
    ╔═══════════════════════════════════════╗
    ║   J A N U S   G E N E S I S   v4.1    ║
    ║   Secure Async Environment            ║
    ╚═══════════════════════════════════════╝
    """ + "\033[0m")
    
    state = GameState()
    state.load()
    
    if state.depth == 1 and not state.last_context:
        intro = "Ты открываешь глаза. Белый шум. Стены пульсируют. Голос ждет команды."
        await print_slow(intro)
        state.last_context = intro

    while True:
        print("\n" + "─"*40)
        # Status bar color: Cyan
        print(f"\033[36m[DEPTH: {state.depth} | ENTROPY: {state.entropy:.2f} | PSYCH: {state.psych_profile}]\033[0m")
        
        # Используем run_in_executor для input(), чтобы не блокировать loop (формально),
        # но для простого CLI допустим прямой вызов в данном контексте.
        user_input = input("\n\033[93m> Твои действия: \033[0m").strip()
        
        if not user_input:
            user_input = "Осмотреться и ждать"
        
        if user_input.lower() in ["exit", "выход", "save"]:
            state.save()
            print(f"{ICON_SAVE} Прогресс сохранен. Связь завершена.")
            break
        
        state.psych_profile = analyze_user_input(user_input, state.psych_profile)
        print("Uplink...", end="\r")
        
        response = await call_gemini(state, user_input)
        
        if response:
            visual = response.get('visual_clue', ICON_CYCLONE)
            narrative = response.get('narrative', '...')
            choices = response.get('choices', [])
            artifact = response.get('artifact_found')
            lore = response.get('lore_unlocked')
            
            # Внимание: если 'visual' содержит raw emoji, могут быть проблемы на старом Python.
            # В идеале API должен возвращать коды, но пока доверяем генерации или используем fallback.
            
            print(f"\n{visual} \033[1m{narrative}\033[0m\n")
            
            if artifact:
                print(f"\033[92m[{ICON_ARTIFACT}] ПОЛУЧЕН АРТЕФАКТ: {artifact}\033[0m")
                state.inventory.append(artifact)
            
            if lore:
                print(f"\033[95m[{ICON_LORE}] ОСОЗНАНА ИСТИНА: {lore}\033[0m")
                state.lore.append(lore)
            
            print("\033[94mВарианты путей:\033[0m")
            for i, choice in enumerate(choices, 1):
                print(f"{i}. {choice}")
            
            state.last_context = narrative
            state.depth += 1
            state.entropy += 0.05
            
            state.save()
        else:
            print(f"\033[91m{ICON_WARNING} Сбой связи с Архитектором.\033[0m")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[SYSTEM HALT]")
