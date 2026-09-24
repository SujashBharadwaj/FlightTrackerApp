"""
wifi_detector.py - Windows Wi-Fi connectivity checker.
Uses `netsh wlan show interfaces` to determine if the machine is connected
to a wireless network. If Wi-Fi is unavailable (e.g. Ethernet only, airplane
mode, or offline), the tracker pauses API requests.
"""

import subprocess


def is_wifi_connected() -> tuple[bool, str]:
    """
    Check whether the system is connected to a Wi-Fi network.

    Returns:
        (connected: bool, ssid: str)
        - connected is True when an active Wi-Fi connection is detected.
        - ssid contains the network name, or a descriptive status string.
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,  # Hide console flash
        )

        if result.returncode != 0:
            return False, "Wi-Fi adapter not found"

        output = result.stdout

        # Parse connection state
        state_connected = False
        ssid = ""

        for line in output.splitlines():
            stripped = line.strip()
            # Look for "State" line (e.g. "State : connected")
            if stripped.lower().startswith("state"):
                if "connected" in stripped.lower() and "disconnected" not in stripped.lower():
                    state_connected = True
            # Look for "SSID" line (but not "BSSID")
            if stripped.upper().startswith("SSID") and not stripped.upper().startswith("BSSID"):
                parts = stripped.split(":", 1)
                if len(parts) == 2:
                    ssid = parts[1].strip()

        if state_connected and ssid:
            return True, ssid
        elif state_connected:
            return True, "Connected (SSID hidden)"
        else:
            return False, "Disconnected"

    except FileNotFoundError:
        # netsh not available (unlikely on Windows, but safe)
        return False, "netsh unavailable"
    except subprocess.TimeoutExpired:
        return False, "Check timed out"
    except Exception as e:
        return False, f"Error: {e}"
