import click
import serial
import time

@click.command()
@click.argument('port', default='/dev/ttyACM0')
def connect_serial(port):
    """
    Connects to a specified port at 1200 bps, waits for a moment, and then disconnects.
    """
    baud_rate = 1200

    try:
        # Initialize serial connection
        set = serial.Serial(port, baud_rate)

        # Check if the port is open
        if set.is_open:
            print(f"Connected to {port} at {baud_rate} bps.")

        # Wait for a moment before closing the port
        time.sleep(0.5)

    except serial.SerialException as e:
        print(f"Error: {e}")

    finally:
        # Close the serial connection
        set.close()
        print(f"Disconnected from {port}.")

if __name__ == '__main__':
    connect_serial()
