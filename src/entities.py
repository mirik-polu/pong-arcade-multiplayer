"""
entities.py - Игровые объекты для Pong (Arcade 3.3.3)
✅ Использует встроенные ресурсы как фоллбэк
"""
import arcade
import os
import random
from constants import *


class Paddle(arcade.Sprite):
    """Ракетка игрока."""

    def __init__(self, is_left: bool):
        texture_name = "paddle_left.png" if is_left else "paddle_right.png"
        texture_path = os.path.join(ASSETS_DIR, texture_name)

        # Загружаем текстуру: файл → встроенный ресурс → минимальная заглушка
        if os.path.exists(texture_path):
            texture = arcade.load_texture(texture_path)
        else:
            # Встроенный ресурс Arcade (гарантированно существует)
            texture = arcade.load_texture(":resources:images/tiles/boxCrate_double.png")

        # ✅ Корректная инициализация спрайта
        super().__init__(texture, scale=1.0)

        # Настраиваем размеры под ракетку
        self.width = PADDLE_WIDTH
        self.height = PADDLE_HEIGHT
        self.center_x = 50 if is_left else SCREEN_WIDTH - 50
        self.center_y = SCREEN_HEIGHT / 2
        self.speed = PADDLE_SPEED
        # Перекрашиваем встроенную текстуру в нужный цвет
        self.color = arcade.color.BLUE if is_left else arcade.color.RED

    def move_to(self, target_y: float):
        self.center_y = max(self.height / 2, min(SCREEN_HEIGHT - self.height / 2, target_y))


class Ball(arcade.Sprite):
    """Мяч для пинг-понга."""

    def __init__(self):
        texture_path = os.path.join(ASSETS_DIR, "ball.png")

        if os.path.exists(texture_path):
            texture = arcade.load_texture(texture_path)
        else:
            # Встроенный ресурс: монета как заглушка для мяча
            texture = arcade.load_texture(":resources:images/items/coinGold.png")

        super().__init__(texture, scale=1.0)
        self.width = BALL_SIZE
        self.height = BALL_SIZE
        self.color = arcade.color.WHITE  # Перекрашиваем в белый

        self.reset()

    def reset(self):
        self.center_x = SCREEN_WIDTH / 2
        self.center_y = SCREEN_HEIGHT / 2
        dir_x = 1 if random.random() > 0.5 else -1
        dir_y = (random.random() * 2 - 1) * 0.5
        self.change_x = dir_x * BALL_SPEED
        self.change_y = dir_y * BALL_SPEED

    def update(self, delta_time: float):
        self.center_x += self.change_x * delta_time * 60
        self.center_y += self.change_y * delta_time * 60