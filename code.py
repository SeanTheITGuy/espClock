import os
#import ipaddress
import wifi
import socketpool
import time
import busio
import rtc
import adafruit_ntp
from board import SCL, SDA
from adafruit_motor import servo
from adafruit_pca9685 import PCA9685

# Constants
DEBUG = False
MILITARY_TIME = False
MIN_PWM = 1000
MAX_PWM = 2000
PWM_FREQ = 50
INVERSION_MAP = [ True, True, False, True, False, True, True ]
SEGMENT_MAP = [ 0b1110111, 0b0100100, 0b1011101, 0b1101101, 0b0101110, 0b1101011, 0b1111011, 0b0100101, 0b1111111, 0b1101111 ]
TZ_OFFSET = -4
RESYNC_HOURS = 4
SERVO_ON = 180 
SERVO_OFF = 0

def wifiConnect():
  try: 
    ssid = os.getenv("WIFI_SSID")
    password = os.getenv("WIFI_PASSWORD")
    print("Connecting to", ssid)
    wifi.radio.connect(ssid, password)
    print("Connected to", ssid, " IP: ", wifi.radio.ipv4_address)
  except:
    print("Failed to connect to wifi.")

  return(socketpool.SocketPool(wifi.radio))
  
# Syncronize internal time via ntp and return current epoch seconds
def syncTime():
  try:
    # Get current time from NTP
    pool = wifiConnect();
    ntp = adafruit_ntp.NTP(pool, tz_offset=TZ_OFFSET)
    rtc.RTC().datetime = ntp.datetime
    print("Time syncronized.")
  except: 
    print("Failed to sync time.")

  return(time.time())

# Initialize two PCA boards and return a list of all 32 available output channels
def getServoList():
  # Use board defined I2C pins
  i2c = busio.I2C(SCL, SDA)
  

  # Servo controller devices
  print("Initializing PCA boards")
  kits = [ PCA9685(i2c, address=0x40), PCA9685(i2c, address=0x41) ]

  # Set up kits and define servo array
  print("Collating Servos...")
  servo_list = []

  for kit in kits:
    kit.frequency = PWM_FREQ
    print("\n", kit, " ", end='')
    for i in range(16):
      print(i, " ", end='')
      servo_list.append(servo.Servo(kit.channels[i], min_pulse=MIN_PWM, max_pulse=MAX_PWM, actuation_range=180))
  print("\nServos Collated")

  return(servo_list)
  
# return a 4 digit number with the current time (eg: 11:42am -> 1142)
def getFourDigitTime(t):
  hour = t.tm_hour
  minute = t.tm_min
  
  # Logic for 12hr time
  if not MILITARY_TIME:
    if hour > 12:
      hour = hour%12

  return(hour * 100 + minute)

# Return the single digit at the nth position of a number
def getDigit(number, n):
  x = number // 10**n % 10
  print("number at ", n, " position is ", x)
  return(x)

# Set a clock digit segment on or off
def setSegment(s, index, is_set):
  # Determine if this segment needs to have its OFF:ON mapping inverted
  if INVERSION_MAP[index%8]:
      print("Servo ", index, " needs inversion")
      is_set = not is_set

  # Move servo to appropriate angle
  if is_set:
    print("Setting servo ", index, " to ", SERVO_ON, " degrees")
    s.angle = SERVO_ON
  else:
    print("Setting servo ", index, " to ", SERVO_OFF, " degrees")
    s.angle = SERVO_OFF

  time.sleep(0.1)
  return

# Take a single digit and display it on the clock at a specified position 
def displayDigit(digit, position, servos):
  # Define where to start in the servo list based on which digit place we are displaying
  servo_index_offset = position * 8
  print("servo offset for number at position ", position, " is ", servo_index_offset)

  # Get an int representing the bits of the desired number's segment map
  segments = SEGMENT_MAP[digit]

  # Logic for single digit hours to not display the leading zero
  if position == 0 and digit == 0:
    print("Leading zero. Setting all segments off")
    segments = 0b0000000

  print("segment map for ", digit, " is ", "{0:b}".format(segments))

  # we only care about the lower 7 bits for our 7 segment display
  for i in range(7):
    servo_position = servo_index_offset + i
    print("Checking bit ", i)
    #if segments & (1<<(i)):
    if (segments >> i) & 1:
      setSegment(servos[servo_position], servo_position, True)
      print("bit ", i, " is ON. Setting servo ", servo_index_offset+i, " ON")
    else:
      setSegment(servos[servo_position], servo_position, False)
      print("bit ", i, " is OFF. Setting servo ", servo_index_offset+i, " OFF")

  return

# Display the passed 4 digit number on the clock
def displayTime(t, servos):
  for i in range(4):
    digit = getDigit(t, i)
    print("Displaying digit ", digit, " at position ", 3-i)
    displayDigit(digit, 3-i, servos)

  return

if __name__ == "__main__":
  # Get a list of the servo channels
  servos = getServoList()

  # Debugging counter, count 0-9 on position 0
  if DEBUG:
    while True:
      for j in range(10):
        for i in range(4):
          displayDigit(j, i, servos)
        time.sleep(2)

  # Sync time via wifi and record the sync time
  sync_time = syncTime()

  # Get the current time in 4 digit format
  last_time = getFourDigitTime(time.localtime())
  print("Start time: ", last_time)

  # Display the initial time
  displayTime(last_time, servos)

  # Start the clock update loop
  while True:

    # check if time needs to be resynced
    if(time.time() - sync_time > RESYNC_HOURS * 3600):
      sync_time = syncTime()

    # Get the current time
    new_time = getFourDigitTime(time.localtime())
    
    # Check if the time has changed 
    if(last_time != new_time):
      # Time has changed, update the clock
      print("Updating time to: ", new_time)
      displayTime(new_time, servos)
      # New time now becomes old time
      last_time = new_time

    # Sleep 
    time.sleep(2)

    for s in servos:
      s.angle = None
