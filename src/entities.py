import arcade
import os
from src.constants import *

class Paddle(arcade.Sprite):
    def __init__(self, is_left: bool):
        # Пытаемся загрузить текстуру, иначе генерируем заглушку
        texture_path = os.path.join(ASSETS_DIR, "paddle_left.png" if is_left else "paddle_right.png")
        if os.path.exists(texture_path):
            texture = arcade.load_texture(texture_path)
            super().__init__(texture, scale=1.0)
        else:
            super().__init__(arcade.SpriteSolidColor(PADDLE_WIDTH, PADDLE_HEIGHT,
                                                     arcade.color.BLUE if is_left else arcade.color.RED))

        self.center_x = 50 if is_left else SCREEN_WIDTH - 50
        self.center_y = SCREEN_HEIGHT / 2
        self.speed = PADDLE_SPEED

    def move_to(self, target_y: float):
        """Универсальный метод: принимает целевой Y (локальный ввод или сетевой пакет)"""
        self.center_y = target_y
        self.center_y = max(self.height / 2, min(SCREEN_HEIGHT - self.height / 2, self.center_y))


class Ball(arcade.Sprite):
    def __init__(self):
        texture_path = os.path.join(ASSETS_DIR, "ball.png")
        if os.path.exists(texture_path):
            texture = arcade.load_texture(texture_path)
            super().__init__(texture, scale=1.0)
        else:
            super().__init__(arcade.SpriteSolidColor(BALL_SIZE, BALL_SIZE, arcade.color.WHITE))

        self.reset()

    def reset(self):
        self.center_x = SCREEN_WIDTH / 2
        self.center_y = SCREEN_HEIGHT / 2
        dir_x = 1 if arcade.get_window().random.random() > 0.5 else -1
        dir_y = (arcade.get_window().random.random() * 2 - 1) * 0.5
        self.change_x = dir_x * BALL_SPEED
        self.change_y = dir_y * BALL_SPEED

    def update(self, delta_time: float):
        self.center_x += self.change_x * delta_time * 60
        self.center_y += self.change_y * delta_time * 60