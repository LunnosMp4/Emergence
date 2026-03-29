import random

import pygame

from src.config import (
    CROP_GROWTH_FRAME_MS,
    FOOD_COLLISION_RADIUS,
    FOOD_MIN_SPRITE_SIZE_PX,
    FOOD_SPRITE_SCALE,
    HEIGHT,
    WIDTH,
)


class Food:
    sprite_variants = []
    sprite_cache = {}

    @classmethod
    def set_sprite_variants(cls, variants):
        cls.sprite_variants = [frames for frames in variants if frames]
        cls.sprite_cache = {}

    @classmethod
    def set_sprite_frames(cls, frames):
        cls.set_sprite_variants([frames] if frames else [])

    def __init__(self):
        self.x = random.randint(10, WIDTH - 10)
        self.y = random.randint(10, HEIGHT - 10)
        self.radius = FOOD_COLLISION_RADIUS
        self.color = (50, 200, 50)
        self.energy_value = 40
        self.spawn_time_ms = pygame.time.get_ticks()
        self.sprite_variant_index = 0

        if type(self).sprite_variants:
            self.sprite_variant_index = random.randrange(len(type(self).sprite_variants))

    def _get_active_frames(self):
        variants = type(self).sprite_variants
        if not variants:
            return []

        if self.sprite_variant_index >= len(variants):
            self.sprite_variant_index = 0

        return variants[self.sprite_variant_index]

    def _get_growth_frame_index(self, frames):
        if len(frames) <= 1:
            return 0

        elapsed_ms = max(0, pygame.time.get_ticks() - self.spawn_time_ms)
        frame_index = elapsed_ms // CROP_GROWTH_FRAME_MS
        return min(len(frames) - 1, frame_index)

    def is_grown(self):
        frames = self._get_active_frames()
        if len(frames) <= 1:
            return True

        elapsed_ms = max(0, pygame.time.get_ticks() - self.spawn_time_ms)
        required_ms = CROP_GROWTH_FRAME_MS * (len(frames) - 1)
        return elapsed_ms >= required_ms

    def draw(self, surface):
        frames = self._get_active_frames()
        if not frames:
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), max(3, self.radius - 2))
            return

        frame_index = self._get_growth_frame_index(frames)
        sprite_size = max(FOOD_MIN_SPRITE_SIZE_PX, int(self.radius * 2 * FOOD_SPRITE_SCALE))
        cache_key = (self.sprite_variant_index, frame_index, sprite_size)

        sprite = type(self).sprite_cache.get(cache_key)
        if sprite is None:
            sprite = pygame.transform.scale(frames[frame_index], (sprite_size, sprite_size))
            type(self).sprite_cache[cache_key] = sprite

        sprite_rect = sprite.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(sprite, sprite_rect)
