import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline

# Data
intervals = [0.125, 0.375, 0.625, 0.875, 1.125, 1.375, 1.625, 1.875]  # midpoints
throughput_mbs = [63.07, 99.66, 104.59, 102.77, 100.89, 106.90, 106.64, 106.14]

# Smooth curve using spline interpolation
x_smooth = np.linspace(min(intervals), max(intervals), 300)
spline = make_interp_spline(intervals, throughput_mbs, k=3)
y_smooth = spline(x_smooth)

# Plot
fig, ax = plt.subplots(figsize=(10, 6))

# Smooth curve in light blue, bold
ax.plot(x_smooth, y_smooth, color='#5BC8F5', linewidth=3, zorder=2)

# Data points
ax.scatter(intervals, throughput_mbs, color='#5BC8F5', s=80, zorder=3)

# Bold black axes labels and tick numbers
ax.set_xlabel('Time Interval (s)', fontsize=13, fontweight='bold', color='black')
ax.set_ylabel('Throughput (MB/s)', fontsize=13, fontweight='bold', color='black')
ax.set_title('Throughput Over Time', fontsize=15, fontweight='bold', color='black')

# Bold tick labels
ax.tick_params(axis='both', labelsize=11, colors='black', width=2)
for label in ax.get_xticklabels() + ax.get_yticklabels():
    label.set_fontweight('bold')
    label.set_color('black')

# Bold axis spines
for spine in ax.spines.values():
    spine.set_linewidth(2)
    spine.set_color('black')

# X-axis ticks at interval midpoints
ax.set_xticks(intervals)
ax.set_xticklabels(['0–0.25', '0.25–0.5', '0.5–0.75', '0.75–1.0',
                     '1.0–1.25', '1.25–1.5', '1.5–1.75', '1.75–2.0'],
                    rotation=30, ha='right', fontweight='bold', color='black')

ax.set_ylim(50, 120)
ax.grid(True, linestyle='--', alpha=0.4, color='gray')

plt.tight_layout()
plt.savefig('throughput_plot.png', dpi=150)
plt.show()
