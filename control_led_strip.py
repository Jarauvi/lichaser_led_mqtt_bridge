import asyncio
import json
import logging
import math
import paho.mqtt.client as mqtt
from bleak import BleakClient

# --- CONFIG ---
MAC_ADDR = "08:65:F0:80:96:D7"
CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"

MQTT_BROKER = "192.168.2.10"
MQTT_USER = "mqtt_user"
MQTT_PASSWORD = "TietoVerkkoni11"

OBJECT_ID = "lichaser_led_strip"
COMMAND_TOPIC = f"homeassistant/light/{OBJECT_ID}/set"
STATE_TOPIC = f"homeassistant/light/{OBJECT_ID}/state"
DISCOVERY_TOPIC = f"homeassistant/light/{OBJECT_ID}/config"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lichaser")
bt_lock = asyncio.Lock()

class LedStrip:
    def __init__(self):
        self.num_segments = 20
        self.header_prefix = "80000057580ae1030014000014"
        self.teal = (0x0e, 0xe4, 0x0c)
        self.off = (0x00, 0x00, 0x00)

    def rgb_to_custom_hsv(self, r, g, b):
        """Maps RGB to the Hue scale found in your captures (Red=0, Green=60, Blue=120)"""
        r_f, g_f, b_f = r / 255.0, g / 255.0, b / 255.0
        max_c, min_c = max(r_f, g_f, b_f), min(r_f, g_f, b_f)
        diff = max_c - min_c

        # Calculate Hue
        if diff == 0: h = 0
        elif max_c == r_f: h = (60 * ((g_f - b_f) / diff) + 360) % 360
        elif max_c == g_f: h = (60 * ((b_f - r_f) / diff) + 120)
        elif max_c == b_f: h = (60 * ((r_f - g_f) / diff) + 240)
        
        # Map 0-360 degrees to your controller's 0-180 scale (based on Red 0, Green 60, Blue 120)
        # Your captures show Hue is degrees / 2
        h_byte = int(h / 2)
        s_byte = int(max_c * 100) if max_c != 0 else 0
        return h_byte, s_byte

    def generate_packet(self, sequence, r, g, b, brightness, effect=None):
        packet = bytearray([0x00, sequence])
        packet.extend(bytearray.fromhex(self.header_prefix))
        
        if effect == "Dashed":
            pattern = ([self.off]*4 + [self.teal]*4 + [self.off]*6 + [self.teal]*2 + [self.off]*2 + [self.teal]*2)
            for pr, pg, pb in pattern:
                packet.extend(bytearray([0xa1, pr, pg, pb]))
        else:
            h, s = self.rgb_to_custom_hsv(r, g, b)
            # Brightness Riddle: 0-255 -> 12-100
            v = int((brightness / 255.0) * (100 - 12) + 12) if brightness > 0 else 0
            for _ in range(self.num_segments):
                packet.extend(bytearray([0xa1, h, s, v]))
        return packet

strip_logic = LedStrip()

async def send_to_ble(r, g, b, br, effect):
    if bt_lock.locked(): return
    async with bt_lock:
        client = BleakClient(MAC_ADDR)
        try:
            await client.connect()
            await client.write_gatt_char(CHAR_UUID, bytearray([0x01, 0x00]), response=True)
            for p in ["00018000000c0d0a1014190c1d140c3301000fc9", "000280000005060aea818a8b59", "000380000002030aea81"]:
                await client.write_gatt_char(CHAR_UUID, bytearray.fromhex(p))
            
            packet = strip_logic.generate_packet(0x0c, r, g, b, br, effect)
            await client.write_gatt_char(CHAR_UUID, packet)
            
            # State Update
            state = {"state": "ON" if br > 0 else "OFF", "brightness": br, "color": {"r": r, "g": g, "b": b}, "effect": effect or "None"}
            mqtt_client.publish(STATE_TOPIC, json.dumps(state), retain=True)
        except Exception as e: logger.error(e)
        finally: await client.disconnect()

def on_connect(client, userdata, flags, rc, props=None):
    client.subscribe(COMMAND_TOPIC)
    discovery = {
        "name": "Lichaser LED", "unique_id": f"{OBJECT_ID}_unique", "schema": "json",
        "command_topic": COMMAND_TOPIC, "state_topic": STATE_TOPIC, "brightness": True,
        "supported_color_modes": ["rgb"], "effect": True, "effect_list": ["None", "Dashed"],
        "device": {"identifiers": ["lichaser_ble_bridge_01"], "name": "Lichaser Bluetooth Bridge"}
    }
    client.publish(DISCOVERY_TOPIC, json.dumps(discovery), retain=True)

def on_message(client, userdata, msg):
    d = json.loads(msg.payload.decode())
    br = d.get("brightness", 255) if d.get("state") == "ON" else 0
    c = d.get("color", {"r": 255, "g": 255, "b": 255})
    asyncio.run_coroutine_threadsafe(send_to_ble(c['r'], c['g'], c['b'], br, d.get("effect")), userdata['loop'])

async def main():
    loop = asyncio.get_running_loop()
    global mqtt_client
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata={'loop': loop})
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    mqtt_client.on_connect, mqtt_client.on_message = on_connect, on_message
    mqtt_client.connect(MQTT_BROKER, 1883)
    mqtt_client.loop_start()
    while True: await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())