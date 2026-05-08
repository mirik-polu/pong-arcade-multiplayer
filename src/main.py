import arcade
from src.game import PongGame

def main():
    arcade.set_background_color(arcade.color.DARK_BLUE_GRAY)
    window = PongGame()
    arcade.run()

if __name__ == "__main__":
    main()
