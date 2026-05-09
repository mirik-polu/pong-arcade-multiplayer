import socket
import threading
import json
import time
import random
import traceback
import sys
from constants import *

class PongServer:
    def __init__(self):
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.state = {
            "p1_y": SCREEN_HEIGHT // 2,
            "p2_y": SCREEN_HEIGHT // 2,
            "bx": SCREEN_WIDTH // 2,
            "by": SCREEN_HEIGHT // 2,
            "bdx": BALL_SPEED * random.choice([-1, 1]),
            "bdy": BALL_SPEED * random.choice([-1, 1]),
            "score": [0, 0],
        }
        self.state_lock = threading.Lock()
        self.running = True
        self.tick_count = 0

    def start(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # 🔥 Отключаем Nagle
        server_sock.bind(("0.0.0.0", SERVER_PORT))
        server_sock.listen(5)
        server_sock.settimeout(1.0)  # Для возможности остановки
        print(f"🟢 Сервер запущен на 0.0.0.0:{SERVER_PORT}. Ожидание игроков...")

        try:
            # Принимаем двух игроков с таймаутом
            c1, addr1 = self._accept_with_timeout(server_sock, 30)
            with self.clients_lock:
                self.clients[c1] = {"side": 1, "up": False, "down": False}
            print(f"✅ Игрок 1 подключился: {addr1}")

            c2, addr2 = self._accept_with_timeout(server_sock, 30)
            with self.clients_lock:
                self.clients[c2] = {"side": 2, "up": False, "down": False}
            print(f"✅ Игрок 2 подключился: {addr2}")

            # Назначаем стороны
            c1.sendall(json.dumps({"type": "assigned", "side": 1}).encode() + b"\n")
            c2.sendall(json.dumps({"type": "assigned", "side": 2}).encode() + b"\n")
            print("🎮 Игра началась!")

            # Запускаем потоки ввода
            for conn in list(self.clients.keys()):
                threading.Thread(target=self.handle_input, args=(conn,), daemon=True).start()

            # Главный игровой цикл
            self.game_loop()

        except KeyboardInterrupt:
            print("\n⚠️  Остановка по запросу пользователя")
        except Exception as e:
            print(f"❌ Сервер упал: {e}")
            traceback.print_exc()
        finally:
            self.shutdown(server_sock)

    def _accept_with_timeout(self, sock, timeout_sec):
        start = time.time()
        while time.time() - start < timeout_sec and self.running:
            try:
                return sock.accept()
            except socket.timeout:
                continue
        raise TimeoutError("Не удалось принять подключение за отведённое время")

    def game_loop(self):
        dt = 1.0 / TICK_RATE
        while self.running:
            frame_start = time.perf_counter()  # 🔥 Точный таймер

            self.update()
            self.broadcast()

            elapsed = time.perf_counter() - frame_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            self.tick_count += 1
            if self.tick_count % 60 == 0:  # Логи раз в секунду
                with self.state_lock:
                    print(f"📊 Tick #{self.tick_count} | Score: {self.state['score']} | Ball: ({self.state['bx']:.1f}, {self.state['by']:.1f})")

    def handle_input(self, conn):
        buffer = b""
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer and self.running:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode())
                        if msg.get("type") == "input":
                            action = msg.get("action")
                            with self.clients_lock:
                                if conn in self.clients:
                                    if action == "stop":
                                        self.clients[conn]["up"] = False
                                        self.clients[conn]["down"] = False
                                    else:
                                        self.clients[conn]["up"] = action == "up"
                                        self.clients[conn]["down"] = action == "down"
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        finally:
            with self.clients_lock:
                self.clients.pop(conn, None)
                print(f"🔌 Клиент отключился. Осталось: {len(self.clients)}")
                if len(self.clients) < 2:
                    print("⚠️  Недостаточно игроков. Остановка сервера.")
                    self.running = False

    def update(self):
        # Обновляем позиции ракеток
        with self.clients_lock:
            for conn, info in self.clients.items():
                target = "p1_y" if info["side"] == 1 else "p2_y"
                current = self.state[target]
                if info["up"]:
                    current = min(SCREEN_HEIGHT - PADDLE_HEIGHT // 2, current + PADDLE_SPEED)
                if info["down"]:
                    current = max(PADDLE_HEIGHT // 2, current - PADDLE_SPEED)
                self.state[target] = current

        # Физика мяча
        with self.state_lock:
            self.state["bx"] += self.state["bdx"]
            self.state["by"] += self.state["bdy"]

            # Отскок от верхней/нижней границы
            if self.state["by"] - BALL_SIZE < 0 or self.state["by"] + BALL_SIZE > SCREEN_HEIGHT:
                self.state["bdy"] *= -1
                # Корректируем позицию, чтобы не застревал
                self.state["by"] = max(BALL_SIZE, min(SCREEN_HEIGHT - BALL_SIZE, self.state["by"]))

            # Коллизия с левой ракеткой
            if (self.state["bx"] - BALL_SIZE <= 40 + PADDLE_WIDTH and
                self.state["p1_y"] - PADDLE_HEIGHT // 2 <= self.state["by"] <= self.state["p1_y"] + PADDLE_HEIGHT // 2 and
                self.state["bdx"] < 0):
                self._bounce_off_paddle(1)

            # Коллизия с правой ракеткой
            if (self.state["bx"] + BALL_SIZE >= SCREEN_WIDTH - 40 - PADDLE_WIDTH and
                self.state["p2_y"] - PADDLE_HEIGHT // 2 <= self.state["by"] <= self.state["p2_y"] + PADDLE_HEIGHT // 2 and
                self.state["bdx"] > 0):
                self._bounce_off_paddle(2)

            # ✅ Фикс бага с очками: проверяем КРАЯ мяча, а не центр
            if self.state["bx"] - BALL_SIZE < 0:
                self.state["score"][1] += 1
                print(f"🎯 Очко игроку 2! Счёт: {self.state['score']}")
                self._reset_ball()
            elif self.state["bx"] + BALL_SIZE > SCREEN_WIDTH:
                self.state["score"][0] += 1
                print(f"🎯 Очко игроку 1! Счёт: {self.state['score']}")
                self._reset_ball()

    def _bounce_off_paddle(self, player_side):
        """Отскок от ракетки с ускорением и углом"""
        self.state["bdx"] = -self.state["bdx"]
        # Ускоряем, но не больше максимума
        new_speed = min(BALL_SPEED, abs(self.state["bdx"]) * 1.03)
        self.state["bdx"] = new_speed * (1 if self.state["bdx"] > 0 else -1)
        # Добавляем угол в зависимости от точки удара
        paddle_y = self.state["p1_y"] if player_side == 1 else self.state["p2_y"]
        hit_offset = (self.state["by"] - paddle_y) / (PADDLE_HEIGHT / 2)
        self.state["bdy"] += hit_offset * 1.5
        # Нормализуем общую скорость
        current_speed = (self.state["bdx"]**2 + self.state["bdy"]**2)**0.5
        if current_speed > 0:
            factor = min(BALL_SPEED, max(BALL_SPEED, current_speed)) / current_speed
            self.state["bdx"] *= factor
            self.state["bdy"] *= factor
        # Сдвигаем мяч, чтобы не застревал в ракетке
        if player_side == 1:
            self.state["bx"] = 40 + PADDLE_WIDTH + BALL_SIZE + 1
        else:
            self.state["bx"] = SCREEN_WIDTH - 40 - PADDLE_WIDTH - BALL_SIZE - 1

    def _reset_ball(self):
        self.state["bx"], self.state["by"] = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        angle = random.uniform(-0.7, 0.7)  # Случайный угол
        direction = random.choice([-1, 1])
        self.state["bdx"] = BALL_SPEED * direction
        self.state["bdy"] = BALL_SPEED * angle

    def broadcast(self):
        with self.state_lock:
            # 🔥 Добавляем таймстамп и номер тика для отладки
            payload = json.dumps({
                **self.state,
                "server_time": time.time(),
                "tick": self.tick_count
            }) + "\n"
            data = payload.encode()

        with self.clients_lock:
            conns = list(self.clients.keys())

        for conn in conns:
            try:
                conn.sendall(data)
            except (BrokenPipeError, ConnectionResetError, OSError):
                with self.clients_lock:
                    self.clients.pop(conn, None)

    def shutdown(self, server_sock):
        self.running = False
        with self.clients_lock:
            for conn in list(self.clients.keys()):
                try:
                    conn.close()
                except:
                    pass
            self.clients.clear()
        try:
            server_sock.close()
        except:
            pass
        print("🔴 Сервер остановлен.")

if __name__ == "__main__":
    print("🚀 Запуск сервера Pong...")
    PongServer().start()