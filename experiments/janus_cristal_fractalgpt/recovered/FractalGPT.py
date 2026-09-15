# -*- coding: utf-8 -*-
"""
FractalGPT: микро-авторегрессионная модель для генерации фрактальных структур.
Поддерживает: итерации фракталов (координаты), фрактальные размерности, параметры масштабирования.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple, Optional

import numpy as np


class Value:
    __slots__ = ("data", "grad", "_children", "_local_grads")

    def __init__(self, data, children=(), local_grads=()):
        self.data = float(data)
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
        return Value(self.data**other, (self,), (other * self.data ** (other - 1),))

    def log(self):
        safe = self.data if self.data > 1e-15 else 1e-15
        return Value(math.log(safe), (self,), (1.0 / safe,))

    def exp(self):
        e = math.exp(self.data)
        return Value(e, (self,), (e,))

    def relu(self):
        return Value(max(0.0, self.data), (self,), (1.0 if self.data > 0 else 0.0,))

    def __neg__(self):
        return self * -1

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        return self + (-other)

    def __rsub__(self, other):
        return other + (-self)

    def __rmul__(self, other):
        return self * other

    def __truediv__(self, other):
        return self * other**-1

    def backward(self):
        topo = []
        visited = set()

        def build(node):
            if node in visited:
                return
            visited.add(node)
            for child in node._children:
                build(child)
            topo.append(node)

        build(self)
        self.grad = 1.0
        for node in reversed(topo):
            for child, local_grad in zip(node._children, node._local_grads):
                child.grad += local_grad * node.grad


class FractalGPT:
    """
    Авторегрессионная модель для генерации и симуляции фрактальных последовательностей.
    Состояние описывается вектором:
      - x, y  : координаты (для 2D фракталов)
      - scale : текущий масштаб
      - angle : угол поворота
      - iteration : номер итерации (или глубина)
    Размерность state_dim настраивается.
    """

    def __init__(
        self,
        state_dim: int = 5,          # x, y, scale, angle, iteration
        n_layer: int = 2,
        n_embd: int = 64,
        block_size: int = 64,
        n_head: int = 4,
    ):
        self.state_dim = int(state_dim)
        self.n_layer = int(n_layer)
        self.n_embd = int(n_embd)
        self.block_size = int(block_size)
        self.n_head = int(n_head)
        self.head_dim = self.n_embd // self.n_head
        if self.head_dim * self.n_head != self.n_embd:
            raise ValueError("n_embd must be divisible by n_head")

        def matrix(nout, nin, std=0.08):
            return [[Value(random.gauss(0, std)) for _ in range(nin)] for _ in range(nout)]

        self.state_dict = {
            "input_proj": matrix(self.n_embd, self.state_dim),
            "output_proj": matrix(self.state_dim, self.n_embd),
            "wpe": matrix(self.block_size, self.n_embd),
        }

        for i in range(self.n_layer):
            self.state_dict[f"layer{i}.attn_wq"] = matrix(self.n_embd, self.n_embd)
            self.state_dict[f"layer{i}.attn_wk"] = matrix(self.n_embd, self.n_embd)
            self.state_dict[f"layer{i}.attn_wv"] = matrix(self.n_embd, self.n_embd)
            self.state_dict[f"layer{i}.attn_wo"] = matrix(self.n_embd, self.n_embd)
            self.state_dict[f"layer{i}.mlp_fc1"] = matrix(4 * self.n_embd, self.n_embd)
            self.state_dict[f"layer{i}.mlp_fc2"] = matrix(self.n_embd, 4 * self.n_embd)

        self.params = [param for mat in self.state_dict.values() for row in mat for param in row]

    def linear(self, x, w):
        return [sum(weight * value for weight, value in zip(row, x)) for row in w]

    def softmax(self, logits):
        max_val = max(item.data if isinstance(item, Value) else item for item in logits)
        exps = [(item - max_val).exp() if isinstance(item, Value) else math.exp(item - max_val) for item in logits]
        total = sum(item.data if isinstance(item, Value) else item for item in exps)
        return [item / total for item in exps]

    def rmsnorm(self, x):
        mean_square = sum((item.data if isinstance(item, Value) else item) ** 2 for item in x) / len(x)
        scale = (mean_square + 1e-5) ** -0.5
        return [item * scale for item in x]

    def forward(self, state_vec: List[float], pos_id: int, keys: List[List], values: List[List]) -> List[Value]:
        token_emb = self.linear(state_vec, self.state_dict["input_proj"])
        pos_emb = self.state_dict["wpe"][int(pos_id) % self.block_size]
        x = self.rmsnorm([t + p for t, p in zip(token_emb, pos_emb)])

        for layer_idx in range(self.n_layer):
            residual = x
            x = self.rmsnorm(x)

            q = self.linear(x, self.state_dict[f"layer{layer_idx}.attn_wq"])
            k = self.linear(x, self.state_dict[f"layer{layer_idx}.attn_wk"])
            v = self.linear(x, self.state_dict[f"layer{layer_idx}.attn_wv"])

            keys[layer_idx].append(k)
            values[layer_idx].append(v)

            attended = []
            for head in range(self.n_head):
                head_start = head * self.head_dim
                q_head = q[head_start:head_start + self.head_dim]
                k_head = [item[head_start:head_start + self.head_dim] for item in keys[layer_idx]]
                v_head = [item[head_start:head_start + self.head_dim] for item in values[layer_idx]]

                logits = [
                    sum(q_head[j] * k_head[t][j] for j in range(self.head_dim)) / (self.head_dim ** 0.5)
                    for t in range(len(k_head))
                ]
                weights = self.softmax(logits)
                head_output = [
                    sum(weights[t] * v_head[t][j] for t in range(len(v_head))) for j in range(self.head_dim)
                ]
                attended.extend(head_output)

            x = [out + res for out, res in zip(self.linear(attended, self.state_dict[f"layer{layer_idx}.attn_wo"]), residual)]

            residual = x
            x = self.rmsnorm(x)
            x = [item.relu() for item in self.linear(x, self.state_dict[f"layer{layer_idx}.mlp_fc1"])]
            x = [out + res for out, res in zip(self.linear(x, self.state_dict[f"layer{layer_idx}.mlp_fc2"]), residual)]

        return self.linear(x, self.state_dict["output_proj"])

    def train_step(self, sequence: List[List[float]], lr: float = 0.001) -> float:
        if len(sequence) < 2:
            return 0.0

        keys = [[] for _ in range(self.n_layer)]
        values = [[] for _ in range(self.n_layer)]
        losses = []
        seq = sequence[:self.block_size]

        for pos in range(len(seq) - 1):
            current = [Value(x) for x in seq[pos]]
            target = seq[pos + 1]
            pred_vec = self.forward(current, pos, keys, values)
            loss = sum((pred_vec[i] - target[i]) ** 2 for i in range(self.state_dim))
            losses.append(loss)

        total_loss = (1.0 / max(1, len(seq) - 1)) * sum(losses, Value(0.0))
        if math.isnan(total_loss.data):
            return 0.0

        total_loss.backward()
        for param in self.params:
            param.grad = max(-1.0, min(1.0, param.grad))
            param.data -= lr * param.grad
            param.grad = 0.0
        return float(total_loss.data)

    def train_on_sequences(self, sequences: List[List[List[float]]], steps: int = 100, lr: float = 0.001):
        if not sequences:
            return
        for _ in range(steps):
            self.train_step(random.choice(sequences), lr)

    def evaluate(self, sequences: List[List[List[float]]]) -> float:
        if not sequences:
            return 0.0
        losses = []
        for seq in sequences:
            if len(seq) < 2:
                continue
            keys = [[] for _ in range(self.n_layer)]
            values = [[] for _ in range(self.n_layer)]
            mse_sum = 0.0
            seq_cut = seq[:self.block_size]
            for pos in range(len(seq_cut) - 1):
                current = [Value(x) for x in seq_cut[pos]]
                target = seq_cut[pos + 1]
                pred = self.forward(current, pos, keys, values)
                mse = sum((pred[i].data - target[i]) ** 2 for i in range(self.state_dim))
                mse_sum += mse
            losses.append(mse_sum / (len(seq_cut) - 1))
        return float(np.mean(losses)) if losses else 0.0

    def generate(self, initial_state: List[float], max_len: int = 100, temperature: float = 0.0) -> List[List[float]]:
        state = [float(v) for v in initial_state]
        states = [state[:]]
        keys = [[] for _ in range(self.n_layer)]
        values = [[] for _ in range(self.n_layer)]

        for pos in range(max_len - 1):
            current = [Value(x) for x in state]
            pred_vec = self.forward(current, pos, keys, values)
            if temperature > 0:
                noise = np.random.normal(0, temperature, self.state_dim)
                next_state = [pred_vec[i].data + noise[i] for i in range(self.state_dim)]
            else:
                next_state = [pred_vec[i].data for i in range(self.state_dim)]
            states.append(next_state)
            state = next_state
        return states

    # ---- Методы для генерации фрактальных обучающих данных ----
    @staticmethod
    def koch_curve(iterations: int = 4, step_size: float = 1.0) -> List[List[float]]:
        """
        Генерирует последовательность точек кривой Коха.
        Возвращает список состояний [x, y, angle, scale, iteration]
        """
        points = []
        # Начальное состояние: (0,0), угол 0, масштаб 1, итерация 0
        x, y = 0.0, 0.0
        angle = 0.0
        # Используем L-систему для кривой Коха: F -> F+F--F+F
        def produce(axiom, rules, n):
            result = axiom
            for _ in range(n):
                result = ''.join(rules.get(ch, ch) for ch in result)
            return result

        rules = {'F': 'F+F--F+F'}
        pattern = produce('F', rules, iterations)
        # Длина шага уменьшается с каждой итерацией, но для простоты фиксируем
        step = step_size / (3 ** iterations)
        points.append([x, y, angle, step, 0.0])
        for ch in pattern:
            if ch == 'F':
                x += step * math.cos(angle)
                y += step * math.sin(angle)
                points.append([x, y, angle, step, 0.0])
            elif ch == '+':
                angle += math.pi / 3
            elif ch == '-':
                angle -= math.pi / 3
        return points

    @staticmethod
    def sierpinski_triangle(iterations: int = 4, size: float = 1.0) -> List[List[float]]:
        """
        Генерирует точки треугольника Серпинского (итерационная система функций).
        """
        points = []
        # Вершины
        vertices = [(0.0, 0.0), (size, 0.0), (size/2, size * math.sqrt(3)/2)]
        # Начальная точка
        x, y = random.uniform(0, size), random.uniform(0, size*0.866)
        points.append([x, y, 0.0, size, float(iterations)])
        for _ in range(500):
            v = random.choice(vertices)
            x = (x + v[0]) / 2
            y = (y + v[1]) / 2
            points.append([x, y, 0.0, size, float(iterations)])
        return points

    @staticmethod
    def fractal_brownian_motion(steps: int = 200, hurst: float = 0.7, scale: float = 1.0) -> List[List[float]]:
        """
        Генерирует фрактальный броуновский ряд (1D) как последовательность [x, 0, value, hurst, 0]
        """
        points = []
        x = 0.0
        value = 0.0
        points.append([x, 0.0, value, hurst, 0.0])
        for i in range(1, steps):
            # Используем приближение с коррелированными приращениями
            inc = np.random.normal(0, scale * (i ** (hurst - 0.5)))
            value += inc
            points.append([float(i), 0.0, value, hurst, 0.0])
        return points

    # ---- Сохранение/загрузка ----
    def get_weights(self):
        return {name: [[param.data for param in row] for row in matrix] for name, matrix in self.state_dict.items()}

    def set_weights(self, weights):
        for name, matrix in weights.items():
            if name not in self.state_dict:
                continue
            for i, row in enumerate(matrix):
                if i >= len(self.state_dict[name]):
                    break
                for j, value in enumerate(row):
                    if j >= len(self.state_dict[name][i]):
                        break
                    self.state_dict[name][i][j].data = float(value)

    def save(self, path: str):
        import pickle
        with open(path, "wb") as f:
            pickle.dump(self.get_weights(), f)

    def load(self, path: str):
        import pickle
        with open(path, "rb") as f:
            self.set_weights(pickle.load(f))


# ------------------- Пример использования: обучение на кривой Коха -------------------
if __name__ == "__main__":
    # Состояние: [x, y, angle, scale, iteration]
    model = FractalGPT(state_dim=5, n_layer=2, n_embd=32, block_size=64, n_head=4)

    # Генерируем обучающие данные из разных фракталов
    train_data = []
    # Кривая Коха с разной глубиной
    for iter in [2, 3, 4]:
        koch = FractalGPT.koch_curve(iterations=iter, step_size=2.0)
        # Разбиваем на блоки длины 32
        for i in range(0, len(koch)-32, 16):
            train_data.append(koch[i:i+32])
    # Треугольник Серпинского
    sier = FractalGPT.sierpinski_triangle(iterations=4, size=2.0)
    for i in range(0, len(sier)-32, 16):
        train_data.append(sier[i:i+32])
    # Фрактальное броуновское движение
    fbm = FractalGPT.fractal_brownian_motion(steps=200, hurst=0.8)
    for i in range(0, len(fbm)-32, 16):
        train_data.append(fbm[i:i+32])

    print(f"Generated {len(train_data)} training sequences.")

    print("Training FractalGPT on fractal sequences...")
    for epoch in range(30):
        loss = model.train_on_sequences(train_data, steps=50, lr=0.001)
        if epoch % 10 == 0:
            val_loss = model.evaluate(train_data[:20])
            print(f"Epoch {epoch}, val MSE = {val_loss:.6f}")

    # Генерация новой фрактальной последовательности
    # Начальное состояние: (0,0), угол 0, масштаб 0.1, итерация 0
    initial = [0.0, 0.0, 0.0, 0.1, 0.0]
    generated = model.generate(initial, max_len=100, temperature=0.02)
    print("\nСгенерированная фрактальная траектория (первые 20 точек):")
    for i, state in enumerate(generated[:20]):
        print(f"step {i:2d}: x={state[0]:6.3f}, y={state[1]:6.3f}, angle={state[2]:5.3f}")
