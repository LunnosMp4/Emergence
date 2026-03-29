import math
import random

import pygame

from src.config import (
    HEIGHT,
    MOTE_MIN_SPRITE_SIZE_PX,
    MOTE_SPRITE_HEADING_OFFSET_DEGREES,
    PREY_BASE_SIZE,
    PREY_FLEE_BLEND_WEIGHT,
    PREY_FLEE_PANIC_SPEED_MULT,
    PREY_FLEE_PRIORITY_THRESHOLD,
    PREY_MAX_ESCAPE_SPEED_MULT,
    PREY_MAX_SIZE,
    PREY_MIN_SIZE,
    PREY_RADIUS_BASE,
    PREY_RADIUS_SCALE,
    PREY_SIZE_ENERGY_DRAIN_MULT,
    PREY_SIZE_SPEED_PENALTY,
    PREY_THREAT_DETECTION_RADIUS,
    SPRITE_ANIMATION_FRAME_MS,
    SPRITE_MOVING_SPEED_THRESHOLD,
    SPRITE_RENDER_SCALE,
    SPRITE_ROTATION_STEP_DEGREES,
    WIDTH,
)


class Mote:
    sprite_variants = []
    sprite_cache = {}

    @classmethod
    def set_sprite_variants(cls, variants):
        cls.sprite_variants = [frames for frames in variants if frames]
        cls.sprite_cache = {}

    @classmethod
    def set_sprite_frames(cls, frames):
        cls.set_sprite_variants([frames] if frames else [])

    def __init__(
        self,
        x,
        y,
        speed=2.0,
        vision=100.0,
        size=PREY_BASE_SIZE,
        energy=100.0,
        generation=0,
    ):
        self.x = x
        self.y = y

        # Genetics
        self.speed = speed
        self.vision_radius = vision
        self.size = max(PREY_MIN_SIZE, min(PREY_MAX_SIZE, size))
        self.radius = self._radius_from_size(self.size)
        self.energy = energy
        self.generation = generation

        # Movement & Steering
        self.wander_angle = random.uniform(0, 2 * math.pi)
        movement_speed = self.get_movement_speed()
        self.vx = math.cos(self.wander_angle) * movement_speed
        self.vy = math.sin(self.wander_angle) * movement_speed
        self.turn_factor = 0.08
        self.facing_angle = math.degrees(math.atan2(-self.vy, self.vx))

        # Color used only if sprite loading fails.
        color_val = max(50, min(255, int((self.speed / 4.0) * 255)))
        self.color = (color_val, 50, 255 - color_val)
        self.sprite_variant_index = 0
        if type(self).sprite_variants:
            self.sprite_variant_index = random.randrange(len(type(self).sprite_variants))

    def _radius_from_size(self, size):
        return max(3, int(PREY_RADIUS_BASE + (size * PREY_RADIUS_SCALE)))

    def get_movement_speed(self):
        size_penalty = 1.0 + (max(0.0, self.size - PREY_BASE_SIZE) * PREY_SIZE_SPEED_PENALTY)
        return self.speed / size_penalty

    def get_energy_drain(self):
        movement_speed = self.get_movement_speed()
        size_cost = max(0.0, self.size - PREY_BASE_SIZE) * PREY_SIZE_ENERGY_DRAIN_MULT
        return 0.1 + (movement_speed * 0.05) + size_cost

    def _current_velocity_magnitude(self):
        return math.hypot(self.vx, self.vy)

    def _get_active_frames(self):
        variants = type(self).sprite_variants
        if not variants:
            return []

        if self.sprite_variant_index >= len(variants):
            self.sprite_variant_index = 0

        return variants[self.sprite_variant_index]

    def _update_facing_angle(self):
        if self._current_velocity_magnitude() >= SPRITE_MOVING_SPEED_THRESHOLD:
            self.facing_angle = math.degrees(math.atan2(-self.vy, self.vx))

    def _get_animation_frame_index(self):
        frames = self._get_active_frames()
        if not frames:
            return 0

        if self._current_velocity_magnitude() < SPRITE_MOVING_SPEED_THRESHOLD:
            return 0

        elapsed = pygame.time.get_ticks()
        return (elapsed // SPRITE_ANIMATION_FRAME_MS) % len(frames)

    def _get_threat_vector(self, carnivores):
        if not carnivores:
            return 0.0, 0.0, 0.0

        steer_x = 0.0
        steer_y = 0.0
        strongest_threat = 0.0

        for carnivore in carnivores:
            dx = self.x - carnivore.x
            dy = self.y - carnivore.y
            dist = math.hypot(dx, dy)

            if dist <= 1e-6 or dist > PREY_THREAT_DETECTION_RADIUS:
                continue

            weight = (PREY_THREAT_DETECTION_RADIUS - dist) / PREY_THREAT_DETECTION_RADIUS
            if carnivore.state == "HUNT":
                weight *= 1.2

            steer_x += (dx / dist) * weight
            steer_y += (dy / dist) * weight
            strongest_threat = max(strongest_threat, weight)

        magnitude = math.hypot(steer_x, steer_y)
        if magnitude <= 1e-6:
            return 0.0, 0.0, 0.0

        return steer_x / magnitude, steer_y / magnitude, min(1.0, strongest_threat)

    def update(self, foods, carnivores=None):
        movement_speed = self.get_movement_speed()

        # Larger prey are safer against predators but cost more to maintain.
        self.energy -= self.get_energy_drain()

        threat_x, threat_y, threat_level = self._get_threat_vector(carnivores)
        target_speed = movement_speed
        if threat_level > 0.0:
            target_speed = movement_speed * min(
                PREY_MAX_ESCAPE_SPEED_MULT,
                1.0 + (threat_level * PREY_FLEE_PANIC_SPEED_MULT),
            )

        nearest_food = self.get_nearest_food(foods)
        desired_vx = self.vx
        desired_vy = self.vy
        seek_mode = False

        if nearest_food:
            seek_mode = True
            dx = nearest_food.x - self.x
            dy = nearest_food.y - self.y
            dist = math.hypot(dx, dy)

            if dist > 0:
                desired_vx = (dx / dist) * movement_speed
                desired_vy = (dy / dist) * movement_speed
        else:
            self.wander_angle += random.uniform(-0.2, 0.2)
            desired_vx = math.cos(self.wander_angle) * movement_speed
            desired_vy = math.sin(self.wander_angle) * movement_speed

        if threat_level >= PREY_FLEE_PRIORITY_THRESHOLD:
            desired_vx = threat_x * target_speed
            desired_vy = threat_y * target_speed
        elif threat_level > 0.0:
            flee_vx = threat_x * target_speed
            flee_vy = threat_y * target_speed
            blend = min(0.85, threat_level * PREY_FLEE_BLEND_WEIGHT)
            desired_vx = (desired_vx * (1.0 - blend)) + (flee_vx * blend)
            desired_vy = (desired_vy * (1.0 - blend)) + (flee_vy * blend)

        if threat_level > 0.0:
            steer_factor = self.turn_factor * 2.2
        elif seek_mode:
            steer_factor = self.turn_factor * 2.0
        else:
            steer_factor = self.turn_factor

        self.vx += (desired_vx - self.vx) * steer_factor
        self.vy += (desired_vy - self.vy) * steer_factor

        current_speed = math.hypot(self.vx, self.vy)
        if current_speed > 0:
            self.vx = (self.vx / current_speed) * target_speed
            self.vy = (self.vy / current_speed) * target_speed

        self.x += self.vx
        self.y += self.vy

        if self.x <= 0 or self.x >= WIDTH:
            self.vx *= -1
            self.x = max(0, min(self.x, WIDTH))
            self.wander_angle = math.atan2(self.vy, self.vx)

        if self.y <= 0 or self.y >= HEIGHT:
            self.vy *= -1
            self.y = max(0, min(self.y, HEIGHT))
            self.wander_angle = math.atan2(self.vy, self.vx)

    def get_nearest_food(self, foods):
        closest = None
        min_dist = self.vision_radius
        for food in foods:
            if hasattr(food, "is_grown") and not food.is_grown():
                continue
            dist = math.hypot(food.x - self.x, food.y - self.y)
            if dist < min_dist:
                min_dist = dist
                closest = food
        return closest

    def draw(self, surface):
        frames = self._get_active_frames()
        if not frames:
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)
            return

        self._update_facing_angle()
        frame_index = self._get_animation_frame_index()
        sprite_size = max(MOTE_MIN_SPRITE_SIZE_PX, int(self.radius * 2 * SPRITE_RENDER_SCALE))
        snapped_angle = int(round(self.facing_angle / SPRITE_ROTATION_STEP_DEGREES) * SPRITE_ROTATION_STEP_DEGREES)
        cache_key = (self.sprite_variant_index, frame_index, sprite_size, snapped_angle)

        sprite = type(self).sprite_cache.get(cache_key)
        if sprite is None:
            source = frames[frame_index]
            scaled = pygame.transform.scale(source, (sprite_size, sprite_size))
            sprite = pygame.transform.rotate(scaled, snapped_angle + MOTE_SPRITE_HEADING_OFFSET_DEGREES)
            type(self).sprite_cache[cache_key] = sprite

        sprite_rect = sprite.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(sprite, sprite_rect)
