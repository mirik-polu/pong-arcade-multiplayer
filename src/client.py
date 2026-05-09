import sys
import arcade
import socket
import threading
import json
import traceback
import warnings
from constants import *
from entities import Paddle, Ball

# Безопасное подавление ворнинга (не упадёт ни в одной версии)
try:
    warnings.filterwarnings("ignore", category=arcade.exceptions.PerformanceWarning)
except AttributeError:
    pass

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
        if self.assigned_side == 1 and key == arcade.key.W: self.send_input("up")
        elif self.assigned_side == 1 and key == arcade.key.S: self.send_input("down")
        elif self.assigned_side == 2 and key == arcade.key.UP: self.send_input("up")
        elif self.assigned_side == 2 and key == arcade.key.DOWN: self.send_input("down")

    def on_key_release(self, key, _):
        if self.assigned_side == 1 and key in (arcade.key.W, arcade.key.S): self.send_input("stop")
        elif self.assigned_side == 2 and key in (arcade.key.UP, arcade.key.DOWN): self.send_input("stop")

    def receive_loop(self):
        buffer = b""
        while self.running:
            try:
                data = self.client.recv(4096)
                if not data:
                    print("⚠️ Сервер закрыл соединение (получены пустые данные)")
                    break
                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode())
                        if msg["type"] == "assigned":
                            self.assigned_side = msg["side"]
                            print(f"🎮 Вы играете за ракетку {self.assigned_side}")
                        else:
                            with self.state_lock:
                                self.buffered_state = msg
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                # 🔍 ПОКАЖЕТ ТОЧНУЮ ПРИЧИНУ РАЗРЫВА
                print(f"⚠️ Потеряно соединение с сервером: {e}")
                break

    def on_update(self, delta_time: float):
        try:
            if self.buffered_state:
                with self.state_lock:
                    s = self.buffered_state
                    self.score = s.get("score", [0, 0])
                    self.paddle1.center_y = s.get("p1_y", SCREEN_HEIGHT//2)
                    self.paddle2.center_y = s.get("p2_y", SCREEN_HEIGHT//2)
                    self.ball.center_x = s.get("bx", SCREEN_WIDTH//2)
                    self.ball.center_y = s.get("by", SCREEN_HEIGHT//2)
        except Exception as e:
            print(f"🔴 Ошибка в on_update: {e}")

    def on_draw(self):
        try:
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
        except Exception as e:
            print(f"🔴 Ошибка в on_draw: {e}")
            traceback.print_exc()

    def on_close(self):
        self.running = False
        try:
            self.client.close()
        except Exception:
            pass
        super().on_close()

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("1", "2"):
        print("Использование: python client.py 1  (или 2)")
        sys.exit(1)
    game = PongGame(player_side=int(sys.argv[1]))
    arcade.run()