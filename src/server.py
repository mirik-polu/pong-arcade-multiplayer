# server.py
import socket
import threading
import json
import time
import random

SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
PADDLE_W, PADDLE_H = 20, 100
BALL_R = 10
PADDLE_SPEED = 5
BALL_SPEED = 5
TICK_RATE = 60

class PongServer:
    def __init__(self):
        self.clients = {}
        self.state = {
            "p1_y": SCREEN_HEIGHT // 2,
            "p2_y": SCREEN_HEIGHT // 2,
            "bx": SCREEN_WIDTH // 2,
            "by": SCREEN_HEIGHT // 2,
            "bdx": BALL_SPEED,
            "bdy": BALL_SPEED,
            "score": [0, 0]
        }
        self.lock = threading.Lock()
        self.running = True

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 5000))
        s.listen(2)
        print("🟢 Сервер запущен на 0.0.0.0:5000. Ожидание игроков...")

        # Ждём ровно 2 подключения
        c1, addr1 = s.accept()
        self.clients[c1] = {"side": 1, "up": False, "down": False}
        print(f"✅ Игрок 1 подключился: {addr1}")

        c2, addr2 = s.accept()
        self.clients[c2] = {"side": 2, "up": False, "down": False}
        print(f"✅ Игрок 2 подключился: {addr2}")

        # Сообщаем клиентам их сторону
        c1.sendall(json.dumps({"type": "assigned", "side": 1}).encode() + b"\n")
        c2.sendall(json.dumps({"type": "assigned", "side": 2}).encode() + b"\n")
        print("🎮 Игра началась!")

        # Потоки ввода
        for conn in self.clients:
            threading.Thread(target=self.handle_input, args=(conn,), daemon=True).start()

        # Игровой цикл
        dt = 1.0 / TICK_RATE
        last_time = time.time()
        while self.running:
            time.sleep(max(0, dt - (time.time() - last_time)))
            last_time = time.time()
            self.update()
            self.broadcast()

    def handle_input(self, conn):
        buffer = b""
        try:
            while self.running:
                data = conn.recv(256)
                if not data: break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    msg = json.loads(line.decode())
                    if msg["type"] == "input":
                        self.clients[conn]["up"] = msg["action"] == "up"
                        self.clients[conn]["down"] = msg["action"] == "down"
                        if msg["action"] == "stop":
                            self.clients[conn]["up"] = False
                            self.clients[conn]["down"] = False
        except Exception:
            print("⚠️ Клиент отключился")
        self.running = False

    def update(self):
        with self.lock:
            # Движение ракеток
            for conn, info in self.clients.items():
                target = "p1_y" if info["side"] == 1 else "p2_y"
                if info["up"]:
                    self.state[target] = min(SCREEN_HEIGHT - PADDLE_H//2, self.state[target] + PADDLE_SPEED)
                if info["down"]:
                    self.state[target] = max(PADDLE_H//2, self.state[target] - PADDLE_SPEED)

            # Движение мяча
            self.state["bx"] += self.state["bdx"]
            self.state["by"] += self.state["bdy"]

            # Отскок от верха/низа
            if self.state["by"] > SCREEN_HEIGHT - BALL_R or self.state["by"] < BALL_R:
                self.state["bdy"] *= -1

            # Коллизии с ракетками (AABB vs Circle упрощённый)
            if self.state["bx"] - BALL_R <= 40 + PADDLE_W and \
               self.state["by"] >= self.state["p1_y"] - PADDLE_H//2 and self.state["by"] <= self.state["p1_y"] + PADDLE_H//2:
                self.state["bdx"] = abs(self.state["bdx"]) * 1.05
                self.state["bx"] = 40 + PADDLE_W + BALL_R + 1

            if self.state["bx"] + BALL_R >= SCREEN_WIDTH - 40 - PADDLE_W and \
               self.state["by"] >= self.state["p2_y"] - PADDLE_H//2 and self.state["by"] <= self.state["p2_y"] + PADDLE_H//2:
                self.state["bdx"] = -abs(self.state["bdx"]) * 1.05
                self.state["bx"] = SCREEN_WIDTH - 40 - PADDLE_W - BALL_R - 1

            # Голы
            if self.state["bx"] < 0:
                self.state["score"][1] += 1
                self.reset_ball()
            elif self.state["bx"] > SCREEN_WIDTH:
                self.state["score"][0] += 1
                self.reset_ball()

    def reset_ball(self):
        self.state["bx"], self.state["by"] = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        self.state["bdx"] = BALL_SPEED * random.choice([-1, 1])
        self.state["bdy"] = BALL_SPEED * random.choice([-1, 1])

    def broadcast(self):
        payload = (json.dumps(self.state) + "\n").encode()
        for conn in self.clients:
            try:
                conn.sendall(payload)
            except Exception:
                pass

if __name__ == "__main__":
    PongServer().start()