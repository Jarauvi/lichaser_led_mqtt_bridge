import asyncio
import json
import logging
import os
import signal
import paho.mqtt.client as mqtt
from bleak import BleakClient

# --- LOAD/SAVE CONFIG ---
CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        logging.error(f"{CONFIG_FILE} not found!")
        exit(1)
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_state_to_config(strip_obj):
    """Saves only the light state back to the config file."""
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        
        data.update({
            "last_r": strip_obj.r,
            "last_g": strip_obj.g,
            "last_b": strip_obj.b,
            "last_br": strip_obj.br,
            "last_eff": strip_obj.eff
        })
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save state: {e}")

cfg = load_config()

# --- CONSTANTS ---
CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
OBJECT_ID = "lichaser_led_v4" 
COMMAND_TOPIC = f"homeassistant/light/{OBJECT_ID}/set"
STATE_TOPIC = f"homeassistant/light/{OBJECT_ID}/state"
DISCOVERY_TOPIC = f"homeassistant/light/{OBJECT_ID}/config"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lichaser")
bt_lock = asyncio.Lock()

class LedStrip:
    def __init__(self, initial_cfg):
        self.num_segments = 20
        self.header_prefix = "80000057580ae1030014000014"
        self.teal = (0x0e, 0xe4, 0x0c)
        self.off = (0x00, 0x00, 0x00)
        
        # Load memory from config file
        self.r = initial_cfg.get("last_r", 255)
        self.g = initial_cfg.get("last_g", 255)
        self.b = initial_cfg.get("last_b", 255)
        self.br = initial_cfg.get("last_br", 255)
        self.eff = initial_cfg.get("last_eff", "None")

    def rgb_to_custom_hsv(self, r, g, b):
        r_f, g_f, b_f = r / 255.0, g / 255.0, b / 255.0
        max_c, min_c = max(r_f, g_f, b_f), min(r_f, g_f, b_f)
        diff = max_c - min_c
        if diff == 0: h = 0
        elif max_c == r_f: h = (60 * ((g_f - b_f) / diff) + 360) % 360
        elif max_c == g_f: h = (60 * ((b_f - r_f) / diff) + 120)
        elif max_c == b_f: h = (60 * ((r_f - g_f) / diff) + 240)
        return int(h / 2), int(max_c * 100)

    def generate_packet(self, sequence):
        packet = bytearray([0x00, sequence])
        packet.extend(bytearray.fromhex(self.header_prefix))
        if self.eff == "Dashed":
            pattern = ([self.off]*4 + [self.teal]*4 + [self.off]*6 + [self.teal]*2 + [self.off]*2 + [self.teal]*2)
            for pr, pg, pb in pattern:
                packet.extend(bytearray([0xa1, pr, pg, pb]))
        else:
            h, s = self.rgb_to_custom_hsv(self.r, self.g, self.b)
            v = int((self.br / 255.0) * (100 - 12) + 12) if self.br > 0 else 0
            for _ in range(self.num_segments):
                packet.extend(bytearray([0xa1, h, s, v]))
        return packet

strip = LedStrip(cfg)

async def update_leds():
    if bt_lock.locked(): return
    async with bt_lock:
        client = BleakClient(cfg['mac_addr'], timeout=10.0)
        try:
            await client.connect()
            await client.write_gatt_char(CHAR_UUID, bytearray([0x01, 0x00]), response=True)
            for p in ["00018000000c0d0a1014190c1d140c3301000fc9", "000280000005060aea818a8b59", "000380000002030aea81"]:
                await client.write_gatt_char(CHAR_UUID, bytearray.fromhex(p))
            
            await client.write_gatt_char(CHAR_UUID, strip.generate_packet(0x0c))
            
            state_payload = {
                "state": "ON" if strip.br > 0 else "OFF",
                "brightness": strip.br,
                "color_mode": "rgb",
                "color": {"r": strip.r, "g": strip.g, "b": strip.b},
                "effect": strip.eff
            }
            mqtt_client.publish(STATE_TOPIC, json.dumps(state_payload), retain=True)
            save_state_to_config(strip) # Save to file after successful update
            logger.info("State applied and saved to config.")
        except Exception as e: 
            logger.error(f"BLE Error: {e}")
        finally: 
            if client.is_connected: await client.disconnect()

# --- MQTT HANDLERS ---
def on_connect(client, userdata, flags, rc, props=None):
    client.subscribe(COMMAND_TOPIC)
    discovery = {
        "name": "Lichaser LED Strip",
        "unique_id": "lichaser_v4_entity", 
        "schema": "json",
        "command_topic": COMMAND_TOPIC,
        "state_topic": STATE_TOPIC,
        "brightness": True,
        "color_mode": True,
        "supported_color_modes": ["rgb"],
        "effect": True,
        "effect_list": ["None", "Dashed"],
        "device": { "identifiers": ["lichaser_ble_v4"], "name": "Lichaser Bluetooth Bridge" }
    }
    client.publish(DISCOVERY_TOPIC, json.dumps(discovery), retain=True)

def on_message(client, userdata, msg):
    try:
        d = json.loads(msg.payload.decode())
        if "state" in d:
            if d["state"] == "OFF": strip.br = 0
            elif d["state"] == "ON" and strip.br == 0: strip.br = 255
        if "brightness" in d: strip.br = d["brightness"]
        if "color" in d:
            strip.r, strip.g, strip.b = d["color"]["r"], d["color"]["g"], d["color"]["b"]
            strip.eff = "None"
        if "effect" in d: strip.eff = d["effect"]
        asyncio.run_coroutine_threadsafe(update_leds(), userdata['loop'])
    except Exception as e: logger.error(f"MQTT Error: {e}")

async def main():
    loop = asyncio.get_running_loop()
    
    # Graceful shutdown handler
    def shutdown():
        logger.info("Shutdown signal received. Saving final state...")
        save_state_to_config(strip)
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    global mqtt_client
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata={'loop': loop})
    mqtt_client.username_pw_set(cfg['mqtt_user'], cfg['mqtt_password'])
    mqtt_client.on_connect, mqtt_client.on_message = on_connect, on_message
    mqtt_client.connect(cfg['mqtt_broker'], cfg['mqtt_port'])
    mqtt_client.loop_start()
    
    while True: await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass