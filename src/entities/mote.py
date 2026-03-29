import math
import random

import pygame

from src.config import (
    COMMUNICATION_ENABLED,
    HEIGHT,
    MOTE_MIN_SPRITE_SIZE_PX,
    MOTE_SPRITE_HEADING_OFFSET_DEGREES,
    PHEROMONE_ALARM_INTENSITY_MULT,
    PHEROMONE_ALARM_MAX_AGE_FRAMES,
    PHEROMONE_CONTACT_RADIUS,
    PHEROMONE_EMIT_COOLDOWN_FRAMES,
    PHEROMONE_FOOD_AVOID_THRESHOLD,
    PHEROMONE_MATE_BLEND_WEIGHT,
    PHEROMONE_MATE_EMIT_COOLDOWN_FRAMES,
    PHEROMONE_MATE_INTENSITY_PREY,
    PHEROMONE_MATE_MAX_AGE_FRAMES,
    PHEROMONE_MATE_SEARCH_RADIUS_PREY,
    PHEROMONE_RELAY_INTENSITY,
    PHEROMONE_RELAY_MAX_AGE_FRAMES,
    PHEROMONE_SEARCH_RADIUS,
    PHEROMONE_SIGNAL_BLEND_WEIGHT,
    PHEROMONE_THREAT_EMIT_THRESHOLD,
    PREY_FAILED_MATING_COOLDOWN_FRAMES,
    PREY_BASE_SIZE,
    PREY_FLEE_BLEND_WEIGHT,
    PREY_MATE_ACTIVE_COLOR,
    PREY_MATE_ENERGY_COST,
    PREY_MATE_ENERGY_THRESHOLD,
    PREY_MATE_SEARCH_RADIUS,
    PREY_MATE_SEEK_COLOR,
    PREY_MATE_TOUCH_DISTANCE,
    PREY_MATING_DRAIN_MULT,
    PREY_MATING_DURATION_FRAMES,
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
    PREY_REPRODUCTION_COOLDOWN_FRAMES,
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

        self.communication_emit_cooldown_frames = random.randint(0, PHEROMONE_EMIT_COOLDOWN_FRAMES)
        self.mate_pheromone_emit_cooldown_frames = random.randint(0, PHEROMONE_MATE_EMIT_COOLDOWN_FRAMES)
        self.reproduction_state = "IDLE"
        self.reproduction_cooldown = 0
        self.mate_partner = None
        self.mating_progress_frames = 0
        self.mate_search_radius = PREY_MATE_SEARCH_RADIUS
        self.mate_touch_distance = PREY_MATE_TOUCH_DISTANCE
        self.mating_duration_frames = PREY_MATING_DURATION_FRAMES
        self.reproduction_cooldown_frames = PREY_REPRODUCTION_COOLDOWN_FRAMES
        self.failed_mating_cooldown_frames = PREY_FAILED_MATING_COOLDOWN_FRAMES
        self.mating_energy_cost = PREY_MATE_ENERGY_COST

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

    def is_ready_to_mate(self):
        return (
            SEXUAL_REPRODUCTION_ENABLED
            and self.energy >= PREY_MATE_ENERGY_THRESHOLD
            and self.reproduction_cooldown <= 0
            and self.reproduction_state != "MATING"
        )

    def can_pair_with(self, other):
        if other is None or other is self:
            return False
        if not isinstance(other, Mote):
            return False
        if other.energy <= 0:
            return False
        return other.is_ready_to_mate()

    def get_nearest_mate(self, motes):
        closest = None
        min_dist = self.mate_search_radius

        for mote in motes:
            if not self.can_pair_with(mote):
                continue
            if mote.reproduction_state != "SEEK_MATE":
                continue
            if mote.mate_partner is not None:
                continue

            dist = math.hypot(mote.x - self.x, mote.y - self.y)
            if dist < min_dist:
                min_dist = dist
                closest = mote

        return closest

    def _has_close_neighbor(self, motes, radius):
        if not motes:
            return False

        radius_sq = radius * radius
        for mote in motes:
            if mote is self or mote.energy <= 0:
                continue

            dx = mote.x - self.x
            dy = mote.y - self.y
            if (dx * dx) + (dy * dy) <= radius_sq:
                return True

        return False

    def _emit_communication(self, pheromone_field, threat_level, nearby_motes):
        if not COMMUNICATION_ENABLED or pheromone_field is None:
            return False, False

        if self.communication_emit_cooldown_frames > 0:
            return False, False

        if threat_level < PHEROMONE_THREAT_EMIT_THRESHOLD:
            return False, False

        alarm_intensity = max(0.08, min(1.0, threat_level * PHEROMONE_ALARM_INTENSITY_MULT))
        alarm_emitted = pheromone_field.emit(
            self.x,
            self.y,
            alarm_intensity,
            "alarm",
            PHEROMONE_ALARM_MAX_AGE_FRAMES,
            species_tag="prey",
        )

        relay_emitted = False
        if (
            threat_level >= PREY_FLEE_PRIORITY_THRESHOLD
            and nearby_motes
            and self._has_close_neighbor(nearby_motes, PHEROMONE_CONTACT_RADIUS)
        ):
            relay_emitted = pheromone_field.emit(
                self.x,
                self.y,
                PHEROMONE_RELAY_INTENSITY,
                "relay",
                PHEROMONE_RELAY_MAX_AGE_FRAMES,
                species_tag="prey",
            )

        if alarm_emitted or relay_emitted:
            self.communication_emit_cooldown_frames = PHEROMONE_EMIT_COOLDOWN_FRAMES

        return alarm_emitted, relay_emitted

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
            PHEROMONE_MATE_INTENSITY_PREY,
            "mate",
            PHEROMONE_MATE_MAX_AGE_FRAMES,
            species_tag="prey",
            source_id=id(self),
        )

        if emitted:
            self.mate_pheromone_emit_cooldown_frames = PHEROMONE_MATE_EMIT_COOLDOWN_FRAMES

        return emitted

    def _draw_reproduction_indicator(self, surface):
        if not SEXUAL_REPRODUCTION_ENABLED:
            return

        center = (int(self.x), int(self.y))
        base_radius = self.radius + REPRO_RING_OFFSET

        if self.reproduction_state == "SEEK_MATE":
            pygame.draw.circle(surface, PREY_MATE_SEEK_COLOR, center, base_radius, REPRO_SEEK_RING_WIDTH)
            return

        if self.reproduction_state == "MATING":
            pulse = 1 + int((math.sin(pygame.time.get_ticks() / REPRO_MATING_PULSE_SPEED_MS) + 1.0) * 1.2)
            pygame.draw.circle(
                surface,
                PREY_MATE_ACTIVE_COLOR,
                center,
                base_radius + pulse,
                REPRO_MATING_RING_WIDTH,
            )

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

    def update(self, foods, carnivores=None, pheromone_field=None, nearby_motes=None):
        movement_speed = self.get_movement_speed()

        if self.communication_emit_cooldown_frames > 0:
            self.communication_emit_cooldown_frames -= 1

        if self.mate_pheromone_emit_cooldown_frames > 0:
            self.mate_pheromone_emit_cooldown_frames -= 1

        if self.reproduction_cooldown > 0:
            self.reproduction_cooldown -= 1
            if self.reproduction_cooldown <= 0 and self.reproduction_state == "COOLDOWN":
                self.reproduction_state = "IDLE"

        if SEXUAL_REPRODUCTION_ENABLED and self.reproduction_state == "MATING":
            self.energy -= self.get_energy_drain() * PREY_MATING_DRAIN_MULT
            self.vx *= 0.35
            self.vy *= 0.35
            return {
                "alarm_emitted": False,
                "relay_emitted": False,
            }

        # Larger prey are safer against predators but cost more to maintain.
        self.energy -= self.get_energy_drain()

        threat_x, threat_y, threat_level = self._get_threat_vector(carnivores)
        pheromone_x = 0.0
        pheromone_y = 0.0
        pheromone_level = 0.0
        relay_signal_level = 0.0
        if COMMUNICATION_ENABLED and pheromone_field is not None:
            pheromone_x, pheromone_y, pheromone_level, relay_signal_level = pheromone_field.get_danger_vector(
                self.x,
                self.y,
                PHEROMONE_SEARCH_RADIUS,
                species_tag="prey",
            )

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
                PHEROMONE_MATE_SEARCH_RADIUS_PREY,
                "prey",
                ignore_source_id=id(self),
            )

        combined_threat_level = max(threat_level, pheromone_level * 0.85, relay_signal_level)

        alarm_emitted, relay_emitted = self._emit_communication(pheromone_field, threat_level, nearby_motes)

        mate_target = None
        if SEXUAL_REPRODUCTION_ENABLED:
            if self.is_ready_to_mate():
                if self.reproduction_state not in ("SEEK_MATE", "MATING"):
                    self.reproduction_state = "SEEK_MATE"
                if nearby_motes:
                    mate_target = self.get_nearest_mate(nearby_motes)
            elif self.reproduction_state == "SEEK_MATE":
                self.reproduction_state = "IDLE"
                self.mate_partner = None
                self.mating_progress_frames = 0

            if combined_threat_level >= PREY_FLEE_PRIORITY_THRESHOLD and self.reproduction_state == "SEEK_MATE":
                self.reproduction_state = "IDLE"
                self.mate_partner = None
                self.mating_progress_frames = 0
                mate_target = None

            if self.reproduction_state == "SEEK_MATE":
                self._emit_mate_pheromone(pheromone_field)

        target_speed = movement_speed
        if threat_level > 0.0:
            target_speed = movement_speed * min(
                PREY_MAX_ESCAPE_SPEED_MULT,
                1.0 + (threat_level * PREY_FLEE_PANIC_SPEED_MULT),
            )
        elif pheromone_level > 0.0:
            target_speed = movement_speed * min(
                PREY_MAX_ESCAPE_SPEED_MULT,
                1.0 + (pheromone_level * PREY_FLEE_PANIC_SPEED_MULT * 0.85),
            )

        nearest_food = self.get_nearest_food(foods)
        if nearest_food and threat_level <= 0.0 and pheromone_level >= PHEROMONE_FOOD_AVOID_THRESHOLD:
            nearest_food = None

        desired_vx = self.vx
        desired_vy = self.vy
        seek_mode = False
        reproduction_seek_mode = False

        if (
            SEXUAL_REPRODUCTION_ENABLED
            and self.reproduction_state == "SEEK_MATE"
            and combined_threat_level < PREY_FLEE_PRIORITY_THRESHOLD
        ):
            if mate_target is not None:
                dx = mate_target.x - self.x
                dy = mate_target.y - self.y
                dist = math.hypot(dx, dy)
                if dist > 0:
                    desired_vx = (dx / dist) * movement_speed
                    desired_vy = (dy / dist) * movement_speed
                    reproduction_seek_mode = True
            else:
                if mate_pheromone_level > 0.0:
                    if mate_pheromone_level >= 0.08:
                        desired_vx = mate_pheromone_x * movement_speed
                        desired_vy = mate_pheromone_y * movement_speed
                    else:
                        blend = min(0.88, max(0.3, mate_pheromone_level * PHEROMONE_MATE_BLEND_WEIGHT))
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
                else:
                    self.wander_angle += random.uniform(-0.16, 0.16)
                    desired_vx = math.cos(self.wander_angle) * movement_speed
                    desired_vy = math.sin(self.wander_angle) * movement_speed
                reproduction_seek_mode = True
        elif nearest_food:
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

        flee_x = 0.0
        flee_y = 0.0
        if combined_threat_level > 0.0:
            if threat_level > 0.0 and pheromone_level > 0.0:
                comm_weight = min(0.65, pheromone_level * PHEROMONE_SIGNAL_BLEND_WEIGHT)
                flee_x = (threat_x * (1.0 - comm_weight)) + (pheromone_x * comm_weight)
                flee_y = (threat_y * (1.0 - comm_weight)) + (pheromone_y * comm_weight)
            elif threat_level > 0.0:
                flee_x = threat_x
                flee_y = threat_y
            else:
                flee_x = pheromone_x
                flee_y = pheromone_y

            flee_mag = math.hypot(flee_x, flee_y)
            if flee_mag > 1e-6:
                flee_x /= flee_mag
                flee_y /= flee_mag

        if combined_threat_level >= PREY_FLEE_PRIORITY_THRESHOLD:
            desired_vx = flee_x * target_speed
            desired_vy = flee_y * target_speed
        elif combined_threat_level > 0.0:
            flee_vx = flee_x * target_speed
            flee_vy = flee_y * target_speed
            blend = min(0.85, combined_threat_level * PREY_FLEE_BLEND_WEIGHT)
            if threat_level <= 0.0 and pheromone_level > 0.0:
                blend = min(0.75, blend + (PHEROMONE_SIGNAL_BLEND_WEIGHT * 0.25))
            desired_vx = (desired_vx * (1.0 - blend)) + (flee_vx * blend)
            desired_vy = (desired_vy * (1.0 - blend)) + (flee_vy * blend)

        if combined_threat_level > 0.0:
            steer_factor = self.turn_factor * 2.2
        elif reproduction_seek_mode:
            steer_factor = self.turn_factor * (2.6 if mate_pheromone_level > 0.0 else 2.1)
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

        return {
            "alarm_emitted": alarm_emitted,
            "relay_emitted": relay_emitted,
        }

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
            self._draw_reproduction_indicator(surface)
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
        self._draw_reproduction_indicator(surface)
