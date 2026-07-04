#!/usr/bin/env python3
"""M5 Atom Lite 外部ボタンの PC 側サービス（Docker で常駐）。

USB シリアル(既定 115200)で ATOM Lite とつながり、

  - 起動・接続できている「正常時」は LED を緑で点灯
  - ボタンが押されている間は赤で点灯（離すと緑へ戻す）

を行う。USB を抜き差ししても自動で再接続する。

設定は環境変数で上書きできる（docker-compose の environment / .env）:

  SERIAL_PORT    シリアルポート          既定 /dev/ttyACM0
  SERIAL_BAUD    ボーレート              既定 115200
  NORMAL_COLOR   正常時の色（RRGGBB）    既定 00FF00（緑）
  PRESSED_COLOR  押下時の色（RRGGBB）    既定 FF0000（赤）
  RECONNECT_SEC  再接続の待ち秒          既定 2
"""
import os
import sys
import time

try:
    import serial  # pyserial
except ImportError:
    sys.exit("pyserial が必要です: pip install pyserial")

PORT = os.environ.get("SERIAL_PORT", "/dev/ttyACM0")
BAUD = int(os.environ.get("SERIAL_BAUD", "115200"))
NORMAL_COLOR = os.environ.get("NORMAL_COLOR", "00FF00").upper()
PRESSED_COLOR = os.environ.get("PRESSED_COLOR", "FF0000").upper()
RECONNECT_SEC = float(os.environ.get("RECONNECT_SEC", "2"))


def log(msg: str) -> None:
    # -u（unbuffered）で起動する前提。docker logs に即時反映させる。
    print(msg, flush=True)


def send(ser, cmd: str) -> None:
    """デバイスへ 1 コマンド送信（改行終端）。"""
    ser.write((cmd + "\n").encode("ascii"))
    ser.flush()


def set_led(ser, hex_color: str) -> None:
    send(ser, f"LED {hex_color}")


def handle_line(ser, line: str) -> None:
    """デバイスから届いた 1 行を処理する。"""
    if line == "BTN DOWN":
        log("[event] ボタン押下 -> 赤")
        set_led(ser, PRESSED_COLOR)
    elif line == "BTN UP":
        log("[event] ボタン解放 -> 緑")
        set_led(ser, NORMAL_COLOR)
    elif line == "READY":
        # デバイスが（再）起動した。正常色に戻す。
        log("[dev] READY -> 緑")
        set_led(ser, NORMAL_COLOR)
    elif line in ("PONG", "OK") or line.startswith("ERR"):
        log(f"[dev] {line}")
    else:
        # ブートログなど未知の行。無視してよいが一応出す。
        log(f"[?] {line}")


def serve_once() -> None:
    """1 回分の接続セッション。切断で例外を投げて呼び出し側に再接続させる。"""
    log(f"接続中: {PORT} @ {BAUD}")
    with serial.Serial(PORT, BAUD, timeout=1) as ser:
        time.sleep(0.2)
        ser.reset_input_buffer()
        # 接続直後は正常色（緑）にして疎通確認。
        set_led(ser, NORMAL_COLOR)
        send(ser, "PING")
        log(f"接続完了。正常時=#{NORMAL_COLOR} / 押下時=#{PRESSED_COLOR}")

        while True:
            raw = ser.readline()  # timeout=1s。空なら None 相当（b""）
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                handle_line(ser, line)


def main() -> None:
    while True:
        try:
            serve_once()
        except serial.SerialException as e:
            log(f"[warn] シリアル切断/未接続: {e}")
        except OSError as e:
            log(f"[warn] I/O エラー: {e}")
        log(f"{RECONNECT_SEC}s 後に再接続します…")
        time.sleep(RECONNECT_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n終了")
