import time
import board

from adafruit_seesaw import seesaw
from adafruit_seesaw import rotaryio
from adafruit_seesaw import digitalio


# --------------------------------------------------
# Connect to the STEMMA QT rotary encoder
# --------------------------------------------------

i2c = board.I2C()

ss = seesaw.Seesaw(
    i2c,
    addr=0x36
)


# --------------------------------------------------
# Rotary encoder
# --------------------------------------------------

encoder = rotaryio.IncrementalEncoder(ss)


# --------------------------------------------------
# Encoder push button
#
# The button on the Adafruit rotary encoder
# is seesaw pin 24.
# --------------------------------------------------

ss.pin_mode(24, ss.INPUT_PULLUP)

button = digitalio.DigitalIO(
    ss,
    24
)


# --------------------------------------------------
# Track previous encoder position/button
# --------------------------------------------------

last_position = encoder.position
last_button = button.value


print("Rotary encoder test running.")
print("Turn the knob or press it.")
print()


while True:

    # ----------------------------------------------
    # Rotation
    # ----------------------------------------------

    position = encoder.position

    if position != last_position:

        if position > last_position:
            print("CLOCKWISE")

        else:
            print("COUNTERCLOCKWISE")

        last_position = position


    # ----------------------------------------------
    # Push button
    #
    # INPUT_PULLUP means:
    # True  = not pressed
    # False = pressed
    # ----------------------------------------------

    current_button = button.value

    if last_button and not current_button:
        print("PRESSED")

    last_button = current_button

    time.sleep(0.01)
