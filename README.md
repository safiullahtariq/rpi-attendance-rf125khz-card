# RFID-Based Door Access and Attendance System

This project is an RFID-based door access control and attendance system designed for Raspberry Pi. It uses an RFID reader to scan employee cards, checks access permissions, logs attendance, and controls a door relay. The system also includes a physical button for manual door control and an LED for status indication.

#### Features
* RFID Card Scanning: Employees can scan their RFID cards to gain access.
* Access Control: The system checks if the employee is allowed access based on their status and time restrictions.
* Attendance Logging: Employee attendance is logged in an SQLite database.
* Door Control: The door relay is controlled based on valid card scans or manual button presses.
* Status LED: An LED indicates the system's readiness for scanning.
* Manual Button: A physical button allows manual door opening with a cooldown period.
* Logging: System status and events are logged to a file for debugging and monitoring.

#### Hardware Requirements
* Raspberry Pi (tested on Raspberry Pi 3/4, Zero 2W)
* RFID Reader (RDM6300)
* Relay Module
* Push Button
* LED
* Jumper Wires
* Power Supply

#### Software Requirements
* Python 3.x
* RPi.GPIO library
* rdm6300 library
* SQLite3


#### Installation
Clone the Repository:

```
git clone https://github.com/safiullahtariq/rpi-attendance-rf125khz-card
```
```
cd rpi-attendance-rf125khz-card
```

#### Install Required Libraries:

```
pip install RPi.GPIO rdm6300
```

#### Set Up the Database:

The script will automatically create the necessary SQLite databases (attendance.db and out_db.db) and tables when run for the first time.
Connect the Hardware:
Connect the RFID reader to the Raspberry Pi's UART pins (e.g., /dev/ttyS0).
Connect the relay to GPIO pin 37.
Connect the button to GPIO pin 18.
Connect the status LED to GPIO pin 38.

Run the Script:

```
python3 rf.py
```
#### Usage

**Scanning an RFID Card:** When the system is ready, scan an employee's RFID card. If access is granted, the door will open for 5 seconds, and the attendance will be logged.

**Manual Door Opening:** Press the physical button to manually open the door. The button has a cooldown period to prevent multiple rapid presses.

**Status LED:** The LED will be on when the system is ready for scanning and off during the scanning process.

#### Database Schema
*attendance.db*
* Employees: Stores employee details (ID, name, team, card ID, status).
* Location: Stores location details.
* Site: Stores site details linked to locations.
* Door: Stores door details linked to sites.
* EmployeeLocation: Tracks employee access to locations.
* EmployeeSite: Tracks employee access to sites.
* EmployeeDoor: Tracks employee access to doors.

*out_db.db*
* Attendance: Logs employee attendance (ID, FullName, PersonnelID, DateTime, Location).

#### Logging
The system logs status messages to status.txt, ensuring that only the last 1000 lines are retained. This helps in debugging and monitoring the system.

#### Customization
* Cooldown Period: Adjust the cooldown_seconds variable to change the cooldown period for the button and door.
* Access Time Restrictions: Modify the EmployeeDoor table to set specific access times for employees at different doors.
* RFID Reader Configuration: Update the rdm6300.
* Reader initialization if using a different RFID reader or UART port.

#### Troubleshooting
* No Card Detected: Ensure the RFID reader is properly connected and powered.
* Door Not Opening: Check the relay connections and ensure the GPIO pins are correctly configured.
* Database Errors: Verify that the SQLite databases are correctly set up and accessible.

#### License
This project is licensed under the Apache License. See the LICENSE file for details.

#### Acknowledgments
Thanks to the RPi.GPIO and rdm6300 library maintainers for their work.

Inspired by various open-source RFID access control projects.
