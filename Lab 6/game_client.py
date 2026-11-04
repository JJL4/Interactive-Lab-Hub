import time
import board
import busio
from adafruit_apds9960.apds9960 import APDS9960
import paho.mqtt.client as mqtt

TEAM_NAME = "simon_says_team"
PI_NAME = "pi1"      # CHANGE TO "pi2"
BROKER = "farlab.infosci.cornell.edu"
PORT = 1883
USER = "idd"
PASSWORD = "device@theFarm"

COMMAND_TOPIC = f"IDD/{TEAM_NAME}/simon/command"
MY_EVENT_TOPIC = f"IDD/{TEAM_NAME}/simon/{PI_NAME}/event"

# Initialize Sensor
i2c = busio.I2C(board.SCL, board.SDA)
apds = APDS9960(i2c)
apds.enable_proximity = True
apds.enable_color = True


def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    if payload.startswith("display:"):
        print("\n" + "*"*40)
        print(payload.replace("display:", ""))
        print("*"*40 + "\n")
    elif payload.startswith("result:"):
        print("-> " + payload.replace("result:", ""))


# Setup MQTT
client = mqtt.Client()
client.username_pw_set(USER, PASSWORD)
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.subscribe(COMMAND_TOPIC)
client.loop_start()

print(f"Hardware Sensor {PI_NAME} ready. Waiting for server...")

try:
    while True:
        action_detected = None

        # Check proximity first
        if apds.proximity > 200:
            action_detected = "close"
        else:
            # Check color if nothing is close
            r, g, b, c = apds.color_data
            if c > 50:
                if r > g + 50 and r > b + 50:
                    action_detected = "red"
                elif g > r + 50 and g > b + 50:
                    action_detected = "green"
                elif b > r + 50 and b > g + 50:
                    action_detected = "blue"
        if action_detected:
            print(f"[Triggered: {action_detected}]")
            client.publish(MY_EVENT_TOPIC, action_detected)
            time.sleep(1.0)  # Debounce: pause sensor for 1 second after firing

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nShutting down client...")
    client.loop_stop()
    client.disconnect()
