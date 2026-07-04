#!/usr/bin/env python3
"""M5 Atom Lite 外部ボタンの PC 側サービス（Docker で常駐）。

USB シリアル(既定 115200)で ATOM Lite とつながり、

  - 起動・接続できている「正常時」は LED を緑で点灯
  - ボタンが押されている間は赤で点灯（離すと緑へ戻す）

を行う。USB を抜き差ししても自動で再接続する。

さらに、現在色を HEARTBEAT_SEC ごとに再送する（ハートビート）。これは
ATOM 側のリンク監視のための定期通信を兼ねる。この通信が途絶えると ATOM は
LED を白にして「PC からの通信が失われた」ことを示し、通信が戻ると次の
ハートビートが正しい色を再送して復帰する。

設定は環境変数で上書きできる（docker-compose の environment / .env）:

  SERIAL_PORT    シリアルポート          既定 /dev/ttyUSB0
  SERIAL_BAUD    ボーレート              既定 115200
  NORMAL_COLOR   正常時の色（RRGGBB）    既定 00FF00（緑）
  PRESSED_COLOR  押下時の色（RRGGBB）    既定 FF0000（赤）
  HEARTBEAT_SEC  ハートビート周期(秒)    既定 1（ATOM 側の断判定は 3 秒）
  RECONNECT_SEC  再接続の待ち秒          既定 2
"""
import os
import sys
import time

try:
    import serial  # pyserial
except ImportError:
    sys.exit("pyserial が必要です: pip install pyserial")

PORT = os.environ.get("SERIAL_PORT", "/dev/ttyUSB0")
BAUD = int(os.environ.get("SERIAL_BAUD", "115200"))
NORMAL_COLOR = os.environ.get("NORMAL_COLOR", "00FF00").upper()
PRESSED_COLOR = os.environ.get("PRESSED_COLOR", "FF0000").upper()
HEARTBEAT_SEC = float(os.environ.get("HEARTBEAT_SEC", "1"))
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


def current_color(state) -> str:
    """今あるべき LED 色（押下中は赤・それ以外は緑）。"""
    return PRESSED_COLOR if state["pressed"] else NORMAL_COLOR


def handle_line(ser, line: str, state) -> None:
    """デバイスから届いた 1 行を処理する。"""
    if line == "BTN DOWN":
        state["pressed"] = True
        log("[event] button down -> red")
        set_led(ser, PRESSED_COLOR)
    elif line == "BTN UP":
        state["pressed"] = False
        log("[event] button up -> green")
        set_led(ser, NORMAL_COLOR)
    elif line == "READY":
        # デバイスが（再）起動した。状態を初期化して正常色に戻す。
        state["pressed"] = False
        log("[dev] READY -> green")
        set_led(ser, NORMAL_COLOR)
    elif line == "OK":
        # ハートビートの ACK が毎秒来るのでログには出さない。
        pass
    elif line == "PONG" or line.startswith("ERR"):
        log(f"[dev] {line}")
    else:
        # ブートログなど未知の行。無視してよいが一応出す。
        log(f"[?] {line}")


def serve_once() -> None:
    """1 回分の接続セッション。切断で例外を投げて呼び出し側に再接続させる。"""
    state = {"pressed": False}
    log(f"connecting: {PORT} @ {BAUD}")
    # timeout はハートビート周期より短くして、アイドル時も概ね周期どおり送れるように。
    with serial.Serial(PORT, BAUD, timeout=0.5) as ser:
        time.sleep(0.2)
        ser.reset_input_buffer()
        set_led(ser, current_color(state))  # 接続直後は正常色（緑）
        last_hb = time.monotonic()
        log(f"connected. normal=#{NORMAL_COLOR} / pressed=#{PRESSED_COLOR} / "
            f"heartbeat {HEARTBEAT_SEC}s")

        while True:
            raw = ser.readline()  # timeout まで最大 0.5s ブロック
            if raw:
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    handle_line(ser, line, state)

            # ハートビート: 現在色を定期再送。ATOM のリンク監視を満たし、
            # 通信復帰時には白から正しい色へ戻す役目も担う。
            now = time.monotonic()
            if now - last_hb >= HEARTBEAT_SEC:
                set_led(ser, current_color(state))
                last_hb = now


def main() -> None:
    while True:
        try:
            serve_once()
        except serial.SerialException as e:
            log(f"[warn] serial disconnected/unavailable: {e}")
        except OSError as e:
            log(f"[warn] I/O error: {e}")
        log(f"reconnecting in {RECONNECT_SEC}s...")
        time.sleep(RECONNECT_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\nstopped")
