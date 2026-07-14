#!/usr/bin/env python3
r"""Interactive 2D Spatial Heatmap with Click-to-Place Node Triangulation.

Reads real-time CSV streams from capture.py and applies Fresnel Zone Elliptical
Triangulation. Allows users to click on the canvas to relocate nodes dynamically.

Controls:
  Press 't' -> Click canvas to move TX (Transmitter)
  Press '1' -> Click canvas to move Desk Node (RX1)
  Press '3' -> Click canvas to move Node 3 (RX2)
  Press 'c' -> Calibrate/zero out static background reflections
"""
import glob
import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Slider

# ==============================================================================
# 1. ROOM & NODE CONFIGURATION (in Feet)
# ==============================================================================
RAW_DIR = os.path.join("..", "data", "raw")
ROOM_WIDTH = 16.0   # Width in feet (X-axis)
ROOM_LENGTH = 16.0  # Length in feet (Y-axis)
GRID_RES = 60       # Grid resolution

# Initial physical (X, Y) coordinates in FEET
NODE_POS = {
    'tx':    np.array([2.0,  2.0]),    # Transmitter (Battery powered)
    'desk':  np.array([14.0, 2.0]),    # Desk PC Receiver
    'node3': np.array([8.0,  14.0])    # Hallway/Door Receiver
}

# ==============================================================================
# 2. STATE & GRID SETUP
# ==============================================================================
x_linspace = np.linspace(0, ROOM_WIDTH, GRID_RES)
y_linspace = np.linspace(0, ROOM_LENGTH, GRID_RES)
grid_x, grid_y = np.meshgrid(x_linspace, y_linspace)

temporal_grid = np.zeros((GRID_RES, GRID_RES))
calibration_grid = np.zeros((GRID_RES, GRID_RES))
sensitivity_val = 0.10
smoothing_decay = 0.70

# Interactive Placement Mode Tracker
active_node_select = None  # Holds 'tx', 'desk', or 'node3'

# ==============================================================================
# 3. DATA INGESTION
# ==============================================================================
def get_latest_node_activity():
    """Reads recent CSI variance from each receiver node's CSV file."""
    activity = {}
    if not os.path.exists(RAW_DIR):
        return activity

    csv_files = glob.glob(os.path.join(RAW_DIR, "*.csv"))
    for filepath in csv_files:
        filename = os.path.basename(filepath)
        node_name = filename.split('_')[0]
        
        if node_name not in NODE_POS:
            continue

        try:
            df = pd.read_csv(filepath)
            if len(df) < 2:
                continue
            
            recent_rows = df.tail(3)
            amplitudes = []
            for _, row in recent_rows.iterrows():
                csi_str = str(row['csi_data'])
                csi_vals = [float(val) for val in csi_str.split(',') if val.strip()]
                amplitudes.append(np.mean(np.abs(csi_vals)))
            
            activity[node_name] = np.var(amplitudes) if len(amplitudes) > 1 else np.mean(amplitudes)
        except Exception:
            continue
            
    return activity

# ==============================================================================
# 4. FRESNEL ZONE ELLIPTICAL TRIANGULATION
# ==============================================================================
def calculate_spatial_frame(activity_data):
    """Maps activity onto the grid using Fresnel Zone Ellipses between TX and RXs."""
    global temporal_grid
    instant_grid = np.zeros((GRID_RES, GRID_RES))
    
    tx_pos = NODE_POS['tx']
    
    if not activity_data:
        return np.maximum(0, temporal_grid - calibration_grid)

    for rx_name, val in activity_data.items():
        if rx_name == 'tx' or rx_name not in NODE_POS:
            continue
            
        rx_pos = NODE_POS[rx_name]
        
        # Calculate direct distance between TX and RX (Baseline LoS)
        los_dist = np.linalg.norm(tx_pos - rx_pos)
        
        # Calculate elliptical path from TX -> Grid Pixel -> RX
        dist_from_tx = np.sqrt((grid_x - tx_pos[0])**2 + (grid_y - tx_pos[1])**2)
        dist_from_rx = np.sqrt((grid_x - rx_pos[0])**2 + (grid_y - rx_pos[1])**2)
        total_path = dist_from_tx + dist_from_rx
        
        # Excess path length (How far pixel is outside direct LoS line)
        excess_path = np.abs(total_path - los_dist)
        
        # Fresnel Zone weighting: maximum along the direct line, decaying outward
        scaled_val = val * sensitivity_val
        influence = (scaled_val * 5.0) / (1.0 + (excess_path ** 2.0))
        instant_grid += influence

    # Temporal smoothing
    temporal_grid = (smoothing_decay * temporal_grid) + ((1.0 - smoothing_decay) * instant_grid)
    display_grid = np.maximum(0, temporal_grid - calibration_grid)
    return display_grid

# ==============================================================================
# 5. VISUALIZATION & INTERACTIVE UI SETUP
# ==============================================================================
fig, ax = plt.subplots(figsize=(9, 8))
plt.subplots_adjust(bottom=0.22)
ax.set_title("CSI Spatial Heatmap // Click-to-Place Active", fontsize=13, fontweight='bold', pad=12)
ax.set_xlabel("Room Width (Feet)")
ax.set_ylabel("Room Length (Feet)")

img_display = ax.imshow(
    np.zeros((GRID_RES, GRID_RES)),
    extent=(0, ROOM_WIDTH, 0, ROOM_LENGTH),
    origin='lower',
    cmap='inferno',
    vmin=0,
    vmax=3.0,
    interpolation='bilinear'
)
cbar = plt.colorbar(img_display, ax=ax, fraction=0.046, pad=0.04)
cbar.set_label("Fresnel Disturbance Intensity", rotation=270, labelpad=15)

# Plot node physical markers
scatter_plots = {}
annotations = {}
for name, coords in NODE_POS.items():
    color = '#ff0055' if name == 'tx' else '#00ffcc'
    marker = '^' if name == 'tx' else 'o'
    sc = ax.scatter(coords[0], coords[1], c=color, s=140, marker=marker, edgecolors='white', zorder=5, label=name.upper())
    ann = ax.annotate(f"  {name.upper()}", (coords[0], coords[1]), color=color, fontweight='bold', zorder=6)
    scatter_plots[name] = sc
    annotations[name] = ann

ax.legend(loc="upper right", framealpha=0.3)
ax.grid(True, linestyle='--', alpha=0.2, color='white')

# Sensitivity Slider
ax_slider = plt.axes([0.18, 0.08, 0.65, 0.03])
slider_sens = Slider(ax_slider, 'Sensitivity', 0.01, 0.50, valinit=sensitivity_val, color='#00ffcc')

def on_slider_change(val):
    global sensitivity_val
    sensitivity_val = val
slider_sens.on_changed(on_slider_change)

# ==============================================================================
# 6. MOUSE & KEYBOARD EVENT HANDLERS
# ==============================================================================
def on_key_press(event):
    global active_node_select, calibration_grid, temporal_grid
    key = event.key.lower() if event.key else ''
    
    if key == 'c':
        calibration_grid = temporal_grid.copy()
        ax.set_title("CSI Spatial Heatmap // CALIBRATED", color='lime', fontsize=13, fontweight='bold', pad=12)
    elif key == 't':
        active_node_select = 'tx'
        ax.set_title("CLICK CANVAS TO PLACE: [ TX TRANSMITTER ]", color='#ff0055', fontsize=13, fontweight='bold', pad=12)
    elif key == '1':
        active_node_select = 'desk'
        ax.set_title("CLICK CANVAS TO PLACE: [ DESK RX1 ]", color='#00ffcc', fontsize=13, fontweight='bold', pad=12)
    elif key == '3':
        active_node_select = 'node3'
        ax.set_title("CLICK CANVAS TO PLACE: [ NODE 3 RX2 ]", color='#00ffcc', fontsize=13, fontweight='bold', pad=12)
    
    fig.canvas.draw_idle()

def on_mouse_click(event):
    global active_node_select
    # Ensure click is inside the main plot area
    if event.inaxes != ax or active_node_select is None:
        return
        
    new_x, new_y = round(event.xdata, 1), round(event.ydata, 1)
    NODE_POS[active_node_select] = np.array([new_x, new_y])
    
    # Update visual markers
    scatter_plots[active_node_select].set_offsets([[new_x, new_y]])
    annotations[active_node_select].set_position((new_x, new_y))
    
    print(f" [!] Relocated {active_node_select.upper()} to X={new_x} ft, Y={new_y} ft")
    ax.set_title("CSI Spatial Heatmap // Click-to-Place Active", color='white', fontsize=13, fontweight='bold', pad=12)
    active_node_select = None
    fig.canvas.draw_idle()

fig.canvas.mpl_connect('key_press_event', on_key_press)
fig.canvas.mpl_connect('button_press_event', on_mouse_click)

# ==============================================================================
# 7. ANIMATION LOOP
# ==============================================================================
def animate(_):
    activity = get_latest_node_activity()
    frame_data = calculate_spatial_frame(activity)
    img_display.set_data(frame_data)
    return [img_display]

print("="*64)
print(" INTERACTIVE FRESNEL CSI TRIANGULATION ENGINE")
print(" Controls:")
print("   [ T ] key -> Click map to relocate TX Transmitter")
print("   [ 1 ] key -> Click map to relocate Desk RX1")
print("   [ 3 ] key -> Click map to relocate Node 3 RX2")
print("   [ C ] key -> Calibrate empty room background")
print("="*64)

ani = animation.FuncAnimation(fig, animate, interval=100, blit=True, cache_frame_data=False)
plt.show()