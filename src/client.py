import sys
import arcade
import socket
import threading
import json
import time
from constants import *
from entities import Paddle, Ball


class PongGame(arcade.Window):
    def __init__(self, player_side: int):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        self.background_color = arcade.color.DARK_BLUE_GRAY
        self.score = [0, 0]

        self.paddle1 = Paddle(is_left=True)
        self.paddle2 = Paddle(is_left=False)
        self.ball = Ball()
        self.paddle_list = arcade.SpriteList()
        self.paddle_list.extend([self.paddle1, self.paddle2])

        self.player_side = player_side
        self.assigned_side = None
        self.buffered_state = None
        self.state_lock = threading.Lock()
        self.running = True

        # 🎯 Интерполяция
        self.prev_state = None
        self.last_update_time = 0
        self.interpolation_alpha = 0.0
        self.ball_velocity_x = BALL_SPEED
        self.ball_velocity_y = BALL_SPEED
        self.last_ball_pos = None
        self.predicting_ball = False

        # 🎮 Клиентское предсказание для своей ракетки
        self.local_paddle_target = None  # 1 = вверх, -1 = вниз, 0 = стоп
        self.local_paddle_corrected = False  # Была ли коррекция от сервера

        # 📊 FPS
        self._fps_counter = 0
        self._fps_last_time = time.time()
        self._fps_display = 0

        self.connect_to_server()
        threading.Thread(target=self.receive_loop, daemon=False).start()

    def connect_to_server(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client.settimeout(10)
        try:
            self.client.connect(("193.233.245.251", 5000))
            self.client.settimeout(None)
            print("📡 Подключено к серверу")
        except Exception as e:
            print(f" Ошибка подключения: {e}")
            sys.exit(1)

    def send_input(self, action: str):
        try:
            msg = json.dumps({"type": "input", "action": action}).encode() + b"\n"
            self.client.sendall(msg)
        except Exception:
            pass

    def on_key_press(self, key, _):
        # 🎮 Мгновенная реакция для своей ракетки
        if self.assigned_side == 1:
            if key == arcade.key.W:
                self.local_paddle_target = 1
                self.send_input("up")
            elif key == arcade.key.S:
                self.local_paddle_target = -1
                self.send_input("down")
        elif self.assigned_side == 2:
            if key == arcade.key.UP:
                self.local_paddle_target = 1
                self.send_input("up")
            elif key == arcade.key.DOWN:
                self.local_paddle_target = -1
                self.send_input("down")

    def on_key_release(self, key, _):
        if self.assigned_side == 1 and key in (arcade.key.W, arcade.key.S):
            self.local_paddle_target = 0
            self.send_input("stop")
        elif self.assigned_side == 2 and key in (arcade.key.UP, arcade.key.DOWN):
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
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode())
                        if msg.get("type") == "assigned":
                            self.assigned_side = msg["side"]
                            print(f"🎮 Вы играете за ракетку {self.assigned_side}")
                        else:
                            with self.state_lock:
                                self.prev_state = self.buffered_state
                                self.buffered_state = msg
                                self.last_update_time = time.time()
                                self.interpolation_alpha = 0.0
                    except json.JSONDecodeError:
                        pass
            except Exception:
                break

    def on_update(self, delta_time: float):
        # 📊 FPS counter
        self._fps_counter += 1
        now = time.time()
        if now - self._fps_last_time >= 1.0:
            self._fps_display = self._fps_counter
            self._fps_counter = 0
            self._fps_last_time = now

        # 🎮 Клиентское предсказание: своя ракетка
        if self.local_paddle_target is not None and self.assigned_side is not None:
            my_paddle = self.paddle1 if self.assigned_side == 1 else self.paddle2
            if self.local_paddle_target != 0:
                new_y = my_paddle.center_y + self.local_paddle_target * my_paddle.speed
                my_paddle.center_y = max(PADDLE_HEIGHT // 2, min(SCREEN_HEIGHT - PADDLE_HEIGHT // 2, new_y))
                self.local_paddle_corrected = False

        # 🎾 Предсказание мяча (движется между пакетами)
        if self.predicting_ball and self.last_ball_pos:
            # Двигаем мяч локально пока не придут новые данные
            self.ball.center_x += self.ball_velocity_x * delta_time * 60
            self.ball.center_y += self.ball_velocity_y * delta_time * 60

            # Отскок от стен (локальная физика)
            if self.ball.center_y > SCREEN_HEIGHT - BALL_SIZE or self.ball.center_y < BALL_SIZE:
                self.ball_velocity_y *= -1
                self.ball.center_y = max(BALL_SIZE, min(SCREEN_HEIGHT - BALL_SIZE, self.ball.center_y))

        # 🎯 Интерполяция от сервера
        with self.state_lock:
            if self.buffered_state:
                s = self.buffered_state
                self.score = s.get("score", [0, 0])

                if self.prev_state:
                    # Чужая ракетка
                    if self.assigned_side == 1:
                        self.paddle2.center_y = self._lerp(
                            self.prev_state.get("p2_y", SCREEN_HEIGHT // 2),
                            s.get("p2_y", SCREEN_HEIGHT // 2),
                            min(1.0, self.interpolation_alpha + delta_time * 15)
                        )
                    else:
                        self.paddle1.center_y = self._lerp(
                            self.prev_state.get("p1_y", SCREEN_HEIGHT // 2),
                            s.get("p1_y", SCREEN_HEIGHT // 2),
                            min(1.0, self.interpolation_alpha + delta_time * 15)
                        )

                    # 🎾 Мяч — вычисляем скорость для предсказания
                    prev_bx = self.prev_state.get("bx", s.get("bx", SCREEN_WIDTH // 2))
                    prev_by = self.prev_state.get("by", s.get("by", SCREEN_HEIGHT // 2))
                    curr_bx = s.get("bx", SCREEN_WIDTH // 2)
                    curr_by = s.get("by", SCREEN_HEIGHT // 2)

                    # Вычисляем направление мяча
                    if curr_bx != prev_bx:
                        self.ball_velocity_x = (curr_bx - prev_bx) * 30  # Примерная скорость
                    if curr_by != prev_by:
                        self.ball_velocity_y = (curr_by - prev_by) * 30

                    # Плавная интерполяция мяча
                    self.ball.center_x = self._lerp(prev_bx, curr_bx,
                                                    min(1.0, self.interpolation_alpha + delta_time * 15))
                    self.ball.center_y = self._lerp(prev_by, curr_by,
                                                    min(1.0, self.interpolation_alpha + delta_time * 15))

                    # Включаем предсказание
                    self.predicting_ball = True
                    self.last_ball_pos = (curr_bx, curr_by)
                else:
                    # Первый кадр
                    if self.assigned_side == 1:
                        self.paddle2.center_y = s.get("p2_y", SCREEN_HEIGHT // 2)
                    else:
                        self.paddle1.center_y = s.get("p1_y", SCREEN_HEIGHT // 2)
                    self.ball.center_x = s.get("bx", SCREEN_WIDTH // 2)
                    self.ball.center_y = s.get("by", SCREEN_HEIGHT // 2)
                    self.ball_velocity_x = s.get("bdx", BALL_SPEED)
                    self.ball_velocity_y = s.get("bdy", BALL_SPEED)
                    self.predicting_ball = True

                # Сброс интерполяции при новом пакете
                self.interpolation_alpha = 0.0

                # Коррекция своей ракетки
                if not self.local_paddle_corrected and self.assigned_side is not None:
                    my_key = "p1_y" if self.assigned_side == 1 else "p2_y"
                    server_y = s.get(my_key)
                    my_paddle = self.paddle1 if self.assigned_side == 1 else self.paddle2
                    if server_y is not None and abs(my_paddle.center_y - server_y) > 10:
                        my_paddle.center_y = self._lerp(my_paddle.center_y, server_y, 0.1)

    def _lerp(self, start, end, alpha):
        """Линейная интерполяция с защитой от float-ошибок"""
        result = start + (end - start) * alpha
        # Если alpha ~1.0, возвращаем точное end (чтобы ракетка доходила до края)
        if alpha >= 0.99:
            return end
        return result

    def on_draw(self):
        self.clear()
        arcade.draw_line(SCREEN_WIDTH / 2, 0, SCREEN_WIDTH / 2, SCREEN_HEIGHT,
                         arcade.color.GRAY, line_width=4)

        arcade.draw_text(
            f"{self.score[0]} : {self.score[1]}",
            SCREEN_WIDTH / 2, SCREEN_HEIGHT - 50,
            arcade.color.WHITE, 36, anchor_x="center", anchor_y="center"
        )

        self.paddle_list.draw()
        arcade.draw_sprite(self.ball)

        # 📊 FPS
        arcade.draw_text(f"FPS: {self._fps_display}", 10, 10, arcade.color.WHITE, 12)

    def on_close(self):
        self.running = False
        try:
            self.client.close()
        except:
            pass
        super().on_close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("1", "2"):
        print("Использование: python client.py 1  (или 2)")
        sys.exit(1)
    game = PongGame(player_side=int(sys.argv[1]))
    arcade.run()