#!/usr/bin/env python3

import time
import struct
import threading
import os
import csv
from datetime import datetime
from queue import Queue, Empty

import numpy as np
import serial
from serial.tools import list_ports

import tkinter as tk
from tkinter import ttk, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


VID = 0x0483
PID = 0x5740


def getport():
    for device in list_ports.comports():
        if device.vid == VID and device.pid == PID:
            return device.device
    raise OSError("tinySA not found")


class TinySA:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=1, write_timeout=2)
        self.lock = threading.Lock()

    def close(self):
        with self.lock:
            try:
                if self.ser and self.ser.is_open:
                    self.ser.close()
            except Exception:
                pass

    def _drain_input(self):
        # Do not loop forever. Drain a few times only.
        for _ in range(5):
            waiting = self.ser.in_waiting
            if waiting <= 0:
                break
            self.ser.read(waiting)
            time.sleep(0.01)

    def _read_until_with_abort(self, marker, stop_event, hard_timeout_s):
        start = time.time()
        buf = bytearray()

        while True:
            if stop_event.is_set():
                raise RuntimeError("Scan stopped by user")

            if time.time() - start > hard_timeout_s:
                raise TimeoutError(f"Timed out waiting for {marker!r}")

            chunk = self.ser.read(1)
            if chunk:
                buf += chunk
                if buf.endswith(marker):
                    return bytes(buf)
            else:
                time.sleep(0.002)

    def scan(self, f_low, f_high, points, rbw, stop_event):
        with self.lock:
            if stop_event.is_set():
                raise RuntimeError("Scan stopped by user")

            self._drain_input()

            if rbw == 0:
                rbw_k = (f_high - f_low) * 7e-6
            else:
                rbw_k = rbw / 1e3

            rbw_k = max(3, min(600, rbw_k))

            self.ser.write(f"rbw {int(rbw_k)}\r".encode())
            self._read_until_with_abort(b"ch> ", stop_event, hard_timeout_s=3.0)

            timeout = ((f_high - f_low) / 20e3) / (rbw_k ** 2) + points / 500 + 1
            hard_timeout = max(3.0, timeout * 2.0)
            self.ser.timeout = 0.2

            self.ser.write(f"scanraw {int(f_low)} {int(f_high)} {int(points)}\r".encode())

            self._read_until_with_abort(b"{", stop_event, hard_timeout_s=hard_timeout)
            raw = self._read_until_with_abort(b"}ch> ", stop_event, hard_timeout_s=hard_timeout)

            # Best effort to restore auto RBW. Ignore failures during stop.
            try:
                if not stop_event.is_set():
                    self.ser.write(b"rbw auto\r")
                    self._read_until_with_abort(b"ch> ", stop_event, hard_timeout_s=3.0)
            except Exception:
                pass

            payload = raw[:-5]

            expected_len = points * 3
            if len(payload) != expected_len:
                raise ValueError(
                    f"Unexpected payload length: got {len(payload)}, expected {expected_len}"
                )

            data = struct.unpack("<" + "xH" * points, payload)
            arr = np.array(data, dtype=np.uint16)

            SCALE = 128
            power = arr / 32 - SCALE

            return power


class RTPlotter:
    def __init__(self, root):
        self.root = root
        root.title("tinySA RT Plotter")

        self.running = False
        self.worker = None
        self.stop_event = threading.Event()
        self.data_lock = threading.Lock()
        self.msg_queue = Queue()

        self.tiny = None
        self.maxhold = None
        self.freq = None
        self.power = None
        self.scan_count = 0

        self.measurement_count = 0
        self.last_recorded_trace = None
        self.last_recorded_timestamp = None

        self.cycle_start_time = None
        self.cycle_scan_count = 0

        self.build_gui()
        self.build_plot()

    def build_gui(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill=tk.X)

        ttk.Label(frame, text="Start Hz").grid(row=0, column=0, sticky="w")
        self.start = tk.StringVar(value="2300000000")
        ttk.Entry(frame, textvariable=self.start, width=15).grid(row=0, column=1, sticky="w")

        ttk.Label(frame, text="End Hz").grid(row=0, column=2, sticky="w")
        self.end = tk.StringVar(value="2500000000")
        ttk.Entry(frame, textvariable=self.end, width=15).grid(row=0, column=3, sticky="w")

        ttk.Label(frame, text="Points").grid(row=0, column=4, sticky="w")
        self.points_var = tk.StringVar(value="401")
        ttk.Entry(frame, textvariable=self.points_var, width=8).grid(row=0, column=5, sticky="w")

        ttk.Label(frame, text="RBW").grid(row=0, column=6, sticky="w")
        self.rbw = tk.StringVar(value="0")
        ttk.Entry(frame, textvariable=self.rbw, width=8).grid(row=0, column=7, sticky="w")

        ttk.Label(frame, text="Display").grid(row=1, column=0, sticky="w")
        self.mode = tk.StringVar(value="Raw")
        ttk.Combobox(
            frame,
            textvariable=self.mode,
            values=["Raw", "Max Hold", "Last Recorded"],
            state="readonly",
            width=12
        ).grid(row=1, column=1, sticky="w")

        ttk.Label(frame, text="Hold Time (s)").grid(row=1, column=2, sticky="w")
        self.hold_time = tk.StringVar(value="3")
        ttk.Entry(frame, textvariable=self.hold_time, width=8).grid(row=1, column=3, sticky="w")

        ttk.Label(frame, text="Min Sweeps").grid(row=1, column=4, sticky="w")
        self.min_sweeps = tk.StringVar(value="3")
        ttk.Entry(frame, textvariable=self.min_sweeps, width=8).grid(row=1, column=5, sticky="w")

        self.auto_cycle = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="Auto Cycle Max Hold",
            variable=self.auto_cycle
        ).grid(row=1, column=6, columnspan=2, sticky="w")

        ttk.Label(frame, text="Port").grid(row=2, column=0, sticky="w")
        self.port = tk.StringVar()
        ttk.Entry(frame, textvariable=self.port, width=18).grid(row=2, column=1, sticky="w")

        self.autosave = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Autosave CSV",
            variable=self.autosave
        ).grid(row=2, column=2, sticky="w")

        ttk.Label(frame, text="Save Dir").grid(row=2, column=3, sticky="w")
        self.save_dir = tk.StringVar(value="measurements")
        ttk.Entry(frame, textvariable=self.save_dir, width=20).grid(row=2, column=4, columnspan=2, sticky="w")

        ttk.Button(frame, text="Auto Detect", command=self.detect).grid(row=2, column=6, sticky="w")

        self.start_btn = ttk.Button(frame, text="Start", command=self.start_scan)
        self.start_btn.grid(row=3, column=0, sticky="w")

        self.stop_btn = ttk.Button(frame, text="Stop", command=self.stop_scan, state=tk.DISABLED)
        self.stop_btn.grid(row=3, column=1, sticky="w")

        ttk.Button(frame, text="Reset MaxHold", command=self.reset_max).grid(row=3, column=2, sticky="w")
        ttk.Button(frame, text="Record Now", command=self.record_now).grid(row=3, column=3, sticky="w")

        self.status = tk.StringVar(value="Idle")
        ttk.Label(self.root, textvariable=self.status, relief=tk.SUNKEN, anchor="w").pack(fill=tk.X)

        self.meas_status = tk.StringVar(value="Measurements: 0")
        ttk.Label(self.root, textvariable=self.meas_status, relief=tk.SUNKEN, anchor="w").pack(fill=tk.X)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_plot(self):
        self.fig = Figure(figsize=(10, 5))
        self.ax = self.fig.add_subplot(111)

        self.raw_line, = self.ax.plot([], [], label="Raw")
        self.max_line, = self.ax.plot([], [], label="Max Hold")
        self.rec_line, = self.ax.plot([], [], label="Last Recorded")

        self.ax.set_xlabel("Frequency (Hz)")
        self.ax.set_ylabel("dBm")
        self.ax.grid(True)
        self.ax.legend()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def post_status(self, text):
        self.msg_queue.put(("status", text))

    def post_meas_status(self, text):
        self.msg_queue.put(("meas_status", text))

    def process_ui_queue(self):
        try:
            while True:
                kind, text = self.msg_queue.get_nowait()
                if kind == "status":
                    self.status.set(text)
                elif kind == "meas_status":
                    self.meas_status.set(text)
        except Empty:
            pass

        self.root.after(50, self.process_ui_queue)

    def detect(self):
        try:
            p = getport()
            self.port.set(p)
            self.status.set(f"tinySA detected on {p}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def reset_max(self):
        with self.data_lock:
            self.maxhold = None
            self.cycle_start_time = time.time()
            self.cycle_scan_count = 0
        self.status.set("Max Hold reset")

    def record_now(self):
        with self.data_lock:
            if self.maxhold is None or self.freq is None:
                messagebox.showwarning("Warning", "No max hold data available to record yet.")
                return
            saved_path = self._record_measurement_locked()

        if saved_path:
            self.status.set(f"Manual record completed | saved: {saved_path}")
        else:
            self.status.set("Manual record completed")

    def start_scan(self):
        if self.worker is not None and self.worker.is_alive():
            messagebox.showwarning("Warning", "Scan thread is already running.")
            return

        try:
            port = self.port.get().strip() or getport()

            self.f_low = float(self.start.get())
            self.f_high = float(self.end.get())
            self.points = int(self.points_var.get())
            self.rbw_hz = float(self.rbw.get())

            self.hold_time_s = float(self.hold_time.get())
            self.min_sweeps_n = int(self.min_sweeps.get())

            if self.f_high <= self.f_low:
                raise ValueError("End Hz must be greater than Start Hz")
            if self.points < 2:
                raise ValueError("Points must be at least 2")
            if self.hold_time_s < 0:
                raise ValueError("Hold Time must be >= 0")
            if self.min_sweeps_n < 1:
                raise ValueError("Min Sweeps must be at least 1")

            self.freq = np.linspace(self.f_low, self.f_high, self.points)

            self.tiny = TinySA(port)

        except Exception as e:
            messagebox.showerror("Input Error", str(e))
            return

        with self.data_lock:
            self.running = True
            self.stop_event.clear()
            self.scan_count = 0
            self.measurement_count = 0
            self.power = None
            self.maxhold = None
            self.last_recorded_trace = None
            self.last_recorded_timestamp = None
            self.cycle_start_time = time.time()
            self.cycle_scan_count = 0

        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status.set("Starting scan...")

        self.worker = threading.Thread(target=self.loop, daemon=True)
        self.worker.start()

    def stop_scan(self):
        self.stop_btn.config(state=tk.DISABLED)
        self.status.set("Stopping...")
        self.stop_event.set()

        tiny = self.tiny
        if tiny is not None:
            try:
                tiny.close()
            except Exception:
                pass

        self.root.after(100, self.finish_stop_check)

    def finish_stop_check(self):
        alive = self.worker is not None and self.worker.is_alive()
        if alive:
            self.root.after(100, self.finish_stop_check)
            return

        with self.data_lock:
            self.running = False

        self.worker = None
        self.tiny = None
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status.set("Stopped")

    def save_trace_csv(self, freq, power, timestamp_str, measurement_idx):
        save_dir = self.save_dir.get().strip() or "measurements"
        os.makedirs(save_dir, exist_ok=True)

        safe_ts = timestamp_str.replace(":", "-").replace(" ", "_")
        filename = f"measurement_{measurement_idx:04d}_{safe_ts}.csv"
        path = os.path.join(save_dir, filename)

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["measurement_index", measurement_idx])
            writer.writerow(["timestamp", timestamp_str])
            writer.writerow(["start_hz", self.f_low])
            writer.writerow(["end_hz", self.f_high])
            writer.writerow(["points", self.points])
            writer.writerow(["rbw_input_hz", self.rbw_hz])
            writer.writerow([])
            writer.writerow(["frequency_hz", "power_dbm"])
            for fval, pval in zip(freq, power):
                writer.writerow([fval, pval])

        return path

    def _record_measurement_locked(self):
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.measurement_count += 1
        self.last_recorded_trace = self.maxhold.copy()
        self.last_recorded_timestamp = timestamp_str

        saved_path = None
        if self.autosave.get():
            saved_path = self.save_trace_csv(
                self.freq.copy(),
                self.last_recorded_trace.copy(),
                timestamp_str,
                self.measurement_count
            )

        self.post_meas_status(
            f"Measurements: {self.measurement_count} | Last: {timestamp_str}"
        )

        return saved_path

    def loop(self):
        try:
            while not self.stop_event.is_set():
                t0 = time.time()

                power = self.tiny.scan(
                    self.f_low,
                    self.f_high,
                    self.points,
                    self.rbw_hz,
                    self.stop_event
                )

                with self.data_lock:
                    self.power = power
                    self.scan_count += 1
                    self.cycle_scan_count += 1

                    if self.maxhold is None:
                        self.maxhold = power.copy()
                    else:
                        self.maxhold = np.maximum(self.maxhold, power)

                    elapsed_cycle = time.time() - self.cycle_start_time
                    ready_by_time = elapsed_cycle >= self.hold_time_s
                    ready_by_sweeps = self.cycle_scan_count >= self.min_sweeps_n

                    saved_path = None

                    if self.auto_cycle.get() and ready_by_time and ready_by_sweeps:
                        saved_path = self._record_measurement_locked()
                        self.maxhold = None
                        self.cycle_start_time = time.time()
                        self.cycle_scan_count = 0

                dt = time.time() - t0

                if self.auto_cycle.get():
                    if saved_path is None:
                        self.post_status(
                            f"scan {self.scan_count} | building max hold | "
                            f"cycle sweeps {self.cycle_scan_count}/{self.min_sweeps_n} | "
                            f"cycle time {elapsed_cycle:.2f}/{self.hold_time_s:.2f}s | "
                            f"last scan {dt:.2f}s"
                        )
                    else:
                        msg = (
                            f"Recorded measurement {self.measurement_count} | "
                            f"released max hold | last scan {dt:.2f}s"
                        )
                        if saved_path:
                            msg += f" | saved: {saved_path}"
                        self.post_status(msg)
                else:
                    self.post_status(
                        f"scan {self.scan_count} | continuous mode | "
                        f"cycle sweeps {self.cycle_scan_count} | last scan {dt:.2f}s"
                    )

        except RuntimeError as e:
            if str(e) != "Scan stopped by user":
                self.post_status(f"Runtime error: {e}")
        except Exception as e:
            self.post_status(f"Error: {e}")
        finally:
            try:
                if self.tiny is not None:
                    self.tiny.close()
            except Exception:
                pass

    def update_plot(self):
        with self.data_lock:
            freq = None if self.freq is None else self.freq.copy()
            power = None if self.power is None else self.power.copy()
            maxhold = None if self.maxhold is None else self.maxhold.copy()
            recorded = None if self.last_recorded_trace is None else self.last_recorded_trace.copy()
            mode = self.mode.get()

        if freq is not None:
            self.raw_line.set_visible(False)
            self.max_line.set_visible(False)
            self.rec_line.set_visible(False)

            y = None

            if mode == "Raw" and power is not None:
                self.raw_line.set_data(freq, power)
                self.raw_line.set_visible(True)
                y = power
            elif mode == "Max Hold" and maxhold is not None:
                self.max_line.set_data(freq, maxhold)
                self.max_line.set_visible(True)
                y = maxhold
            elif mode == "Last Recorded" and recorded is not None:
                self.rec_line.set_data(freq, recorded)
                self.rec_line.set_visible(True)
                y = recorded
            elif power is not None:
                self.raw_line.set_data(freq, power)
                self.raw_line.set_visible(True)
                y = power

            if y is not None and len(y) > 0:
                self.ax.set_xlim(freq[0], freq[-1])

                ymin = float(np.min(y) - 5)
                ymax = float(np.max(y) + 5)

                if ymin == ymax:
                    ymin -= 1
                    ymax += 1

                self.ax.set_ylim(ymin, ymax)

            self.canvas.draw_idle()

        self.root.after(100, self.update_plot)

    def on_close(self):
        self.stop_event.set()

        try:
            if self.tiny is not None:
                self.tiny.close()
        except Exception:
            pass

        self.root.destroy()


def main():
    root = tk.Tk()
    app = RTPlotter(root)
    root.after(50, app.process_ui_queue)
    root.after(100, app.update_plot)
    root.mainloop()


if __name__ == "__main__":
    main()
