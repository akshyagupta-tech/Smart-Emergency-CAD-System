"""Non-blocking UDP peer for timestamped multi-junction green-wave tokens.

Tokens are coordination hints, not authenticated safety commands. Deployments
must isolate the corridor network and authenticate peers before actuator use.
"""

from __future__ import annotations

import json
import logging
import select
import socket
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger("smart_traffic.corridor_network")


@dataclass(frozen=True, slots=True)
class GreenWaveToken:
    """A corridor pre-allocation hint sent to an adjacent junction."""

    token_id: str
    origin_junction: str
    target_junction: str
    vehicle_class: str
    timestamp: float
    eta_seconds: float
    corridor_locks: tuple[int, ...]
    group_size: int

    def to_json(self) -> bytes:
        """Serialize the token as a compact UTF-8 UDP datagram."""
        payload = asdict(self)
        payload["corridor_locks"] = list(self.corridor_locks)
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")


class CorridorNetwork:
    """Broadcast eligible clearance events and consume adjacent-node tokens."""

    DEFAULT_PORT = 9999

    def __init__(
        self,
        junction_id: str = "Junction1",
        *,
        target_junction: str = "Junction2",
        port: int = DEFAULT_PORT,
        listen_host: str = "0.0.0.0",
        broadcast_address: str = "255.255.255.255",
        dense_brt_threshold: int = 5,
        on_preallocate: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        if not junction_id or not target_junction:
            raise ValueError("junction IDs must not be empty")
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if dense_brt_threshold <= 0:
            raise ValueError("dense_brt_threshold must be positive")
        self.junction_id = junction_id
        self.target_junction = target_junction
        self.port = port
        self.listen_host = listen_host
        self.broadcast_address = broadcast_address
        self.dense_brt_threshold = dense_brt_threshold
        self.on_preallocate = on_preallocate
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._received_tokens: list[dict[str, Any]] = []

    @property
    def received_tokens(self) -> tuple[dict[str, Any], ...]:
        """Return a stable copy of received coordination tokens."""
        with self._send_lock:
            return tuple(dict(token) for token in self._received_tokens)

    def start(self) -> None:
        """Bind the UDP peer and start its non-blocking receive thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        peer.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        peer.bind((self.listen_host, self.port))
        peer.setblocking(False)
        self._socket = peer
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._receive_loop,
            name=f"{self.junction_id}-udp-peer",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the receive thread and close the UDP socket."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self._thread = None
        peer, self._socket = self._socket, None
        if peer is not None:
            peer.close()

    def publish_clearance(
        self,
        vehicle_class: str,
        *,
        eta_seconds: float = 5.0,
        corridor_locks: tuple[int, ...] = (1, 2, 3),
        group_size: int = 1,
    ) -> GreenWaveToken | None:
        """Broadcast an ambulance clearance or a sufficiently dense BRT group."""
        normalized = vehicle_class.strip().upper()
        eligible = normalized in {"AMBULANCE", "EMERGENCY"} or (
            normalized in {"BRT", "BRT_BUS", "BUS"}
            and group_size >= self.dense_brt_threshold
        )
        if not eligible:
            return None
        if eta_seconds < 0 or group_size <= 0:
            raise ValueError("eta_seconds must be non-negative and group_size positive")
        if not corridor_locks or any(
            not isinstance(zone, int) or isinstance(zone, bool) or zone not in (1, 2, 3)
            for zone in corridor_locks
        ):
            raise ValueError("corridor_locks must contain one or more zones from 1 to 3")
        token = GreenWaveToken(
            token_id=uuid.uuid4().hex,
            origin_junction=self.junction_id,
            target_junction=self.target_junction,
            vehicle_class=normalized,
            timestamp=time.time(),
            eta_seconds=float(eta_seconds),
            corridor_locks=tuple(sorted(set(corridor_locks))),
            group_size=group_size,
        )
        if not self.send_token(token):
            return None
        return token

    def send_token(self, token: GreenWaveToken) -> bool:
        """Send one token without blocking; return false if not started or busy."""
        peer = self._socket
        if peer is None:
            logger.warning("corridor peer is not started; token was not sent")
            return False
        try:
            payload = token.to_json()
            sent = peer.sendto(payload, (self.broadcast_address, self.port))
            return sent == len(payload)
        except (BlockingIOError, OSError) as error:
            logger.warning("green-wave datagram send failed: %s", error)
            return False

    def _receive_loop(self) -> None:
        peer = self._socket
        if peer is None:
            return
        while not self._stop.is_set():
            try:
                readable, _, _ = select.select([peer], [], [], 0.1)
                if not readable:
                    continue
                packet, _address = peer.recvfrom(4096)
            except (BlockingIOError, OSError, ValueError):
                if self._stop.is_set():
                    break
                continue
            try:
                token = json.loads(packet.decode("utf-8"))
                self._accept_token(token)
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                logger.warning("discarded invalid green-wave token: %s", error)

    def _accept_token(self, token: Any) -> None:
        if not isinstance(token, dict):
            raise ValueError("token payload must be an object")
        required = {
            "token_id",
            "origin_junction",
            "target_junction",
            "vehicle_class",
            "timestamp",
            "eta_seconds",
            "corridor_locks",
            "group_size",
        }
        if not required.issubset(token):
            raise ValueError("token is missing required fields")
        if token["target_junction"] != self.junction_id:
            return
        if token["origin_junction"] == self.junction_id:
            return
        if not isinstance(token["corridor_locks"], list) or not all(
            isinstance(zone, int) and not isinstance(zone, bool) and zone in (1, 2, 3)
            for zone in token["corridor_locks"]
        ):
            raise ValueError("corridor_locks must be a list of zone IDs from 1 to 3")
        with self._send_lock:
            self._received_tokens.append(token)
        if self.on_preallocate is not None:
            try:
                self.on_preallocate(token)
            except Exception:
                logger.exception("upstream corridor pre-allocation callback failed")

    def __enter__(self) -> CorridorNetwork:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()


__all__ = ["CorridorNetwork", "GreenWaveToken"]