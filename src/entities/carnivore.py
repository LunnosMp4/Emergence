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
    CARNIVORE_REPRODUCTION_COOLDOWN_FRAMES,
    MAX_CARNIVORES,
    CARNIVORE_SIZE_DRAIN_MULT,
    CARNIVORE_SIZE_SPEED_PENALTY,
    CARNIVORE_SPEED_DRAIN_MULT,
    CARNIVORE_START_ENERGY,
    CARNIVORE_MIN_SPRITE_SIZE_PX,
    CARNIVORE_SPRITE_HEADING_OFFSET_DEGREES,
    HEIGHT,
    PHEROMONE_MATE_BLEND_WEIGHT,
    PHEROMONE_MATE_EMIT_COOLDOWN_FRAMES,
    PHEROMONE_MATE_INTENSITY_PREDATOR,
    PHEROMONE_MATE_MAX_AGE_FRAMES,
    PHEROMONE_MATE_SEARCH_RADIUS_PREDATOR,
    PREDATOR_MATE_PHEROMONE_LOCK_THRESHOLD,
    PREDATOR_MATE_PHEROMONE_TURN_MAX,
    PREDATOR_MATE_PHEROMONE_TURN_MIN,
    PREDATOR_FAILED_MATING_COOLDOWN_FRAMES,
    PREDATOR_MATE_ACTIVE_COLOR,
    PREDATOR_MATE_ENERGY_COST,
    PREDATOR_MATE_ENERGY_THRESHOLD,
    PREDATOR_MATE_SEARCH_RADIUS,
    PREDATOR_MATE_SEEK_COLOR,
    PREDATOR_MATE_TOUCH_DISTANCE,
    PREDATOR_MATING_DRAIN_MULT,
    PREDATOR_MATING_DURATION_FRAMES,
    PREDATOR_REPRODUCTION_COOLDOWN_FRAMES,
    PREDATION_SIZE_ADVANTAGE_FACTOR,
    REPRO_MATING_PULSE_SPEED_MS,
    REPRO_MATING_RING_WIDTH,
    REPRO_RING_OFFSET,
    REPRO_SEEK_RING_WIDTH,
    SEXUAL_REPRODUCTION_ENABLED,
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
        self.reproduction_state = "IDLE"
        self.mate_partner = None
        self.mating_progress_frames = 0
        self.mate_search_radius = PREDATOR_MATE_SEARCH_RADIUS
        self.mate_touch_distance = PREDATOR_MATE_TOUCH_DISTANCE
        self.mating_duration_frames = PREDATOR_MATING_DURATION_FRAMES
        self.reproduction_cooldown_frames = PREDATOR_REPRODUCTION_COOLDOWN_FRAMES
        self.failed_mating_cooldown_frames = PREDATOR_FAILED_MATING_COOLDOWN_FRAMES
        self.mating_energy_cost = PREDATOR_MATE_ENERGY_COST
        self.mate_pheromone_emit_cooldown_frames = random.randint(0, PHEROMONE_MATE_EMIT_COOLDOWN_FRAMES)

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

    def is_ready_to_mate(self):
        return (
            SEXUAL_REPRODUCTION_ENABLED
            and self.energy >= PREDATOR_MATE_ENERGY_THRESHOLD
            and self.reproduction_cooldown <= 0
            and self.reproduction_state != "MATING"
        )

    def can_pair_with(self, other):
        if other is None or other is self:
            return False
        if not isinstance(other, Carnivore):
            return False
        if other.energy <= 0:
            return False
        return other.is_ready_to_mate()

    def get_nearest_mate(self, carnivores):
        closest = None
        min_dist = self.mate_search_radius

        for carnivore in carnivores:
            if not self.can_pair_with(carnivore):
                continue
            if carnivore.reproduction_state != "SEEK_MATE":
                continue
            if carnivore.mate_partner is not None:
                continue

            dist = math.hypot(carnivore.x - self.x, carnivore.y - self.y)
            if dist < min_dist:
                min_dist = dist
                closest = carnivore

        return closest

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

    def _draw_reproduction_indicator(self, surface):
        if not SEXUAL_REPRODUCTION_ENABLED:
            return

        center = (int(self.x), int(self.y))
        base_radius = self.radius + REPRO_RING_OFFSET

        if self.reproduction_state == "SEEK_MATE":
            pygame.draw.circle(surface, PREDATOR_MATE_SEEK_COLOR, center, base_radius, REPRO_SEEK_RING_WIDTH)
            return

        if self.reproduction_state == "MATING":
            pulse = 1 + int((math.sin(pygame.time.get_ticks() / REPRO_MATING_PULSE_SPEED_MS) + 1.0) * 1.4)
            pygame.draw.circle(
                surface,
                PREDATOR_MATE_ACTIVE_COLOR,
                center,
                base_radius + pulse,
                REPRO_MATING_RING_WIDTH,
            )

    def _emit_mate_pheromone(self, pheromone_field):
        if not SEXUAL_REPRODUCTION_ENABLED or pheromone_field is None:
            return False

        if self.reproduction_state != "SEEK_MATE":
            return False

        if self.mate_pheromone_emit_cooldown_frames > 0:
            return False

        emitted = pheromone_field.emit(
            self.x,
            self.y,
            PHEROMONE_MATE_INTENSITY_PREDATOR,
            "mate",
            PHEROMONE_MATE_MAX_AGE_FRAMES,
            species_tag="predator",
            source_id=id(self),
        )

        if emitted:
            self.mate_pheromone_emit_cooldown_frames = PHEROMONE_MATE_EMIT_COOLDOWN_FRAMES

        return emitted

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

    def update(self, motes, carnivores=None, pheromone_field=None):
        if self.reproduction_cooldown > 0:
            self.reproduction_cooldown -= 1
            if self.reproduction_cooldown <= 0 and self.reproduction_state == "COOLDOWN":
                self.reproduction_state = "WANDER"

        if self.attack_cooldown > 0:
            self.attack_cooldown -= 1

        if self.mate_pheromone_emit_cooldown_frames > 0:
            self.mate_pheromone_emit_cooldown_frames -= 1

        if SEXUAL_REPRODUCTION_ENABLED and self.reproduction_state == "MATING":
            self.energy -= max(CARNIVORE_REST_DRAIN, self.get_active_energy_drain() * PREDATOR_MATING_DRAIN_MULT)
            self.vx *= 0.35
            self.vy *= 0.35
            return

        mate_pheromone_x = 0.0
        mate_pheromone_y = 0.0
        mate_pheromone_level = 0.0
        if (
            SEXUAL_REPRODUCTION_ENABLED
            and pheromone_field is not None
            and self.reproduction_state == "SEEK_MATE"
        ):
            mate_pheromone_x, mate_pheromone_y, mate_pheromone_level = pheromone_field.get_mate_vector(
                self.x,
                self.y,
                PHEROMONE_MATE_SEARCH_RADIUS_PREDATOR,
                "predator",
                ignore_source_id=id(self),
            )

        mate_target = None
        predator_cap_reached = bool(carnivores) and len(carnivores) >= MAX_CARNIVORES
        if SEXUAL_REPRODUCTION_ENABLED:
            if predator_cap_reached:
                if self.reproduction_state == "SEEK_MATE":
                    self.reproduction_state = "WANDER"
                    self.mate_partner = None
                    self.mating_progress_frames = 0
            elif self.is_ready_to_mate():
                if self.reproduction_state not in ("SEEK_MATE", "MATING"):
                    self.reproduction_state = "SEEK_MATE"
                if carnivores:
                    mate_target = self.get_nearest_mate(carnivores)
            elif self.reproduction_state == "SEEK_MATE":
                self.reproduction_state = "WANDER"
                self.mate_partner = None
                self.mating_progress_frames = 0

            if self.reproduction_state == "SEEK_MATE":
                self._emit_mate_pheromone(pheromone_field)
                movement_speed = self.get_movement_speed()
                if mate_target:
                    dx = mate_target.x - self.x
                    dy = mate_target.y - self.y
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        desired_vx = (dx / dist) * movement_speed
                        desired_vy = (dy / dist) * movement_speed
                        self.vx += (desired_vx - self.vx) * (self.turn_factor * 2.3)
                        self.vy += (desired_vy - self.vy) * (self.turn_factor * 2.3)
                else:
                    turn_strength = self.turn_factor
                    if mate_pheromone_level > 0.0:
                        if mate_pheromone_level >= PREDATOR_MATE_PHEROMONE_LOCK_THRESHOLD:
                            desired_vx = mate_pheromone_x * movement_speed
                            desired_vy = mate_pheromone_y * movement_speed
                            signal_strength = min(1.0, mate_pheromone_level)
                            turn_strength = PREDATOR_MATE_PHEROMONE_TURN_MIN + (
                                (PREDATOR_MATE_PHEROMONE_TURN_MAX - PREDATOR_MATE_PHEROMONE_TURN_MIN)
                                * signal_strength
                            )
                            self.wander_angle = math.atan2(desired_vy, desired_vx)
                        else:
                            blend = min(0.92, max(0.35, mate_pheromone_level * PHEROMONE_MATE_BLEND_WEIGHT))
                            wander_x = math.cos(self.wander_angle)
                            wander_y = math.sin(self.wander_angle)
                            steer_x = (mate_pheromone_x * blend) + (wander_x * (1.0 - blend))
                            steer_y = (mate_pheromone_y * blend) + (wander_y * (1.0 - blend))
                            steer_mag = math.hypot(steer_x, steer_y)
                            if steer_mag > 1e-6:
                                desired_vx = (steer_x / steer_mag) * movement_speed
                                desired_vy = (steer_y / steer_mag) * movement_speed
                            else:
                                desired_vx = mate_pheromone_x * movement_speed
                                desired_vy = mate_pheromone_y * movement_speed
                            turn_strength = self.turn_factor * 1.9
                    else:
                        self.wander_angle += random.uniform(-0.12, 0.12)
                        desired_vx = math.cos(self.wander_angle) * movement_speed
                        desired_vy = math.sin(self.wander_angle) * movement_speed
                    self.vx += (desired_vx - self.vx) * turn_strength
                    self.vy += (desired_vy - self.vy) * turn_strength

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

                self.state = "SEEK_MATE"
                self.energy -= self.get_active_energy_drain()
                return

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
            self._draw_reproduction_indicator(surface)
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
        self._draw_reproduction_indicator(surface)
