import tkinter as tk
from tkinter import scrolledtext, messagebox, filedialog
import numpy as np
import re
import csv

# ---------- Processing functions ----------

def extract_line_based(text):
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
    return values


def extract_trigger_based(text):
    pattern = r"seconds=([\d\.]+)"
    matches = re.findall(pattern, text)
    values = []
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            continue
    return values


def display_results(values, label):
    if not values:
        label.config(text="❌ No valid numeric values found.")
        return

    vals = np.array(values)
    label.config(text=
        f"✅ Count: {len(vals)}\n"
        f"Average: {np.mean(vals):.4f}\n"
        f"Std Dev: {np.std(vals):.4f}\n"
        f"Min: {np.min(vals):.4f}\n"
        f"Max: {np.max(vals):.4f}"
    )

# ---------- Export functions ----------

def export_single(values):
    if not values:
        messagebox.showerror("Error", "No data to export.")
        return

    filename = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv")]
    )
    if not filename: return

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Values"])
        for v in values:
            writer.writerow([v])

    messagebox.showinfo("Export Successful", f"Saved to:\n{filename}")


def export_both(values1, values2):
    if not values1 and not values2:
        messagebox.showerror("Error", "No data to export.")
        return

    filename = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv")]
    )
    if not filename: return

    max_len = max(len(values1), len(values2))
    values1 += ["" for _ in range(max_len - len(values1))]
    values2 += ["" for _ in range(max_len - len(values2))]

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["LineBasedValues", "TriggerBasedValues"])
        for i in range(max_len):
            writer.writerow([values1[i], values2[i]])

    messagebox.showinfo("Export Successful", f"Saved to:\n{filename}")


# ---------- Windows ----------

def open_line_based():
    win = tk.Toplevel()
    win.title("Line-Based Processor")

    tk.Label(win, text="Paste 4-column space-separated data:").pack()
    input_box = scrolledtext.ScrolledText(win, width=60, height=15)
    input_box.pack(pady=5)

    result_label = tk.Label(win, text="", font=("Arial", 12), justify="left")
    result_label.pack()

    vals = []

    def run_processing():
        nonlocal vals
        vals = extract_line_based(input_box.get("1.0", tk.END))
        display_results(vals, result_label)

    tk.Button(win, text="Process", command=run_processing).pack(pady=5)
    tk.Button(win, text="Export CSV",
              command=lambda: export_single(vals)).pack(pady=5)


def open_trigger_based():
    win = tk.Toplevel()
    win.title("Trigger-Based Processor")

    tk.Label(win, text="Paste text containing 'seconds=' values:").pack()
    input_box = scrolledtext.ScrolledText(win, width=60, height=15)
    input_box.pack(pady=5)

    result_label = tk.Label(win, text="", font=("Arial", 12), justify="left")
    result_label.pack()

    vals = []

    def run_processing():
        nonlocal vals
        vals = extract_trigger_based(input_box.get("1.0", tk.END))
        display_results(vals, result_label)

    tk.Button(win, text="Process", command=run_processing).pack(pady=5)
    tk.Button(win, text="Export CSV",
              command=lambda: export_single(vals)).pack(pady=5)


def open_both():
    win = tk.Toplevel()
    win.title("Both Modes")

    # Left
    lf = tk.LabelFrame(win, text="Line-Based")
    lf.grid(row=0, column=0, padx=10, pady=5)

    input1 = scrolledtext.ScrolledText(lf, width=50, height=12)
    input1.pack()
    res1 = tk.Label(lf, text="", justify="left")
    res1.pack()

    # Right
    rf = tk.LabelFrame(win, text="Trigger-Based")
    rf.grid(row=0, column=1, padx=10, pady=5)

    input2 = scrolledtext.ScrolledText(rf, width=50, height=12)
    input2.pack()
    res2 = tk.Label(rf, text="", justify="left")
    res2.pack()

    vals1 = []
    vals2 = []

    def proc_left():
        nonlocal vals1
        vals1 = extract_line_based(input1.get("1.0", tk.END))
        display_results(vals1, res1)

    def proc_right():
        nonlocal vals2
        vals2 = extract_trigger_based(input2.get("1.0", tk.END))
        display_results(vals2, res2)

    tk.Button(lf, text="Process", command=proc_left).pack(pady=5)
    tk.Button(rf, text="Process", command=proc_right).pack(pady=5)

    tk.Button(win, text="Export Combined CSV",
              command=lambda: export_both(vals1, vals2)).grid(
        row=1, column=0, columnspan=2, pady=10
    )


# ---------- Launch Window ----------

root = tk.Tk()
root.title("Select Processing Mode")

tk.Label(root, text="Choose processing mode:").pack(pady=10)

tk.Button(root, text="1️⃣ Line-Based Only",
          width=25, command=open_line_based).pack(pady=5)

tk.Button(root, text="2️⃣ Trigger-Based Only",
          width=25, command=open_trigger_based).pack(pady=5)

tk.Button(root, text="3️⃣ Both Windows",
          width=25, command=open_both).pack(pady=10)

root.mainloop()
