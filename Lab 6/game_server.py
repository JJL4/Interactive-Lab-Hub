import time
import random
import paho.mqtt.client as mqtt

TEAM_NAME = "simon_says_team"
BROKER = "farlab.infosci.cornell.edu"
PORT = 1883
USER = "idd"
PASSWORD = "device@theFarm"

COMMAND_TOPIC = f"IDD/{TEAM_NAME}/simon/command"
EVENT_TOPIC_WILDCARD = f"IDD/{TEAM_NAME}/simon/+/event"

current_event = None
event_source = None


def on_message(client, userdata, msg):
    global current_event, event_source
    # We only care about the FIRST message per round.
    # If current_event is already set, ignore latecomers.
    if current_event is None:
        parts = msg.topic.split('/')
        event_source = parts[3]  # Extracts 'pi1' or 'pi2'
        current_event = msg.payload.decode()


client = mqtt.Client()
client.username_pw_set(USER, PASSWORD)
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.subscribe(EVENT_TOPIC_WILDCARD)
client.loop_start()

scores = {"pi1": 0, "pi2": 0}
actions = ["red", "green", "close", "blue"]

print(f"Starting HEAD-TO-HEAD Simon Says...")
time.sleep(2)

try:
    while True:
        target_action = random.choice(actions)
        is_simon = random.choice([True, False])

        # Shrinking Timer based on the highest score
        max_score = max(scores.values())
        time_limit = max(1.2, 3.5 - (max_score * 0.15))

        if is_simon:
            command_text = f"SIMON SAYS: FIRST TO SHOW [{target_action.upper()}] WINS!"
        else:
            command_text = f"FIRST TO SHOW [{target_action.upper()}] WINS!"

        print("\n" + "="*50)
        print(f"SCORES -> P1: {scores['pi1']} | P2: {scores['pi2']}")
        print(f"DISPLAYING: {command_text}")

        client.publish(COMMAND_TOPIC, f"display:{command_text}")

        # Clear the event trigger right before starting the clock
        current_event = None
        event_source = None

        start_time = time.time()
        acted = False

        # The Timer Loop
        while time.time() - start_time < time_limit:
            if current_event:
                acted = True
                break  # First person to trigger it stops the clock
            time.sleep(0.05)

        # Evaluation Logic
        if is_simon:
            if acted:
                if current_event == target_action:
                    scores[event_source] += 1
                    result_msg = f"BOOM! {event_source.upper()} got it right first! +1 point."
                else:
                    scores[event_source] -= 1
                    result_msg = f"OOPS! {event_source.upper()} did the wrong action! -1 point."
            else:
                result_msg = "TOO SLOW! Neither player scores."

        else:  # NOT Simon Says (The Fake-Out)
            if acted:
                scores[event_source] -= 1
                result_msg = f"CAUGHT YOU! {event_source.upper()} moved when Simon didn't say! -1 point."
            else:
                result_msg = "Phew! Both held still."

        print(result_msg)
        client.publish(
            COMMAND_TOPIC, f"result:{result_msg} (P1:{scores['pi1']} P2:{scores['pi2']})")

        time.sleep(3.5)  # Time to reset physical objects before next round

        WINNING_SCORE = 5
        if scores["pi1"] >= WINNING_SCORE or scores["pi2"] >= WINNING_SCORE:
            if scores["pi1"] > scores["pi2"]:
                winner = "PLAYER 1"
            elif scores["pi2"] > scores["pi1"]:
                winner = "PLAYER 2"
            else:
                winner = "TIE"

            game_over_text = f"GAME OVER! {winner} WINS THE MATCH!"
            print("\n" + "#"*50)
            print(game_over_text)
            print("#"*50 + "\n")

            client.publish(COMMAND_TOPIC, f"display:{game_over_text}")
            time.sleep(5)  # Leave the victory message up for 5 seconds
            break

except KeyboardInterrupt:
    print("\nQuitting game server.")
    client.loop_stop()
    client.disconnect()
