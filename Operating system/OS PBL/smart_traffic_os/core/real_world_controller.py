"""Hardware-facing safety and resource controls for a traffic edge node.

This module provides an integration boundary for real sensors, signal drivers,
and junction peers. The included defaults are safe simulation mocks; they are
not certified for controlling public-road signals without a safety case,
redundant hardware interlocks, and independent validation.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

if __package__:
    from core.corridor_network import CorridorNetwork, GreenWaveToken
else:
    from corridor_network import CorridorNetwork, GreenWaveToken

logger = logging.getLogger("smart_traffic.real_world_controller")
Zone: TypeAlias = str | int


@dataclass(slots=True)
class LockLease:
    """Generation-tagged ownership token invalidated by emergency release."""

    zone: int
    generation: int
    active: bool = True


class EmergencyReleasableLockBank:
    """Short-lived crossing locks that can be invalidated by the watchdog.

    Normal locks use non-blocking acquisition so the lock-state guard is never
    held while waiting. A lease generation prevents a stale owner from
    releasing a lock acquired after watchdog recovery.
    """

    def __init__(self, zones: tuple[int, ...] = (1, 2, 3)) -> None:
        self._locks = {zone: threading.Lock() for zone in zones}
        self._guard = threading.Lock()
        self._generation = 0
        self._failsafe = False
        self._leases: dict[int, LockLease] = {}

    def acquire(self, zone: int) -> LockLease | None:
        """Acquire a zone without blocking, or return ``None`` if unavailable."""
        with self._guard:
            if self._failsafe or zone not in self._locks:
                return None
            lock = self._locks[zone]
            if not lock.acquire(blocking=False):
                return None
            lease = LockLease(zone, self._generation)
            self._leases[zone] = lease
            return lease

    def release(self, lease: LockLease) -> None:
        """Release a current-generation lease; stale leases are harmless."""
        with self._guard:
            if not lease.active:
                return
            lease.active = False
            lock = self._locks.get(lease.zone)
            current = self._leases.get(lease.zone)
            if (
                lease.generation == self._generation
                and current is lease
                and lock is not None
                and lock.locked()
            ):
                lock.release()
                self._leases.pop(lease.zone, None)

    @contextmanager
    def hold(self, zone: int):
        """Context-manager convenience for a non-blocking zone lock."""
        lease = self.acquire(zone)
        if lease is None:
            raise RuntimeError(f"zone {zone} is unavailable or in fail-safe mode")
        try:
            yield lease
        finally:
            self.release(lease)

    def emergency_release_all(self) -> None:
        """Release every held zone and block new acquisitions until recovery."""
        with self._guard:
            self._failsafe = True
            self._generation += 1
            for lease in self._leases.values():
                lease.active = False
            self._leases.clear()
            for lock in self._locks.values():
                if lock.locked():
                    lock.release()

    def resume_after_recovery(self) -> None:
        """Allow new lock leases after the controller validates all sensors."""
        with self._guard:
            self._generation += 1
            self._failsafe = False

    @property
    def failsafe_active(self) -> bool:
        with self._guard:
            return self._failsafe


class RealWorldController:
    """Monitor roadside hardware and arbitrate fail-safe operating modes."""

    ZONES = ("North", "South", "East", "West")
    SENSOR_TIMEOUT_SECONDS = 3.0
    THERMAL_LIMIT_C = 75.0
    NORMAL_FRAME_RATE = 30
    THROTTLED_FRAME_RATE = 10
    MINIMUM_WALK_SECONDS = 5.0
    PEDESTRIAN_CLEARANCE_SECONDS = 2.0

    def __init__(
        self,
        *,
        sensor_timeout_seconds: float = SENSOR_TIMEOUT_SECONDS,
        thermal_limit_c: float = THERMAL_LIMIT_C,
        minimum_walk_seconds: float = MINIMUM_WALK_SECONDS,
        clearance_seconds: float = PEDESTRIAN_CLEARANCE_SECONDS,
        thermal_reader: Callable[[], float] | None = None,
        thermal_path: str | Path = "/sys/class/thermal/thermal_zone0/temp",
        fallback_temperature_c: float = 45.0,
        set_signal: Callable[[str, str], None] | None = None,
        set_frame_rate: Callable[[int], None] | None = None,
        set_page_replacement_policy: Callable[[str], None] | None = None,
        release_all_locks: Callable[[], None] | None = None,
        reset_locks: Callable[[], None] | None = None,
        emergency_dispatch: Callable[[str], Any] | None = None,
        network: CorridorNetwork | None = None,
        clock: Callable[[], float] = time.monotonic,
        interruptible_wait: Callable[[float], bool] | None = None,
        watchdog_poll_seconds: float = 0.1,
    ) -> None:
        if sensor_timeout_seconds <= 0 or thermal_limit_c <= 0:
            raise ValueError("sensor timeout and thermal limit must be positive")
        if minimum_walk_seconds < 5.0:
            raise ValueError("minimum pedestrian walk time must be at least 5 seconds")
        if clearance_seconds < 0 or watchdog_poll_seconds <= 0:
            raise ValueError("clearance must be non-negative and watchdog poll positive")
        self.sensor_timeout_seconds = sensor_timeout_seconds
        self.thermal_limit_c = thermal_limit_c
        self.minimum_walk_seconds = minimum_walk_seconds
        self.clearance_seconds = clearance_seconds
        self.thermal_path = Path(thermal_path)
        self.fallback_temperature_c = fallback_temperature_c
        self._thermal_reader = thermal_reader or (
            lambda: self.read_thermal_zone(
                self.thermal_path, fallback_c=self.fallback_temperature_c
            )
        )
        self._set_signal_callback = set_signal
        self._set_frame_rate_callback = set_frame_rate
        self._set_policy_callback = set_page_replacement_policy
        self._emergency_dispatch = emergency_dispatch
        self.network = network
        self._clock = clock
        self._wait_for_interrupt = interruptible_wait
        self._watchdog_poll_seconds = watchdog_poll_seconds

        self.intersection_locks = EmergencyReleasableLockBank()
        self._external_release_locks = release_all_locks
        self._external_reset_locks = reset_locks
        self._release_all_locks = self._release_intersection_locks
        self._reset_locks = self._resume_intersection_locks
        self._preallocation_lock = threading.Lock()
        self._preallocated_corridors: dict[str, list[LockLease]] = {}
        self._external_preallocate = network.on_preallocate if network else None
        if network is not None:
            network.on_preallocate = self._handle_green_wave_token
        self._state_lock = threading.RLock()
        now = self._clock()
        self._last_sensor_frame = {zone: now for zone in self.ZONES}
        self._lights = {zone: "RED" for zone in self.ZONES}
        self._failsafe_active = False
        self._failsafe_reason: str | None = None
        self._emergency_active = False
        self._emergency_interrupt = threading.Event()
        self._pedestrian_requests = {
            zone: threading.Semaphore(0) for zone in self.ZONES
        }
        self._pedestrian_service = {
            zone: threading.Semaphore(1) for zone in self.ZONES
        }
        self._stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        self._pedestrian_threads: list[threading.Thread] = []

        self.cpu_temperature_c = self.fallback_temperature_c
        self.frame_rate_fps = self.NORMAL_FRAME_RATE
        self.page_replacement_policy = "LFU"
        self.frames_accepted = 0
        self.frames_dropped = 0
        self._last_frame_accepted_at: float | None = None
        self._frame_lock = threading.Lock()
        self._pedestrian_counters = {zone: 0 for zone in self.ZONES}

    @staticmethod
    def normalize_zone(zone: Zone) -> str:
        """Normalize direction names or 1-based approach numbers."""
        if isinstance(zone, int) and not isinstance(zone, bool):
            if zone in range(1, 5):
                return RealWorldController.ZONES[zone - 1]
        elif isinstance(zone, str):
            value = zone.strip().title()
            if value in RealWorldController.ZONES:
                return value
            if value.upper() in {"Z1", "Z2", "Z3", "Z4"}:
                return RealWorldController.ZONES[int(value[1]) - 1]
        raise ValueError("zone must be North, South, East, West, or 1 through 4")

    @staticmethod
    def read_thermal_zone(
        path: str | Path = "/sys/class/thermal/thermal_zone0/temp",
        *,
        fallback_c: float = 45.0,
    ) -> float:
        """Read Linux thermal-zone millidegrees or use a deterministic mock."""
        mock_value = os.getenv("SMART_TRAFFIC_TEMPERATURE_C")
        if mock_value is not None:
            try:
                return float(mock_value)
            except ValueError:
                logger.warning("invalid SMART_TRAFFIC_TEMPERATURE_C=%r", mock_value)
        try:
            raw = float(Path(path).read_text(encoding="ascii").strip())
            return raw / 1000.0 if abs(raw) >= 1000 else raw
        except (OSError, ValueError):
            return float(fallback_c)

    def start(self) -> None:
        """Start the sensor watchdog and one queued pedestrian worker per zone."""
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return
        self._stop.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name="traffic-sensor-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()
        self._pedestrian_threads = [
            threading.Thread(
                target=self._pedestrian_loop,
                args=(zone,),
                name=f"pedestrian-{zone.lower()}-worker",
                daemon=True,
            )
            for zone in self.ZONES
        ]
        for thread in self._pedestrian_threads:
            thread.start()
        if self.network is not None:
            self.network.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop watchdog, pedestrian workers, and optional corridor networking."""
        self._stop.set()
        self._emergency_interrupt.set()
        threads = [self._watchdog_thread, *self._pedestrian_threads]
        for thread in threads:
            if thread is not None:
                thread.join(timeout)
        self._watchdog_thread = None
        self._pedestrian_threads = []
        if self.network is not None:
            self.network.stop(timeout=timeout)

    def record_sensor_heartbeat(
        self, zone: Zone, *, frame_received: bool = True, received_at: float | None = None
    ) -> bool:
        """Record a frame/heartbeat and recover only when every sensor is fresh."""
        normalized = self.normalize_zone(zone)
        if not frame_received:
            return False
        with self._state_lock:
            self._last_sensor_frame[normalized] = (
                self._clock() if received_at is None else received_at
            )
            recover = self._failsafe_active and self._all_sensors_fresh_locked(
                self._clock()
            )
        if recover:
            self.recover_sensor_dropout()
        return True

    def check_sensor_watchdog(self, now: float | None = None) -> dict[str, Any]:
        """Enter four-way caution if any sensor has been silent over 3 seconds."""
        current_time = self._clock() if now is None else now
        with self._state_lock:
            stale = {
                zone: round(current_time - timestamp, 3)
                for zone, timestamp in self._last_sensor_frame.items()
                if current_time - timestamp > self.sensor_timeout_seconds
            }
            already_active = self._failsafe_active
        if stale and not already_active:
            self._enter_sensor_failsafe(stale)
        with self._state_lock:
            return {
                "failsafe_active": self._failsafe_active,
                "stale_sensors": stale,
                "reason": self._failsafe_reason,
                "lights": dict(self._lights),
            }

    def recover_sensor_dropout(self) -> bool:
        """Latch back to all-red only after all four sensors send fresh frames."""
        with self._state_lock:
            if not self._failsafe_active or not self._all_sensors_fresh_locked(
                self._clock()
            ):
                return False
            self._failsafe_active = False
            self._failsafe_reason = None
            self._lights = {zone: "RED" for zone in self.ZONES}
            lights = dict(self._lights)
            clear_emergency_event = not self._emergency_active
        self._reset_locks()
        if clear_emergency_event:
            self._emergency_interrupt.clear()
        self._publish_lights(lights)
        logger.info("sensor watchdog recovered; signals latched all-red")
        return True

    def _enter_sensor_failsafe(self, stale: Mapping[str, float]) -> None:
        with self._state_lock:
            if self._failsafe_active:
                return
            self._failsafe_active = True
            self._failsafe_reason = "sensor heartbeat timeout"
            self._emergency_interrupt.set()
        try:
            self._release_all_locks()
        except Exception:
            logger.exception("failed to release intersection locks during fallback")
        with self._state_lock:
            self._lights = {zone: "FLASHING_AMBER" for zone in self.ZONES}
            lights = dict(self._lights)
        self._publish_lights(lights)
        logger.critical("sensor dropout; entering four-way caution: %s", dict(stale))

    def trigger_pedestrian_walk(self, zone: Zone) -> dict[str, Any]:
        """Queue an interrupt-driven walk request using a counting semaphore."""
        normalized = self.normalize_zone(zone)
        with self._state_lock:
            if self._failsafe_active:
                return {"queued": False, "zone": normalized, "reason": "sensor fail-safe active"}
            self._pedestrian_counters[normalized] += 1
            request_id = self._pedestrian_counters[normalized]
            self._pedestrian_requests[normalized].release()
        return {"queued": True, "zone": normalized, "request_id": request_id}

    def process_pedestrian_request(
        self,
        zone: Zone,
        *,
        interruptible_wait: Callable[[float], bool] | None = None,
    ) -> dict[str, Any]:
        """Serve one request with walk/clearance intervals, preemptible by P0.

        The per-zone service semaphore is held while pedestrians cross, but no
        intersection/PCP lock is held during either timed interval. Emergency
        handling therefore never waits for a pedestrian lock owner.
        """
        normalized = self.normalize_zone(zone)
        if self._is_interrupted():
            return {"served": False, "zone": normalized, "reason": "emergency preemption"}
        request = self._pedestrian_requests[normalized]
        if not request.acquire(blocking=False):
            return {"served": False, "zone": normalized, "reason": "no queued request"}
        service_gate = self._pedestrian_service[normalized]
        if not service_gate.acquire(blocking=False):
            request.release()
            return {"served": False, "zone": normalized, "reason": "walk already active"}
        wait = interruptible_wait or self._wait_for_interrupt or self._emergency_interrupt.wait
        try:
            if self._is_interrupted():
                request.release()
                return {"served": False, "zone": normalized, "reason": "emergency preemption"}
            self._set_light(normalized, "WALK")
            if wait(self.minimum_walk_seconds) or self._is_interrupted():
                return {"served": False, "zone": normalized, "reason": "preempted during walk"}
            self._set_light(normalized, "CLEARANCE")
            if wait(self.clearance_seconds) or self._is_interrupted():
                return {"served": False, "zone": normalized, "reason": "preempted during clearance"}
            self._set_light(normalized, "RED")
            return {
                "served": True,
                "zone": normalized,
                "walk_seconds": self.minimum_walk_seconds,
                "clearance_seconds": self.clearance_seconds,
            }
        finally:
            service_gate.release()
            if self._failsafe_active:
                self._set_light(normalized, "FLASHING_AMBER")

    def activate_emergency(self, vehicle_type: str = "Ambulance", zone: Zone = "North") -> Any:
        """Signal pedestrian workers immediately, then dispatch the emergency."""
        normalized_vehicle = vehicle_type.strip().title()
        if normalized_vehicle not in {"Ambulance", "Fire"}:
            raise ValueError("vehicle_type must be Ambulance or Fire")
        normalized_zone = self.normalize_zone(zone)
        self._emergency_interrupt.set()
        with self._state_lock:
            self._emergency_active = True
            failsafe_active = self._failsafe_active
            if failsafe_active:
                self._lights = {
                    approach: "FLASHING_AMBER" for approach in self.ZONES
                }
            else:
                self._lights = {approach: "RED" for approach in self.ZONES}
                self._lights[normalized_zone] = "EMERGENCY_GREEN"
            lights = dict(self._lights)
        self._publish_lights(lights)
        if failsafe_active:
            return {
                "vehicle_type": normalized_vehicle,
                "zone": normalized_zone,
                "priority": 0,
                "dispatched": False,
                "reason": "sensor fail-safe keeps all approaches in caution",
            }
        if self._emergency_dispatch is not None:
            return self._emergency_dispatch(normalized_vehicle)
        return {"vehicle_type": normalized_vehicle, "zone": normalized_zone, "priority": 0}

    def clear_emergency(self) -> None:
        """Clear the emergency interrupt without overriding sensor fail-safe."""
        with self._state_lock:
            self._emergency_active = False
            failsafe = self._failsafe_active
            self._lights = {
                zone: "FLASHING_AMBER" if failsafe else "RED"
                for zone in self.ZONES
            }
            lights = dict(self._lights)
        if not failsafe:
            self._emergency_interrupt.clear()
        self._publish_lights(lights)

    def poll_temperature(self, temperature_c: float | None = None) -> dict[str, Any]:
        """Apply hot/cool frame-rate and page-replacement profiles."""
        temperature = float(
            self._thermal_reader() if temperature_c is None else temperature_c
        )
        if temperature < -40 or temperature > 150:
            raise ValueError("temperature is outside a plausible roadside range")
        throttled = temperature > self.thermal_limit_c
        frame_rate = self.THROTTLED_FRAME_RATE if throttled else self.NORMAL_FRAME_RATE
        policy = "FIFO" if throttled else "LFU"
        with self._state_lock:
            self.cpu_temperature_c = temperature
            frame_rate_changed = frame_rate != self.frame_rate_fps
            policy_changed = policy != self.page_replacement_policy
            self.frame_rate_fps = frame_rate
            self.page_replacement_policy = policy
        if frame_rate_changed and self._set_frame_rate_callback is not None:
            self._set_frame_rate_callback(frame_rate)
        if policy_changed and self._set_policy_callback is not None:
            self._set_policy_callback(policy)
        return {
            "temperature_c": temperature,
            "throttled": throttled,
            "frame_rate_fps": frame_rate,
            "page_replacement_policy": policy,
        }

    def should_ingest_frame(self, now: float | None = None) -> bool:
        """Accept only the adaptive rate; count rejected camera frames as drops."""
        self.poll_temperature()
        timestamp = self._clock() if now is None else now
        with self._frame_lock:
            interval = 1.0 / self.frame_rate_fps
            if (
                self._last_frame_accepted_at is None
                or timestamp - self._last_frame_accepted_at >= interval
            ):
                self._last_frame_accepted_at = timestamp
                self.frames_accepted += 1
                return True
            self.frames_dropped += 1
            return False

    def on_corridor_clearance(
        self,
        vehicle_class: str,
        *,
        group_size: int = 1,
        eta_seconds: float = 5.0,
        corridor_locks: tuple[int, ...] = (1, 2, 3),
    ) -> GreenWaveToken | None:
        """Publish an eligible ambulance or dense-BRT green-wave token."""
        if self.network is None:
            return None
        return self.network.publish_clearance(
            vehicle_class,
            group_size=group_size,
            eta_seconds=eta_seconds,
            corridor_locks=corridor_locks,
        )

    def release_preallocated_corridor(self, token_id: str) -> bool:
        """Release a token's reserved zone leases after its convoy clears."""
        with self._preallocation_lock:
            leases = self._preallocated_corridors.pop(token_id, None)
        if leases is None:
            return False
        for lease in reversed(leases):
            self.intersection_locks.release(lease)
        return True

    def snapshot(self) -> dict[str, Any]:
        """Return a stable controller diagnostic view."""
        with self._state_lock:
            with self._frame_lock:
                accepted = self.frames_accepted
                dropped = self.frames_dropped
            with self._preallocation_lock:
                preallocated_count = len(self._preallocated_corridors)
            return {
                "failsafe_active": self._failsafe_active,
                "failsafe_reason": self._failsafe_reason,
                "sensor_age_seconds": {
                    zone: round(self._clock() - timestamp, 3)
                    for zone, timestamp in self._last_sensor_frame.items()
                },
                "lights": dict(self._lights),
                "emergency_active": self._emergency_active,
                "cpu_temperature_c": self.cpu_temperature_c,
                "frame_rate_fps": self.frame_rate_fps,
                "page_replacement_policy": self.page_replacement_policy,
                "frames_accepted": accepted,
                "frames_dropped": dropped,
                "preallocated_corridor_tokens": preallocated_count,
                "pedestrian_queue_depths": {
                    zone: count
                    for zone, count in self._pedestrian_counters.items()
                },
            }

    def _all_sensors_fresh_locked(self, now: float) -> bool:
        return all(
            now - timestamp <= self.sensor_timeout_seconds
            for timestamp in self._last_sensor_frame.values()
        )

    def _release_intersection_locks(self) -> None:
        self.intersection_locks.emergency_release_all()
        if self._external_release_locks is not None:
            self._external_release_locks()

    def _resume_intersection_locks(self) -> None:
        self.intersection_locks.resume_after_recovery()
        if self._external_reset_locks is not None:
            self._external_reset_locks()
        with self._preallocation_lock:
            self._preallocated_corridors.clear()

    def _handle_green_wave_token(self, token: Mapping[str, Any]) -> None:
        """Reserve every requested zone before forwarding the token callback."""
        token_id = str(token["token_id"])
        zones = tuple(sorted(set(token["corridor_locks"])))
        leases: list[LockLease] = []
        for zone in zones:
            lease = self.intersection_locks.acquire(zone)
            if lease is None:
                for held_lease in reversed(leases):
                    self.intersection_locks.release(held_lease)
                logger.warning("could not preallocate all corridor locks for %s", token_id)
                break
            leases.append(lease)
        else:
            with self._preallocation_lock:
                previous = self._preallocated_corridors.pop(token_id, [])
                self._preallocated_corridors[token_id] = leases
            for old_lease in reversed(previous):
                self.intersection_locks.release(old_lease)
        if self._external_preallocate is not None:
            self._external_preallocate(token)

    def _is_interrupted(self) -> bool:
        with self._state_lock:
            return self._emergency_active or self._failsafe_active or self._stop.is_set()

    def _set_light(self, zone: str, phase: str) -> None:
        with self._state_lock:
            if self._failsafe_active:
                phase = "FLASHING_AMBER"
            self._lights[zone] = phase
        self._publish_lights({zone: phase})

    def _publish_lights(self, lights: Mapping[str, str]) -> None:
        if self._set_signal_callback is None:
            return
        for zone, phase in lights.items():
            try:
                self._set_signal_callback(zone, phase)
            except Exception:
                logger.exception("signal driver update failed for %s", zone)

    def _watchdog_loop(self) -> None:
        while not self._stop.wait(self._watchdog_poll_seconds):
            self.check_sensor_watchdog()

    def _pedestrian_loop(self, zone: str) -> None:
        request = self._pedestrian_requests[zone]
        while not self._stop.is_set():
            if self._is_interrupted():
                self._stop.wait(0.05)
                continue
            if request.acquire(timeout=0.1):
                request.release()
                self.process_pedestrian_request(zone)


def _self_test_sensor_dropout_recovery() -> None:
    clock = [0.0]
    dispatched: list[str] = []
    controller = RealWorldController(
        clock=lambda: clock[0],
        emergency_dispatch=dispatched.append,
    )
    lease = controller.intersection_locks.acquire(1)
    assert lease is not None
    clock[0] = 3.1
    failure = controller.check_sensor_watchdog()
    assert failure["failsafe_active"]
    assert all(phase == "FLASHING_AMBER" for phase in failure["lights"].values())
    assert not lease.active
    assert controller.intersection_locks.acquire(1) is None
    emergency = controller.activate_emergency("Ambulance", "North")
    assert emergency["dispatched"] is False and not dispatched
    assert all(
        phase == "FLASHING_AMBER"
        for phase in controller.snapshot()["lights"].values()
    )
    for zone in controller.ZONES:
        controller.record_sensor_heartbeat(zone, received_at=3.1)
    assert not controller.snapshot()["failsafe_active"]
    assert all(phase == "RED" for phase in controller.snapshot()["lights"].values())
    recovered_lease = controller.intersection_locks.acquire(1)
    assert recovered_lease is not None
    controller.intersection_locks.release(recovered_lease)
    print("PASS sensor dropout enters caution and recovers after fresh heartbeats")


def _self_test_pedestrian_emergency_preemption() -> None:
    controller = RealWorldController()

    def emergency_during_walk(_duration: float) -> bool:
        controller.activate_emergency("Ambulance", "North")
        return True

    assert controller.trigger_pedestrian_walk("North")["queued"]
    result = controller.process_pedestrian_request(
        "North", interruptible_wait=emergency_during_walk
    )
    assert not result["served"] and "preempted" in result["reason"]
    assert controller.snapshot()["emergency_active"]
    lights = controller.snapshot()["lights"]
    assert lights["North"] == "EMERGENCY_GREEN"
    assert all(phase == "RED" for zone, phase in lights.items() if zone != "North")
    print("PASS emergency preempts the semaphore-served pedestrian interval")


def _self_test_thermal_throttling() -> None:
    controller = RealWorldController(
        thermal_reader=lambda: 80.0,
        clock=lambda: 0.0,
    )
    state = controller.poll_temperature()
    assert state["throttled"]
    assert state["frame_rate_fps"] == 10
    assert state["page_replacement_policy"] == "FIFO"
    assert controller.should_ingest_frame(now=0.0)
    assert not controller.should_ingest_frame(now=0.05)
    assert controller.should_ingest_frame(now=0.1)
    assert controller.snapshot()["frames_dropped"] == 1
    print("PASS high-temperature governor throttles ingest to 10 FPS and FIFO")


if __name__ == "__main__":
    _self_test_sensor_dropout_recovery()
    _self_test_pedestrian_emergency_preemption()
    _self_test_thermal_throttling()