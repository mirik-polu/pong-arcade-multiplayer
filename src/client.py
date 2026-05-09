# client.py
import sys
import time
import socket
import threading
import json
import arcade
from constants import *
from entities import Paddle, Ball

class PongGame(arcade.Window):
    def __init__(self, player_side: int):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, "🏓 Online Pong")
        self.background_color = arcade.color.DARK_BLUE_GRAY
        self.score = [0, 0]

        self.paddle1 = Paddle(is_left=True)
        self.paddle2 = Paddle(is_left=False)
        self.ball = Ball()
        self.paddle_list = arcade.SpriteList()
        self.paddle_list.extend([self.paddle1, self.paddle2])

        self.player_side = player_side
        self.assigned_side = None

        # 🔐 Состояние с сервера
        self.buffered_state = None
        self.prev_state = None
        self.state_lock = threading.Lock()

        # 🎯 Интерполяция
        self.interpolation_alpha = 1.0  # Начинаем с 1.0, чтобы сразу показать актуальное
        self.last_packet_time = 0

        # 🎮 Клиентское предсказание
        self.local_paddle_target = 0  # 1 = вверх, -1 = вниз, 0 = стоп
        self.last_sent_input = None

        # 🎾 Предсказание мяча
        self.ball_velocity_x = BALL_SPEED
        self.ball_velocity_y = BALL_SPEED
        self.predicting_ball = False

        # 📊 FPS
        self._fps_counter = 0
        self._fps_last_time = time.time()
        self._fps_display = 0

        self.running = True
        self.client = None

        self.connect_to_server()
        threading.Thread(target=self.receive_loop, daemon=True).start()

    def connect_to_server(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # 🔥 Отключаем Nagle
        self.client.settimeout(10)
        try:
            self.client.connect((SERVER_IP, SERVER_PORT))
            self.client.settimeout(None)  # Блокирующий режим после подключения
            print(f"📡 Подключено к {SERVER_IP}:{SERVER_PORT}")
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            arcade.close_window()
            sys.exit(1)

    def send_input(self, action: str):
        if action == self.last_sent_input:
            return  # Не спамим одинаковыми действиями
        try:
            msg = json.dumps({"type": "input", "action": action}).encode() + b"\n"
            self.client.sendall(msg)
            self.last_sent_input = action
        except (BrokenPipeError, ConnectionResetError, OSError):
            print("⚠️  Потеряно соединение при отправке")
            self.running = False

    def on_key_press(self, key, _):
        if self.assigned_side is None:
            return
        if (self.assigned_side == 1 and key == arcade.key.W) or \
           (self.assigned_side == 2 and key == arcade.key.UP):
            self.local_paddle_target = 1
            self.send_input("up")
        elif (self.assigned_side == 1 and key == arcade.key.S) or \
             (self.assigned_side == 2 and key == arcade.key.DOWN):
            self.local_paddle_target = -1
            self.send_input("down")

    def on_key_release(self, key, _):
        if self.assigned_side is None:
            return
        if (self.assigned_side == 1 and key in (arcade.key.W, arcade.key.S)) or \
           (self.assigned_side == 2 and key in (arcade.key.UP, arcade.key.DOWN)):
            self.local_paddle_target = 0
            self.send_input("stop")

    def receive_loop(self):
        buffer = b""
        while self.running:
            try:
                data = self.client.recv(4096)
                if not data:
                    break
                buffer += data
                while b"\n" in buffer and self.running:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode())
                        if msg.get("type") == "assigned":
                            self.assigned_side = msg["side"]
                            print(f"🎮 Вы играете за ракетку {self.assigned_side}")
                        else:
                            with self.state_lock:
                                self.prev_state = self.buffered_state
                                self.buffered_state = msg
                                self.last_packet_time = time.time()
                                # 🔥 НЕ сбрасываем alpha — продолжаем интерполяцию
                    except json.JSONDecodeError:
                        continue
            except (ConnectionResetError, BrokenPipeError, OSError):
                print("⚠️  Соединение разорвано")
                break
            except Exception as e:
                print(f"❌ Ошибка в receive_loop: {e}")
                break
        self.running = False
        arcade.schedule_once(lambda dt: arcade.close_window(), 0.1)

    def on_update(self, delta_time: float):
        # 📊 FPS counter
        self._fps_counter += 1
        now = time.time()
        if now - self._fps_last_time >= 1.0:
            self._fps_display = self._fps_counter
            self._fps_counter = 0
            self._fps_last_time = now

        # 🎮 Клиентское предсказание: своя ракетка
        if self.assigned_side is not None and self.local_paddle_target != 0:
            my_paddle = self.paddle1 if self.assigned_side == 1 else self.paddle2
            new_y = my_paddle.center_y + self.local_paddle_target * my_paddle.speed * delta_time * 60
            my_paddle.center_y = max(PADDLE_HEIGHT // 2, min(SCREEN_HEIGHT - PADDLE_HEIGHT // 2, new_y))

        # 🎾 Предсказание мяча между пакетами
        if self.predicting_ball:
            self.ball.center_x += self.ball_velocity_x * delta_time * 60
            self.ball.center_y += self.ball_velocity_y * delta_time * 60
            # Локальные отскоки от стен (для плавности)
            if self.ball.center_y - BALL_SIZE < 0 or self.ball.center_y + BALL_SIZE > SCREEN_HEIGHT:
                self.ball_velocity_y *= -1
                self.ball.center_y = max(BALL_SIZE, min(SCREEN_HEIGHT - BALL_SIZE, self.ball.center_y))

        # 🎯 Интерполяция от сервера
        with self.state_lock:
            if self.buffered_state:
                s = self.buffered_state
                self.score = s.get("score", [0, 0])

                if self.prev_state and self.interpolation_alpha < 1.0:
                    # 🔥 Плавно увеличиваем alpha
                    self.interpolation_alpha = min(1.0, self.interpolation_alpha + delta_time * INTERPOLATION_SPEED)
                    alpha = self.interpolation_alpha

                    # Чужая ракетка
                    if self.assigned_side == 1:
                        self.paddle2.center_y = self._lerp(self.prev_state.get("p2_y"), s.get("p2_y"), alpha)
                    else:
                        self.paddle1.center_y = self._lerp(self.prev_state.get("p1_y"), s.get("p1_y"), alpha)

                    # 🎾 Мяч: интерполяция + берём скорость с сервера
                    prev_bx = self.prev_state.get("bx", s.get("bx"))
                    prev_by = self.prev_state.get("by", s.get("by"))
                    curr_bx = s.get("bx")
                    curr_by = s.get("by")

                    self.ball.center_x = self._lerp(prev_bx, curr_bx, alpha)
                    self.ball.center_y = self._lerp(prev_by, curr_by, alpha)

                    # 🔥 Берём скорость напрямую с сервера для предсказания
                    if "bdx" in s and "bdy" in s:
                        self.ball_velocity_x = s["bdx"]
                        self.ball_velocity_y = s["bdy"]
                    self.predicting_ball = True

                elif not self.prev_state:
                    # Первый кадр — сразу показываем актуальное
                    if self.assigned_side == 1:
                        self.paddle2.center_y = s.get("p2_y", SCREEN_HEIGHT // 2)
                    else:
                        self.paddle1.center_y = s.get("p1_y", SCREEN_HEIGHT // 2)
                    self.ball.center_x = s.get("bx", SCREEN_WIDTH // 2)
                    self.ball.center_y = s.get("by", SCREEN_HEIGHT // 2)
                    self.ball_velocity_x = s.get("bdx", BALL_SPEED)
                    self.ball_velocity_y = s.get("bdy", BALL_SPEED)
                    self.predicting_ball = True
                    self.interpolation_alpha = 1.0
                    self.prev_state = s  # Инициализируем prev для следующего кадра

                # 🔥 Мягкая коррекция своей ракетки (без рэбербэндинга)
                if self.assigned_side is not None:
                    my_key = "p1_y" if self.assigned_side == 1 else "p2_y"
                    server_y = s.get(my_key)
                    my_paddle = self.paddle1 if self.assigned_side == 1 else self.paddle2
                    if server_y is not None:
                        # Всегда немного тянем к серверному значению
                        my_paddle.center_y = self._lerp(my_paddle.center_y, server_y, PADDLE_CORRECTION_FACTOR)

    def _lerp(self, start, end, alpha):
        """Безопасная линейная интерполяция"""
        if start is None or end is None:
            return end if end is not None else start
        if alpha >= 0.99:
            return end
        return start + (end - start) * alpha

    def on_draw(self):
        self.clear()
        # Сетка
        arcade.draw_line(SCREEN_WIDTH / 2, 0, SCREEN_WIDTH / 2, SCREEN_HEIGHT,
                         arcade.color.GRAY, line_width=4)
        # Счёт
        arcade.draw_text(f"{self.score[0]} : {self.score[1]}",
                         SCREEN_WIDTH / 2, SCREEN_HEIGHT - 50,
                         arcade.color.WHITE, 36, anchor_x="center")
        # Ракетки и мяч
        self.paddle_list.draw()
        arcade.draw_sprite(self.ball)
        # Статус
        if self.assigned_side is None:
            arcade.draw_text("⏳ Ожидание назначения...", SCREEN_WIDTH/2, SCREEN_HEIGHT/2,
                             arcade.color.YELLOW, 18, anchor_x="center")
        # FPS
        arcade.draw_text(f"FPS: {self._fps_display}", 10, 10, arcade.color.WHITE, 12)

    def on_close(self):
        self.running = False
        if self.client:
            try:
                self.client.close()
            except:
                pass
        super().on_close()

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("1", "2"):
        print("Использование: python client.py 1  (или 2)")
        sys.exit(1)
    print(f"🚀 Запуск клиента (сторона {sys.argv[1]})...")
    game = PongGame(player_side=int(sys.argv[1]))
    arcade.run()