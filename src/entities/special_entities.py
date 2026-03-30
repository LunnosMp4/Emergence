import math
import random

import pygame

from src.config import (
    HEIGHT,
    SPRITE_ANIMATION_FRAME_MS,
    SPRITE_MOVING_SPEED_THRESHOLD,
    SPRITE_RENDER_SCALE,
    SPRITE_ROTATION_STEP_DEGREES,
    SSH_ENTITY_BASE_SIZE,
    SSH_ENTITY_BASE_SPEED,
    SSH_ENTITY_EDGE_MARGIN,
    SSH_ENTITY_EDGE_PULL,
    SSH_ENTITY_MIN_SPRITE_SIZE_PX,
    SSH_ENTITY_RADIUS_BASE,
    SSH_ENTITY_RADIUS_SCALE,
    SSH_ENTITY_SPRITE_HEADING_OFFSET_DEGREES,
    SSH_ENTITY_TURN_FACTOR,
    SSH_ENTITY_WANDER_JITTER,
    STEAM_ENTITY_BASE_SIZE,
    STEAM_ENTITY_BASE_SPEED,
    STEAM_ENTITY_MIN_SPRITE_SIZE_PX,
    STEAM_ENTITY_PAUSE_CHANCE,
    STEAM_ENTITY_PAUSE_FRAMES_MAX,
    STEAM_ENTITY_PAUSE_FRAMES_MIN,
    STEAM_ENTITY_RADIUS_BASE,
    STEAM_ENTITY_RADIUS_SCALE,
    STEAM_ENTITY_SPRITE_HEADING_OFFSET_DEGREES,
    STEAM_ENTITY_TURN_FACTOR,
    STEAM_ENTITY_WANDER_JITTER,
    WIDTH,
)


class _SpecialEntityBase:
    def __init__(
        self,
        x,
        y,
        *,
        speed,
        size,
        radius_base,
        radius_scale,
        turn_factor,
        min_sprite_size_px,
        heading_offset_degrees,
        fallback_color,
    ):
        self.x = float(x)
        self.y = float(y)
        self.speed = max(0.05, float(speed))
        self.size = max(0.5, float(size))
        self.radius = max(4, int(radius_base + (self.size * radius_scale)))
        self.turn_factor = max(0.01, float(turn_factor))
        self.min_sprite_size_px = max(12, int(min_sprite_size_px))
        self.heading_offset_degrees = float(heading_offset_degrees)
        self.color = fallback_color
        self.energy = float("inf")

        self.wander_angle = random.uniform(0.0, 2.0 * math.pi)
        self.vx = math.cos(self.wander_angle) * self.speed
        self.vy = math.sin(self.wander_angle) * self.speed
        self.facing_angle = math.degrees(math.atan2(-self.vy, self.vx))
        self.phase = random.uniform(0.0, math.pi * 2.0)

    def _current_velocity_magnitude(self):
        return math.hypot(self.vx, self.vy)

    def _update_facing_angle(self):
        if self._current_velocity_magnitude() >= SPRITE_MOVING_SPEED_THRESHOLD:
            self.facing_angle = math.degrees(math.atan2(-self.vy, self.vx))

    def _get_animation_frame_index(self):
        frames = type(self).sprite_frames
        if not frames:
            return 0

        if self._current_velocity_magnitude() < SPRITE_MOVING_SPEED_THRESHOLD:
            return 0

        elapsed = pygame.time.get_ticks()
        return (elapsed // SPRITE_ANIMATION_FRAME_MS) % len(frames)

    def _steer_velocity(self, desired_vx, desired_vy):
        self.vx += (desired_vx - self.vx) * self.turn_factor
        self.vy += (desired_vy - self.vy) * self.turn_factor

        current_speed = self._current_velocity_magnitude()
        if current_speed > 1e-6:
            self.vx = (self.vx / current_speed) * self.speed
            self.vy = (self.vy / current_speed) * self.speed

    def _move_and_bounce(self):
        self.x += self.vx
        self.y += self.vy

        if self.x <= 0.0 or self.x >= WIDTH:
            self.vx *= -1.0
            self.x = max(0.0, min(self.x, WIDTH))
            self.wander_angle = math.atan2(self.vy, self.vx)

        if self.y <= 0.0 or self.y >= HEIGHT:
            self.vy *= -1.0
            self.y = max(0.0, min(self.y, HEIGHT))
            self.wander_angle = math.atan2(self.vy, self.vx)

    def _draw_accent(self, surface):
        # Subclasses can override this for harmless visual identity cues.
        return

    def draw(self, surface):
        frames = type(self).sprite_frames
        if not frames:
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)
            self._draw_accent(surface)
            return

        self._update_facing_angle()
        frame_index = self._get_animation_frame_index()
        sprite_size = max(self.min_sprite_size_px, int(self.radius * 2 * SPRITE_RENDER_SCALE))
        snapped_angle = int(round(self.facing_angle / SPRITE_ROTATION_STEP_DEGREES) * SPRITE_ROTATION_STEP_DEGREES)
        cache_key = (frame_index, sprite_size, snapped_angle)

        sprite = type(self).sprite_cache.get(cache_key)
        if sprite is None:
            source = frames[frame_index]
            scaled = pygame.transform.scale(source, (sprite_size, sprite_size))
            sprite = pygame.transform.rotate(scaled, snapped_angle + self.heading_offset_degrees)
            type(self).sprite_cache[cache_key] = sprite

        sprite_rect = sprite.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(sprite, sprite_rect)
        self._draw_accent(surface)


class SteamGiant(_SpecialEntityBase):
    sprite_frames = []
    sprite_cache = {}

    @classmethod
    def set_sprite_frames(cls, frames):
        cls.sprite_frames = frames or []
        cls.sprite_cache = {}

    def __init__(self, x, y):
        super().__init__(
            x,
            y,
            speed=STEAM_ENTITY_BASE_SPEED,
            size=STEAM_ENTITY_BASE_SIZE,
            radius_base=STEAM_ENTITY_RADIUS_BASE,
            radius_scale=STEAM_ENTITY_RADIUS_SCALE,
            turn_factor=STEAM_ENTITY_TURN_FACTOR,
            min_sprite_size_px=STEAM_ENTITY_MIN_SPRITE_SIZE_PX,
            heading_offset_degrees=STEAM_ENTITY_SPRITE_HEADING_OFFSET_DEGREES,
            fallback_color=(236, 178, 120),
        )
        self.pause_frames_remaining = 0

    def update(self):
        if self.pause_frames_remaining > 0:
            self.pause_frames_remaining -= 1
            self.vx *= 0.94
            self.vy *= 0.94
            self._move_and_bounce()
            return

        if random.random() < STEAM_ENTITY_PAUSE_CHANCE:
            self.pause_frames_remaining = random.randint(STEAM_ENTITY_PAUSE_FRAMES_MIN, STEAM_ENTITY_PAUSE_FRAMES_MAX)

        self.wander_angle += random.uniform(-STEAM_ENTITY_WANDER_JITTER, STEAM_ENTITY_WANDER_JITTER)
        desired_vx = math.cos(self.wander_angle) * self.speed
        desired_vy = math.sin(self.wander_angle) * self.speed
        self._steer_velocity(desired_vx, desired_vy)
        self._move_and_bounce()

    def _draw_accent(self, surface):
        return


class SSHWarden(_SpecialEntityBase):
    sprite_frames = []
    sprite_cache = {}

    @classmethod
    def set_sprite_frames(cls, frames):
        cls.sprite_frames = frames or []
        cls.sprite_cache = {}

    def __init__(self, x, y):
        super().__init__(
            x,
            y,
            speed=SSH_ENTITY_BASE_SPEED,
            size=SSH_ENTITY_BASE_SIZE,
            radius_base=SSH_ENTITY_RADIUS_BASE,
            radius_scale=SSH_ENTITY_RADIUS_SCALE,
            turn_factor=SSH_ENTITY_TURN_FACTOR,
            min_sprite_size_px=SSH_ENTITY_MIN_SPRITE_SIZE_PX,
            heading_offset_degrees=SSH_ENTITY_SPRITE_HEADING_OFFSET_DEGREES,
            fallback_color=(120, 210, 255),
        )

    def update(self):
        center_x = WIDTH * 0.5
        center_y = HEIGHT * 0.5
        rel_x = self.x - center_x
        rel_y = self.y - center_y
        rel_dist = math.hypot(rel_x, rel_y)

        if rel_dist <= 1e-6:
            rel_x = 1.0
            rel_y = 0.0
            rel_dist = 1.0

        radial_x = rel_x / rel_dist
        radial_y = rel_y / rel_dist

        tangent_x = -radial_y
        tangent_y = radial_x

        desired_ring_radius = max(40.0, min(center_x, center_y) - SSH_ENTITY_EDGE_MARGIN)
        ring_error = (desired_ring_radius - rel_dist) / max(1.0, desired_ring_radius)

        desired_x = tangent_x + (radial_x * ring_error * SSH_ENTITY_EDGE_PULL)
        desired_y = tangent_y + (radial_y * ring_error * SSH_ENTITY_EDGE_PULL)

        jitter = random.uniform(-SSH_ENTITY_WANDER_JITTER, SSH_ENTITY_WANDER_JITTER)
        cos_jitter = math.cos(jitter)
        sin_jitter = math.sin(jitter)
        rotated_x = (desired_x * cos_jitter) - (desired_y * sin_jitter)
        rotated_y = (desired_x * sin_jitter) + (desired_y * cos_jitter)

        direction_mag = math.hypot(rotated_x, rotated_y)
        if direction_mag > 1e-6:
            rotated_x /= direction_mag
            rotated_y /= direction_mag
        else:
            rotated_x = tangent_x
            rotated_y = tangent_y

        desired_vx = rotated_x * self.speed
        desired_vy = rotated_y * self.speed
        self._steer_velocity(desired_vx, desired_vy)
        self._move_and_bounce()

    def _draw_accent(self, surface):
        return
