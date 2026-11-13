# janus_genesis/language_model.py
import math
import random
import numpy as np
import json
import os
import re
from collections import deque, Counter
from typing import List, Dict, Optional, Tuple, Any

from .vocab import get_vocab


# ===== ГИБРИДНЫЙ ТОКЕНИЗАТОР (слово/символ) =====
class Tokenizer:
    """
    Гибридный токенизатор: поддерживает режимы 'word' (слова + пунктуация) и 'char' (символы).
    Строит словарь из текстов, может загружать готовый.
    """
    def __init__(self, mode='word', vocab=None, texts=None, max_vocab=10000):
        self.mode = mode
        self.special_tokens = ["<PAD>", "<UNK>", "<EOS>", "<BOS>"]

        if vocab is not None:
            # Копируем, чтобы не мутировать исходный список
            full_vocab = list(vocab)
            # Вставляем специальные токены в начало, если их нет
            for st in reversed(self.special_tokens):
                if st not in full_vocab:
                    full_vocab.insert(0, st)
            self.vocab = full_vocab
            self.stoi = {w: i for i, w in enumerate(full_vocab)}
            self.itos = {i: w for i, w in enumerate(full_vocab)}
        else:
            self.vocab = self.special_tokens.copy()
            self.stoi = {w: i for i, w in enumerate(self.vocab)}
            self.itos = {i: w for i, w in enumerate(self.vocab)}
            if texts:
                self.build_vocab(texts, max_vocab)

    def build_vocab(self, texts: List[str], max_vocab=10000):
        """Строит словарь из списка текстов, сохраняя специальные токены в начале."""
        counter = Counter()
        for text in texts:
            tokens = self._tokenize(text)
            counter.update(tokens)
        # добавляем наиболее частотные слова, не превышая max_vocab
        new_words = [word for word, _ in counter.most_common(max_vocab - len(self.special_tokens))]
        full_vocab = self.special_tokens + new_words
        self.vocab = full_vocab
        self.stoi = {w: i for i, w in enumerate(full_vocab)}
        self.itos = {i: w for i, w in enumerate(full_vocab)}
        return self.vocab

    def _tokenize(self, text: str) -> List[str]:
        """Разбивает текст на токены в зависимости от режима."""
        if self.mode == 'word':
            # слова и знаки препинания
            return re.findall(r"\w+|[^\w\s]", text.lower())
        else:  # char
            return list(text)

    def encode(self, text: str) -> List[int]:
        """Преобразует строку в список индексов."""
        tokens = self._tokenize(text)
        return [self.stoi.get(t, self.stoi["<UNK>"]) for t in tokens]

    def decode(self, ids: List[int]) -> str:
        """Преобразует индексы в строку."""
        if self.mode == 'word':
            # слова разделяем пробелом, знаки препинания слитно
            result = []
            for i, w in enumerate([self.itos.get(i, "<UNK>") for i in ids]):
                if i > 0 and w not in ".,!?;:-":
                    result.append(" " + w)
                else:
                    result.append(w)
            return "".join(result).strip()
        else:
            return "".join(self.itos.get(i, "<UNK>") for i in ids)

    def __len__(self):
        return len(self.vocab)


# ===== АВТОГРАД (Value) =====
class Value:
    __slots__ = ('data', 'grad', '_children', '_local_grads')
    def __init__(self, data, children=(), local_grads=()):
        self.data = data
        self.grad = 0.0
        self._children = children
        self._local_grads = local_grads

    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        return Value(self.data + other.data, (self, other), (1, 1))

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        return Value(self.data * other.data, (self, other), (other.data, self.data))

    def __pow__(self, other):
        return Value(self.data ** other, (self,), (other * self.data ** (other - 1),))

    def log(self):
        val = self.data if self.data > 1e-15 else 1e-15
        return Value(math.log(val), (self,), (1 / val,))

    def exp(self):
        return Value(math.exp(self.data), (self,), (math.exp(self.data),))

    def relu(self):
        return Value(max(0, self.data), (self,), (float(self.data > 0),))

    def __neg__(self): return self * -1
    def __radd__(self, other): return self + other
    def __sub__(self, other): return self + (-other)
    def __rsub__(self, other): return other + (-self)
    def __rmul__(self, other): return self * other
    def __truediv__(self, other): return self * other ** -1

    def backward(self):
        topo = []
        visited = set()
        def build_topo(v):
            if v not in visited:
                visited.add(v)
                for child in v._children:
                    build_topo(child)
                topo.append(v)
        build_topo(self)
        self.grad = 1.0
        for v in reversed(topo):
            for child, local_grad in zip(v._children, v._local_grads):
                child.grad += local_grad * v.grad


# ===== МИКРО-ТРАНСФОРМЕР =====
class MicroGPT:
    def __init__(self, vocab_size, n_layer=1, n_embd=16, block_size=32, n_head=4):
        self.vocab_size = max(vocab_size, 2)
        self.n_layer = n_layer
        self.n_embd = n_embd
        self.block_size = block_size
        self.n_head = n_head
        self.head_dim = n_embd // n_head
        assert self.head_dim * n_head == n_embd, "n_embd должно делиться на n_head"

        matrix = lambda nout, nin, std=0.08: [
            [Value(random.gauss(0, std)) for _ in range(nin)] for _ in range(nout)
        ]

        self.state_dict = {
            'wte': matrix(self.vocab_size, n_embd),
            'wpe': matrix(block_size, n_embd),
            'lm_head': matrix(self.vocab_size, n_embd)
        }
        for i in range(n_layer):
            self.state_dict[f'layer{i}.attn_wq'] = matrix(n_embd, n_embd)
            self.state_dict[f'layer{i}.attn_wk'] = matrix(n_embd, n_embd)
            self.state_dict[f'layer{i}.attn_wv'] = matrix(n_embd, n_embd)
            self.state_dict[f'layer{i}.attn_wo'] = matrix(n_embd, n_embd)
            self.state_dict[f'layer{i}.mlp_fc1'] = matrix(4 * n_embd, n_embd)
            self.state_dict[f'layer{i}.mlp_fc2'] = matrix(n_embd, 4 * n_embd)

        self.params = [p for mat in self.state_dict.values() for row in mat for p in row]

    def linear(self, x, w):
        return [sum(wi * xi for wi, xi in zip(wo, x)) for wo in w]

    def softmax(self, logits):
        max_val = max(l.data if isinstance(l, Value) else l for l in logits)
        exps = [(l - max_val).exp() if isinstance(l, Value) else math.exp(l - max_val) for l in logits]
        total = sum(e.data if isinstance(e, Value) else e for e in exps)
        return [e / total for e in exps]

    def rmsnorm(self, x):
        ms = sum(xi.data * xi.data if isinstance(xi, Value) else xi * xi for xi in x) / len(x)
        scale = (ms + 1e-5) ** -0.5
        return [xi * scale for xi in x]

    def forward(self, token_id, pos_id, keys, values):
        safe_pos = pos_id % self.block_size
        x = self.rmsnorm([t + p for t, p in zip(self.state_dict['wte'][token_id],
                                                 self.state_dict['wpe'][safe_pos])])

        for li in range(self.n_layer):
            x_residual = x
            x = self.rmsnorm(x)

            q = self.linear(x, self.state_dict[f'layer{li}.attn_wq'])
            k = self.linear(x, self.state_dict[f'layer{li}.attn_wk'])
            v = self.linear(x, self.state_dict[f'layer{li}.attn_wv'])

            keys[li].append(k)
            values[li].append(v)

            if len(keys[li]) > self.block_size:
                keys[li].pop(0)
                values[li].pop(0)

            x_attn = []
            for h in range(self.n_head):
                hs = h * self.head_dim
                q_h = q[hs:hs + self.head_dim]
                k_h = [ki[hs:hs + self.head_dim] for ki in keys[li]]
                v_h = [vi[hs:hs + self.head_dim] for vi in values[li]]

                attn_logits = []
                for t in range(len(k_h)):
                    score = sum(q_h[j] * k_h[t][j] for j in range(self.head_dim)) / (self.head_dim ** 0.5)
                    attn_logits.append(score)
                attn_weights = self.softmax(attn_logits)

                x_attn_h = [sum(attn_weights[t] * v_h[t][j] for t in range(len(v_h))) for j in range(self.head_dim)]
                x_attn.extend(x_attn_h)

            x = [a + b for a, b in zip(self.linear(x_attn, self.state_dict[f'layer{li}.attn_wo']), x_residual)]

            x_residual = x
            x = self.rmsnorm(x)
            x = [xi.relu() for xi in self.linear(x, self.state_dict[f'layer{li}.mlp_fc1'])]
            x = [a + b for a, b in zip(self.linear(x, self.state_dict[f'layer{li}.mlp_fc2']), x_residual)]

        return self.linear(x, self.state_dict['lm_head'])

    def train_step(self, batch, lr=0.01, reward_func=None):
        total_loss = Value(0.0)
        n_tokens = 0
        for seq in batch:
            if len(seq) > self.block_size:
                seq = seq[:self.block_size]
            keys = [[] for _ in range(self.n_layer)]
            values = [[] for _ in range(self.n_layer)]
            for pos in range(len(seq) - 1):
                token_id = seq[pos]
                target_id = seq[pos + 1]
                # Защита от выхода индекса за пределы словаря
                if target_id < 0 or target_id >= self.vocab_size:
                    continue
                logits = self.forward(token_id, pos, keys, values)
                probs = self.softmax(logits)
                loss_t = -probs[target_id].log()

                if reward_func is not None:
                    reward = reward_func(token_id, pos, seq, target_id)
                    loss_t = loss_t - 0.1 * reward

                total_loss += loss_t
                n_tokens += 1
        if n_tokens == 0:
            return 0.0
        avg_loss = total_loss * (1.0 / n_tokens)
        avg_loss.backward()
        for p in self.params:
            if p.grad is not None:
                p.grad = max(-1.0, min(1.0, p.grad))
                p.data -= lr * p.grad
                p.grad = 0.0
        return avg_loss.data

    def generate(self, start_tokens, max_len=20, temperature=1.0):
        tokens = start_tokens.copy()
        keys = [[] for _ in range(self.n_layer)]
        values = [[] for _ in range(self.n_layer)]
        for pos in range(len(tokens) - 1):
            self.forward(tokens[pos], pos, keys, values)
        for pos in range(len(tokens), min(max_len, self.block_size)):
            logits = self.forward(tokens[-1], pos-1, keys, values)
            logits_scaled = [l.data / temperature for l in logits]
            max_val = max(logits_scaled)
            exps = [math.exp(v - max_val) for v in logits_scaled]
            probs = [e / sum(exps) for e in exps]
            next_tok = np.random.choice(self.vocab_size, p=probs)
            tokens.append(next_tok)
        return tokens

    def save(self, path):
        import pickle
        with open(path, 'wb') as f:
            pickle.dump(self.state_dict, f)

    def load(self, path):
        import pickle
        with open(path, 'rb') as f:
            self.state_dict = pickle.load(f)


# ===== LANGUAGE ENGINE =====
class LanguageEngine:
    def __init__(self, vocab_file="vocab.json", model_path=None, tokenizer=None,
                 mode='word', **model_kwargs):
        """
        mode: 'word' (слова+пунктуация) или 'char' (символьный).
        """
        if tokenizer is None:
            # Если есть файл vocab.json, используем его как словарь символов для обратной совместимости,
            # но для словесного режима лучше построить свой словарь.
            char_vocab = get_vocab(vocab_file)
            self.tokenizer = Tokenizer(mode=mode, vocab=char_vocab if mode=='char' else None)
        else:
            self.tokenizer = tokenizer
        self.vocab_size = len(self.tokenizer)
        self.model = MicroGPT(self.vocab_size, **model_kwargs)
        if model_path and os.path.exists(model_path):
            self.model.load(model_path)
        self.history = []
        self.best_texts = []
        self.evolution_pool = deque(maxlen=100)
        self.event_keywords = {
            "RECORD": ["record", "victory", "triumph", "celebration"],
            "EXTINCTION": ["extinct", "death", "loss", "empty"],
            "NEW_SPECIES": ["new", "birth", "species", "evolution"],
            "RAID": ["raid", "battle", "fight", "attack"],
            "WORMHOLE": ["wormhole", "portal", "mystery", "unknown"]
        }

    def encode(self, text):
        return self.tokenizer.encode(text)

    def decode(self, ids):
        return self.tokenizer.decode(ids)

    def clean_text(self, text):
        words = text.split()
        cleaned = []
        prev = None
        for w in words:
            if w != prev:
                cleaned.append(w)
                prev = w
        return " ".join(cleaned)

    def compute_reward(self, text, event_type=None):
        words = text.split()
        if not words:
            return 0.0
        unique = len(set(words))
        total = len(words)
        info_density = unique / total if total > 0 else 0.0
        length_penalty = -math.log1p(total) / 5.0
        event_reward = 0.0
        if event_type and event_type in self.event_keywords:
            keywords = self.event_keywords[event_type]
            for kw in keywords:
                if kw in text.lower():
                    event_reward += 0.2
        reward = info_density + event_reward + length_penalty
        return max(0.0, min(1.0, reward))

    def generate(self, prompt, max_len=50, temperature=0.9, event_type=None, clean=True):
        ids = self.encode(prompt)
        if not ids:
            ids = [self.tokenizer.stoi.get("<BOS>", 0)]
        generated = self.model.generate(ids, max_len=len(ids)+max_len, temperature=temperature)
        text = self.decode(generated[:len(ids)+max_len])
        text = text.strip()
        if clean:
            text = self.clean_text(text)
        reward = self.compute_reward(text, event_type) if event_type else None
        return text, reward

    def train_step(self, text, lr=0.01, event_type=None):
        ids = self.encode(text)
        if len(ids) < 2:
            return 0.0
        chunks = []
        for i in range(0, len(ids), self.model.block_size):
            chunk = ids[i:i+self.model.block_size]
            if len(chunk) >= 2:
                chunks.append(chunk)
        if not chunks:
            return 0.0

        def reward_func(token_id, pos, seq, target_id):
            if event_type and event_type in self.event_keywords:
                token_str = self.tokenizer.itos.get(token_id, "")
                if token_str in self.event_keywords[event_type]:
                    return 0.1
            return 0.0

        loss = self.model.train_step(chunks, lr, reward_func)
        self.history.append(text)
        if len(self.history) > 1000:
            self.history.pop(0)
        return loss

    def learn_from_event(self, event_type, context, world=None):
        prompt = f"Event {event_type}: {context}"
        generated, reward = self.generate(prompt, max_len=40, event_type=event_type, clean=True)
        if reward is not None and reward > 0.6:
            self.train_step(generated, lr=0.01, event_type=event_type)
            self.evolution_pool.append((generated, reward))
        return generated, reward

    def learn_from_visionary(self, prompt, image_score):
        if image_score > 0.7:
            self.train_step(prompt, lr=0.005)
            self.best_texts.append(prompt)
            if len(self.best_texts) > 50:
                self.best_texts.pop(0)
            return True
        return False

    def learn_from_meme(self, meme_text):
        self.train_step(meme_text, lr=0.01)

    def self_critic(self, text):
        words = text.split()
        if len(words) < 3:
            return 0.2, ["too short"]
        unique = len(set(words))
        density = unique / len(words)
        if density > 0.8:
            return 0.9, ["good density"]
        elif density < 0.3:
            return 0.4, ["too repetitive", "add more variety"]
        return 0.6, ["acceptable"]

    def improve_text(self, text, suggestions):
        if "too repetitive" in suggestions:
            words = text.split()
            cleaned = []
            prev = None
            for w in words:
                if w != prev:
                    cleaned.append(w)
                    prev = w
            return " ".join(cleaned)
        return text

    def evolve_prompts(self):
        if not self.evolution_pool:
            return None
        best = sorted(self.evolution_pool, key=lambda x: x[1], reverse=True)[:5]
        if not best:
            return None
        parent, _ = random.choice(best)
        words = parent.split()
        if not words:
            return None
        idx = random.randint(0, len(words)-1)
        all_words = list(self.tokenizer.stoi.keys())
        new_word = random.choice(all_words)
        words[idx] = new_word
        return " ".join(words)

    def save(self, path):
        self.model.save(path)

    def load(self, path):
        self.model.load(path)