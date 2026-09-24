# RJ Airplane Tracker Widget

A native Windows desktop widget for tracking live airborne aircraft within a geofenced radius around Mumbai International Airport (BOM) using OpenSky Network data.

**Architecture**: Python backend + WebView2 (Microsoft Edge) frontend with Leaflet.js for GPU-accelerated, buttery-smooth map rendering.

---

## 🚀 How to Run

Double-click `run.bat` or open a terminal in this directory and run:

```bash
pip install -r requirements.txt
python tracker_widget.py
```

---

## 🛑 How to Close the Application

### Method 1: Using the GUI Close Button (Recommended)
- Click the **✕** button in the top-right corner of the widget header.
- This gracefully stops the background polling thread, unhooks the Windows mutex, and completely terminates the process.

### Method 2: Alt+F4
- Press `Alt + F4` while the widget window is focused.

### Method 3: Terminating Ghost or Stuck Instances (Force Close)
If an older instance was launched in the background without a visible window and is still sending notifications:

1. Open **Command Prompt** or **PowerShell** and run:
   ```cmd
   taskkill /F /IM python.exe
   ```

2. Alternatively, via **Task Manager**:
   - Press `Ctrl + Shift + Esc`.
   - In the **Processes** tab, look for **Python** or **RJ Airplane Tracker**.
   - Right-click it and select **End task**.

---

## ⚙️ Features
- **GPU-Accelerated Map**: Leaflet.js rendered via WebView2 (Edge) — smooth 60 FPS zoom and pan.
- **Dark Premium UI**: CartoDB Dark Matter tiles with glassmorphism info cards and gradient header.
- **Geofence Tracking**: Defaults to 10 km around Mumbai Airport (19.09° N, 72.87° E).
- **Switchable Radius**: Quick buttons (5 / 10 / 15 / 20 / 30 km) to dynamically resize the geofence.
- **Aircraft Click Popup**: Click any airplane icon to see full telemetry — callsign, ICAO24, altitude (m/ft), speed (km/h / knots), heading, vertical rate, distance, and country.
- **Interactive Callsign Picker**: Select callsigns from a live list of detected flights instead of typing manually.
- **Resizable Window**: Drag any edge or corner to resize the widget freely.
- **Wi-Fi Protection**: Pauses polling when off Wi-Fi to save battery and mobile data.
- **Notification Filters**:
  - First poll is silently seeded to eliminate startup toast spam.
  - Choose between: **All Airborne Flights**, **Specific Callsigns Only** (exact match), or **Low Altitude Only**.
  - Can be toggled OFF completely with zero background notifications.
- **Single Instance Enforcement**: Windows named mutex prevents multiple instances from running at the same time.

---

## 📁 File Structure
| File | Purpose |
|------|---------|
| `tracker_widget.py` | Main entry point — pywebview host + Python↔JS bridge |
| `index.html` | Frontend UI — Leaflet map, info cards, settings panel |
| `india_boundary.geojson` / `india_boundary.js` | Official composite vector boundaries for India (SOI standard) |
| `opensky_service.py` | Background API polling thread with geofence filtering |
| `notification_mgr.py` | Smart toast notification manager with dedup & throttling |
| `config.py` | Central configuration and JSON settings persistence |
| `geofence.py` | Haversine math and bounding box calculations |
| `wifi_detector.py` | Windows Wi-Fi connectivity checker |
| `run.bat` | One-click launcher |

---

## 🔗 Repository
- **GitHub Repository**: [SujashBharadwaj/FlightTrackerApp](https://github.com/SujashBharadwaj/FlightTrackerApp)

