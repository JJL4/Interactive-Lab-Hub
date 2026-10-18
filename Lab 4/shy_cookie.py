
import time
from statistics import mean

import pi_servo_hat
import qwiic_proximity


# --------------------------------------
# SHY COOKIE SETTINGS
# --------------------------------------

SERVO_CHANNEL = 0

# Initial servo positions (0-90 degrees)
# Adjust these after testing the door.
OPEN_ANGLE = 15
CLOSED_ANGLE = 65

# Motion speed
STEP_DELAY = 0.02

# Sensor settings
POLL_INTERVAL = 0.1
CALIBRATION_SAMPLES = 20

# Consecutive readings required before changing state
CLOSE_CONFIRM = 3
OPEN_CONFIRM = 5


def calibrate(sensor, message):
    """Average proximity readings in one position."""
    input(message + "\nPress Enter when ready...")

    readings = []

    for _ in range(CALIBRATION_SAMPLES):
        readings.append(sensor.get_proximity())
        time.sleep(0.08)

    result = mean(readings)
    print(f"Average proximity: {result:.1f}\n")
    return result


def main():
    print("============================")
    print("       SHY COOKIE")
    print("============================")

    # Initialize proximity sensor
    sensor = qwiic_proximity.QwiicProximity()

    if not sensor.connected:
        print("ERROR: Proximity sensor not detected!")
        return

    sensor.begin()
    sensor.set_led_current(200)
    sensor.set_prox_integration_time(8)

    print("Proximity sensor connected!")

    # Initialize servo
    servo = pi_servo_hat.PiServoHat()
    servo.restart()

    current_angle = OPEN_ANGLE

    def move_to(target):
        """Move the servo gradually to the target."""
        nonlocal current_angle

        if current_angle == target:
            return

        step = 1 if target > current_angle else -1

        for angle in range(
            current_angle + step,
            target + step,
            step
        ):
            servo.move_servo_position(
                SERVO_CHANNEL, angle
            )
            current_angle = angle
            time.sleep(STEP_DELAY)

    # Start with the cookie visible
    servo.move_servo_position(
        SERVO_CHANNEL, OPEN_ANGLE
    )

    print("Servo initialized!")
    print("Door is OPEN.\n")

    try:
        # Calibrate background reading
        far_value = calibrate(
            sensor,
            "Keep your hand AWAY from the cookie."
        )

        # Calibrate detection reading
        near_value = calibrate(
            sensor,
            "Hold your hand near the sensor "
            "at the distance you want to trigger the door."
        )

        difference = near_value - far_value

        if difference < max(20, far_value * 0.1):
            print("Calibration failed:")
            print("The near reading was not sufficiently")
            print("higher than the far reading.")
            print("Reposition the sensor and try again.")
            return

        # Two thresholds to prevent rapid flickering
        close_threshold = far_value + difference * 0.60
        open_threshold = far_value + difference * 0.35

        print(f"Close threshold: {close_threshold:.1f}")
        print(f"Open threshold:  {open_threshold:.1f}")
        print("\nShy Cookie is ACTIVE!")
        print("Press Ctrl+C to stop.\n")

        door_closed = False
        close_count = 0
        open_count = 0

        while True:
            value = sensor.get_proximity()

            if not door_closed:
                # Wait for approaching hand
                if value >= close_threshold:
                    close_count += 1
                else:
                    close_count = 0

                if close_count >= CLOSE_CONFIRM:
                    print("HAND DETECTED!")
                    print("Cookie is hiding!")

                    move_to(CLOSED_ANGLE)

                    door_closed = True
                    close_count = 0
                    open_count = 0

            else:
                # Wait until the hand leaves
                if value <= open_threshold:
                    open_count += 1
                else:
                    open_count = 0

                if open_count >= OPEN_CONFIRM:
                    print("Hand has left!")
                    print("Cookie is coming back!")

                    move_to(OPEN_ANGLE)

                    door_closed = False
                    close_count = 0
                    open_count = 0

            state = "CLOSED" if door_closed else "OPEN"
            print(f"Proximity: {value:5d} | Door: {state}")

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nStopping Shy Cookie...")

    finally:
        print("Returning servo to open position.")
        move_to(OPEN_ANGLE)
        print("Goodbye!")


if __name__ == "__main__":
    main()
