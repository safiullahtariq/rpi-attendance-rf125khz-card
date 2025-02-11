import sqlite3
from datetime import datetime
import time
import RPi.GPIO as GPIO
import socket
import rdm6300
import threading
from threading import Lock, Timer
from collections import defaultdict
import os
from collections import deque

# Get the hostname dynamically
HOSTNAME = socket.gethostname()
print("Hostname:", HOSTNAME)

# Setup GPIO
GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
RELAY_PIN = 37
Button = 18  # Use physical pin number 31 for GPIO 6
StatusLED = 38  # LED pin (physical pin 20)
cooldown_seconds = 3  # Cooldown time in seconds
rfid_reader = rdm6300.Reader('/dev/ttyS0')



GPIO.setup(RELAY_PIN, GPIO.OUT)

GPIO.setup(Button, GPIO.IN, pull_up_down=GPIO.PUD_UP)


GPIO.setup(StatusLED, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.HIGH)
GPIO.output(StatusLED, GPIO.HIGH)  # LED on initially (ready for scanning)

# Define constants and the log_status function
STATUS_FILE = 'status.txt'
MAX_LINES = 1000

def log_status(message):
    """Logs a status message, ensuring the file contains only the last MAX_LINES."""
    try:
        lines = deque(maxlen=MAX_LINES)
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as file:
                lines.extend(file.readlines())
        lines.append(f"{datetime.now()}: {message}\n")
        with open(STATUS_FILE, 'w') as file:
            file.writelines(lines)
            file.flush()  # Ensure data is written immediately
            os.fsync(file.fileno())  # Force write to disk
    except Exception as e:
        print(f"Error writing to status file: {e}")

# Example usage in the script
log_status("System initialized and ready for card scans.")

# Replace print statements with log_status
print("Door opened.")  # Original
log_status("Door opened.")  # Updated




# SQLite database setup
def init_db():
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Employees (
                     ID INTEGER PRIMARY KEY,
                     name TEXT,
                     team_name TEXT,
                     card_id INTEGER UNIQUE,
                     status TEXT CHECK(status IN ('active', 'disabled')) DEFAULT 'active')''')
    c.execute('''CREATE TABLE IF NOT EXISTS Location (
                     LocationID INTEGER PRIMARY KEY,
                     LocationName TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Site (
                     SiteID INTEGER PRIMARY KEY,
                     SiteName TEXT,
                     LocationID INTEGER,
                     FOREIGN KEY (LocationID) REFERENCES Location(LocationID))''')
    c.execute('''CREATE TABLE IF NOT EXISTS Door (
                     DoorID INTEGER PRIMARY KEY,
                     DoorName TEXT,
                     SiteID INTEGER,
                     FOREIGN KEY (SiteID) REFERENCES Site(SiteID))''')
    c.execute('''CREATE TABLE IF NOT EXISTS EmployeeLocation (
                     EmployeeID INTEGER,
                     LocationID INTEGER,
                     StartTime TEXT,
                     EndTime TEXT,
                     PRIMARY KEY (EmployeeID, LocationID),
                     FOREIGN KEY (EmployeeID) REFERENCES Employees(ID),
                     FOREIGN KEY (LocationID) REFERENCES Location(LocationID))''')
    c.execute('''CREATE TABLE IF NOT EXISTS EmployeeSite (
                     EmployeeID INTEGER,
                     SiteID INTEGER,
                     StartTime TEXT,
                     EndTime TEXT,
                     PRIMARY KEY (EmployeeID, SiteID),
                     FOREIGN KEY (EmployeeID) REFERENCES Employees(ID),
                     FOREIGN KEY (SiteID) REFERENCES Site(SiteID))''')
    c.execute('''CREATE TABLE IF NOT EXISTS EmployeeDoor (
                     EmployeeID INTEGER,
                     DoorID INTEGER,
                     StartTime TEXT,
                     EndTime TEXT,
                     PRIMARY KEY (EmployeeID, DoorID),
                     FOREIGN KEY (EmployeeID) REFERENCES Employees(ID),
                     FOREIGN KEY (DoorID) REFERENCES Door(DoorID))''')
    conn.commit()
    return conn

# Initialize the output database
def setup_db():
    conn = sqlite3.connect('out_db.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Attendance (
                     ID INTEGER,
                     FullName TEXT,
                     PersonnelID INTEGER,
                     DateTime TEXT,
                     Location TEXT)''')
    conn.commit()
    return conn

conn = init_db()
out_db_conn = setup_db()

def is_access_allowed(employee):
    return employee[3] == 'active'

def get_employee_by_card_id(card_id):
    c = conn.cursor()
    c.execute('''SELECT ID, name, card_id, status
                 FROM Employees
                 WHERE card_id = ?''', (card_id,))
    return c.fetchone()

def is_employee_allowed_at_door(employee_id, door_name, current_time):
    c = conn.cursor()
    c.execute('''SELECT ed.StartTime, ed.EndTime
                 FROM EmployeeDoor ed
                 JOIN Door d ON ed.DoorID = d.DoorID
                 WHERE ed.EmployeeID = ? AND d.DoorName = ?''', (employee_id, door_name))
    row = c.fetchone()
    if row:
        start_time, end_time = row
        start_time = datetime.strptime(start_time, '%H:%M').time()
        end_time = datetime.strptime(end_time, '%H:%M').time()
        return start_time <= current_time <= end_time
    return None

last_button_press = datetime.min
relay_lock = Lock()

# Variables for software-based debounce
button_press_timer = None  # Timer for debouncing
debounce_lock = Lock()  # Lock to prevent race conditions in debounce handling
DEBOUNCE_TIME_SECONDS = 0.3  # Debounce time in seconds

def debounce_callback():
    """Handles button press events after software debounce."""
    global last_button_press
    now = datetime.now()
    with relay_lock:  # Ensure thread-safe state handling
        if (now - last_button_press).total_seconds() < cooldown_seconds:  # Cooldown for 3 seconds
            print("Button cooldown active. Ignoring press.")
            log_status("Button cooldown active. Ignoring press.")
            return
        last_button_press = now  # Update the last button press time
        print("Button pressed, deactivating relay for 5 seconds.")
        log_status("Button pressed, deactivating relay for 5 seconds.")
        GPIO.output(RELAY_PIN, GPIO.LOW)
        Timer(5, relay_reset).start()  # Reset the relay after 5 seconds in a non-blocking way

def relay_reset():
    """Resets the relay to its default state."""
    with relay_lock:
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        print("Relay reactivated. Ready for the next press.")
        log_status("Relay reactivated. Ready for the next press.")

def button_callback(channel):
    """Triggered by GPIO event detection."""
    debounce_callback()

cooldown_seconds = 3  # Cooldown period for the door (in seconds)
ignore_same_card_seconds = 2  # Ignore duplicate scans of the same card within this time
last_access_time = datetime.min  # Initialize to a very old time
door_open = False
door_open_time = None  # Track when the door was opened
last_card_scan = defaultdict(lambda: datetime.min)  # Dictionary to track last scan time for each card

def open_door():
    """Open the door for 5 seconds and then close it."""
    global door_open, door_open_time, last_access_time
    
    GPIO.output(RELAY_PIN, GPIO.LOW)  # Unlock the door
    print("Door opened.")
    log_status("Door opened.")
    time.sleep(5)  # Keep the door open for 5 seconds
    GPIO.output(RELAY_PIN, GPIO.HIGH)  # Lock the door
    print("Door closed.")
    log_status("Door closed")
    
    # Reset door state and cooldown after door closes
    door_open = False
    door_open_time = None
    last_access_time = datetime.now()  # Immediately reset cooldown
    print("Cooldown reset after door closed.")
    log_status("Cooldown reset after door closed.")

def record_attendance():
    global door_open, door_open_time, last_access_time, last_card_scan

    while True:
        try:
            GPIO.output(StatusLED, GPIO.HIGH)  # LED on (ready for scanning)
            print('Scan Your Card')
            log_status('Scan Your Card')
            card = rfid_reader.read()  # Blocking call to read the card
            GPIO.output(StatusLED, GPIO.LOW)  # LED off (scanning in process)

            now = datetime.now()  # Get the current time once per iteration

            # Check if the card is valid
            if card:
                card_id = card.value
                print(f'Card ID: {card_id}')
                log_status(f'Card ID: {card_id}')
                print(f'Time of Scan: {now.strftime("%d-%m-%Y %I:%M:%S %p")}')
                log_status(f'Time of Scan: {now.strftime("%d-%m-%Y %I:%M:%S %p")}')

                # Ignore multiple scans of the same card within the specified time
                if (now - last_card_scan[card_id]).total_seconds() < ignore_same_card_seconds:
                    print(f"Ignoring duplicate scan for Card ID: {card_id}")
                    log_status(f"Ignoring duplicate scan for Card ID: {card_id}")
                    continue

                # Update the last scan time for this card
                last_card_scan[card_id] = now

                # Check employee details
                employee = get_employee_by_card_id(card_id)
                if employee:
                    print('Employee details:', employee)
                    log_status(f"Employee details: {employee}")
                    if is_access_allowed(employee):
                        allowed_time_range = is_employee_allowed_at_door(employee[0], HOSTNAME, now.time())
                        if allowed_time_range is not None:
                            if allowed_time_range:
                                print("Access allowed. Recording attendance...")
                                log_status("Access allowed. Recording attendance...")

                                # Record attendance in the SQLite database
                                c = out_db_conn.cursor()
                                c.execute('''INSERT INTO Attendance (ID, FullName, PersonnelID, DateTime, Location)
                                             VALUES (?, ?, ?, ?, ?)''',
                                          (employee[0], employee[1], employee[2], now.strftime("%d-%m-%Y %I:%M:%S %p"), HOSTNAME))
                                out_db_conn.commit()

                                # Open door on first valid scan
                                if not door_open:
                                    door_open = True
                                    door_open_time = now  # Track the time when the door was opened
                                    threading.Thread(target=open_door).start()  # Open door in a separate thread
                                else:
                                    print("Door is already open. Attendance recorded for additional scan.")
                                    log_status("Door is already open. Attendance recorded for additional scan.")
                            else:
                                print("Access not allowed at this time.")
                                log_status("Access not allowed at this time.")
                        else:
                            print("Access not allowed at this door.")
                            log_status("Access not allowed at this door.")
                    else:
                        print("Employee is disabled. Attendance not recorded.")
                        log_status("Employee is disabled. Attendance not recorded.")
                else:
                    print("Employee not found.")
                    log_status("Employee not found.")
                    last_access_time = now  # Start cooldown for unregistered cards
                    time.sleep(1)
            else:
                print("No card detected.")
                log_status("No card detected.")

            # Handle door closing logic based on timing
            if door_open and door_open_time:
                time_elapsed = (now - door_open_time).total_seconds()
                print(f"Time elapsed since door opened: {time_elapsed} seconds")
                log_status(f"Time elapsed since door opened: {time_elapsed} seconds")
                if time_elapsed >= 5:  # Ensure the door stays open for 5 seconds
                    GPIO.output(RELAY_PIN, GPIO.HIGH)  # Lock the door
                    print("Door closed after timeout.")
                    log_status("Door closed after timeout.")
                    last_access_time = now  # Update cooldown immediately after door closes
                    door_open = False  # Door state changed to closed
                    door_open_time = None  # Reset door open time

        except Exception as e:
            print(f"Error during attendance recording: {e}")
            log_status(f"Error during attendance recording: {e}")
        except KeyboardInterrupt:
            print("Script terminated by user.")
            log_status("Script terminated by user.")
            break
        finally:
            GPIO.output(StatusLED, GPIO.HIGH)  # Turn LED back on (ready for scanning)
            time.sleep(0.1)  # Small delay to avoid high CPU usage

if __name__ == "__main__":
    try:
        GPIO.add_event_detect(Button, GPIO.RISING, callback=button_callback, bouncetime=500)  # Hardware debounce of 300ms
        record_attendance()
    except KeyboardInterrupt:
        print("Program terminated by user")
        log_status("Program terminated by user")
    finally:
        out_db_conn.close()  # Close the output database connection
        GPIO.cleanup()
