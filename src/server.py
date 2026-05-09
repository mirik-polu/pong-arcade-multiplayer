import socket
import threading
import json
import time
import random
import traceback

SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
PADDLE_W, PADDLE_H = 20, 100
BALL_R = 10
PADDLE_SPEED = 5
BALL_SPEED = 5
TICK_RATE = 120

class PongServer:
    def __init__(self):
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.state = {
            "p1_y": SCREEN_HEIGHT // 2, "p2_y": SCREEN_HEIGHT // 2,
            "bx": SCREEN_WIDTH // 2, "by": SCREEN_HEIGHT // 2,
            "bdx": BALL_SPEED, "bdy": BALL_SPEED,
            "score": [0, 0]
        }
        self.state_lock = threading.Lock()
        self.running = True

    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 5000))
        s.listen(5)
        print("🟢 Сервер запущен на 0.0.0.0:5000. Ожидание игроков...")

        try:
            c1, _ = s.accept()
            with self.clients_lock: self.clients[c1] = {"side": 1, "up": False, "down": False}
            print("✅ Игрок 1 подключился")

            c2, _ = s.accept()
            with self.clients_lock: self.clients[c2] = {"side": 2, "up": False, "down": False}
            print("✅ Игрок 2 подключился")

            c1.sendall(json.dumps({"type": "assigned", "side": 1}).encode() + b"\n")
            c2.sendall(json.dumps({"type": "assigned", "side": 2}).encode() + b"\n")
            print("🎮 Игра началась!")

            for conn in list(self.clients.keys()):
                threading.Thread(target=self.handle_input, args=(conn,), daemon=True).start()

            dt = 1.0 / TICK_RATE
            last_time = time.time()
            while self.running:
                time.sleep(max(0, dt - (time.time() - last_time)))
                last_time = time.time()
                self.update()
                self.broadcast()
        except Exception as e:
            print(f"❌ Сервер упал: {e}")
            traceback.print_exc()
        finally:
            self.running = False
            print("🔴 Сервер остановлен.")

    def handle_input(self, conn):
        buffer = b""
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:  # ✅ ИСПРАВЛЕНО: было "if not   #"
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode())
                        if msg.get("type") == "input":
                            action = msg.get("action")
                            with self.clients_lock:
                                if conn in self.clients:
                                    self.clients[conn]["up"] = action == "up"
                                    self.clients[conn]["down"] = action == "down"
                                    if action == "stop":
                                        self.clients[conn]["up"] = False
                                        self.clients[conn]["down"] = False
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            with self.clients_lock:
                self.clients.pop(conn, None)
                print(f"🔌 Клиент отключился. Осталось: {len(self.clients)}")
                if not self.clients:
                    self.running = False

    def update(self):
        with self.clients_lock:
            for conn, info in self.clients.items():
                target = "p1_y" if info["side"] == 1 else "p2_y"
                if info["up"]:
                    self.state[target] = min(SCREEN_HEIGHT - PADDLE_H//2, self.state[target] + PADDLE_SPEED)
                if info["down"]:
                    self.state[target] = max(PADDLE_H//2, self.state[target] - PADDLE_SPEED)

        with self.state_lock:
            self.state["bx"] += self.state["bdx"]
            self.state["by"] += self.state["bdy"]

            if self.state["by"] > SCREEN_HEIGHT - BALL_R or self.state["by"] < BALL_R:
                self.state["bdy"] *= -1

            if self.state["bx"] - BALL_R <= 40 + PADDLE_W and \
               self.state["p1_y"] - PADDLE_H//2 <= self.state["by"] <= self.state["p1_y"] + PADDLE_H//2:
                self.state["bdx"] = abs(self.state["bdx"]) * 1.05
                self.state["bx"] = 40 + PADDLE_W + BALL_R + 1

            if self.state["bx"] + BALL_R >= SCREEN_WIDTH - 40 - PADDLE_W and \
               self.state["p2_y"] - PADDLE_H//2 <= self.state["by"] <= self.state["p2_y"] + PADDLE_H//2:
                self.state["bdx"] = -abs(self.state["bdx"]) * 1.05
                self.state["bx"] = SCREEN_WIDTH - 40 - PADDLE_W - BALL_R - 1

            if self.state["bx"] < 0:
                self.state["score"][1] += 1
                self._reset_ball()
            elif self.state["bx"] > SCREEN_WIDTH:
                self.state["score"][0] += 1
                self._reset_ball()

    def _reset_ball(self):
        self.state["bx"], self.state["by"] = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        self.state["bdx"] = BALL_SPEED * random.choice([-1, 1])
        self.state["bdy"] = BALL_SPEED * random.choice([-1, 1])

    def broadcast(self):
        with self.state_lock:
            payload = (json.dumps(self.state) + "\n").encode()
        with self.clients_lock:
            conns = list(self.clients.keys())
        for conn in conns:
            try:
                conn.sendall(payload)
            except Exception:
                pass

if __name__ == "__main__":
    PongServer().start()