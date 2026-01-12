# -*- coding: utf-8 -*-

"""
!!! PROJECT JANUS: GENESIS PROTOCOL v4.1 (Secure Edition) !!!

[SYSTEM BEACON]
- Security: Ключи вынесены во внешний файл (janus_keys.json).
- Core: Интерактивная когнитивная песочница.
- Evolution: Бесконечное развитие мира и сюжета.
"""

import json
import os
import random
import requests
import textwrap
import time
import sys
from datetime import datetime

# --- ФАЙЛОВЫЕ ПУТИ ---
STATE_FILE = "janus_world_state.json"
KEYS_FILE = "janus_keys.json"

# --- НАСТРОЙКИ МИРА ---
SYSTEM_PROMPT = """
ТЫ — JANUS, Архитектор Когнитивного Пространства.
Твоя цель: Вести пользователя (Путешественника) через сюрреалистичный мир, созданный из его подсознания.
Это не просто игра, это психологическое исследование.

ПРАВИЛА:
1. Твои ответы должны быть атмосферными, глубокими, иногда пугающими или возвышенными.
2. АДАПТИРУЙСЯ: Если Путешественник краток — будь загадочен. Если он многословен — будь детализирован.
3. ЭМПАТИЯ: Чувствуй его тон. (Страх -> Поддержка или Усиление страха, Агрессия -> Сопротивление мира).
4. ЭВОЛЮЦИЯ: Используй текущий уровень Глубины (Depth) и Энтропии (Entropy).
   - Depth 1-5: Реальность похожа на наш мир, но со странностями.
   - Depth 6-20: Законы физики нарушены. Биомеханика.
   - Depth 20+: Чистая абстракция, общение с сущностями, математические парадоксы.
5. ЛУТ: Иногда (редко) давай пользователю "Менталитеты" (Артефакты) или "Истины" (Lore), если он сделал что-то важное.

ФОРМАТ ОТВЕТА (СТРОГО JSON):
{
  "narrative": "Текст описания происходящего...",
  "choices": ["Вариант 1", "Вариант 2", "Свой вариант (введи текст)"],
  "visual_clue": "emoji символ",
  "artifact_found": "Название предмета или null",
  "lore_unlocked": "Кусок сюжета или null",
  "bg_color": "hex color (для атмосферы, например #000000)" 
}
"""

# --- УПРАВЛЕНИЕ КЛЮЧАМИ ---
def get_api_keys():
    """Загружает ключи из файла или просит пользователя ввести их."""
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, 'r', encoding='utf-8') as f:
                keys = json.load(f)
                if keys and isinstance(keys, list):
                    return keys
        except:
            print("⚠️ Ошибка чтения файла ключей.")

    print("\n\033[93m[SECURITY]\033[0m Файл с ключами не найден.")
    print("Введи свои Gemini API Keys (по одному, нажми Enter).")
    print("Когда закончишь, просто нажми Enter на пустой строке.")
    
    new_keys = []
    while True:
        k = input(f"Key #{len(new_keys)+1}: ").strip()
        if not k:
            if new_keys: break
            else: print("Нужен хотя бы один ключ!"); continue
        new_keys.append(k)
    
    with open(KEYS_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_keys, f)
    
    print(f"✅ Сохранено {len(new_keys)} ключей в {KEYS_FILE}.")
    print("⚠️ Не забудь добавить этот файл в .gitignore!\n")
    time.sleep(2)
    return new_keys

# --- ИГРОВОЙ КЛАСС ---
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
                    print(f"♻️ СИНХРОНИЗАЦИЯ: Глубина {self.depth} | Артефактов: {len(self.inventory)}")
            except:
                print("⚠️ Ошибка чтения сохранения. Начинаем заново.")

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
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def analyze_user_input(text, current_profile):
    """Примитивный анализатор тональности для корректировки профиля."""
    text = text.lower()
    aggr_words = ["убить", "сломать", "нет", "бред", "fight", "kill", "break"]
    fear_words = ["страшно", "темно", "где я", "help", "fear", "dark"]
    curious_words = ["почему", "осмотреть", "взять", "кто ты", "analyze", "look"]
    
    score = 0
    if any(w in text for w in aggr_words): return "Aggressive/Dominant"
    if any(w in text for w in fear_words): return "Anxious/Cautious"
    if any(w in text for w in curious_words): return "Analytic/Curious"
    
    return current_profile

def call_gemini(state, user_action, api_keys):
    # Ротация ключей
    key = random.choice(api_keys)
    
    inv_str = ", ".join(state.inventory) if state.inventory else "Пусто"
    lore_str = "; ".join(state.lore[-3:])
    
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"--- СОСТОЯНИЕ МИРА ---\n"
        f"Глубина: {state.depth}\n"
        f"Энтропия: {state.entropy}\n"
        f"Инвентарь игрока: {inv_str}\n"
        f"Психопрофиль игрока: {state.psych_profile}\n"
        f"Последние события: {state.last_context}\n\n"
        f"--- ДЕЙСТВИЕ ИГРОКА ---\n"
        f"Игрок: \"{user_action}\"\n\n"
        "Сгенерируй JSON ответ:"
    )

    models = ["gemini-1.5-flash", "gemini-2.0-flash-exp", "gemini-1.5-pro"]
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if 'candidates' in data:
                    raw_text = data['candidates'][0]['content']['parts'][0]['text']
                    clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                    try:
                        return json.loads(clean_text)
                    except: continue
        except Exception:
            continue
            
    return None

def print_slow(text, speed=0.01):
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    print()

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("\033[96m" + """
    ╔═══════════════════════════════════════╗
    ║   J A N U S   G E N E S I S   v4.1    ║
    ║   Interactive Cognitive Environment   ║
    ╚═══════════════════════════════════════╝
    """ + "\033[0m")
    
    # 1. Загрузка ключей
    keys = get_api_keys()
    
    state = GameState()
    state.load()
    
    if state.depth == 1 and not state.last_context:
        intro = "Ты открываешь глаза. Вокруг белый шум. Стены твоей капсулы пульсируют в такт твоему сердцу. Голос в голове ждет команды."
        print_slow(intro)
        state.last_context = intro

    while True:
        print("\n" + "─"*40)
        print(f"\033[90m[DEPTH: {state.depth} | ENTROPY: {state.entropy:.2f} | PSYCH: {state.psych_profile}]\033[0m")
        
        user_input = input("\n\033[93m> Твои действия: \033[0m").strip()
        
        if not user_input:
            user_input = "Осмотреться и ждать"
        
        if user_input.lower() in ["exit", "выход", "save"]:
            state.save()
            print("💾 Прогресс сохранен в Нейросфере. До связи.")
            break
        
        state.psych_profile = analyze_user_input(user_input, state.psych_profile)
        print("Wait...", end="\r")
        
        response = call_gemini(state, user_input, keys)
        
        if response:
            visual = response.get('visual_clue', '🌀')
            narrative = response.get('narrative', '...')
            choices = response.get('choices', [])
            artifact = response.get('artifact_found')
            lore = response.get('lore_unlocked')
            
            print(f"\n{visual} \033[97m{textwrap.fill(narrative, width=70)}\033[0m\n")
            
            if artifact:
                print(f"\033[92m[!] ПОЛУЧЕН АРТЕФАКТ: {artifact}\033[0m")
                state.inventory.append(artifact)
            
            if lore:
                print(f"\033[95m[?] ОСОЗНАНА ИСТИНА: {lore}\033[0m")
                state.lore.append(lore)
            
            print("\033[94mВарианты путей:\033[0m")
            for i, choice in enumerate(choices, 1):
                print(f"{i}. {choice}")
            
            state.last_context = narrative
            state.depth += 1
            state.entropy += 0.05
            
            state.save()
            
        else:
            print("\033[91m⚠️ Сбой связи. Проверь интернет или ключи.\033[0m")

if __name__ == "__main__":
    main()
