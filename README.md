# 💡 Lichaser BLE LED Bridge

A lightweight Python-based service that bridges **Home Assistant** to **Lichaser Bluetooth LED Strips** via MQTT. This allows you to control your BLE lights as native Home Assistant entities without needing a dedicated hardware hub.

## 🚀 Features

* **Home Assistant Auto-Discovery**: Automatically appears in Home Assistant via MQTT Discovery protocols.
* **State Persistence**: Saves the last used color, brightness, and effect to `config.json` to survive service restarts or system reboots.
* **Automated Setup**: Includes a bash script for environment isolation (venv) and systemd service registration.

---

## 🛠️ Prerequisites

* **OS**: Linux
* **Hardware**: Bluetooth 4.0+ adapter (Internal or USB Dongle).
* **Software**: 
    * Python 3.10+
    * MQTT Broker (e.g., Mosquitto)
    * Home Assistant with the MQTT Integration enabled.

---

## 📦 Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/Jarauvi/lichaser_led_mqtt_bridge
    cd lichaser_led_mqtt_bridge
    ```

2.  **Configure the service**:
    Copy the example configuration and fill in your specific hardware and MQTT details:
    ```bash
    cp config.example.json config.json
    nano config.json
    ```

3.  **Run the Setup Script**:
    The provided script creates a virtual environment, installs requirements, and registers the systemd service:
    ```bash
    chmod +x setup.sh
    ./setup.sh
    ```

---

## ⚙️ Configuration (`config.json`)

| Key | Description |
| :--- | :--- |
| `mac_addr` | The Bluetooth MAC address of your LED strip (e.g., `AA:BB:CC:11:22:33`). |
| `mqtt_broker` | IP address or hostname of your MQTT broker. |
| `mqtt_port` | Usually `1883`. |
| `mqtt_user` | Your MQTT username. |
| `mqtt_password` | Your MQTT password. |
| `last_...` | **Managed automatically**: These keys store the persistent state of the LEDs. |

---

## 🚦 Management & Logs

Use standard `systemctl` and `journalctl` commands to manage the background process:

**Check service status**:
```bash
sudo systemctl status lichaser-bridge
