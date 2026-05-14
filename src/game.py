import arcade
from src.constants import *
from src.entities import Paddle, Ball


class PongGame(arcade.Window):
    def __init__(self):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        self.background_color = arcade.color.DARK_BLUE_GRAY

        self.score = [0, 0]
        self.keys = set()

        self.paddle1 = Paddle(is_left=True)
        self.paddle2 = Paddle(is_left=False)
        self.ball = Ball()

        self.paddle_list = arcade.SpriteList()
        self.paddle_list.extend([self.paddle1, self.paddle2])

        # 🌐 TODO для коллеги: сюда будут падать сетевые пакеты
        self.network_inputs = {"paddle1_y": None, "paddle2_y": None}

    def on_key_press(self, key, _):
        self.keys.add(key)

    def on_key_release(self, key, _):
        self.keys.discard(key)

    def apply_input(self):
        if arcade.key.W in self.keys:
            self.paddle1.move_to(self.paddle1.center_y + self.paddle1.speed)
        if arcade.key.S in self.keys:
            self.paddle1.move_to(self.paddle1.center_y - self.paddle1.speed)
        if arcade.key.UP in self.keys:
            self.paddle2.move_to(self.paddle2.center_y + self.paddle2.speed)
        if arcade.key.DOWN in self.keys:
            self.paddle2.move_to(self.paddle2.center_y - self.paddle2.speed)

    def update_physics(self):
        # Отскок от верха/низа
        if self.ball.top > SCREEN_HEIGHT or self.ball.bottom < 0:
            self.ball.change_y *= -1

        # Отскок от ракеток
        collisions = arcade.check_for_collision_with_list(self.ball, self.paddle_list)
        if collisions:
            self.ball.change_x *= -1.05
            if collisions[0] == self.paddle1:
                self.ball.left = self.paddle1.right + 1
            else:
                self.ball.right = self.paddle2.left - 1

        # Гол
        if self.ball.right < 0:
            self.score[1] += 1
            self.ball.reset()
        elif self.ball.left > SCREEN_WIDTH:
            self.score[0] += 1
            self.ball.reset()

    def on_update(self, delta_time: float):
        self.apply_input()
        self.ball.update(delta_time)
        self.update_physics()

    def on_draw(self):
        self.clear()

        # Центральная линия
        arcade.draw_line(SCREEN_WIDTH / 2, 0, SCREEN_WIDTH / 2, SCREEN_HEIGHT,
                         arcade.color.GRAY, line_width=4)

        # Счёт
        arcade.draw_text(
            f"{self.score[0]} : {self.score[1]}",
            SCREEN_WIDTH / 2, SCREEN_HEIGHT - 50,
            arcade.color.WHITE, 36,
            anchor_x="center", anchor_y="center"
        )

        self.paddle_list.draw()

        arcade.draw_sprite(self.ball)
