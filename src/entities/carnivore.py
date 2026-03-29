import math
import random

import pygame

from src.config import (
    CARNIVORE_BASE_DRAIN,
    CARNIVORE_BASE_SIZE,
    CARNIVORE_BASE_SPEED,
    CARNIVORE_BASE_VISION,
    CARNIVORE_MAX_SIZE,
    CARNIVORE_MAX_SPEED,
    CARNIVORE_MAX_VISION,
    CARNIVORE_MIN_ATTACK_ALIGNMENT_DOT,
    CARNIVORE_MIN_ATTACK_SPEED,
    CARNIVORE_MIN_SIZE,
    CARNIVORE_MIN_SPEED,
    CARNIVORE_MIN_VISION,
    CARNIVORE_RADIUS_BASE,
    CARNIVORE_RADIUS_SCALE,
    CARNIVORE_REST_DRIFT_FACTOR,
    CARNIVORE_REST_DRIFT_SPEED,
    CARNIVORE_REST_DRAIN,
    CARNIVORE_REST_ENERGY_THRESHOLD,
    CARNIVORE_SIZE_DRAIN_MULT,
    CARNIVORE_SIZE_SPEED_PENALTY,
    CARNIVORE_SPEED_DRAIN_MULT,
    CARNIVORE_START_ENERGY,
    CARNIVORE_MIN_SPRITE_SIZE_PX,
    CARNIVORE_SPRITE_HEADING_OFFSET_DEGREES,
    HEIGHT,
    PREDATION_SIZE_ADVANTAGE_FACTOR,
    SPRITE_ANIMATION_FRAME_MS,
    SPRITE_MOVING_SPEED_THRESHOLD,
    SPRITE_RENDER_SCALE,
    SPRITE_ROTATION_STEP_DEGREES,
    WIDTH,
)


class Carnivore:
    sprite_frames = []
    sprite_cache = {}

    @classmethod
    def set_sprite_frames(cls, frames):
        cls.sprite_frames = frames
        cls.sprite_cache = {}

    def __init__(
        self,
        x,
        y,
        speed=CARNIVORE_BASE_SPEED,
        vision=CARNIVORE_BASE_VISION,
        size=CARNIVORE_BASE_SIZE,
        energy=CARNIVORE_START_ENERGY,
        generation=0,
    ):
        self.x = x
        self.y = y

        self.speed = max(CARNIVORE_MIN_SPEED, min(CARNIVORE_MAX_SPEED, speed))
        self.vision_radius = max(CARNIVORE_MIN_VISION, min(CARNIVORE_MAX_VISION, vision))
        self.size = max(CARNIVORE_MIN_SIZE, min(CARNIVORE_MAX_SIZE, size))
        self.radius = self._radius_from_size(self.size)
        self.energy = energy
        self.generation = generation

        self.state = "WANDER"
        self.wander_angle = random.uniform(0, 2 * math.pi)
        movement_speed = self.get_movement_speed()
        self.vx = math.cos(self.wander_angle) * movement_speed
        self.vy = math.sin(self.wander_angle) * movement_speed
        self.turn_factor = 0.07
        self.reproduction_cooldown = 0
        self.attack_cooldown = 0
        self.facing_angle = math.degrees(math.atan2(-self.vy, self.vx))

        size_tint = max(0, min(55, int((self.size - CARNIVORE_MIN_SIZE) * 60)))
        self.color = (230, 90 + size_tint, 70)

    def _radius_from_size(self, size):
        return max(5, int(CARNIVORE_RADIUS_BASE + (size * CARNIVORE_RADIUS_SCALE)))

    def get_movement_speed(self):
        size_penalty = 1.0 + (max(0.0, self.size - CARNIVORE_BASE_SIZE) * CARNIVORE_SIZE_SPEED_PENALTY)
        return self.speed / size_penalty

    def get_active_energy_drain(self):
        movement_speed = self.get_movement_speed()
        size_cost = max(0.0, self.size - CARNIVORE_BASE_SIZE) * CARNIVORE_SIZE_DRAIN_MULT
        return CARNIVORE_BASE_DRAIN + (movement_speed * CARNIVORE_SPEED_DRAIN_MULT) + size_cost

    def _current_velocity_magnitude(self):
        return math.hypot(self.vx, self.vy)

    def _update_facing_angle(self):
        if self._current_velocity_magnitude() >= SPRITE_MOVING_SPEED_THRESHOLD:
            self.facing_angle = math.degrees(math.atan2(-self.vy, self.vx))

    def _get_animation_frame_index(self):
        if not type(self).sprite_frames:
            return 0

        if self._current_velocity_magnitude() < SPRITE_MOVING_SPEED_THRESHOLD:
            return 0

        elapsed = pygame.time.get_ticks()
        return (elapsed // SPRITE_ANIMATION_FRAME_MS) % len(type(self).sprite_frames)

    def can_consume(self, mote):
        return self.size >= (mote.size * PREDATION_SIZE_ADVANTAGE_FACTOR)

    def get_nearest_prey(self, motes):
        closest = None
        min_dist = self.vision_radius

        for mote in motes:
            if mote.energy <= 0 or not self.can_consume(mote):
                continue

            dist = math.hypot(mote.x - self.x, mote.y - self.y)
            if dist < min_dist:
                min_dist = dist
                closest = mote

        return closest

    def on_failed_attack(self, mote):
        dx = self.x - mote.x
        dy = self.y - mote.y
        dist = math.hypot(dx, dy)

        if dist > 0:
            push_speed = self.get_movement_speed()
            self.vx = (dx / dist) * push_speed
            self.vy = (dy / dist) * push_speed
            self.wander_angle = math.atan2(self.vy, self.vx)

    def on_successful_hunt(self, mote):
        dx = self.x - mote.x
        dy = self.y - mote.y
        dist = math.hypot(dx, dy)

        if dist > 0:
            impulse_speed = max(CARNIVORE_REST_DRIFT_SPEED, self.get_movement_speed() * 0.6)
            self.vx = (dx / dist) * impulse_speed
            self.vy = (dy / dist) * impulse_speed
            self.wander_angle = math.atan2(self.vy, self.vx)

        self.state = "WANDER"

    def can_attack_target(self, mote):
        if self.state != "HUNT":
            return False

        speed = self._current_velocity_magnitude()
        if speed < CARNIVORE_MIN_ATTACK_SPEED:
            return False

        dx = mote.x - self.x
        dy = mote.y - self.y
        dist = math.hypot(dx, dy)
        if dist <= 1e-6:
            return False

        approach_dot = ((self.vx / speed) * (dx / dist)) + ((self.vy / speed) * (dy / dist))
        return approach_dot >= CARNIVORE_MIN_ATTACK_ALIGNMENT_DOT

    def update(self, motes):
        if self.reproduction_cooldown > 0:
            self.reproduction_cooldown -= 1

        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1

        if self.energy >= CARNIVORE_REST_ENERGY_THRESHOLD:
            self.state = "REST"
            self.wander_angle += random.uniform(-0.08, 0.08)

            rest_speed = max(
                CARNIVORE_REST_DRIFT_SPEED,
                self.get_movement_speed() * CARNIVORE_REST_DRIFT_FACTOR,
            )
            desired_vx = math.cos(self.wander_angle) * rest_speed
            desired_vy = math.sin(self.wander_angle) * rest_speed
            self.vx += (desired_vx - self.vx) * (self.turn_factor * 0.8)
            self.vy += (desired_vy - self.vy) * (self.turn_factor * 0.8)

            rest_velocity = math.hypot(self.vx, self.vy)
            if rest_velocity > 1e-6:
                self.vx = (self.vx / rest_velocity) * rest_speed
                self.vy = (self.vy / rest_velocity) * rest_speed

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

            self.energy -= CARNIVORE_REST_DRAIN
            return

        movement_speed = self.get_movement_speed()
        nearest_prey = self.get_nearest_prey(motes)

        if nearest_prey:
            self.state = "HUNT"
            dx = nearest_prey.x - self.x
            dy = nearest_prey.y - self.y
            dist = math.hypot(dx, dy)

            if dist > 0:
                desired_vx = (dx / dist) * movement_speed
                desired_vy = (dy / dist) * movement_speed
                self.vx += (desired_vx - self.vx) * (self.turn_factor * 2)
                self.vy += (desired_vy - self.vy) * (self.turn_factor * 2)
        else:
            self.state = "WANDER"
            self.wander_angle += random.uniform(-0.18, 0.18)
            desired_vx = math.cos(self.wander_angle) * movement_speed
            desired_vy = math.sin(self.wander_angle) * movement_speed
            self.vx += (desired_vx - self.vx) * self.turn_factor
            self.vy += (desired_vy - self.vy) * self.turn_factor

        current_speed = math.hypot(self.vx, self.vy)
        if current_speed > 0:
            self.vx = (self.vx / current_speed) * movement_speed
            self.vy = (self.vy / current_speed) * movement_speed

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

        self.energy -= self.get_active_energy_drain()

    def draw(self, surface):
        if not type(self).sprite_frames:
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), self.radius)
            pygame.draw.circle(surface, (255, 220, 190), (int(self.x), int(self.y)), self.radius, 1)
            return

        self._update_facing_angle()
        frame_index = self._get_animation_frame_index()
        sprite_size = max(CARNIVORE_MIN_SPRITE_SIZE_PX, int(self.radius * 2 * SPRITE_RENDER_SCALE))
        snapped_angle = int(round(self.facing_angle / SPRITE_ROTATION_STEP_DEGREES) * SPRITE_ROTATION_STEP_DEGREES)
        cache_key = (frame_index, sprite_size, snapped_angle)

        sprite = type(self).sprite_cache.get(cache_key)
        if sprite is None:
            source = type(self).sprite_frames[frame_index]
            scaled = pygame.transform.scale(source, (sprite_size, sprite_size))
            sprite = pygame.transform.rotate(scaled, snapped_angle + CARNIVORE_SPRITE_HEADING_OFFSET_DEGREES)
            type(self).sprite_cache[cache_key] = sprite

        sprite_rect = sprite.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(sprite, sprite_rect)
