"""Development actuator adapter for a USB microcontroller or Raspberry Pi.

Mock mode is the default. Live hardware is opt-in and this module is not a
safety-certified traffic-signal controller. Serial writes are one prebuilt byte
to minimize overhead; Python, USB, firmware, and GPIO scheduling prevent a
zero-latency guarantee.
"""

from __future__ import annotations

import argparse
import glob
import sys
import time
from dataclasses import dataclass
from typing import Any

GPIO_PINS = {
    "green": 17,
    "yellow": 27,
    "red": 22,
    "blue": 23,
}
COMMAND_BYTES = {
    "G": b"G",
    "Y": b"Y",
    "R": b"R",
    "E": b"E",
}
COMMAND_NAMES = {
    "G": "North Green",
    "Y": "North Yellow",
    "R": "North Red",
    "E": "Emergency Override Strobe",
}
ANSI_COLORS = {
    "G": "\033[32m",
    "Y": "\033[33m",
    "R": "\033[31m",
    "E": "\033[34;1m",
}
ANSI_RESET = "\033[0m"


@dataclass(frozen=True, slots=True)
class ActuationResult:
    command: str
    backend: str
    latency_ns: int


class HardwareActuator:
    """Route scheduler commands to opt-in hardware or the ANSI mock."""

    def __init__(
        self,
        *,
        live_hardware: bool = False,
        serial_port: str | None = None,
        prefer_gpio: bool = False,
    ) -> None:
        self.live_hardware = live_hardware
        self.serial_port = serial_port
        self.prefer_gpio = prefer_gpio
        self.backend = "mock"
        self._serial: Any | None = None
        self._gpio_devices: dict[str, Any] = {}
        self._gpio_module: Any | None = None
        self._closed = False
        self._connect_reason = "live hardware was not enabled"
        self.connect()

    def connect(self) -> str:
        """Try the requested physical backends, then retain a mock fallback."""
        if not self.live_hardware:
            self._mock(self._connect_reason)
            return self.backend

        attempts = (self._connect_gpio, self._connect_serial) if self.prefer_gpio else (
            self._connect_serial,
            self._connect_gpio,
        )
        failures: list[str] = []
        for attempt in attempts:
            try:
                if attempt():
                    print(f"Actuator backend: {self.backend}")
                    return self.backend
            except Exception as error:
                failures.append(str(error))
        reason = "; ".join(failures) or "no compatible serial or GPIO device found"
        self._mock(reason)
        return self.backend

    def actuate(self, command: str) -> ActuationResult:
        """Apply one scheduler command and report measured call latency."""
        if self._closed:
            raise RuntimeError("actuator is closed")
        if command not in COMMAND_BYTES:
            raise ValueError(f"unsupported actuation command: {command!r}")

        started = time.perf_counter_ns()
        if self.backend == "serial":
            written = self._serial.write(COMMAND_BYTES[command])
            if written != 1:
                raise OSError("serial backend did not accept the complete command byte")
        elif self.backend in {"gpiozero", "rpi.gpio"}:
            self._write_gpio(command)
        else:
            self._print_mock(command)
        latency_ns = time.perf_counter_ns() - started
        return ActuationResult(command, self.backend, latency_ns)

    def close(self) -> None:
        """Release resources opened by this adapter."""
        if self._closed:
            return
        try:
            if self.backend != "mock":
                self.actuate("R")
        finally:
            if self._serial is not None:
                self._serial.close()
            if self.backend == "gpiozero":
                for device in self._gpio_devices.values():
                    device.close()
            elif self.backend == "rpi.gpio" and self._gpio_module is not None:
                self._gpio_module.cleanup(tuple(GPIO_PINS.values()))
            self._closed = True

    def __enter__(self) -> "HardwareActuator":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _connect_serial(self) -> bool:
        try:
            import serial
        except ImportError:
            return False

        ports = [self.serial_port] if self.serial_port else self._serial_candidates()
        for port in ports:
            if not port:
                continue
            try:
                connection = serial.Serial(
                    port=port,
                    baudrate=115200,
                    timeout=0,
                    write_timeout=0.1,
                )
            except (OSError, serial.SerialException):
                continue
            if connection.write(COMMAND_BYTES["R"]) != 1:
                connection.close()
                continue
            self._serial = connection
            self.backend = "serial"
            self.serial_port = port
            return True
        return False

    def _serial_candidates(self) -> list[str]:
        try:
            from serial.tools import list_ports
        except ImportError:
            candidates = []
            for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*", "COM[0-9]*"):
                candidates.extend(glob.glob(pattern))
            return sorted(candidates)

        return [port.device for port in list_ports.comports()]

    def _connect_gpio(self) -> bool:
        try:
            from gpiozero import OutputDevice
        except ImportError:
            OutputDevice = None

        if OutputDevice is not None:
            created: dict[str, Any] = {}
            try:
                for name, pin in GPIO_PINS.items():
                    created[name] = OutputDevice(
                        pin,
                        active_high=True,
                        initial_value=name == "red",
                    )
            except Exception:
                for device in created.values():
                    device.close()
            else:
                self._gpio_devices = created
                self.backend = "gpiozero"
                return True

        try:
            import RPi.GPIO as gpio
        except ImportError:
            return False

        gpio.setmode(gpio.BCM)
        for name, pin in GPIO_PINS.items():
            gpio.setup(pin, gpio.OUT, initial=gpio.HIGH if name == "red" else gpio.LOW)
        self._gpio_module = gpio
        self.backend = "rpi.gpio"
        return True

    def _write_gpio(self, command: str) -> None:
        states = {
            "G": {"green": True, "yellow": False, "red": False, "blue": False},
            "Y": {"green": False, "yellow": True, "red": False, "blue": False},
            "R": {"green": False, "yellow": False, "red": True, "blue": False},
            "E": {"green": False, "yellow": False, "red": True, "blue": True},
        }[command]
        if self.backend == "gpiozero":
            for name, active in states.items():
                self._gpio_devices[name].value = active
        else:
            for name, pin in GPIO_PINS.items():
                self._gpio_module.output(
                    pin,
                    self._gpio_module.HIGH if states[name] else self._gpio_module.LOW,
                )

    def _mock(self, reason: str) -> None:
        self.backend = "mock"
        self._connect_reason = reason
        print(f"Mock actuator active: {reason}")

    def _print_mock(self, command: str) -> None:
        color = ANSI_COLORS[command]
        suffix = " (North Red held)" if command == "E" else ""
        print(f"{color}[MOCK] {COMMAND_NAMES[command]}{suffix}{ANSI_RESET}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-hardware",
        action="store_true",
        help="opt in to opening a serial/GPIO device; mock mode is otherwise used",
    )
    parser.add_argument("--serial-port", help="explicit USB serial port, e.g. /dev/ttyACM0 or COM3")
    parser.add_argument("--prefer-gpio", action="store_true", help="try Raspberry Pi GPIO before serial")
    parser.add_argument(
        "--commands",
        nargs="+",
        choices=tuple(COMMAND_BYTES),
        default=["R"],
        help="scheduler commands to apply in order (default: R)",
    )
    args = parser.parse_args(argv)

    with HardwareActuator(
        live_hardware=args.live_hardware,
        serial_port=args.serial_port,
        prefer_gpio=args.prefer_gpio,
    ) as actuator:
        for command in args.commands:
            result = actuator.actuate(command)
            print(
                f"command={result.command} backend={result.backend} "
                f"measured_latency={result.latency_ns} ns"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())