#!/usr/bin/env python3
"""M5 Atom Lite 外部ボタンの PC 側 最小クライアント。

USB シリアル(115200)経由で ATOM Lite とやり取りする:
  - デバイスから届く行（READY / BTN DOWN / BTN UP / PONG / OK / ERR ...）を表示
  - ボタンを押している間だけ LED を赤く点灯し、離すと消灯

使い方:
  python3 -m pip install pyserial
  python3 button_client.py [PORT] [BAUD]
    PORT 省略時は /dev/ttyACM0、BAUD 省略時は 115200

これは動作確認用のサンプル。実アプリでは on_button_down() 等を
好きな処理（アプリ起動・ショートカット送出など）に置き換える。
"""
import sys
import time

try:
    import serial  # pyserial
except ImportError:
    sys.exit("pyserial が必要です: python3 -m pip install pyserial")


def send(ser, cmd: str) -> None:
    """デバイスへ 1 コマンド送信（改行終端）。"""
    ser.write((cmd + "\n").encode("ascii"))
    ser.flush()


def set_led(ser, hex_color: str) -> None:
    """LED を 16進色で点灯。'OFF' 相当は 'LED OFF'。"""
    send(ser, f"LED {hex_color}")


# ---- ボタンイベントのフック（ここを好きな処理に差し替える）----
def on_button_down(ser) -> None:
    print("[event] ボタンが押された")
    set_led(ser, "FF0000")   # 押している間は赤


def on_button_up(ser) -> None:
    print("[event] ボタンが離された")
    set_led(ser, "OFF")      # 離したら消灯


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM0"
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    print(f"接続中: {port} @ {baud}")
    with serial.Serial(port, baud, timeout=1) as ser:
        time.sleep(0.2)
        ser.reset_input_buffer()
        send(ser, "PING")  # 疎通確認

        while True:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            # デバイス発の既知プレフィックスで分岐
            if line == "BTN DOWN":
                on_button_down(ser)
            elif line == "BTN UP":
                on_button_up(ser)
            elif line in ("READY", "PONG", "OK") or line.startswith("ERR"):
                print(f"[dev] {line}")
            else:
                # ブートログなど未知の行はそのまま表示（無視しても良い）
                print(f"[?] {line}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n終了")
