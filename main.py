"""
RC Car Wi-Fi Control Script (Raspberry Pi Pico W)

This script runs on the Pico W to enable wireless control of an RC car using
a web API. It reads configuration for hardware setup and network credentials
from JSON files on the device filesystem. The car can receive movement commands
from a remote client over HTTP and control an ESC (electronic speed controller)
and steering servo via PWM.

Configuration Files:
- config.json: contains hardware pin mappings and hostname
- networkinfo.json: contains Wi-Fi SSID and password

Expected HTTP format:
GET /api?cmd=forward&turn=left

Author: Kevin Thompson
Date: 2025-06-13
"""


import network
import socket
import time
from machine import Pin, PWM
import ujson as json



# ==== CONFIGURATION ====

def load_config(config_filename: str) -> Dict[str, Any]:
    """Loads a JSON configuration file from the Pico filesystem.
    
    Args:
        config_filename: Name of the file to load.
    
    Returns:
        Parsed dictionary containing config values.
    """
    with open(config_filename) as f:
        return json.load(f)

# Load configurations
cfg = load_config("config.json")
net_cfg = load_config("networkinfo.json")

# Apply configuration values
HOSTNAME: str = cfg.get("hostname", "testrc")
ESC_PIN: int = cfg.get("esc_pin", 16)
SERVO_PIN: int = cfg.get("servo_pin", 17)

SSID: str = net_cfg.get("SSID", "")
PASSWORD: str = net_cfg.get("PASSWORD", "")

# Onboard LED setup
LED = Pin("LED", Pin.OUT)

# ==== PWM Helpers ====
class PWMOutput:
    """Handles PWM signal output for servos or ESCs."""
    def __init__(self, pin_num: int) -> None:
        self.pwm = PWM(Pin(pin_num))
        self.pwm.freq(50)  # Standard RC frequency
    
    def set_pulse(self, microseconds: int) -> None:
        """Sets a PWM duty cycle based on a pulse width.
        
        Args:
            microseconds: Duration of the high pulse in microseconds (1000-2000 typical).
        """
        duty = int(microseconds / 20000 * 65535)
        self.pwm.duty_u16(duty)

# ==== RC Controller ====
class RCCar:
    """Represents a remotely controlled RC car with drive and steering PWM outputs."""
    def __init__(self, esc, servo):
        self.esc = esc
        self.servo = servo
        self.stop()
        self.center()
    
    def forward(self) -> None:
        self.esc.set_pulse(1700)
    
    def stop(self) -> None:
        self.esc.set_pulse(1500)
    
    def left(self) -> None:
        self.servo.set_pulse(1200)
    
    def right(self) -> None:
        self.servo.set_pulse(1800)
    
    def center(self) -> None:
        self.servo.set_pulse(1500)

# ==== Connect to Wi-Fi ====
def connect_wifi(ssid: str, password: str, hostname: str) -> str:
    """Connects to a Wi-Fi network and sets the Pico's mDNS hostname.
    
    Args:
        ssid: Wi-Fi SSID
        password: Wi-Fi password
        hostname: Hostname to broadvast via mDNS
    
    Returns:
        IP address as a string
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.ifconfig(('10.10.20.63', '255.255.255.0', '10.10.20.1', '10.10.20.1'))
    wlan.connect(ssid, password)

    print("Connecting to Wi-Fi...")
    while not wlan.isconnected():
        LED.toggle()
        time.sleep(0.25)
    
    LED.on()
    ip = wlan.ifconfig()
    print(f"Connected. IP address: {ip}")
    return ip[0]


# ==== Handle Requests ====
def handle_api_request(request: str, car: RCCar) -> None:
    """Parses an incoming API request and updates car state.

    Args:
        request: Raw HTTP GET request string
        car: RCCar instance to control
    """
    try:
        query = request.split('GET /api?')[1].split(' ')[0]
        print(f"Incoming request: {query}")
        params = query.split('&')
        for p in params:
            if p.startswith('cmd='):
                cmd = p[4:]
                if cmd == 'forward':
                    car.forward()
                elif cmd == 'stop':
                    car.stop()
                print(f"Drive Command: {cmd}")
            elif p.startswith('turn='):
                direction = p[5:]
                if direction == 'left':
                    car.left()
                    print("turn left")
                elif direction == 'right':
                    car.right()
                    print("turn right")
                elif direction == 'center':
                    car.center()
                    print("centering")
                print(f"Steering Command: {direction}")
    except Exception as e:
        print("Error parsing request:", e)

# ==== Main Entry ====
def main() -> None:
    """Main entry point: sets up car, connects Wi-Fi, and starts HTTP server."""
    ip = connect_wifi(SSID, PASSWORD, HOSTNAME)
    esc = PWMOutput(ESC_PIN)
    servo = PWMOutput(SERVO_PIN)
    car = RCCar(esc, servo)
    
    addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(addr)
    sock.listen(1)
    
    print(f"Server listening on http://{ip}/api?cmd=...")
    
    while True:
        cl, addr = sock.accept()
        try:
            request = cl.recv(1024).decode()
            if 'GET /api?' in request:
                handle_api_request(request, car)
                cl.send("HTTP/1.1 204 No Content\r\n\r\n")
            else:
                cl.send("HTTP/1.1 404 Not Found\r\n\r\n")
        except Exception as e:
            print("Request error:", e)
        finally:
            cl.close()

main()


