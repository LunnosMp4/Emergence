import math
import os
import random
import time

import pygame

from src.config import *
from src.entities import Carnivore, Food, Mote, load_sprite_frames
from src.metrics.logger import MetricsLogger, MetricsSnapshot


class Simulation:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Mote Ecosystem V1")
        self.clock = pygame.time.Clock()
        self.background_surface = None
        self._load_background_asset()
        self._load_sprite_assets()

        self.foods = []
        self.motes = [
            Mote(
                random.randint(0, WIDTH),
                random.randint(0, HEIGHT),
                size=random.uniform(PREY_MIN_SIZE, PREY_BASE_SIZE + 0.1),
            )
            for _ in range(INITIAL_MOTE_COUNT)
        ]
        self.carnivores = []
        if ENABLE_PREDATORS:
            self.carnivores = [
                Carnivore(
                    random.randint(0, WIDTH),
                    random.randint(0, HEIGHT),
                    speed=CARNIVORE_BASE_SPEED + random.uniform(-0.12, 0.12),
                    vision=CARNIVORE_BASE_VISION + random.uniform(-8.0, 8.0),
                    size=CARNIVORE_BASE_SIZE + random.uniform(-0.06, 0.06),
                )
                for _ in range(INITIAL_CARNIVORE_COUNT)
            ]
        self.running = True

        self.metrics_logger = MetricsLogger(
            file_path=METRICS_OUTPUT_PATH,
            batch_size=METRICS_BATCH_SIZE,
            flush_interval_seconds=METRICS_FLUSH_INTERVAL_SECONDS,
            queue_size=METRICS_QUEUE_SIZE,
            max_file_bytes=METRICS_MAX_FILE_BYTES,
            reset_on_start=METRICS_RESET_ON_START,
        )
        self.metrics_logger.start()
        self.metrics_history = self._load_metric_history(METRICS_OUTPUT_PATH, GRAPH_HISTORY_POINTS)

        self.start_time = time.time()
        self.frame_count = 0
        self.ecosystem_stress_index = 0.0
        self.adaptive_mode_active = False
        self._adaptive_trigger_counter = 0
        self._adaptive_active_frames = 0
        self._adaptive_cooldown_frames = 0

        self.overlay_font = pygame.font.Font(None, 22)
        self.graph_title_font = pygame.font.Font(None, 22)
        self.graph_legend_font = pygame.font.Font(None, 16)
        self.overlay_text_surface = None
        self.overlay_bg_surface = None
        self.graph_surface = None
        self._update_overlay_text(
            0.0,
            len(self.motes),
            len(self.foods),
            len(self.carnivores),
            self.ecosystem_stress_index,
            self.adaptive_mode_active,
        )
        self._update_graph_surface()
        self._collect_and_log_metrics()

    def _load_sprite_variants_from_directory(self, relative_directory, label):
        directory_path = os.path.join(PROJECT_ROOT, relative_directory)
        variants = []

        try:
            directory_entries = sorted(os.listdir(directory_path))
        except OSError as exc:
            print(f"Warning: failed to list {label} sprite directory ({directory_path}): {exc}")
            return variants

        for entry_name in directory_entries:
            if not entry_name.lower().endswith(SPRITE_FILE_EXTENSIONS):
                continue

            sprite_sheet_path = os.path.join(directory_path, entry_name)
            if not os.path.isfile(sprite_sheet_path):
                continue

            try:
                variants.append(load_sprite_frames(sprite_sheet_path))
            except (pygame.error, OSError) as exc:
                print(f"Warning: failed to load {label} spritesheet ({sprite_sheet_path}): {exc}")

        if not variants:
            print(f"Warning: no valid {label} spritesheets found in {directory_path}")

        return variants

    def _load_sprite_assets(self):
        carnivore_sheet = os.path.join(PROJECT_ROOT, CARNIVORE_SPRITESHEET_PATH)
        fallback_mote_sheet = os.path.join(PROJECT_ROOT, MOTE_SPRITESHEET_PATH)

        prey_variants = self._load_sprite_variants_from_directory(PREY_SPRITES_DIR, "prey")
        if prey_variants:
            Mote.set_sprite_variants(prey_variants)
        else:
            try:
                Mote.set_sprite_frames(load_sprite_frames(fallback_mote_sheet))
            except (pygame.error, OSError) as exc:
                print(f"Warning: failed to load fallback prey spritesheet ({fallback_mote_sheet}): {exc}")
                Mote.set_sprite_frames([])

        crop_variants = self._load_sprite_variants_from_directory(CROP_SPRITES_DIR, "crop")
        Food.set_sprite_variants(crop_variants)

        try:
            Carnivore.set_sprite_frames(load_sprite_frames(carnivore_sheet))
        except (pygame.error, OSError) as exc:
            print(f"Warning: failed to load carnivore spritesheet ({carnivore_sheet}): {exc}")
            Carnivore.set_sprite_frames([])

    def _load_background_asset(self):
        background_path = os.path.join(PROJECT_ROOT, BACKGROUND_TEXTURE_PATH)

        try:
            background_image = pygame.image.load(background_path).convert()
            self.background_surface = pygame.transform.scale(background_image, (WIDTH, HEIGHT))
        except (pygame.error, OSError) as exc:
            print(f"Warning: failed to load background texture ({background_path}): {exc}")
            self.background_surface = None

    def _compute_ecosystem_stress(self):
        prey_count = len(self.motes)
        predator_count = len(self.carnivores)

        if prey_count <= 0:
            return 1.0

        prey_floor = max(1, int(INITIAL_MOTE_COUNT * ADAPTIVE_PREY_FLOOR_RATIO))
        prey_pressure = max(0.0, (prey_floor - prey_count) / prey_floor)

        predator_ratio = predator_count / max(1, prey_count)
        ratio_band = max(1e-6, ADAPTIVE_RATIO_DANGER - ADAPTIVE_RATIO_SOFT)
        ratio_pressure = max(0.0, min(1.0, (predator_ratio - ADAPTIVE_RATIO_SOFT) / ratio_band))

        trend_pressure = 0.0
        recent_history = self.metrics_history[-8:]
        if len(recent_history) >= 4:
            first_population = recent_history[0].population
            last_population = recent_history[-1].population
            if first_population > 0:
                decline = (first_population - last_population) / first_population
                trend_pressure = max(0.0, min(1.0, decline))

        combined_stress = (prey_pressure * 0.45) + (ratio_pressure * 0.4) + (trend_pressure * 0.15)
        return min(1.0, max(0.0, combined_stress))

    def _update_adaptive_mode(self):
        if not ADAPTIVE_BALANCING_ENABLED:
            self.ecosystem_stress_index = 0.0
            self.adaptive_mode_active = False
            return

        self.ecosystem_stress_index = self._compute_ecosystem_stress()

        if self._adaptive_cooldown_frames > 0:
            self._adaptive_cooldown_frames -= 1

        if self.adaptive_mode_active:
            self._adaptive_active_frames += 1

            should_release = (
                self._adaptive_active_frames >= ADAPTIVE_MIN_ACTIVE_FRAMES
                and self.ecosystem_stress_index <= ADAPTIVE_STRESS_RELEASE
            )
            force_release = self._adaptive_active_frames >= ADAPTIVE_MAX_ACTIVE_FRAMES

            if should_release or force_release:
                self.adaptive_mode_active = False
                self._adaptive_active_frames = 0
                self._adaptive_cooldown_frames = ADAPTIVE_COOLDOWN_FRAMES
                self._adaptive_trigger_counter = 0
            return

        if self._adaptive_cooldown_frames > 0:
            return

        if self.ecosystem_stress_index >= ADAPTIVE_STRESS_TRIGGER:
            self._adaptive_trigger_counter += 1
        else:
            self._adaptive_trigger_counter = max(0, self._adaptive_trigger_counter - 1)

        if self._adaptive_trigger_counter >= ADAPTIVE_TRIGGER_FRAMES:
            self.adaptive_mode_active = True
            self._adaptive_active_frames = 0
            self._adaptive_trigger_counter = 0

    def _load_metric_history(self, file_path, max_points):
        if not os.path.exists(file_path) or max_points <= 0:
            return []

        lines = self._read_tail_lines(file_path, max_points + 1)
        history = []

        for line in lines:
            if not line or line.startswith("timestamp"):
                continue

            parts = line.strip().split(",")
            try:
                if len(parts) >= 14:
                    carnivore_population = int(parts[7])
                    avg_carnivore_speed = float(parts[8])
                    avg_carnivore_energy = float(parts[9])
                    avg_carnivore_size = float(parts[10])
                    predator_prey_ratio = float(parts[11])
                    ecosystem_stress_index = float(parts[12])
                    adaptive_mode_active = int(parts[13])
                elif len(parts) >= 12:
                    carnivore_population = int(parts[7])
                    avg_carnivore_speed = float(parts[8])
                    avg_carnivore_energy = float(parts[9])
                    avg_carnivore_size = float(parts[10])
                    predator_prey_ratio = float(parts[11])
                    ecosystem_stress_index = 0.0
                    adaptive_mode_active = 0
                elif len(parts) == 7:
                    carnivore_population = 0
                    avg_carnivore_speed = 0.0
                    avg_carnivore_energy = 0.0
                    avg_carnivore_size = 0.0
                    predator_prey_ratio = 0.0
                    ecosystem_stress_index = 0.0
                    adaptive_mode_active = 0
                else:
                    continue

                history.append(
                    MetricsSnapshot(
                        timestamp=float(parts[0]),
                        elapsed_seconds=float(parts[1]),
                        population=int(parts[2]),
                        food_count=int(parts[3]),
                        avg_speed=float(parts[4]),
                        avg_vision_radius=float(parts[5]),
                        max_generation=int(parts[6]),
                        carnivore_population=carnivore_population,
                        avg_carnivore_speed=avg_carnivore_speed,
                        avg_carnivore_energy=avg_carnivore_energy,
                        avg_carnivore_size=avg_carnivore_size,
                        predator_prey_ratio=predator_prey_ratio,
                        ecosystem_stress_index=ecosystem_stress_index,
                        adaptive_mode_active=adaptive_mode_active,
                    )
                )
            except ValueError:
                continue

        return history[-max_points:]

    def _read_tail_lines(self, file_path, line_count):
        if line_count <= 0:
            return []

        block_size = 2048
        data = b""
        lines = []

        try:
            with open(file_path, "rb") as handle:
                handle.seek(0, os.SEEK_END)
                cursor = handle.tell()

                while cursor > 0 and len(lines) <= line_count:
                    read_size = min(block_size, cursor)
                    cursor -= read_size
                    handle.seek(cursor)
                    data = handle.read(read_size) + data
                    lines = data.splitlines()
        except OSError:
            return []

        decoded = []
        for raw_line in lines[-line_count:]:
            try:
                decoded.append(raw_line.decode("utf-8"))
            except UnicodeDecodeError:
                continue

        return decoded

    def _collect_and_log_metrics(self):
        population = len(self.motes)
        food_count = len(self.foods)
        carnivore_population = len(self.carnivores)

        total_speed = 0.0
        total_vision = 0.0
        max_generation = 0
        total_carnivore_speed = 0.0
        total_carnivore_energy = 0.0
        total_carnivore_size = 0.0

        for mote in self.motes:
            total_speed += mote.speed
            total_vision += mote.vision_radius
            if mote.generation > max_generation:
                max_generation = mote.generation

        if population > 0:
            avg_speed = total_speed / population
            avg_vision_radius = total_vision / population
        else:
            avg_speed = 0.0
            avg_vision_radius = 0.0

        for carnivore in self.carnivores:
            total_carnivore_speed += carnivore.speed
            total_carnivore_energy += carnivore.energy
            total_carnivore_size += carnivore.size

        if carnivore_population > 0:
            avg_carnivore_speed = total_carnivore_speed / carnivore_population
            avg_carnivore_energy = total_carnivore_energy / carnivore_population
            avg_carnivore_size = total_carnivore_size / carnivore_population
        else:
            avg_carnivore_speed = 0.0
            avg_carnivore_energy = 0.0
            avg_carnivore_size = 0.0

        predator_prey_ratio = carnivore_population / max(1, population)

        timestamp = time.time()
        elapsed_seconds = timestamp - self.start_time

        snapshot = MetricsSnapshot(
            timestamp=timestamp,
            elapsed_seconds=elapsed_seconds,
            population=population,
            food_count=food_count,
            avg_speed=avg_speed,
            avg_vision_radius=avg_vision_radius,
            max_generation=max_generation,
            carnivore_population=carnivore_population,
            avg_carnivore_speed=avg_carnivore_speed,
            avg_carnivore_energy=avg_carnivore_energy,
            avg_carnivore_size=avg_carnivore_size,
            predator_prey_ratio=predator_prey_ratio,
            ecosystem_stress_index=self.ecosystem_stress_index,
            adaptive_mode_active=int(self.adaptive_mode_active),
        )
        self.metrics_logger.log_snapshot(snapshot)

        self.metrics_history.append(snapshot)
        if len(self.metrics_history) > GRAPH_HISTORY_POINTS:
            del self.metrics_history[: len(self.metrics_history) - GRAPH_HISTORY_POINTS]

        self._update_overlay_text(
            elapsed_seconds,
            population,
            food_count,
            carnivore_population,
            self.ecosystem_stress_index,
            self.adaptive_mode_active,
        )
        self._update_graph_surface()

    def _update_overlay_text(
        self,
        elapsed_seconds,
        population,
        food_count,
        carnivore_count,
        ecosystem_stress=0.0,
        adaptive_mode=False,
    ):
        runtime_text = time.strftime("%H:%M:%S", time.gmtime(elapsed_seconds))
        adaptive_label = "ON" if adaptive_mode else "OFF"
        overlay_text = (
            f"{runtime_text} | Prey: {population} | Pred: {carnivore_count} | "
            f"Food: {food_count} | Stress: {ecosystem_stress:.2f} | Aid: {adaptive_label}"
        )
        self.overlay_text_surface = self.overlay_font.render(overlay_text, True, OVERLAY_TEXT_COLOR)
        self.overlay_bg_surface = pygame.Surface(
            (self.overlay_text_surface.get_width() + 16, self.overlay_text_surface.get_height() + 10),
            pygame.SRCALPHA,
        )
        pygame.draw.rect(
            self.overlay_bg_surface,
            OVERLAY_BG_COLOR,
            self.overlay_bg_surface.get_rect(),
            border_radius=OVERLAY_BORDER_RADIUS,
        )
        pygame.draw.rect(
            self.overlay_bg_surface,
            OVERLAY_BORDER_COLOR,
            self.overlay_bg_surface.get_rect(),
            width=1,
            border_radius=OVERLAY_BORDER_RADIUS,
        )

    def _smooth_points(self, points):
        if len(points) < 3:
            return points

        smoothed = points
        for _ in range(2):
            if len(smoothed) < 3:
                break

            refined = [smoothed[0]]
            for left, right in zip(smoothed[:-1], smoothed[1:]):
                qx = (0.75 * left[0]) + (0.25 * right[0])
                qy = (0.75 * left[1]) + (0.25 * right[1])
                rx = (0.25 * left[0]) + (0.75 * right[0])
                ry = (0.25 * left[1]) + (0.75 * right[1])
                refined.append((qx, qy))
                refined.append((rx, ry))
            refined.append(smoothed[-1])
            smoothed = refined

        return smoothed

    def _build_series_points(self, values, chart_rect):
        if not values:
            return []

        if len(values) == 1:
            return [(chart_rect.left, chart_rect.centery)]

        min_value = min(values)
        max_value = max(values)
        value_range = max_value - min_value

        points = []
        for index, value in enumerate(values):
            x = chart_rect.left + (index / (len(values) - 1)) * chart_rect.width

            if value_range <= 1e-9:
                normalized = 0.5
            else:
                normalized = (value - min_value) / value_range

            y = chart_rect.bottom - (normalized * chart_rect.height)
            points.append((x, y))

        return points

    def _draw_graph_series(self, surface, chart_rect, values, color):
        base_points = self._build_series_points(values, chart_rect)
        if len(base_points) < 2:
            return

        smooth_points = self._smooth_points(base_points)
        draw_points = [(int(x), int(y)) for x, y in smooth_points]

        if len(draw_points) < 2:
            return

        pygame.draw.lines(surface, color, False, draw_points, 2)
        pygame.draw.aalines(surface, color, False, draw_points)
        end_x, end_y = base_points[-1]
        pygame.draw.circle(surface, color, (int(end_x), int(end_y)), 3)

    def _update_graph_surface(self):
        panel_width, panel_height = GRAPH_PANEL_SIZE
        self.graph_surface = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel_rect = self.graph_surface.get_rect()

        pygame.draw.rect(
            self.graph_surface,
            GRAPH_PANEL_BG_COLOR,
            panel_rect,
            border_radius=GRAPH_PANEL_RADIUS,
        )
        pygame.draw.rect(
            self.graph_surface,
            GRAPH_PANEL_BORDER_COLOR,
            panel_rect,
            width=1,
            border_radius=GRAPH_PANEL_RADIUS,
        )

        title_surface = self.graph_title_font.render("Live Metrics", True, GRAPH_TITLE_COLOR)
        self.graph_surface.blit(title_surface, (12, 8))

        chart_rect = pygame.Rect(12, 30, panel_width - 24, panel_height - 52)

        for grid_step in range(1, 4):
            y = chart_rect.top + int((grid_step / 4) * chart_rect.height)
            pygame.draw.line(
                self.graph_surface,
                GRAPH_GRID_COLOR,
                (chart_rect.left, y),
                (chart_rect.right, y),
                1,
            )

        history = self.metrics_history[-GRAPH_HISTORY_POINTS:]
        if len(history) < 2:
            hint_surface = self.graph_legend_font.render("Collecting data...", True, GRAPH_HINT_COLOR)
            self.graph_surface.blit(hint_surface, (12, panel_height - 18))
            return

        population_values = [snapshot.population for snapshot in history]
        speed_values = [snapshot.avg_speed for snapshot in history]
        vision_values = [snapshot.avg_vision_radius for snapshot in history]
        predator_values = [snapshot.carnivore_population for snapshot in history]
        ratio_values = [snapshot.predator_prey_ratio for snapshot in history]
        stress_values = [snapshot.ecosystem_stress_index for snapshot in history]

        self._draw_graph_series(self.graph_surface, chart_rect, population_values, GRAPH_POPULATION_COLOR)
        self._draw_graph_series(self.graph_surface, chart_rect, speed_values, GRAPH_SPEED_COLOR)
        self._draw_graph_series(self.graph_surface, chart_rect, vision_values, GRAPH_VISION_COLOR)
        self._draw_graph_series(self.graph_surface, chart_rect, predator_values, GRAPH_PREDATOR_COLOR)
        self._draw_graph_series(self.graph_surface, chart_rect, ratio_values, GRAPH_RATIO_COLOR)
        self._draw_graph_series(self.graph_surface, chart_rect, stress_values, GRAPH_STRESS_COLOR)

        pop_legend = self.graph_legend_font.render("POP", True, GRAPH_POPULATION_COLOR)
        speed_legend = self.graph_legend_font.render("SPD", True, GRAPH_SPEED_COLOR)
        vision_legend = self.graph_legend_font.render("VIS", True, GRAPH_VISION_COLOR)
        predator_legend = self.graph_legend_font.render("PRD", True, GRAPH_PREDATOR_COLOR)
        ratio_legend = self.graph_legend_font.render("RAT", True, GRAPH_RATIO_COLOR)
        stress_legend = self.graph_legend_font.render("STR", True, GRAPH_STRESS_COLOR)
        self.graph_surface.blit(pop_legend, (12, panel_height - 18))
        self.graph_surface.blit(speed_legend, (50, panel_height - 18))
        self.graph_surface.blit(vision_legend, (88, panel_height - 18))
        self.graph_surface.blit(predator_legend, (126, panel_height - 18))
        self.graph_surface.blit(ratio_legend, (164, panel_height - 18))
        self.graph_surface.blit(stress_legend, (202, panel_height - 18))

    def _draw_overlay(self):
        if self.overlay_text_surface is None or self.overlay_bg_surface is None:
            return

        self.screen.blit(self.overlay_bg_surface, OVERLAY_POS)
        self.screen.blit(self.overlay_text_surface, (OVERLAY_POS[0] + 8, OVERLAY_POS[1] + 5))

        if self.graph_surface is not None:
            graph_x = OVERLAY_POS[0]
            graph_y = OVERLAY_POS[1] + self.overlay_bg_surface.get_height() + GRAPH_PANEL_GAP
            self.screen.blit(self.graph_surface, (graph_x, graph_y))

    def run(self):
        try:
            while self.running:
                self._update_adaptive_mode()

                if self.background_surface is not None:
                    self.screen.blit(self.background_surface, (0, 0))
                else:
                    self.screen.fill(BG_COLOR)

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False

                food_spawn_chance = FOOD_SPAWN_CHANCE
                if ADAPTIVE_BALANCING_ENABLED and self.adaptive_mode_active:
                    food_spawn_chance *= ADAPTIVE_FOOD_SPAWN_MULT

                if len(self.foods) < MAX_FOOD and random.random() < min(0.95, food_spawn_chance):
                    self.foods.append(Food())

                for food in self.foods:
                    food.draw(self.screen)

                new_motes = []
                alive_motes = []
                new_carnivores = []
                alive_carnivores = []
                consumed_mote_ids = set()

                if ENABLE_PREDATORS:
                    for carnivore in self.carnivores:
                        carnivore.update(self.motes)

                        if ADAPTIVE_BALANCING_ENABLED and self.adaptive_mode_active:
                            carnivore.energy -= ADAPTIVE_PREDATOR_DRAIN_BONUS

                        if carnivore.energy <= 0:
                            continue

                        colliding_mote = None
                        closest_dist = float("inf")
                        for mote in self.motes:
                            mote_id = id(mote)
                            if mote_id in consumed_mote_ids:
                                continue

                            dist = math.hypot(mote.x - carnivore.x, mote.y - carnivore.y)
                            attack_reach = carnivore.radius + mote.radius + CARNIVORE_ATTACK_REACH_BONUS
                            if dist < attack_reach and dist < closest_dist:
                                closest_dist = dist
                                colliding_mote = mote

                        if (
                            colliding_mote is not None
                            and carnivore.attack_cooldown <= 0
                            and carnivore.can_attack_target(colliding_mote)
                        ):
                            if carnivore.can_consume(colliding_mote):
                                energy_reward = CARNIVORE_KILL_ENERGY_REWARD
                                if ADAPTIVE_BALANCING_ENABLED and self.adaptive_mode_active:
                                    energy_reward *= ADAPTIVE_KILL_REWARD_MULT

                                consumed_mote_ids.add(id(colliding_mote))
                                carnivore.energy = min(
                                    CARNIVORE_MAX_ENERGY,
                                    carnivore.energy + energy_reward,
                                )
                                carnivore.on_successful_hunt(colliding_mote)
                                carnivore.attack_cooldown = max(
                                    CARNIVORE_ATTACK_COOLDOWN_FRAMES,
                                    CARNIVORE_DIGEST_COOLDOWN_FRAMES,
                                )
                            else:
                                carnivore.energy -= CARNIVORE_FAILED_ATTACK_PENALTY
                                carnivore.on_failed_attack(colliding_mote)
                                carnivore.attack_cooldown = CARNIVORE_ATTACK_COOLDOWN_FRAMES

                        active_predator_count = len(alive_carnivores) + len(new_carnivores) + 1
                        remaining_prey = max(0, len(self.motes) - len(consumed_mote_ids))
                        prey_ratio = remaining_prey / max(1, active_predator_count)
                        required_prey_ratio = CARNIVORE_MIN_PREY_PER_PREDATOR
                        if ADAPTIVE_BALANCING_ENABLED and self.adaptive_mode_active:
                            required_prey_ratio *= ADAPTIVE_REPRODUCTION_GATE_MULT

                        if (
                            carnivore.energy >= CARNIVORE_REPRODUCTION_THRESHOLD
                            and carnivore.reproduction_cooldown <= 0
                            and active_predator_count < MAX_CARNIVORES
                            and prey_ratio >= required_prey_ratio
                        ):
                            carnivore.energy = CARNIVORE_POST_REPRODUCTION_ENERGY
                            carnivore.reproduction_cooldown = CARNIVORE_REPRODUCTION_COOLDOWN_FRAMES

                            mutated_speed = max(
                                CARNIVORE_MIN_SPEED,
                                min(
                                    CARNIVORE_MAX_SPEED,
                                    carnivore.speed + random.uniform(*CARNIVORE_SPEED_MUTATION_RANGE),
                                ),
                            )
                            mutated_vision = max(
                                CARNIVORE_MIN_VISION,
                                min(
                                    CARNIVORE_MAX_VISION,
                                    carnivore.vision_radius + random.uniform(*CARNIVORE_VISION_MUTATION_RANGE),
                                ),
                            )
                            mutated_size = carnivore.size * (
                                1.0 + random.uniform(-CARNIVORE_SIZE_MUTATION_RATIO, CARNIVORE_SIZE_MUTATION_RATIO)
                            )
                            mutated_size = max(CARNIVORE_MIN_SIZE, min(CARNIVORE_MAX_SIZE, mutated_size))

                            child = Carnivore(
                                carnivore.x,
                                carnivore.y,
                                speed=mutated_speed,
                                vision=mutated_vision,
                                size=mutated_size,
                                energy=CARNIVORE_OFFSPRING_ENERGY,
                                generation=carnivore.generation + 1,
                            )
                            child.reproduction_cooldown = CARNIVORE_REPRODUCTION_COOLDOWN_FRAMES // 2
                            new_carnivores.append(child)

                        if carnivore.energy > 0:
                            alive_carnivores.append(carnivore)

                active_carnivores = self.carnivores if ENABLE_PREDATORS else None

                for mote in self.motes:
                    if id(mote) in consumed_mote_ids:
                        continue

                    mote.update(self.foods, active_carnivores)

                    if mote.energy <= 0:
                        continue

                    for food in self.foods[:]:
                        if not food.is_grown():
                            continue

                        dist = math.hypot(food.x - mote.x, food.y - mote.y)
                        if dist < mote.radius + food.radius:
                            mote.energy += food.energy_value
                            self.foods.remove(food)

                    if mote.energy >= MOTE_REPRODUCTION_THRESHOLD:
                        mote.energy = MOTE_POST_REPRODUCTION_ENERGY
                        mutated_speed = max(MOTE_MIN_SPEED, mote.speed + random.uniform(*MOTE_SPEED_MUTATION_RANGE))
                        mutated_vision = max(MOTE_MIN_VISION, mote.vision_radius + random.uniform(*MOTE_VISION_MUTATION_RANGE))
                        mutated_size = mote.size * (
                            1.0 + random.uniform(-PREY_SIZE_MUTATION_RATIO, PREY_SIZE_MUTATION_RATIO)
                        )
                        mutated_size = max(PREY_MIN_SIZE, min(PREY_MAX_SIZE, mutated_size))
                        child = Mote(
                            mote.x,
                            mote.y,
                            speed=mutated_speed,
                            vision=mutated_vision,
                            size=mutated_size,
                            energy=MOTE_POST_REPRODUCTION_ENERGY,
                            generation=mote.generation + 1,
                        )
                        new_motes.append(child)

                    alive_motes.append(mote)
                    mote.draw(self.screen)

                self.motes = alive_motes + new_motes
                if ENABLE_PREDATORS:
                    self.carnivores = alive_carnivores + new_carnivores
                else:
                    self.carnivores = []

                for carnivore in self.carnivores:
                    carnivore.draw(self.screen)

                self.frame_count += 1

                if self.frame_count % METRICS_SAMPLE_FRAMES == 0:
                    self._collect_and_log_metrics()

                self._draw_overlay()
                pygame.display.flip()
                self.clock.tick(FPS)
        finally:
            self.metrics_logger.stop()
            pygame.quit()
