import asyncio
import logging

from bumble.att import Attribute
from bumble.core import AdvertisingData
from bumble.device import Device
from bumble.gatt import Characteristic, Service
from bumble.hci import Address
from bumble.transport import open_transport

# ログ設定
logging.basicConfig(level=logging.INFO)

# UUID定義（ブラウザ側と合わせる）
SERVICE_UUID = "A07498CA-AD5B-474E-940D-16F1FBE7E8CD"
CHARACTERISTIC_UUID = "51FF12BB-3ED8-46E5-B4F9-D64E2FEC021B"


async def main():
    print("Bumble BLE Server を起動します...")
    print("<<< connecting to HCI...")

    # 公式サンプルに従い、Context Manager を使用して Transport を開く
    # "usb:0" は最初のUSBドングルを使用
    async with await open_transport("usb:0") as hci_transport:
        print("<<< connected")

        # Device の初期化
        # transport そのものではなく、source と sink を渡すのが最新の作法です
        target_name = "ほうじちゃ"
        device = Device.with_hci(
            target_name,  # デバイス名
            Address("F0:F1:F2:F3:F4:F5"),  # MACアドレス
            hci_transport.source,  # 受信ストリーム
            hci_transport.sink,  # 送信ストリーム
        )

        # --- GATT テーブル（サービスとキャラクタリスティック）の作成 ---

        # 書き込み時のコールバック関数
        def on_write(connection, value):
            try:
                text = value.decode("utf-8")
                print(f"=== [受信] ブラウザからの書き込み: {text}")
            except:
                print(f"=== [受信] バイナリデータ: {value.hex()}")

        # キャラクタリスティックの定義
        char_element = Characteristic(
            CHARACTERISTIC_UUID,
            properties=(
                Characteristic.Properties.READ
                | Characteristic.Properties.WRITE
                | Characteristic.Properties.NOTIFY
            ),
            permissions=(
                Attribute.Permissions.READABLE | Attribute.Permissions.WRITEABLE
            ),
            value=b"Hello from Bumble!",
        )

        # 書き込みイベントのハンドラを登録
        char_element.on("write", on_write)

        # サービスの定義
        service_element = Service(SERVICE_UUID, [char_element])

        # デバイスにサービスを追加
        device.add_service(service_element)

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
