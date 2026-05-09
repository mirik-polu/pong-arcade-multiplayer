import arcade
from constants import *

class Paddle(arcade.SpriteSolidColor):
    def __init__(self, is_left: bool):
        super().__init__(PADDLE_WIDTH, PADDLE_HEIGHT, arcade.color.WHITE)
        self.center_x = 40 + PADDLE_WIDTH if is_left else SCREEN_WIDTH - 40 - PADDLE_WIDTH
        self.center_y = SCREEN_HEIGHT // 2
        self.speed = PADDLE_SPEED
        self.is_left = is_left

class Ball(arcade.SpriteSolidColor):
    def __init__(self):
        super().__init__(BALL_SIZE * 2, BALL_SIZE * 2, arcade.color.ORANGE)
        self.center_x = SCREEN_WIDTH // 2
        self.center_y = SCREEN_HEIGHT // 2