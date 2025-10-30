import tkinter as tk
from tkinter import scrolledtext, messagebox
import numpy as np
import re

# ---------- Processing functions ----------

def process_line_based(text, result_label):
    lines = text.splitlines()
    values = []

    for line in lines:
        parts = line.split()
        if len(parts) == 4:
            val_str = parts[2].rstrip('s')
            try:
                values.append(float(val_str))
            except ValueError:
                continue

    display_results(values, result_label)


def process_trigger_based(text, result_label):
    pattern = r"seconds=([\d\.]+)"
    matches = re.findall(pattern, text)

    values = []
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            continue

    display_results(values, result_label)


def display_results(values, result_label):
    if not values:
        result_label.config(
            text="❌ No valid numeric values found."
        )
        return

    vals = np.array(values)
    result = (
        f"✅ Count: {len(vals)}\n"
        f"Average: {np.mean(vals):.4f}\n"
        f"Std Dev: {np.std(vals):.4f}\n"
        f"Min: {np.min(vals):.4f}\n"
        f"Max: {np.max(vals):.4f}"
    )
    result_label.config(text=result)


# ---------- Windows ----------

def open_line_based():
    win = tk.Toplevel()
    win.title("Line-Based Processor")

    tk.Label(win, text="Paste 4-column space-separated data:").pack()
    input_box = scrolledtext.ScrolledText(win, width=60, height=15)
    input_box.pack(pady=5)

    result_label = tk.Label(win, text="", font=("Arial", 12), justify="left")
    result_label.pack()

    tk.Button(win, text="Process",
              command=lambda: process_line_based(input_box.get("1.0", tk.END),
                                                result_label)).pack(pady=10)


def open_trigger_based():
    win = tk.Toplevel()
    win.title("Trigger-Based Processor")

    tk.Label(win, text="Paste text containing 'seconds=' patterns:").pack()
    input_box = scrolledtext.ScrolledText(win, width=60, height=15)
    input_box.pack(pady=5)

    result_label = tk.Label(win, text="", font=("Arial", 12), justify="left")
    result_label.pack()

    tk.Button(win, text="Process",
              command=lambda: process_trigger_based(input_box.get("1.0", tk.END),
                                                    result_label)).pack(pady=10)


def open_both():
    win = tk.Toplevel()
    win.title("Both Processors")

    # Left - Line based
    lf = tk.LabelFrame(win, text="Line-Based")
    lf.grid(row=0, column=0, padx=10, pady=5)

    input_box1 = scrolledtext.ScrolledText(lf, width=50, height=12)
    input_box1.pack()
    result_label1 = tk.Label(lf, text="", justify="left")
    result_label1.pack()
    tk.Button(lf, text="Process",
              command=lambda: process_line_based(input_box1.get("1.0", tk.END),
                                                result_label1)).pack(pady=5)

    # Right - Trigger based
    rf = tk.LabelFrame(win, text="Trigger-Based")
    rf.grid(row=0, column=1, padx=10, pady=5)

    input_box2 = scrolledtext.ScrolledText(rf, width=50, height=12)
    input_box2.pack()
    result_label2 = tk.Label(rf, text="", justify="left")
    result_label2.pack()
    tk.Button(rf, text="Process",
              command=lambda: process_trigger_based(input_box2.get("1.0", tk.END),
                                                    result_label2)).pack(pady=5)


# ---------- Launcher Window ----------

root = tk.Tk()
root.title("Processing Mode Selector")

tk.Label(root, text="Choose processing mode:").pack(pady=10)

tk.Button(root, text="1️⃣ Line-Based Only",
          width=25, command=open_line_based).pack(pady=5)

tk.Button(root, text="2️⃣ Trigger-Based Only",
          width=25, command=open_trigger_based).pack(pady=5)

tk.Button(root, text="3️⃣ Both in Same Window",
          width=25, command=open_both).pack(pady=10)

root.mainloop()
