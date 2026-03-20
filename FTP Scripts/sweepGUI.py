#!/usr/bin/env python3
"""
Modern PyQt6 tinySA real-time spectrum application.

What this version changes compared to the original Tkinter utility:
- Full PyQt6 desktop UI with a modern dark Fusion-based theme.
- Unit-aware controls for frequencies, time, points, and RBW.
- RBW is handled explicitly in kHz with a proper spin box.
- Better validation and configuration summary.
- Measurement history table and integrated log console.
- Cleaner threading using QThread and signals.
- Export/load/save configuration helpers.
- Better plot management, peak display, and richer status metrics.

Dependencies:
    pip install pyqt6 pyserial numpy matplotlib
"""

from __future__ import annotations

import csv
import json
import os
import struct
import sys
import time
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import serial
from serial.tools import list_ports

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter


VID = 0x0483
PID = 0x5740
APP_NAME = "tinySA PyQt Spectrum Console"
APP_ORG = "OpenAI"
DEFAULT_SAVE_DIR = "measurements"
CONFIG_EXT = ".tinysa.json"


FREQUENCY_UNITS = {
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    "GHz": 1e9,
}


THEME_QSS = """
QWidget {
    background: #0f1117;
    color: #e6edf3;
    font-size: 12px;
}
QMainWindow {
    background: #0f1117;
}
QGroupBox {
    border: 1px solid #2d333b;
    border-radius: 12px;
    margin-top: 14px;
    padding-top: 12px;
    font-weight: 600;
    background: #151a22;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #9ecbff;
}
QPushButton {
    background: #1f6feb;
    border: none;
    border-radius: 10px;
    padding: 8px 14px;
    color: white;
    font-weight: 600;
}
QPushButton:hover {
    background: #388bfd;
}
QPushButton:pressed {
    background: #1158c7;
}
QPushButton:disabled {
    background: #30363d;
    color: #8b949e;
}
QToolButton {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 6px 10px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 6px 8px;
    selection-background-color: #1f6feb;
}
QComboBox QAbstractItemView {
    background: #0d1117;
    border: 1px solid #30363d;
    selection-background-color: #1f6feb;
}
QCheckBox {
    spacing: 8px;
}
QScrollArea {
    border: none;
}
QStatusBar {
    background: #0d1117;
    border-top: 1px solid #30363d;
}
QTableWidget {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 10px;
    gridline-color: #30363d;
}
QHeaderView::section {
    background: #161b22;
    color: #c9d1d9;
    border: none;
    border-right: 1px solid #30363d;
    border-bottom: 1px solid #30363d;
    padding: 6px;
    font-weight: 600;
}
QTabWidget::pane {
    border: 1px solid #30363d;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: #161b22;
    border: 1px solid #30363d;
    padding: 8px 12px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
}
QTabBar::tab:selected {
    background: #1f2937;
    color: #9ecbff;
}
"""


@dataclass
class ScanConfig:
    port: str
    start_hz: float
    end_hz: float
    points: int
    rbw_khz: int
    hold_time_s: float
    min_sweeps: int
    auto_cycle: bool
    autosave_csv: bool
    save_dir: str
    display_mode: str
    y_auto: bool
    y_min_dbm: float
    y_max_dbm: float
    peak_marker_enabled: bool


@dataclass
class MeasurementMeta:
    measurement_index: int
    timestamp: str
    start_hz: float
    end_hz: float
    points: int
    rbw_input_khz: int
    rbw_effective_khz: int
    peak_frequency_hz: float
    peak_power_dbm: float
    mode: str
    file_path: str = ""


@dataclass
class PortInfo:
    device: str
    description: str
    manufacturer: str
    vid: Optional[int]
    pid: Optional[int]


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_timestamp_for_filename(timestamp_str: str) -> str:
    return timestamp_str.replace(":", "-").replace(" ", "_")


def format_frequency_hz(hz: float) -> str:
    abs_hz = abs(hz)
    if abs_hz >= 1e9:
        return f"{hz / 1e9:.6f} GHz"
    if abs_hz >= 1e6:
        return f"{hz / 1e6:.6f} MHz"
    if abs_hz >= 1e3:
        return f"{hz / 1e3:.3f} kHz"
    return f"{hz:.0f} Hz"


def format_dbm(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.2f} dBm"


def format_seconds(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.2f} s"


def list_available_ports() -> List[PortInfo]:
    ports: List[PortInfo] = []
    for p in list_ports.comports():
        ports.append(
            PortInfo(
                device=p.device,
                description=p.description or "",
                manufacturer=p.manufacturer or "",
                vid=p.vid,
                pid=p.pid,
            )
        )
    return ports


def autodetect_port() -> str:
    for device in list_ports.comports():
        if device.vid == VID and device.pid == PID:
            return device.device
    raise OSError("tinySA not found")


def ensure_directory(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_trace_csv(
    file_path: str,
    freq: np.ndarray,
    power: np.ndarray,
    metadata: MeasurementMeta,
) -> None:
    with open(file_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["measurement_index", metadata.measurement_index])
        writer.writerow(["timestamp", metadata.timestamp])
        writer.writerow(["start_hz", metadata.start_hz])
        writer.writerow(["end_hz", metadata.end_hz])
        writer.writerow(["points", metadata.points])
        writer.writerow(["rbw_input_khz", metadata.rbw_input_khz])
        writer.writerow(["rbw_effective_khz", metadata.rbw_effective_khz])
        writer.writerow(["peak_frequency_hz", metadata.peak_frequency_hz])
        writer.writerow(["peak_power_dbm", metadata.peak_power_dbm])
        writer.writerow(["mode", metadata.mode])
        writer.writerow([])
        writer.writerow(["frequency_hz", "power_dbm"])
        for fval, pval in zip(freq, power):
            writer.writerow([f"{fval:.6f}", f"{pval:.6f}"])


def choose_frequency_axis_scale(freq: np.ndarray) -> Tuple[float, str]:
    if freq.size == 0:
        return 1.0, "Hz"
    max_abs = max(abs(float(freq[0])), abs(float(freq[-1])))
    if max_abs >= 1e9:
        return 1e9, "GHz"
    if max_abs >= 1e6:
        return 1e6, "MHz"
    if max_abs >= 1e3:
        return 1e3, "kHz"
    return 1.0, "Hz"


class TinySA:
    """Minimal tinySA serial interface, preserving the original scan logic."""

    def __init__(self, port: str):
        self.ser = serial.Serial(
            port=port,
            baudrate=115200,
            timeout=1,
            write_timeout=2,
        )
        self.lock = threading.Lock()

    def close(self) -> None:
        with self.lock:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass

    def _drain_input(self) -> None:
        while self.ser.in_waiting:
            self.ser.read_all()
            time.sleep(0.1)

    def scan(
        self,
        f_low: float,
        f_high: float,
        points: int,
        rbw_khz: int,
        stop_event: threading.Event,
    ) -> Tuple[np.ndarray, int, float]:
        with self.lock:
            if stop_event.is_set():
                raise RuntimeError("Scan stopped by user")

            self.ser.timeout = 1
            self._drain_input()

            if rbw_khz == 0:
                actual_rbw_khz = (f_high - f_low) * 7e-6
            else:
                actual_rbw_khz = rbw_khz

            if actual_rbw_khz < 3:
                actual_rbw_khz = 3
            elif actual_rbw_khz > 600:
                actual_rbw_khz = 600

            rbw_command = f"rbw {int(actual_rbw_khz)}\r".encode()
            self.ser.write(rbw_command)
            self.ser.read_until(b"ch> ")

            if stop_event.is_set():
                raise RuntimeError("Scan stopped by user")

            timeout = ((f_high - f_low) / 20e3) / (actual_rbw_khz ** 2) + points / 500 + 1
            self.ser.timeout = max(1.0, timeout * 2.0)

            scan_command = f"scanraw {int(f_low)} {int(f_high)} {int(points)}\r".encode()
            self.ser.write(scan_command)

            raw_start = self.ser.read_until(b"{")
            if not raw_start.endswith(b"{"):
                raise TimeoutError("Did not receive start of scan payload from tinySA")

            raw_data = self.ser.read_until(b"}ch> ")
            if not raw_data.endswith(b"}ch> "):
                raise TimeoutError("Did not receive complete scan payload from tinySA")

            try:
                self.ser.write(b"rbw auto\r")
            except Exception:
                pass

            payload = raw_data[:-5]
            expected_len = points * 3
            if len(payload) != expected_len:
                raise ValueError(
                    f"Unexpected payload length: got {len(payload)}, expected {expected_len}"
                )

            unpacked = struct.unpack("<" + "xH" * points, payload)
            raw_array = np.array(unpacked, dtype=np.uint16)
            scale = 128
            dbm_power = raw_array / 32 - scale
            return dbm_power, int(actual_rbw_khz), float(timeout)


class FrequencyInput(QWidget):
    """Numeric frequency input with explicit units."""

    def __init__(self, label_text: str, default_hz: float, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.label = QLabel(label_text)
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(6)
        self.spin.setRange(0.0, 999999999999.0)
        self.spin.setSingleStep(1.0)
        self.spin.setAccelerated(True)
        self.unit = QComboBox()
        for unit_name in FREQUENCY_UNITS:
            self.unit.addItem(unit_name)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.spin, 1)
        layout.addWidget(self.unit, 0)
        self.set_from_hz(default_hz)

    def set_from_hz(self, hz: float) -> None:
        if hz >= 1e9:
            self.unit.setCurrentText("GHz")
            self.spin.setValue(hz / 1e9)
        elif hz >= 1e6:
            self.unit.setCurrentText("MHz")
            self.spin.setValue(hz / 1e6)
        elif hz >= 1e3:
            self.unit.setCurrentText("kHz")
            self.spin.setValue(hz / 1e3)
        else:
            self.unit.setCurrentText("Hz")
            self.spin.setValue(hz)

    def get_hz(self) -> float:
        multiplier = FREQUENCY_UNITS[self.unit.currentText()]
        return float(self.spin.value() * multiplier)

    def connect_changed(self, callback) -> None:
        self.spin.valueChanged.connect(callback)
        self.unit.currentTextChanged.connect(callback)


class MetricCard(QFrame):
    """Small information tile used in the modern dashboard."""

    def __init__(self, title: str, value: str = "—", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            """
            QFrame#MetricCard {
                background: #151a22;
                border: 1px solid #2d333b;
                border-radius: 14px;
            }
            QLabel#MetricTitle {
                color: #8b949e;
                font-size: 11px;
                font-weight: 600;
            }
            QLabel#MetricValue {
                color: #e6edf3;
                font-size: 17px;
                font-weight: 700;
            }
            """
        )
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.value_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


class LogConsole(QTextEdit):
    """Read-only log console."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Consolas", 10))

    def append_line(self, text: str) -> None:
        timestamp = now_string()
        self.append(f"[{timestamp}] {text}")
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)


class MeasurementTable(QTableWidget):
    """History table for recorded measurements."""

    HEADERS = [
        "#",
        "Timestamp",
        "Mode",
        "Peak Frequency",
        "Peak Power",
        "RBW",
        "File",
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

    def add_measurement(self, meta: MeasurementMeta) -> None:
        row = self.rowCount()
        self.insertRow(row)
        values = [
            str(meta.measurement_index),
            meta.timestamp,
            meta.mode,
            format_frequency_hz(meta.peak_frequency_hz),
            f"{meta.peak_power_dbm:.2f} dBm",
            f"{meta.rbw_effective_khz} kHz",
            meta.file_path,
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col == 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, col, item)
        self.scrollToBottom()

    def selected_file_path(self) -> str:
        items = self.selectedItems()
        if not items:
            return ""
        row = items[0].row()
        file_item = self.item(row, 6)
        return file_item.text() if file_item is not None else ""


class SpectrumCanvas(QWidget):
    """Matplotlib-based spectrum canvas with toolbar and peak annotation."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.figure = Figure(figsize=(10, 6), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.ax = self.figure.add_subplot(111)

        self.raw_line, = self.ax.plot([], [], linewidth=1.5, label="Raw")
        self.max_line, = self.ax.plot([], [], linewidth=1.8, label="Max Hold")
        self.rec_line, = self.ax.plot([], [], linewidth=1.6, label="Last Recorded")

        self.peak_marker, = self.ax.plot([], [], marker="o", markersize=7, linestyle="None")
        self.peak_text = self.ax.annotate(
            "",
            xy=(0, 0),
            xytext=(10, 12),
            textcoords="offset points",
            fontsize=10,
            bbox=dict(boxstyle="round,pad=0.3", fc="#151a22", ec="#30363d", alpha=0.95),
            color="#e6edf3",
        )
        self.peak_text.set_visible(False)

        self.ax.set_title("Spectrum")
        self.ax.set_xlabel("Frequency")
        self.ax.set_ylabel("Power (dBm)")
        self.ax.grid(True, alpha=0.25)
        self.ax.legend(loc="upper right")
        self.ax.set_facecolor("#0d1117")
        self.figure.patch.set_facecolor("#0f1117")
        self.ax.tick_params(colors="#c9d1d9")
        for spine in self.ax.spines.values():
            spine.set_color("#30363d")
        self.ax.title.set_color("#9ecbff")
        self.ax.xaxis.label.set_color("#c9d1d9")
        self.ax.yaxis.label.set_color("#c9d1d9")
        legend = self.ax.legend(loc="upper right")
        if legend is not None:
            legend.get_frame().set_facecolor("#151a22")
            legend.get_frame().set_edgecolor("#30363d")
            for text in legend.get_texts():
                text.set_color("#e6edf3")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)

    def clear_plot(self) -> None:
        self.raw_line.set_data([], [])
        self.max_line.set_data([], [])
        self.rec_line.set_data([], [])
        self.peak_marker.set_data([], [])
        self.peak_text.set_visible(False)
        self.canvas.draw_idle()

    def redraw(
        self,
        freq: Optional[np.ndarray],
        raw: Optional[np.ndarray],
        maxhold: Optional[np.ndarray],
        recorded: Optional[np.ndarray],
        mode: str,
        y_auto: bool,
        y_min_dbm: float,
        y_max_dbm: float,
        peak_marker_enabled: bool,
    ) -> Tuple[Optional[float], Optional[float]]:
        self.raw_line.set_visible(False)
        self.max_line.set_visible(False)
        self.rec_line.set_visible(False)
        self.peak_marker.set_visible(False)
        self.peak_text.set_visible(False)

        if freq is None or freq.size == 0:
            self.canvas.draw_idle()
            return None, None

        active_y: Optional[np.ndarray] = None

        if mode == "Raw" and raw is not None:
            self.raw_line.set_data(freq, raw)
            self.raw_line.set_visible(True)
            active_y = raw
        elif mode == "Max Hold" and maxhold is not None:
            self.max_line.set_data(freq, maxhold)
            self.max_line.set_visible(True)
            active_y = maxhold
        elif mode == "Last Recorded" and recorded is not None:
            self.rec_line.set_data(freq, recorded)
            self.rec_line.set_visible(True)
            active_y = recorded
        elif mode == "Overlay All":
            if raw is not None:
                self.raw_line.set_data(freq, raw)
                self.raw_line.set_visible(True)
            if maxhold is not None:
                self.max_line.set_data(freq, maxhold)
                self.max_line.set_visible(True)
            if recorded is not None:
                self.rec_line.set_data(freq, recorded)
                self.rec_line.set_visible(True)
            if raw is not None:
                active_y = raw
            elif maxhold is not None:
                active_y = maxhold
            elif recorded is not None:
                active_y = recorded
        else:
            if raw is not None:
                self.raw_line.set_data(freq, raw)
                self.raw_line.set_visible(True)
                active_y = raw

        if active_y is None or active_y.size == 0:
            self.canvas.draw_idle()
            return None, None

        scale, unit_label = choose_frequency_axis_scale(freq)
        self.ax.set_xlim(float(freq[0]), float(freq[-1]))
        self.ax.set_xlabel(f"Frequency ({unit_label})")
        self.ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x / scale:.3f}"))

        if y_auto:
            ymin = float(np.min(active_y) - 5.0)
            ymax = float(np.max(active_y) + 5.0)
            if ymin == ymax:
                ymin -= 1.0
                ymax += 1.0
            self.ax.set_ylim(ymin, ymax)
        else:
            self.ax.set_ylim(y_min_dbm, y_max_dbm)

        peak_idx = int(np.argmax(active_y))
        peak_freq = float(freq[peak_idx])
        peak_power = float(active_y[peak_idx])

        if peak_marker_enabled:
            self.peak_marker.set_data([peak_freq], [peak_power])
            self.peak_marker.set_visible(True)
            self.peak_text.xy = (peak_freq, peak_power)
            self.peak_text.set_text(
                f"Peak\n{format_frequency_hz(peak_freq)}\n{peak_power:.2f} dBm"
            )
            self.peak_text.set_visible(True)

        self.canvas.draw_idle()
        return peak_freq, peak_power


class ScanWorker(QThread):
    """Background scan thread. Keeps serial work away from the GUI thread."""

    scan_result = pyqtSignal(dict)
    status_update = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    connection_update = pyqtSignal(str)

    def __init__(self, config: ScanConfig, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.config = config
        self.stop_event = threading.Event()
        self.tiny: Optional[TinySA] = None
        self.scan_index = 0

    def stop(self) -> None:
        self.stop_event.set()
        try:
            if self.tiny is not None:
                self.tiny.close()
        except Exception:
            pass

    def run(self) -> None:
        try:
            self.connection_update.emit(f"Opening {self.config.port}")
            self.tiny = TinySA(self.config.port)
            self.connection_update.emit(f"Connected: {self.config.port}")
            self.status_update.emit("Scan worker started")

            while not self.stop_event.is_set():
                t0 = time.time()
                power, actual_rbw_khz, scan_timeout = self.tiny.scan(
                    self.config.start_hz,
                    self.config.end_hz,
                    self.config.points,
                    self.config.rbw_khz,
                    self.stop_event,
                )
                dt = time.time() - t0
                self.scan_index += 1
                payload = {
                    "power": power,
                    "actual_rbw_khz": int(actual_rbw_khz),
                    "scan_timeout": float(scan_timeout),
                    "scan_duration_s": float(dt),
                    "scan_index": self.scan_index,
                }
                self.scan_result.emit(payload)

        except RuntimeError as exc:
            if str(exc) != "Scan stopped by user":
                self.error_signal.emit(str(exc))
        except Exception as exc:
            self.error_signal.emit(str(exc))
        finally:
            try:
                if self.tiny is not None:
                    self.tiny.close()
            except Exception:
                pass
            self.connection_update.emit("Disconnected")
            self.status_update.emit("Scan worker finished")


class MainWindow(QMainWindow):
    """Main PyQt6 application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1500, 900)

        self.worker: Optional[ScanWorker] = None
        self.freq: Optional[np.ndarray] = None
        self.power: Optional[np.ndarray] = None
        self.maxhold: Optional[np.ndarray] = None
        self.last_recorded_trace: Optional[np.ndarray] = None
        self.last_recorded_timestamp: Optional[str] = None
        self.last_peak_freq_hz: Optional[float] = None
        self.last_peak_power_dbm: Optional[float] = None

        self.running = False
        self.scan_count = 0
        self.measurement_count = 0
        self.actual_rbw_khz: Optional[int] = None
        self.last_scan_timeout: Optional[float] = None
        self.last_scan_duration_s: Optional[float] = None
        self.cycle_start_time: Optional[float] = None
        self.cycle_scan_count = 0
        self.current_config: Optional[ScanConfig] = None
        self.measurements: List[MeasurementMeta] = []

        self._build_actions()
        self._build_menu()
        self._build_status_bar()
        self._build_ui()
        self._connect_signals()
        self.refresh_ports(select_auto=True)
        self.update_config_summary()
        self.refresh_metrics()
        self.append_log("Application initialized")

        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(250)
        self.ui_timer.timeout.connect(self.update_runtime_metrics)
        self.ui_timer.start()

    # ---------------------------------------------------------------------
    # UI construction
    # ---------------------------------------------------------------------
    def _build_actions(self) -> None:
        self.act_start = QAction("Start", self)
        self.act_start.setShortcut("Ctrl+R")
        self.act_start.triggered.connect(self.start_scan)

        self.act_stop = QAction("Stop", self)
        self.act_stop.setShortcut("Ctrl+.")
        self.act_stop.triggered.connect(self.stop_scan)

        self.act_refresh_ports = QAction("Refresh Ports", self)
        self.act_refresh_ports.triggered.connect(lambda: self.refresh_ports(select_auto=False))

        self.act_auto_detect = QAction("Auto Detect tinySA", self)
        self.act_auto_detect.triggered.connect(self.autodetect_device)

        self.act_save_config = QAction("Save Config", self)
        self.act_save_config.setShortcut("Ctrl+S")
        self.act_save_config.triggered.connect(self.save_config_dialog)

        self.act_load_config = QAction("Load Config", self)
        self.act_load_config.setShortcut("Ctrl+O")
        self.act_load_config.triggered.connect(self.load_config_dialog)

        self.act_export_raw = QAction("Export Raw Trace", self)
        self.act_export_raw.triggered.connect(self.export_current_raw_trace)

        self.act_export_max = QAction("Export Max Hold", self)
        self.act_export_max.triggered.connect(self.export_maxhold_trace)

        self.act_export_recorded = QAction("Export Last Recorded", self)
        self.act_export_recorded.triggered.connect(self.export_recorded_trace)

        self.act_reset_max = QAction("Reset Max Hold", self)
        self.act_reset_max.triggered.connect(self.reset_maxhold)

        self.act_record_now = QAction("Record Now", self)
        self.act_record_now.triggered.connect(self.record_now)

        self.act_open_save_dir = QAction("Open Save Directory", self)
        self.act_open_save_dir.triggered.connect(self.open_save_directory_in_file_manager)

        self.act_clear_log = QAction("Clear Log", self)
        self.act_clear_log.triggered.connect(self.clear_log)

        self.act_about = QAction("About", self)
        self.act_about.triggered.connect(self.show_about)

        self.act_exit = QAction("Exit", self)
        self.act_exit.triggered.connect(self.close)

    def _build_menu(self) -> None:
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)

        file_menu = menubar.addMenu("File")
        file_menu.addAction(self.act_save_config)
        file_menu.addAction(self.act_load_config)
        file_menu.addSeparator()
        file_menu.addAction(self.act_export_raw)
        file_menu.addAction(self.act_export_max)
        file_menu.addAction(self.act_export_recorded)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        device_menu = menubar.addMenu("Device")
        device_menu.addAction(self.act_refresh_ports)
        device_menu.addAction(self.act_auto_detect)
        device_menu.addAction(self.act_open_save_dir)

        scan_menu = menubar.addMenu("Scan")
        scan_menu.addAction(self.act_start)
        scan_menu.addAction(self.act_stop)
        scan_menu.addSeparator()
        scan_menu.addAction(self.act_reset_max)
        scan_menu.addAction(self.act_record_now)

        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction(self.act_clear_log)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction(self.act_about)

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.status_label = QLabel("Idle")
        self.connection_label = QLabel("Disconnected")
        self.statusBar().addPermanentWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.connection_label, 0)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        header = self._create_header()
        root_layout.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 1080])

        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

    def _create_header(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(
            """
            QFrame {
                background: #151a22;
                border: 1px solid #2d333b;
                border-radius: 16px;
            }
            QLabel#HeaderTitle {
                font-size: 20px;
                font-weight: 700;
                color: #9ecbff;
            }
            QLabel#HeaderSubtitle {
                color: #8b949e;
                font-size: 12px;
            }
            """
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        title_block = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("HeaderTitle")
        subtitle = QLabel(
            "Modern PyQt6 front end for tinySA live spectrum scanning, max-hold cycling, and trace recording"
        )
        subtitle.setObjectName("HeaderSubtitle")
        subtitle.setWordWrap(True)
        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        self.start_button = QPushButton("Start Scan")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.record_button = QPushButton("Record Now")
        self.reset_button = QPushButton("Reset Max Hold")

        layout.addLayout(title_block, 1)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.record_button)
        layout.addWidget(self.reset_button)
        return frame

    def _create_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._create_metrics_group())
        layout.addWidget(self._create_scan_group())
        layout.addWidget(self._create_cycle_group())
        layout.addWidget(self._create_display_group())
        layout.addWidget(self._create_storage_group())
        layout.addWidget(self._create_summary_group())
        layout.addStretch(1)

        scroll.setWidget(holder)
        return scroll

    def _create_right_panel(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        plot_container = QWidget()
        plot_layout = QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(8)
        self.plot_canvas = SpectrumCanvas()
        plot_layout.addWidget(self.plot_canvas, 1)

        tabs = QTabWidget()
        tabs.addTab(self._create_measurements_tab(), "Measurements")
        tabs.addTab(self._create_log_tab(), "Log")

        splitter.addWidget(plot_container)
        splitter.addWidget(tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([640, 260])
        return splitter

    def _create_metrics_group(self) -> QWidget:
        frame = QWidget()
        layout = QGridLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)

        self.card_connection = MetricCard("Connection", "Disconnected")
        self.card_scans = MetricCard("Scans", "0")
        self.card_measurements = MetricCard("Measurements", "0")
        self.card_rbw = MetricCard("Effective RBW", "—")
        self.card_last_scan = MetricCard("Last Scan", "—")
        self.card_peak = MetricCard("Visible Peak", "—")
        self.card_cycle = MetricCard("Cycle", "0 sweeps")
        self.card_last_recorded = MetricCard("Last Recorded", "—")

        cards = [
            self.card_connection,
            self.card_scans,
            self.card_measurements,
            self.card_rbw,
            self.card_last_scan,
            self.card_peak,
            self.card_cycle,
            self.card_last_recorded,
        ]
        positions = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)]
        for card, pos in zip(cards, positions):
            layout.addWidget(card, pos[0], pos[1])
        return frame

    def _create_scan_group(self) -> QWidget:
        group = QGroupBox("Scan Parameters")
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.input_start = FrequencyInput("Start", 2_300_000_000.0)
        self.input_end = FrequencyInput("End", 2_500_000_000.0)

        self.spin_points = QSpinBox()
        self.spin_points.setRange(2, 10001)
        self.spin_points.setSingleStep(1)
        self.spin_points.setValue(401)
        self.spin_points.setSuffix(" pts")
        self.spin_points.setAccelerated(True)

        self.spin_rbw = QSpinBox()
        self.spin_rbw.setRange(0, 600)
        self.spin_rbw.setValue(0)
        self.spin_rbw.setSingleStep(1)
        self.spin_rbw.setSpecialValueText("Auto / Calculated")
        self.spin_rbw.setSuffix(" kHz")

        port_row = QWidget()
        port_layout = QHBoxLayout(port_row)
        port_layout.setContentsMargins(0, 0, 0, 0)
        port_layout.setSpacing(6)
        self.combo_port = QComboBox()
        self.combo_port.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.btn_refresh_ports = QToolButton()
        self.btn_refresh_ports.setText("Refresh")
        self.btn_auto_detect = QToolButton()
        self.btn_auto_detect.setText("Detect")
        port_layout.addWidget(self.combo_port, 1)
        port_layout.addWidget(self.btn_refresh_ports)
        port_layout.addWidget(self.btn_auto_detect)

        form.addRow("Start Frequency", self.input_start)
        form.addRow("End Frequency", self.input_end)
        form.addRow("Sweep Points", self.spin_points)
        form.addRow("RBW", self.spin_rbw)
        form.addRow("Serial Port", port_row)
        return group

    def _create_cycle_group(self) -> QWidget:
        group = QGroupBox("Max-Hold / Cycle Logic")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.spin_hold_time = QDoubleSpinBox()
        self.spin_hold_time.setRange(0.0, 36000.0)
        self.spin_hold_time.setDecimals(2)
        self.spin_hold_time.setSingleStep(0.25)
        self.spin_hold_time.setValue(3.0)
        self.spin_hold_time.setSuffix(" s")

        self.spin_min_sweeps = QSpinBox()
        self.spin_min_sweeps.setRange(1, 100000)
        self.spin_min_sweeps.setValue(3)
        self.spin_min_sweeps.setSuffix(" sweeps")

        self.check_auto_cycle = QCheckBox("Auto cycle max-hold and record when both thresholds are met")
        self.check_auto_cycle.setChecked(True)

        form.addRow("Hold Time", self.spin_hold_time)
        form.addRow("Minimum Sweeps", self.spin_min_sweeps)
        form.addRow("Cycle Mode", self.check_auto_cycle)
        return group

    def _create_display_group(self) -> QWidget:
        group = QGroupBox("Display / Plot")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Raw", "Max Hold", "Last Recorded", "Overlay All"])

        self.check_peak_marker = QCheckBox("Show peak marker")
        self.check_peak_marker.setChecked(True)

        self.check_y_auto = QCheckBox("Auto Y range")
        self.check_y_auto.setChecked(True)

        y_range_row = QWidget()
        y_range_layout = QHBoxLayout(y_range_row)
        y_range_layout.setContentsMargins(0, 0, 0, 0)
        y_range_layout.setSpacing(8)
        self.spin_y_min = QDoubleSpinBox()
        self.spin_y_min.setRange(-200.0, 100.0)
        self.spin_y_min.setDecimals(2)
        self.spin_y_min.setValue(-120.0)
        self.spin_y_min.setSuffix(" dBm")
        self.spin_y_max = QDoubleSpinBox()
        self.spin_y_max.setRange(-200.0, 100.0)
        self.spin_y_max.setDecimals(2)
        self.spin_y_max.setValue(0.0)
        self.spin_y_max.setSuffix(" dBm")
        y_range_layout.addWidget(self.spin_y_min)
        y_range_layout.addWidget(self.spin_y_max)

        form.addRow("Display Mode", self.combo_mode)
        form.addRow("Peak Marker", self.check_peak_marker)
        form.addRow("Y Axis", self.check_y_auto)
        form.addRow("Manual Range", y_range_row)
        return group

    def _create_storage_group(self) -> QWidget:
        group = QGroupBox("Recording / Storage")
        form = QFormLayout(group)
        form.setSpacing(10)

        self.check_autosave = QCheckBox("Autosave each recorded measurement to CSV")
        self.check_autosave.setChecked(False)

        save_row = QWidget()
        save_layout = QHBoxLayout(save_row)
        save_layout.setContentsMargins(0, 0, 0, 0)
        save_layout.setSpacing(6)
        self.edit_save_dir = QLineEdit(DEFAULT_SAVE_DIR)
        self.btn_browse_save_dir = QToolButton()
        self.btn_browse_save_dir.setText("Browse")
        self.btn_open_save_dir = QToolButton()
        self.btn_open_save_dir.setText("Open")
        save_layout.addWidget(self.edit_save_dir, 1)
        save_layout.addWidget(self.btn_browse_save_dir)
        save_layout.addWidget(self.btn_open_save_dir)

        form.addRow("Autosave", self.check_autosave)
        form.addRow("Save Directory", save_row)
        return group

    def _create_summary_group(self) -> QWidget:
        group = QGroupBox("Configuration Summary")
        layout = QVBoxLayout(group)
        self.label_summary = QLabel("—")
        self.label_summary.setWordWrap(True)
        self.label_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label_summary.setStyleSheet(
            "QLabel { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 10px; }"
        )
        layout.addWidget(self.label_summary)
        return group

    def _create_measurements_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        button_row = QHBoxLayout()
        self.btn_export_selected = QPushButton("Open Selected File Path")
        self.btn_clear_measurements = QPushButton("Clear Table")
        button_row.addWidget(self.btn_export_selected)
        button_row.addWidget(self.btn_clear_measurements)
        button_row.addStretch(1)

        self.measurement_table = MeasurementTable()
        layout.addLayout(button_row)
        layout.addWidget(self.measurement_table, 1)
        return page

    def _create_log_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.log_console = LogConsole()
        layout.addWidget(self.log_console, 1)
        return page

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self.start_scan)
        self.stop_button.clicked.connect(self.stop_scan)
        self.record_button.clicked.connect(self.record_now)
        self.reset_button.clicked.connect(self.reset_maxhold)

        self.btn_refresh_ports.clicked.connect(lambda: self.refresh_ports(select_auto=False))
        self.btn_auto_detect.clicked.connect(self.autodetect_device)
        self.btn_browse_save_dir.clicked.connect(self.browse_save_directory)
        self.btn_open_save_dir.clicked.connect(self.open_save_directory_in_file_manager)

        self.combo_mode.currentTextChanged.connect(self.redraw_plot)
        self.check_peak_marker.toggled.connect(self.redraw_plot)
        self.check_y_auto.toggled.connect(self.on_y_auto_toggled)
        self.spin_y_min.valueChanged.connect(self.redraw_plot)
        self.spin_y_max.valueChanged.connect(self.redraw_plot)

        self.input_start.connect_changed(self.update_config_summary)
        self.input_end.connect_changed(self.update_config_summary)
        self.spin_points.valueChanged.connect(self.update_config_summary)
        self.spin_rbw.valueChanged.connect(self.update_config_summary)
        self.spin_hold_time.valueChanged.connect(self.update_config_summary)
        self.spin_min_sweeps.valueChanged.connect(self.update_config_summary)
        self.check_auto_cycle.toggled.connect(self.update_config_summary)
        self.check_autosave.toggled.connect(self.update_config_summary)
        self.edit_save_dir.textChanged.connect(self.update_config_summary)
        self.combo_mode.currentTextChanged.connect(self.update_config_summary)
        self.check_y_auto.toggled.connect(self.update_config_summary)
        self.spin_y_min.valueChanged.connect(self.update_config_summary)
        self.spin_y_max.valueChanged.connect(self.update_config_summary)
        self.check_peak_marker.toggled.connect(self.update_config_summary)

        self.btn_export_selected.clicked.connect(self.show_selected_measurement_file)
        self.btn_clear_measurements.clicked.connect(self.clear_measurement_table)

        self.on_y_auto_toggled(self.check_y_auto.isChecked())

    # ---------------------------------------------------------------------
    # Utility logging and status helpers
    # ---------------------------------------------------------------------
    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def set_connection_status(self, text: str) -> None:
        self.connection_label.setText(text)
        self.card_connection.set_value(text)

    def append_log(self, text: str) -> None:
        self.log_console.append_line(text)

    def clear_log(self) -> None:
        self.log_console.clear()
        self.append_log("Log cleared")

    # ---------------------------------------------------------------------
    # Configuration and validation
    # ---------------------------------------------------------------------
    def get_selected_port(self) -> str:
        data = self.combo_port.currentData()
        if isinstance(data, str) and data.strip():
            return data.strip()
        text = self.combo_port.currentText().strip()
        if text:
            return text.split(" ")[0]
        return ""

    def build_scan_config(self) -> ScanConfig:
        port = self.get_selected_port() or autodetect_port()
        start_hz = self.input_start.get_hz()
        end_hz = self.input_end.get_hz()
        points = int(self.spin_points.value())
        rbw_khz = int(self.spin_rbw.value())
        hold_time_s = float(self.spin_hold_time.value())
        min_sweeps = int(self.spin_min_sweeps.value())
        auto_cycle = self.check_auto_cycle.isChecked()
        autosave_csv = self.check_autosave.isChecked()
        save_dir = self.edit_save_dir.text().strip() or DEFAULT_SAVE_DIR
        display_mode = self.combo_mode.currentText()
        y_auto = self.check_y_auto.isChecked()
        y_min_dbm = float(self.spin_y_min.value())
        y_max_dbm = float(self.spin_y_max.value())
        peak_marker_enabled = self.check_peak_marker.isChecked()

        if end_hz <= start_hz:
            raise ValueError("End Frequency must be greater than Start Frequency")
        if points < 2:
            raise ValueError("Sweep Points must be at least 2")
        if rbw_khz < 0:
            raise ValueError("RBW must be 0 or a positive value in kHz")
        if hold_time_s < 0:
            raise ValueError("Hold Time must be >= 0 s")
        if min_sweeps < 1:
            raise ValueError("Minimum Sweeps must be at least 1")
        if not y_auto and y_max_dbm <= y_min_dbm:
            raise ValueError("Manual Y Max must be greater than Y Min")

        return ScanConfig(
            port=port,
            start_hz=start_hz,
            end_hz=end_hz,
            points=points,
            rbw_khz=rbw_khz,
            hold_time_s=hold_time_s,
            min_sweeps=min_sweeps,
            auto_cycle=auto_cycle,
            autosave_csv=autosave_csv,
            save_dir=save_dir,
            display_mode=display_mode,
            y_auto=y_auto,
            y_min_dbm=y_min_dbm,
            y_max_dbm=y_max_dbm,
            peak_marker_enabled=peak_marker_enabled,
        )

    def update_config_summary(self) -> None:
        try:
            cfg = self.build_scan_config()
            span_hz = cfg.end_hz - cfg.start_hz
            step_hz = span_hz / max(1, cfg.points - 1)
            rbw_text = "Auto / Calculated by span" if cfg.rbw_khz == 0 else f"{cfg.rbw_khz} kHz"
            summary = (
                f"<b>Port:</b> {cfg.port}<br>"
                f"<b>Start:</b> {format_frequency_hz(cfg.start_hz)}<br>"
                f"<b>End:</b> {format_frequency_hz(cfg.end_hz)}<br>"
                f"<b>Span:</b> {format_frequency_hz(span_hz)}<br>"
                f"<b>Point Spacing:</b> {format_frequency_hz(step_hz)}<br>"
                f"<b>Points:</b> {cfg.points}<br>"
                f"<b>RBW:</b> {rbw_text}<br>"
                f"<b>Hold Time:</b> {cfg.hold_time_s:.2f} s<br>"
                f"<b>Min Sweeps:</b> {cfg.min_sweeps}<br>"
                f"<b>Auto Cycle:</b> {'Yes' if cfg.auto_cycle else 'No'}<br>"
                f"<b>Autosave CSV:</b> {'Yes' if cfg.autosave_csv else 'No'}<br>"
                f"<b>Display Mode:</b> {cfg.display_mode}<br>"
                f"<b>Y Axis:</b> {'Auto' if cfg.y_auto else f'Manual ({cfg.y_min_dbm:.2f} to {cfg.y_max_dbm:.2f} dBm)'}<br>"
                f"<b>Peak Marker:</b> {'On' if cfg.peak_marker_enabled else 'Off'}<br>"
                f"<b>Save Dir:</b> {cfg.save_dir}"
            )
            self.label_summary.setText(summary)
        except Exception as exc:
            self.label_summary.setText(f"<span style='color:#ff7b72;'><b>Validation Error:</b> {exc}</span>")

    def apply_config(self, cfg: ScanConfig) -> None:
        self.input_start.set_from_hz(cfg.start_hz)
        self.input_end.set_from_hz(cfg.end_hz)
        self.spin_points.setValue(cfg.points)
        self.spin_rbw.setValue(cfg.rbw_khz)
        self.spin_hold_time.setValue(cfg.hold_time_s)
        self.spin_min_sweeps.setValue(cfg.min_sweeps)
        self.check_auto_cycle.setChecked(cfg.auto_cycle)
        self.check_autosave.setChecked(cfg.autosave_csv)
        self.edit_save_dir.setText(cfg.save_dir)
        self.combo_mode.setCurrentText(cfg.display_mode)
        self.check_y_auto.setChecked(cfg.y_auto)
        self.spin_y_min.setValue(cfg.y_min_dbm)
        self.spin_y_max.setValue(cfg.y_max_dbm)
        self.check_peak_marker.setChecked(cfg.peak_marker_enabled)

        found = False
        for i in range(self.combo_port.count()):
            data = self.combo_port.itemData(i)
            if data == cfg.port:
                self.combo_port.setCurrentIndex(i)
                found = True
                break
        if not found and cfg.port:
            self.combo_port.addItem(cfg.port, cfg.port)
            self.combo_port.setCurrentIndex(self.combo_port.count() - 1)

        self.update_config_summary()
        self.redraw_plot()

    # ---------------------------------------------------------------------
    # Port management
    # ---------------------------------------------------------------------
    def refresh_ports(self, select_auto: bool = False) -> None:
        current = self.get_selected_port()
        self.combo_port.clear()
        ports = list_available_ports()
        for p in ports:
            suffix = []
            if p.description:
                suffix.append(p.description)
            if p.manufacturer:
                suffix.append(p.manufacturer)
            if p.vid is not None and p.pid is not None:
                suffix.append(f"VID:PID {p.vid:04X}:{p.pid:04X}")
            text = f"{p.device} — {' | '.join(suffix)}" if suffix else p.device
            self.combo_port.addItem(text, p.device)

        if self.combo_port.count() == 0:
            self.combo_port.addItem("No serial ports found", "")

        if select_auto:
            try:
                auto_port = autodetect_port()
                for i in range(self.combo_port.count()):
                    if self.combo_port.itemData(i) == auto_port:
                        self.combo_port.setCurrentIndex(i)
                        self.append_log(f"Auto-detected tinySA on {auto_port}")
                        break
            except Exception:
                if current:
                    for i in range(self.combo_port.count()):
                        if self.combo_port.itemData(i) == current:
                            self.combo_port.setCurrentIndex(i)
                            break
        elif current:
            for i in range(self.combo_port.count()):
                if self.combo_port.itemData(i) == current:
                    self.combo_port.setCurrentIndex(i)
                    break

        self.update_config_summary()

    def autodetect_device(self) -> None:
        try:
            port = autodetect_port()
            found = False
            for i in range(self.combo_port.count()):
                if self.combo_port.itemData(i) == port:
                    self.combo_port.setCurrentIndex(i)
                    found = True
                    break
            if not found:
                self.combo_port.addItem(port, port)
                self.combo_port.setCurrentIndex(self.combo_port.count() - 1)
            self.set_status(f"tinySA detected on {port}")
            self.append_log(f"Auto-detect selected port {port}")
        except Exception as exc:
            QMessageBox.critical(self, "Device Detection Error", str(exc))
            self.append_log(f"Auto-detect failed: {exc}")

    # ---------------------------------------------------------------------
    # Save/load config
    # ---------------------------------------------------------------------
    def save_config_dialog(self) -> None:
        try:
            cfg = self.build_scan_config()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid Configuration", str(exc))
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Configuration",
            str(Path.home() / f"tinySA_config{CONFIG_EXT}"),
            f"tinySA Config (*{CONFIG_EXT});;JSON (*.json)",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, indent=2)
        self.set_status(f"Saved config: {path}")
        self.append_log(f"Configuration saved to {path}")

    def load_config_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Configuration",
            str(Path.home()),
            f"tinySA Config (*{CONFIG_EXT});;JSON (*.json)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = ScanConfig(**data)
            self.apply_config(cfg)
            self.set_status(f"Loaded config: {path}")
            self.append_log(f"Configuration loaded from {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            self.append_log(f"Failed to load config {path}: {exc}")

    # ---------------------------------------------------------------------
    # Scan state reset helpers
    # ---------------------------------------------------------------------
    def reset_runtime_state(self) -> None:
        self.freq = None
        self.power = None
        self.maxhold = None
        self.last_recorded_trace = None
        self.last_recorded_timestamp = None
        self.last_peak_freq_hz = None
        self.last_peak_power_dbm = None
        self.scan_count = 0
        self.measurement_count = 0
        self.actual_rbw_khz = None
        self.last_scan_timeout = None
        self.last_scan_duration_s = None
        self.cycle_start_time = time.time()
        self.cycle_scan_count = 0
        self.measurements.clear()
        self.measurement_table.setRowCount(0)

    def reset_maxhold(self) -> None:
        self.maxhold = None
        self.cycle_start_time = time.time()
        self.cycle_scan_count = 0
        self.set_status("Max Hold reset")
        self.append_log("Max-hold buffer reset")
        self.redraw_plot()
        self.refresh_metrics()

    # ---------------------------------------------------------------------
    # Start/stop worker
    # ---------------------------------------------------------------------
    def start_scan(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(self, "Already Running", "A scan is already in progress.")
            return

        try:
            cfg = self.build_scan_config()
        except Exception as exc:
            QMessageBox.critical(self, "Invalid Configuration", str(exc))
            self.append_log(f"Start blocked by invalid config: {exc}")
            return

        self.current_config = cfg
        self.freq = np.linspace(cfg.start_hz, cfg.end_hz, cfg.points)
        self.power = None
        self.maxhold = None
        self.last_recorded_trace = None
        self.last_recorded_timestamp = None
        self.last_peak_freq_hz = None
        self.last_peak_power_dbm = None
        self.scan_count = 0
        self.measurement_count = 0
        self.actual_rbw_khz = None
        self.last_scan_timeout = None
        self.last_scan_duration_s = None
        self.cycle_start_time = time.time()
        self.cycle_scan_count = 0
        self.measurements.clear()
        self.measurement_table.setRowCount(0)

        if cfg.autosave_csv:
            try:
                ensure_directory(cfg.save_dir)
            except Exception as exc:
                QMessageBox.critical(self, "Save Directory Error", str(exc))
                self.append_log(f"Could not create save directory {cfg.save_dir}: {exc}")
                return

        self.worker = ScanWorker(cfg, self)
        self.worker.scan_result.connect(self.handle_scan_result)
        self.worker.status_update.connect(self.handle_worker_status)
        self.worker.error_signal.connect(self.handle_worker_error)
        self.worker.connection_update.connect(self.handle_connection_update)
        self.worker.finished.connect(self.handle_worker_finished)

        self.running = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.act_start.setEnabled(False)
        self.act_stop.setEnabled(True)
        self.set_status("Starting scan worker...")
        self.append_log(
            f"Starting scan on {cfg.port} | span {format_frequency_hz(cfg.end_hz - cfg.start_hz)} | "
            f"points {cfg.points} | RBW {'auto' if cfg.rbw_khz == 0 else str(cfg.rbw_khz) + ' kHz'}"
        )
        self.worker.start()

    def stop_scan(self) -> None:
        if self.worker is None:
            self.running = False
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.act_start.setEnabled(True)
            self.act_stop.setEnabled(False)
            self.set_status("Stopped")
            return

        self.set_status("Stopping...")
        self.append_log("Stop requested")
        self.stop_button.setEnabled(False)
        self.act_stop.setEnabled(False)
        self.worker.stop()

    def handle_worker_status(self, text: str) -> None:
        self.set_status(text)
        self.append_log(text)

    def handle_worker_error(self, text: str) -> None:
        self.set_status(f"Error: {text}")
        self.append_log(f"Worker error: {text}")
        QMessageBox.critical(self, "Scan Error", text)

    def handle_connection_update(self, text: str) -> None:
        self.set_connection_status(text)
        self.append_log(text)

    def handle_worker_finished(self) -> None:
        self.running = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.act_start.setEnabled(True)
        self.act_stop.setEnabled(False)
        self.worker = None
        self.set_status("Stopped")
        self.append_log("Worker thread finished")
        self.refresh_metrics()

    # ---------------------------------------------------------------------
    # Scan updates, recording, and autosave logic
    # ---------------------------------------------------------------------
    def handle_scan_result(self, payload: Dict[str, Any]) -> None:
        if self.current_config is None:
            return

        power = payload["power"]
        self.power = power
        self.scan_count = int(payload["scan_index"])
        self.actual_rbw_khz = int(payload["actual_rbw_khz"])
        self.last_scan_timeout = float(payload["scan_timeout"])
        self.last_scan_duration_s = float(payload["scan_duration_s"])
        self.cycle_scan_count += 1

        if self.maxhold is None:
            self.maxhold = power.copy()
        else:
            self.maxhold = np.maximum(self.maxhold, power)

        elapsed_cycle = 0.0
        if self.cycle_start_time is not None:
            elapsed_cycle = time.time() - self.cycle_start_time
        ready_by_time = elapsed_cycle >= self.current_config.hold_time_s
        ready_by_sweeps = self.cycle_scan_count >= self.current_config.min_sweeps

        self.redraw_plot()

        if self.current_config.auto_cycle and ready_by_time and ready_by_sweeps:
            saved_path = self.record_measurement_from_maxhold(mode_label="Auto Cycle")
            self.maxhold = None
            self.cycle_start_time = time.time()
            self.cycle_scan_count = 0
            msg = (
                f"Recorded measurement {self.measurement_count} | "
                f"RBW {self.actual_rbw_khz} kHz | "
                f"released max-hold | last scan {self.last_scan_duration_s:.2f} s"
            )
            if saved_path:
                msg += f" | saved: {saved_path}"
            self.set_status(msg)
            self.append_log(msg)
        else:
            if self.current_config.auto_cycle:
                msg = (
                    f"scan {self.scan_count} | RBW {self.actual_rbw_khz} kHz | "
                    f"serial timeout {self.last_scan_timeout:.2f} s | "
                    f"building max-hold | cycle sweeps {self.cycle_scan_count}/{self.current_config.min_sweeps} | "
                    f"cycle time {elapsed_cycle:.2f}/{self.current_config.hold_time_s:.2f} s | "
                    f"last scan {self.last_scan_duration_s:.2f} s"
                )
            else:
                msg = (
                    f"scan {self.scan_count} | RBW {self.actual_rbw_khz} kHz | "
                    f"serial timeout {self.last_scan_timeout:.2f} s | continuous mode | "
                    f"cycle sweeps {self.cycle_scan_count} | last scan {self.last_scan_duration_s:.2f} s"
                )
            self.set_status(msg)
        self.refresh_metrics()

    def build_measurement_meta(self, trace: np.ndarray, mode_label: str) -> MeasurementMeta:
        if self.current_config is None or self.freq is None:
            raise RuntimeError("No active configuration available for measurement metadata")
        timestamp = now_string()
        peak_idx = int(np.argmax(trace))
        peak_freq = float(self.freq[peak_idx])
        peak_power = float(trace[peak_idx])
        return MeasurementMeta(
            measurement_index=self.measurement_count + 1,
            timestamp=timestamp,
            start_hz=self.current_config.start_hz,
            end_hz=self.current_config.end_hz,
            points=self.current_config.points,
            rbw_input_khz=self.current_config.rbw_khz,
            rbw_effective_khz=self.actual_rbw_khz or 0,
            peak_frequency_hz=peak_freq,
            peak_power_dbm=peak_power,
            mode=mode_label,
            file_path="",
        )

    def record_measurement_from_maxhold(self, mode_label: str = "Manual Record") -> str:
        if self.maxhold is None or self.freq is None:
            raise RuntimeError("No max-hold trace is available to record")
        if self.current_config is None:
            raise RuntimeError("No active configuration available")

        trace = self.maxhold.copy()
        meta = self.build_measurement_meta(trace, mode_label)
        self.measurement_count += 1
        meta.measurement_index = self.measurement_count
        self.last_recorded_trace = trace
        self.last_recorded_timestamp = meta.timestamp

        file_path = ""
        if self.current_config.autosave_csv:
            ensure_directory(self.current_config.save_dir)
            filename = f"measurement_{meta.measurement_index:04d}_{safe_timestamp_for_filename(meta.timestamp)}.csv"
            file_path = str(Path(self.current_config.save_dir) / filename)
            save_trace_csv(file_path, self.freq.copy(), trace.copy(), meta)
            meta.file_path = file_path

        self.measurements.append(meta)
        self.measurement_table.add_measurement(meta)
        self.card_last_recorded.set_value(meta.timestamp)
        self.refresh_metrics()
        self.redraw_plot()
        return file_path

    def record_now(self) -> None:
        try:
            file_path = self.record_measurement_from_maxhold(mode_label="Manual Record")
            msg = f"Manual record completed #{self.measurement_count}"
            if file_path:
                msg += f" | saved: {file_path}"
            self.set_status(msg)
            self.append_log(msg)
        except Exception as exc:
            QMessageBox.warning(self, "Record Warning", str(exc))
            self.append_log(f"Record failed: {exc}")

    # ---------------------------------------------------------------------
    # Export helpers
    # ---------------------------------------------------------------------
    def export_trace_with_dialog(self, trace: Optional[np.ndarray], default_name: str, mode_label: str) -> None:
        if trace is None or self.freq is None:
            QMessageBox.warning(self, "Export Warning", "There is no trace data available for export.")
            return
        if self.current_config is None:
            QMessageBox.warning(self, "Export Warning", "No active configuration available.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {mode_label}",
            str(Path.home() / default_name),
            "CSV Files (*.csv)",
        )
        if not path:
            return

        meta = self.build_measurement_meta(trace, mode_label)
        meta.file_path = path
        save_trace_csv(path, self.freq.copy(), trace.copy(), meta)
        self.set_status(f"Exported {mode_label}: {path}")
        self.append_log(f"Exported {mode_label} to {path}")

    def export_current_raw_trace(self) -> None:
        self.export_trace_with_dialog(self.power, "tinySA_raw_trace.csv", "Raw Export")

    def export_maxhold_trace(self) -> None:
        self.export_trace_with_dialog(self.maxhold, "tinySA_maxhold_trace.csv", "Max Hold Export")

    def export_recorded_trace(self) -> None:
        self.export_trace_with_dialog(self.last_recorded_trace, "tinySA_recorded_trace.csv", "Last Recorded Export")

    # ---------------------------------------------------------------------
    # Save directory and file path helpers
    # ---------------------------------------------------------------------
    def browse_save_directory(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose Save Directory",
            self.edit_save_dir.text().strip() or str(Path.home()),
        )
        if selected:
            self.edit_save_dir.setText(selected)
            self.append_log(f"Save directory set to {selected}")
            self.update_config_summary()

    def open_save_directory_in_file_manager(self) -> None:
        directory = self.edit_save_dir.text().strip() or DEFAULT_SAVE_DIR
        try:
            ensure_directory(directory)
        except Exception as exc:
            QMessageBox.critical(self, "Directory Error", str(exc))
            self.append_log(f"Cannot create/open save dir {directory}: {exc}")
            return

        path = os.path.abspath(directory)
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        if opened:
            self.set_status(f"Opened save directory: {path}")
            self.append_log(f"Opened save directory in file manager: {path}")
        else:
            self.append_log(f"Could not open directory in file manager; path is {path}")
            QMessageBox.information(self, "Save Directory", f"Save directory:\n{path}")

    def show_selected_measurement_file(self) -> None:
        path = self.measurement_table.selected_file_path()
        if not path:
            QMessageBox.information(self, "Measurement File", "Select a measurement row that has a saved file path.")
            return
        QMessageBox.information(self, "Measurement File", path)

    def clear_measurement_table(self) -> None:
        self.measurement_table.setRowCount(0)
        self.measurements.clear()
        self.append_log("Measurement table cleared")

    # ---------------------------------------------------------------------
    # Plot and metrics updates
    # ---------------------------------------------------------------------
    def redraw_plot(self) -> None:
        mode = self.combo_mode.currentText()
        peak_freq, peak_power = self.plot_canvas.redraw(
            freq=None if self.freq is None else self.freq.copy(),
            raw=None if self.power is None else self.power.copy(),
            maxhold=None if self.maxhold is None else self.maxhold.copy(),
            recorded=None if self.last_recorded_trace is None else self.last_recorded_trace.copy(),
            mode=mode,
            y_auto=self.check_y_auto.isChecked(),
            y_min_dbm=float(self.spin_y_min.value()),
            y_max_dbm=float(self.spin_y_max.value()),
            peak_marker_enabled=self.check_peak_marker.isChecked(),
        )
        self.last_peak_freq_hz = peak_freq
        self.last_peak_power_dbm = peak_power
        self.refresh_metrics()

    def refresh_metrics(self) -> None:
        self.card_scans.set_value(str(self.scan_count))
        self.card_measurements.set_value(str(self.measurement_count))
        self.card_rbw.set_value(
            f"{self.actual_rbw_khz} kHz" if self.actual_rbw_khz is not None else "—"
        )
        self.card_last_scan.set_value(format_seconds(self.last_scan_duration_s))

        if self.last_peak_freq_hz is not None and self.last_peak_power_dbm is not None:
            self.card_peak.set_value(
                f"{format_frequency_hz(self.last_peak_freq_hz)}\n{self.last_peak_power_dbm:.2f} dBm"
            )
        else:
            self.card_peak.set_value("—")

        if self.current_config is not None and self.cycle_start_time is not None:
            elapsed = max(0.0, time.time() - self.cycle_start_time)
            cycle_text = f"{self.cycle_scan_count} sweeps\n{elapsed:.2f}/{self.current_config.hold_time_s:.2f} s"
            self.card_cycle.set_value(cycle_text)
        else:
            self.card_cycle.set_value("0 sweeps")

        self.card_last_recorded.set_value(self.last_recorded_timestamp or "—")

    def update_runtime_metrics(self) -> None:
        self.refresh_metrics()

    def on_y_auto_toggled(self, checked: bool) -> None:
        self.spin_y_min.setEnabled(not checked)
        self.spin_y_max.setEnabled(not checked)
        self.redraw_plot()

    # ---------------------------------------------------------------------
    # Dialogs
    # ---------------------------------------------------------------------
    def show_about(self) -> None:
        text = (
            f"<b>{APP_NAME}</b><br><br>"
            "PyQt6-based tinySA desktop spectrum console.<br><br>"
            "Major upgrades in this version:<br>"
            "• unit-aware input widgets<br>"
            "• explicit RBW control in kHz<br>"
            "• modern dashboard layout<br>"
            "• measurement history table<br>"
            "• safer threading and better status reporting<br>"
            "• CSV export, config save/load, and cleaner plotting"
        )
        QMessageBox.information(self, "About", text)

    # ---------------------------------------------------------------------
    # Window lifecycle
    # ---------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Exit",
                "A scan is still running. Stop it and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.stop_scan()
            if self.worker is not None:
                self.worker.wait(3000)
        event.accept()


# -------------------------------------------------------------------------
# Application bootstrap
# -------------------------------------------------------------------------
def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setStyle("Fusion")
    app.setStyleSheet(THEME_QSS)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
