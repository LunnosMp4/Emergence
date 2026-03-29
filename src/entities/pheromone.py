from dataclasses import dataclass
import math


@dataclass
class PheromoneMarker:
    x: float
    y: float
    intensity: float
    marker_type: str
    species_tag: str | None = None
    source_id: int | None = None
    age_frames: int = 0
    max_age_frames: int = 120

    @property
    def freshness(self) -> float:
        if self.max_age_frames <= 0:
            return 0.0
        return max(0.0, 1.0 - (self.age_frames / self.max_age_frames))


class PheromoneField:
    TYPE_WEIGHT = {
        "alarm": 1.00,
        "relay": 0.90,
        "distress": 1.20,
        "kill_site": 1.08,
        "mate": 0.95,
    }

    def __init__(self, max_markers: int = 120) -> None:
        self.max_markers = max(10, max_markers)
        self._markers: list[PheromoneMarker] = []

    def emit(
        self,
        x: float,
        y: float,
        intensity: float,
        marker_type: str,
        max_age_frames: int,
        species_tag: str | None = None,
        source_id: int | None = None,
    ) -> bool:
        clamped_intensity = max(0.05, min(1.0, intensity))
        marker = PheromoneMarker(
            x=x,
            y=y,
            intensity=clamped_intensity,
            marker_type=marker_type,
            species_tag=species_tag,
            source_id=source_id,
            age_frames=0,
            max_age_frames=max(1, int(max_age_frames)),
        )

        if len(self._markers) >= self.max_markers:
            # Drop the oldest signal first to keep memory and CPU bounded.
            self._markers.pop(0)

        self._markers.append(marker)
        return True

    def tick(self) -> None:
        alive_markers = []
        for marker in self._markers:
            marker.age_frames += 1
            if marker.age_frames < marker.max_age_frames and marker.intensity > 0.01:
                alive_markers.append(marker)
        self._markers = alive_markers

    def active_count(self) -> int:
        return len(self._markers)

    def iter_markers(self) -> tuple[PheromoneMarker, ...]:
        return tuple(self._markers)

    def get_danger_vector(
        self,
        x: float,
        y: float,
        search_radius: float,
        species_tag: str | None = None,
    ) -> tuple[float, float, float, float]:
        if not self._markers:
            return 0.0, 0.0, 0.0, 0.0

        steer_x = 0.0
        steer_y = 0.0
        strongest_signal = 0.0
        relay_signal = 0.0
        radius = max(1.0, search_radius)
        radius_sq = radius * radius

        for marker in self._markers:
            if marker.marker_type == "mate":
                continue

            if species_tag is not None and marker.species_tag is not None and marker.species_tag != species_tag:
                continue

            dx = x - marker.x
            dy = y - marker.y
            dist_sq = (dx * dx) + (dy * dy)
            if dist_sq <= 1e-6 or dist_sq > radius_sq:
                continue

            dist = math.sqrt(dist_sq)
            proximity = max(0.0, 1.0 - (dist / radius))
            marker_weight = self.TYPE_WEIGHT.get(marker.marker_type, 1.0)
            weight = marker.intensity * marker.freshness * proximity * marker_weight

            if weight <= 1e-6:
                continue

            steer_x += (dx / dist) * weight
            steer_y += (dy / dist) * weight
            strongest_signal = max(strongest_signal, weight)

            if marker.marker_type == "relay":
                relay_signal = max(relay_signal, weight)

        magnitude = math.hypot(steer_x, steer_y)
        if magnitude <= 1e-6:
            return 0.0, 0.0, 0.0, min(1.0, relay_signal)

        return (
            steer_x / magnitude,
            steer_y / magnitude,
            min(1.0, strongest_signal),
            min(1.0, relay_signal),
        )

    def get_mate_vector(
        self,
        x: float,
        y: float,
        search_radius: float,
        species_tag: str,
        ignore_source_id: int | None = None,
    ) -> tuple[float, float, float]:
        if not self._markers:
            return 0.0, 0.0, 0.0

        steer_x = 0.0
        steer_y = 0.0
        strongest_signal = 0.0
        dominant_x = 0.0
        dominant_y = 0.0
        dominant_weight = 0.0
        radius = max(1.0, search_radius)
        radius_sq = radius * radius

        for marker in self._markers:
            if marker.marker_type != "mate":
                continue

            if marker.species_tag != species_tag:
                continue

            if ignore_source_id is not None and marker.source_id == ignore_source_id:
                continue

            dx = marker.x - x
            dy = marker.y - y
            dist_sq = (dx * dx) + (dy * dy)
            if dist_sq <= 1e-6 or dist_sq > radius_sq:
                continue

            dist = math.sqrt(dist_sq)
            proximity = max(0.0, 1.0 - (dist / radius))
            marker_weight = self.TYPE_WEIGHT.get(marker.marker_type, 1.0)
            signal_strength = marker.intensity * marker.freshness * marker_weight
            # Keep long-range detectability while still preferring closer trails.
            weight = signal_strength * (0.25 + (0.75 * proximity))
            if signal_strength <= 1e-6 or weight <= 1e-6:
                continue

            dir_x = dx / dist
            dir_y = dy / dist
            steer_x += dir_x * weight
            steer_y += dir_y * weight
            strongest_signal = max(strongest_signal, signal_strength * proximity)

            if weight > dominant_weight:
                dominant_weight = weight
                dominant_x = dir_x
                dominant_y = dir_y

        if dominant_weight > 1e-6:
            dominance = min(0.72, max(0.20, dominant_weight))
            steer_x = (steer_x * (1.0 - dominance)) + (dominant_x * dominance)
            steer_y = (steer_y * (1.0 - dominance)) + (dominant_y * dominance)

        magnitude = math.hypot(steer_x, steer_y)
        if magnitude <= 1e-6:
            return 0.0, 0.0, 0.0

        return (
            steer_x / magnitude,
            steer_y / magnitude,
            min(1.0, strongest_signal),
        )
