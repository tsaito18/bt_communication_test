import asyncio
import logging
import random

from bumble.att import Attribute
from bumble.core import AdvertisingData
from bumble.device import Device
from bumble.gatt import Characteristic, Service
from bumble.hci import Address
from bumble.transport import open_transport

# ログ設定
logging.basicConfig(level=logging.INFO)

# UUID定義（ブラウザ側と合わせる）
SERVICE_UUID = "845d1d9a-b986-45b8-8b0e-21ee94307983"
TX_CHARACTERISTIC_UUID = "3ecd3272-0f80-4518-ad58-78aa9af3ec9d"
RX_CHARACTERISTIC_UUID = "47153006-9eef-45e5-afb7-038ea60ad893"


async def main():
    print("Bumble BLE Server を起動します...")
    print("<<< connecting to HCI...")

    # 公式サンプルに従い、Context Manager を使用して Transport を開く
    # "usb:0" は最初のUSBドングルを使用
    async with await open_transport("usb:0") as hci_transport:
        print("<<< connected")

        # Device の初期化
        # transport そのものではなく、source と sink を渡すのが最新の作法です
        target_name = f"ほうじちゃ_{random.randint(0, 9999):04d}"

        # BLEの静的ランダムアドレスを生成（先頭バイトの上位2ビット=11）
        def make_static_random_address():
            bytes_ = bytearray(random.getrandbits(8) for _ in range(6))
            bytes_[0] = (bytes_[0] & 0x3F) | 0xC0
            return ":".join(f"{b:02X}" for b in bytes_)

        rand_addr = make_static_random_address()
        print(f"=== 使用アドレス(Static Random): {rand_addr}")
        device = Device.with_hci(
            target_name,  # デバイス名
            Address(rand_addr),  # 静的ランダム MACアドレス
            hci_transport.source,  # 受信ストリーム
            hci_transport.sink,  # 送信ストリーム
        )

        # --- GATT テーブル（サービスとキャラクタリスティック）の作成 ---

        # RX用のカスタムキャラクタリスティッククラス（書き込みを受信）
        class RxCharacteristic(Characteristic):
            def on_write(self, connection, value):
                try:
                    text = value.decode("utf-8")
                    print(f"=== [受信] ブラウザからの書き込み: {text}")
                except:
                    print(f"=== [受信] バイナリデータ: {value.hex()}")

        # キャラクタリスティックの定義（TX: 送信専用 / RX: 受信専用）
        tx_char = Characteristic(
            TX_CHARACTERISTIC_UUID,
            properties=(
                Characteristic.Properties.READ | Characteristic.Properties.NOTIFY
            ),
            permissions=(Attribute.Permissions.READABLE),
            value=b"Hello from Bumble!",
        )

        rx_char = RxCharacteristic(
            RX_CHARACTERISTIC_UUID,
            properties=(
                Characteristic.Properties.WRITE
                | Characteristic.Properties.WRITE_WITHOUT_RESPONSE
            ),
            permissions=(Attribute.Permissions.WRITEABLE),
            value=b"",
        )

        # サービスの定義
        service_element = Service(SERVICE_UUID, [tx_char, rx_char])

        # デバイスにサービスを追加
        device.add_service(service_element)

        # --- メッセージ送信タスク管理 ---
        send_task = None

        async def send_messages_periodically():
            """1秒ごとにメッセージを送信"""
            message_counter = 0
            try:
                while True:
                    message_counter += 1
                    message = f"Message #{message_counter} from Bumble".encode("utf-8")
                    tx_char.value = message
                    await device.notify_subscribers(tx_char)
                    print(f"=== [送信] {message.decode('utf-8')}")
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                print("=== メッセージ送信を停止しました")
                raise

        def on_connection(connection):
            """接続時のコールバック"""
            nonlocal send_task
            print(f"=== クライアント接続: {connection}")
            # メッセージ送信タスクを開始
            send_task = asyncio.create_task(send_messages_periodically())

        def on_disconnection(connection):
            """切断時のコールバック"""
            nonlocal send_task
            print(f"=== クライアント切断: {connection}")
            # メッセージ送信タスクをキャンセル
            if send_task and not send_task.done():
                send_task.cancel()
            send_task = None

        # イベントハンドラーを登録
        device.on("connection", on_connection)
        device.on("disconnection", on_disconnection)

        # --- サーバー起動 ---

        print(f"=== サーバー起動: {device.name}")
        await device.power_on()

        # アドバタイズデータ（スキャンした時に見える情報）を明示的に作成
        # 0x09 = Complete Local Name
        advertising_data = AdvertisingData(
            [(AdvertisingData.COMPLETE_LOCAL_NAME, bytes(target_name, "utf-8"))]
        )

        # アドバタイズデータ（スキャンした時に見える情報）を明示的に作成
        await device.start_advertising(
            advertising_data=bytes(advertising_data), auto_restart=True
        )

        print("=== アドバタイズ中... ブラウザから接続してください")

        # サーバーを維持し続ける
        await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
