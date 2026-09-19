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

while True:
    # Clear the screen
    draw.rectangle((0, 0, width, height), outline=0, fill=(0, 0, 0))

    # Get the current time
    current_time = time.localtime()

    # Calculate how far we are through the day/Modify this function later for recording purposes
    minutes_today = (
        current_time.tm_hour * 60
        + current_time.tm_min
        + current_time.tm_sec / 60
    )

    day_progress = minutes_today / (24 * 60)

    # Draw title
    draw.text((5, 5), "Day Journey", font=font, fill="#FFFFFF")

    # Draw the path
    path_start = 15
    path_end = width - 15
    path_y = 75

    draw.line(
        (path_start, path_y, path_end, path_y),
        fill="#FFFFFF",
        width=3
    )

    # Calculate where the person/marker should be
    marker_x = int(
        path_start + day_progress * (path_end - path_start)
    )

    # Draw the traveler as a simple circle
    draw.ellipse(
        (
            marker_x - 6,
            path_y - 6,
            marker_x + 6,
            path_y + 6
        ),
        fill="#FFFF00"
    )

    # Morning and night labels
    draw.text((5, 100), "Morning", font=font, fill="#FFFFFF")
    draw.text((165, 100), "Night", font=font, fill="#FFFFFF")

    # Display image
    disp.image(image, rotation)
    time.sleep(1)
