import time
import board
import adafruit_lis3dh

i2c = board.I2C()
sensor = adafruit_lis3dh.LIS3DH_I2C(i2c)

while True:
    x, y, z = sensor.acceleration
    print(f"X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
    time.sleep(0.1)