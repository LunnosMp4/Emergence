from __future__ import annotations

import csv
import io
import os
import queue
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricsSnapshot:
    timestamp: float
    elapsed_seconds: float
    population: int
    food_count: int
    avg_speed: float
    avg_vision_radius: float
    max_generation: int
    carnivore_population: int
    avg_carnivore_speed: float
    avg_carnivore_energy: float
    avg_carnivore_size: float
    predator_prey_ratio: float
    ecosystem_stress_index: float
    adaptive_mode_active: int


class MetricsLogger:
    CSV_HEADER = (
        "timestamp",
        "elapsed_seconds",
        "population",
        "food_count",
        "avg_speed",
        "avg_vision_radius",
        "max_generation",
        "carnivore_population",
        "avg_carnivore_speed",
        "avg_carnivore_energy",
        "avg_carnivore_size",
        "predator_prey_ratio",
        "ecosystem_stress_index",
        "adaptive_mode_active",
    )

    def __init__(
        self,
        file_path: str,
        batch_size: int = 30,
        flush_interval_seconds: float = 2.0,
        queue_size: int = 256,
        max_file_bytes: int = 1 * 1024 * 1024 * 1024,
        reset_on_start: bool = False,
    ) -> None:
        self.file_path = file_path
        self.batch_size = max(1, batch_size)
        self.flush_interval_seconds = max(0.2, flush_interval_seconds)
        self.max_file_bytes = max(1024, int(max_file_bytes))
        self.reset_on_start = reset_on_start
        self._queue = queue.Queue(maxsize=max(1, queue_size))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._lock = threading.Lock()
        self._rows_written = 0
        self._dropped_rows = 0
        self._file_resets = 0
        self._last_error = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._prepare_output_file()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._writer_loop, name="metrics-writer", daemon=True)
        self._thread.start()

    def stop(self, timeout_seconds: float = 3.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=max(0.1, timeout_seconds))

    def log_snapshot(self, snapshot: MetricsSnapshot) -> bool:
        try:
            self._queue.put_nowait(snapshot)
            return True
        except queue.Full:
            with self._lock:
                self._dropped_rows += 1
            return False

    def get_health(self) -> dict[str, int | str]:
        with self._lock:
            return {
                "rows_written": self._rows_written,
                "dropped_rows": self._dropped_rows,
                "file_resets": self._file_resets,
                "queue_size": self._queue.qsize(),
                "last_error": self._last_error,
            }

    def _prepare_output_file(self) -> None:
        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        if not self.reset_on_start:
            return

        with open(self.file_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(self.CSV_HEADER)

        with self._lock:
            self._file_resets += 1

    def _writer_loop(self) -> None:
        pending: list[MetricsSnapshot] = []
        last_flush = time.monotonic()

        while not self._stop_event.is_set() or not self._queue.empty() or pending:
            timeout = max(0.05, self.flush_interval_seconds - (time.monotonic() - last_flush))

            try:
                snapshot = self._queue.get(timeout=timeout)
                pending.append(snapshot)
            except queue.Empty:
                pass

            should_flush = (
                bool(pending)
                and (
                    len(pending) >= self.batch_size
                    or (time.monotonic() - last_flush) >= self.flush_interval_seconds
                    or self._stop_event.is_set()
                )
            )

            if should_flush:
                try:
                    self._append_rows(pending)
                    pending.clear()
                    last_flush = time.monotonic()
                except OSError as exc:
                    # Preserve data in memory and retry on the next loop iteration.
                    with self._lock:
                        self._last_error = str(exc)
                    time.sleep(0.25)

    def _append_rows(self, rows: list[MetricsSnapshot]) -> None:
        if not rows:
            return

        directory = os.path.dirname(self.file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        serialized_rows = self._serialize_rows(rows)
        serialized_rows_bytes = serialized_rows.encode("utf-8")

        file_exists = os.path.exists(self.file_path)
        current_size = os.path.getsize(self.file_path) if file_exists else 0
        file_will_reset = file_exists and current_size > 0 and (
            current_size >= self.max_file_bytes
            or (current_size + len(serialized_rows_bytes)) > self.max_file_bytes
        )

        mode = "w" if file_will_reset else "a"
        needs_header = file_will_reset or not file_exists or current_size == 0

        with open(self.file_path, mode, newline="", encoding="utf-8") as handle:
            if needs_header:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(self.CSV_HEADER)

            handle.write(serialized_rows)

        with self._lock:
            self._rows_written += len(rows)
            if file_will_reset:
                self._file_resets += 1
            self._last_error = ""

    def _serialize_rows(self, rows: list[MetricsSnapshot]) -> str:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        for row in rows:
            writer.writerow(
                (
                    f"{row.timestamp:.3f}",
                    f"{row.elapsed_seconds:.3f}",
                    row.population,
                    row.food_count,
                    f"{row.avg_speed:.4f}",
                    f"{row.avg_vision_radius:.4f}",
                    row.max_generation,
                    row.carnivore_population,
                    f"{row.avg_carnivore_speed:.4f}",
                    f"{row.avg_carnivore_energy:.4f}",
                    f"{row.avg_carnivore_size:.4f}",
                    f"{row.predator_prey_ratio:.4f}",
                    f"{row.ecosystem_stress_index:.4f}",
                    row.adaptive_mode_active,
                )
            )

        return output.getvalue()
