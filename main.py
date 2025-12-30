import asyncio
import json
import logging
import math
import random

from bumble.att import Attribute
from bumble.core import AdvertisingData
from bumble.device import Device
from bumble.gatt import Characteristic, CharacteristicValue, Service
from bumble.hci import Address
from bumble.transport import open_transport

logging.basicConfig(level=logging.INFO)

SERVICE_UUID = "845d1d9a-b986-45b8-8b0e-21ee94307983"
TX_CHARACTERISTIC_UUID = "3ecd3272-0f80-4518-ad58-78aa9af3ec9d"
RX_CHARACTERISTIC_UUID = "47153006-9eef-45e5-afb7-038ea60ad893"


async def main():
    print("Starting BLE GATT Server...")
    print("<<< connecting to HCI...")

    # "usb:0" means "the first USB Bluetooth adapter"
    async with await open_transport("usb:0") as hci_transport:
        print("<<< connected")

        # Generate a random device name
        target_name = f"Hojicha_{random.randint(0, 9999):04d}"

        # Generate a static random address
        def make_static_random_address():
            bytes_ = bytearray(random.getrandbits(8) for _ in range(6))
            bytes_[0] = (bytes_[0] & 0x3F) | 0xC0
            return ":".join(f"{b:02X}" for b in bytes_)

        rand_addr = make_static_random_address()
        print(f"=== Using address: {rand_addr}")
        device = Device.with_hci(
            target_name,
            Address(rand_addr),
            hci_transport.source,  # receive stream
            hci_transport.sink,  # transmit stream
        )

        # Create GATT table (services and characteristics)

        # RX write handler (receive writes from browser)
        def on_rx_write(connection, value):
            try:
                text = value.decode("utf-8")
                print(f"=== [Received] Write from browser: {text}")
            except:
                print(f"=== [Received] Binary data: {value.hex()}")

        # Define characteristics
        tx_char = Characteristic(
            TX_CHARACTERISTIC_UUID,
            properties=(
                Characteristic.Properties.READ | Characteristic.Properties.NOTIFY
            ),
            permissions=(Attribute.Permissions.READABLE),
            value=b"Hello from Bumble!",
        )

        rx_char = Characteristic(
            RX_CHARACTERISTIC_UUID,
            properties=(
                Characteristic.Properties.WRITE
                | Characteristic.Properties.WRITE_WITHOUT_RESPONSE
            ),
            permissions=(Attribute.Permissions.WRITEABLE),
            value=CharacteristicValue(write=on_rx_write),
        )

        # Define service
        service_element = Service(SERVICE_UUID, [tx_char, rx_char])
        device.add_service(service_element)

        # Manage message sending task
        send_task = None

        async def send_messages_periodically():
            """Send robot position data every 100ms"""
            # Define waypoints for smooth path
            waypoints = [
                (388, 388),
                (388, 6500),
                (1100, 6500),
                (1100, 1400),
                (1900, 1400),
                (1900, 6500),
                (2500, 6500),
                (2500, 388),
                (388, 388),
            ]

            # Calculate total distance for interpolation
            def distance(p1, p2):
                return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)

            def interpolate_path(waypoints, progress):
                """Interpolate position along waypoints. progress: 0.0 to 1.0"""
                # Calculate cumulative distances
                distances = [0.0]
                for i in range(len(waypoints) - 1):
                    distances.append(
                        distances[-1] + distance(waypoints[i], waypoints[i + 1])
                    )

                total_distance = distances[-1]
                target_distance = progress * total_distance

                # Find current segment
                for i in range(len(distances) - 1):
                    if distances[i] <= target_distance <= distances[i + 1]:
                        segment_progress = (
                            (target_distance - distances[i])
                            / (distances[i + 1] - distances[i])
                            if distances[i + 1] != distances[i]
                            else 0
                        )
                        p1 = waypoints[i]
                        p2 = waypoints[i + 1]
                        x = p1[0] + segment_progress * (p2[0] - p1[0])
                        y = p1[1] + segment_progress * (p2[1] - p1[1])
                        return x, y

                return waypoints[-1]

            message_counter = 0
            try:
                while True:
                    message_counter += 1

                    # Calculate position along the path (cycles every 20 seconds)
                    # 100ms per message, so 200 messages per cycle
                    progress = (message_counter % 200) / 200.0
                    x, y = interpolate_path(waypoints, progress)

                    # Calculate angle (oscillates between -15 and +15 degrees)
                    # Complete oscillation every 40 messages
                    angle = 15 * math.sin(2 * math.pi * message_counter / 40)

                    # Create JSON message
                    data = {
                        "type": "robot_pos",
                        "x": round(x, 2),
                        "y": round(y, 2),
                        "angle": round(angle, 2),
                    }
                    message = json.dumps(data).encode("utf-8")
                    tx_char.value = message
                    await device.notify_subscribers(tx_char)
                    print(f"=== [Sent] {message.decode('utf-8')}")
                    await asyncio.sleep(0.1)  # 100ms interval
            except asyncio.CancelledError:
                print("=== Stopped sending messages")
                raise

        def on_connection(connection):
            """Connection callback"""
            nonlocal send_task
            print(f"=== Client connected: {connection}")
            # Also listen on the connection object to ensure cleanup fires
            connection.on("disconnection", on_disconnection)
            # Start message sending task
            send_task = asyncio.create_task(send_messages_periodically())

        def on_disconnection(connection):
            """Disconnection callback"""
            nonlocal send_task
            print(f"=== Client disconnected: {connection}")
            # Cancel message sending task
            if send_task and not send_task.done():
                send_task.cancel()
            send_task = None

        # Register event handlers
        device.on("connection", on_connection)
        device.on("disconnection", on_disconnection)

        # Start server
        print(f"=== Server started: {device.name}")
        await device.power_on()

        # Explicitly create advertising data (information visible when scanned)
        advertising_data = AdvertisingData(
            [(AdvertisingData.COMPLETE_LOCAL_NAME, bytes(target_name, "utf-8"))]
        )

        # Explicitly create advertising data (information visible when scanned)
        await device.start_advertising(
            advertising_data=bytes(advertising_data), auto_restart=True
        )

        print("=== Advertising... Please connect from the browser")

        # Keep the server running
        await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
