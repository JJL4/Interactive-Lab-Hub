import time
import subprocess
import digitalio
import board
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

# Configuration for CS and DC pins (these are FeatherWing defaults on M0/M4):
cs_pin = digitalio.DigitalInOut(board.D5) 
dc_pin = digitalio.DigitalInOut(board.D25)
reset_pin = None

# Config for display baudrate (default max is 24mhz):
BAUDRATE = 64000000

# Setup SPI bus using hardware SPI:
spi = board.SPI()

# Create the ST7789 display:
disp = st7789.ST7789(
    spi,
    cs=cs_pin,
    dc=dc_pin,
    rst=reset_pin,
    baudrate=BAUDRATE,
    width=135,
    height=240,
    x_offset=53,
    y_offset=40,
)

# Create blank image for drawing.
# Make sure to create image with mode 'RGB' for full color.
height = disp.width  # we swap height/width to rotate it to landscape!
width = disp.height
image = Image.new("RGB", (width, height))
rotation = 90

# Get drawing object to draw on image.
draw = ImageDraw.Draw(image)

# Draw a black filled box to clear the image.
draw.rectangle((0, 0, width, height), outline=0, fill=(0, 0, 0))
disp.image(image, rotation)
# Draw some shapes.
# First define some constants to allow easy resizing of shapes.
padding = -2
top = padding
bottom = height - padding
# Move left to right keeping track of the current x position for drawing shapes.
x = 0

# Alternatively load a TTF font.  Make sure the .ttf font file is in the
# same directory as the python script!
# Some other nice fonts to try: http://www.dafont.com/bitmap.php
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)

# Turn on the backlight
backlight = digitalio.DigitalInOut(board.D22)
backlight.switch_to_output()
backlight.value = True

# MiniPiTFT buttons
button_A = digitalio.DigitalInOut(board.D23)
button_A.direction = digitalio.Direction.INPUT
button_A.pull = digitalio.Pull.UP

button_B = digitalio.DigitalInOut(board.D24)
button_B.direction = digitalio.Direction.INPUT
button_B.pull = digitalio.Pull.UP

while True:
    # Get current time
    now = time.localtime()

    hour = now.tm_hour
    minute = now.tm_min
    second = now.tm_sec

    minutes_today = hour * 60 + minute + second / 60
    day_progress = minutes_today / 1440

    # Determine current stage of day
    if 6 <= hour < 12:
        sky_color = (100, 170, 220)
        phase = "Morning"
        next_phase = "Afternoon"
        next_hour = 12

    elif 12 <= hour < 17:
        sky_color = (70, 150, 220)
        phase = "Afternoon"
        next_phase = "Evening"
        next_hour = 17

    elif 17 <= hour < 21:
        sky_color = (220, 120, 70)
        phase = "Evening"
        next_phase = "Night"
        next_hour = 21

    else:
        sky_color = (15, 20, 55)
        phase = "Night"

        if hour >= 21:
            next_phase = "Morning"
            next_hour = 30
        else:
            next_phase = "Morning"
            next_hour = 6

    # Clear screen
    draw.rectangle(
        (0, 0, width, height),
        outline=sky_color,
        fill=sky_color
    )

    # Button A being held down

    if not button_A.value:

        exact_time = time.strftime("%I:%M:%S %p")

        draw.text(
            (10, 20),
            "Exact Time",
            font=font,
            fill="#FFFFFF"
        )

        draw.text(
            (35, 60),
            exact_time,
            font=font,
            fill="#FFFF00"
        )

        draw.text(
            (75, 100),
            phase,
            font=font,
            fill="#FFFFFF"
        )

    # Button B being held down

    elif not button_B.value:

        current_minutes = hour * 60 + minute

        milestone_minutes = next_hour * 60

        if milestone_minutes < current_minutes:
            milestone_minutes += 1440

        remaining = milestone_minutes - current_minutes

        remaining_hours = remaining // 60
        remaining_minutes = remaining % 60

        draw.text(
            (10, 15),
            "Next Stage",
            font=font,
            fill="#FFFFFF"
        )

        draw.text(
            (10, 50),
            next_phase,
            font=font,
            fill="#FFFF00"
        )

        countdown = (
            str(remaining_hours)
            + "h "
            + str(remaining_minutes)
            + "m"
        )

        draw.text(
            (10, 85),
            countdown,
            font=font,
            fill="#FFFFFF"
        )

    # Default Screen

    else:

        draw.text(
            (5, 3),
            "Day Journey",
            font=font,
            fill="#FFFFFF"
        )

        # Sun during daytime
        if 6 <= hour < 18:
            draw.ellipse(
                (195, 8, 220, 33),
                fill="#FFFF00"
            )

        # Moon during nighttime
        else:
            draw.ellipse(
                (195, 8, 220, 33),
                fill="#FFFFFF"
            )

            draw.ellipse(
                (202, 5, 222, 28),
                fill=sky_color
            )

        # Draw journey path
        path_start = 15
        path_end = width - 15
        path_y = 72

        draw.line(
            (path_start, path_y, path_end, path_y),
            fill="#FFFFFF",
            width=3
        )

        # Traveler position
        marker_x = int(
            path_start
            + day_progress * (path_end - path_start)
        )

        # Head
        draw.ellipse(
            (
                marker_x - 5,
                path_y - 18,
                marker_x + 5,
                path_y - 8
            ),
            fill="#FFFF00"
        )

        # Body
        draw.line(
            (
                marker_x,
                path_y - 8,
                marker_x,
                path_y + 3
            ),
            fill="#FFFF00",
            width=2
        )

        # Left leg
        draw.line(
            (
                marker_x,
                path_y + 3,
                marker_x - 5,
                path_y + 10
            ),
            fill="#FFFF00",
            width=2
        )

        # Right leg
        draw.line(
            (
                marker_x,
                path_y + 3,
                marker_x + 5,
                path_y + 10
            ),
            fill="#FFFF00",
            width=2
        )

        draw.text(
            (5, 98),
            "Morning",
            font=font,
            fill="#FFFFFF"
        )

        draw.text(
            (165, 98),
            "Night",
            font=font,
            fill="#FFFFFF"
        )

    # Update display
    disp.image(image, rotation)

    time.sleep(0.1)
