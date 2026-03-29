import random

import pygame

from src.config import HEIGHT, WIDTH


class Food:
    def __init__(self):
        self.x = random.randint(10, WIDTH - 10)
        self.y = random.randint(10, HEIGHT - 10)
        self.radius = 3
        self.color = (50, 200, 50)
        self.energy_value = 40

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)
