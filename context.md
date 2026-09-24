Project Overview
The goal is to build a native, standalone Windows desktop widget for local flight tracking. The application will run as a frameless, always-on-top mini window displaying a live map. It will monitor a specific geofenced area based on user provided coordinates and issue native Windows notifications when specific aircraft fly overhead. The system operates entirely locally with no database or browser dependencies.

Technical Stack

Language: Python.

User Interface: CustomTkinter for a modern, frameless widget window.

Mapping: TkinterMapView for native map rendering without a web browser.

Data Source: OpenSky Network REST API via the requests library.

Notifications: Native Windows toast notifications using the win11toast library.

Core Requirements

Native Widget UI: The application must launch as a borderless window that stays on top of other applications. It should be small and unobtrusive, functioning strictly as a widget.

Geofencing: The system must accept bounding box coordinates to define the monitoring area. These coordinates will be passed to the OpenSky API to limit the data payload.

Map Integration: The widget must display an interactive map centered on the geofenced area. Aircraft must be plotted on this map using yellow markers.

Rate Limiting & Safety: Requests to the OpenSky API must be restricted to a safe interval of 30 to 60 seconds to respect public API limits and prevent IP bans.

Filtering & Notifications: The background logic must parse incoming flight data against a predefined list of interesting aircraft. When a match is found, it must trigger a Windows toast notification and update a state dictionary to prevent duplicate alerts.

Deployment: The application will run locally on a Windows environment. A simple batch script will handle installing dependencies and executing the Python script.

Repository & Map Geodata:
- Upstream / Target Repository: https://github.com/SujashBharadwaj/FlightTrackerApp
- Official Indian Boundaries: Composite vector borders (SOI standard) bundled as `india_boundary.geojson` / `india_boundary.js` and rendered via Leaflet vector overlay on the base world map.