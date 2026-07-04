# M5 Atom Lite 外部ボタン（USB UART）

M5 Atom Lite（ESP32）を **PC の外付けボタン + RGB インジケータ** にするファームウェア。
PC とは **USB シリアル（UART0, 115200bps）** でつながり、

- 本体ボタン（GPIO39）の押下/解放を PC へテキストで通知
- PC から届いたコマンドで本体 RGB LED（GPIO27, SK6812）を任意の色に点灯

する。WiFi は使わず、USB ケーブル 1 本で完結する。

- フレームワーク: **ESP-IDF v5.5**（C）
- ビルド/フラッシュ: **Docker**（ホストに ESP-IDF を入れない。公式 `espressif/idf` イメージ）
- RGB LED 制御: ESP-IDF Component Manager 経由の `espressif/led_strip`

> ビルド環境（Docker + Rakefile ラッパー）は `ref/youtuber_counter/firmware/m5atom-bme280` を踏襲。

## 配線

配線は不要。ATOM Lite を USB-C ケーブルで PC につなぐだけ。ボタンと LED は本体内蔵。

| 用途 | GPIO | 備考 |
|---|---|---|
| ボタン | GPIO39 | 押下で LOW（基板上プルアップ） |
| RGB LED | GPIO27 | SK6812 × 1（GRB） |
| USB シリアル | UART0 (TX=1 / RX=3) | 115200bps |

## ビルド・書き込み

```bash
cd firmware/atomlite-button

rake image           # 専用ビルドイメージ作成（ESP-IDF v5.5 固定。初回のみ。build から自動実行もされる）
rake build           # Docker で ESP-IDF ビルド（初回は set-target esp32 を自動実行）
rake check-port      # シリアルポート自動検出（.serial_port にキャッシュ）
rake flash           # 書き込み / ボーレート指定は FLASH_BAUD=115200 rake flash
rake monitor         # シリアルモニタ（Ctrl-] で終了）
rake flash_monitor   # 書き込み + モニタ
```

- 初回ビルドは `led_strip` コンポーネントの取得とベースイメージ（数 GB）の取得に時間がかかる。
- 既存の別 ESP-IDF イメージを使いたい場合は `.env`（`.env.example` をコピー）に
  `DOCKER_IMAGE=espressif/idf:v5.5` 等を指定する。

## 通信プロトコル（行単位・テキスト）

PC 側は届いた行を **行頭のキーワードで判別** する。デバイス発の行は CRLF 終端。

### Device → PC

| 行 | 意味 |
|---|---|
| `READY` | 起動完了 |
| `BTN DOWN` | ボタン押下（デバウンス済み） |
| `BTN UP` | ボタン解放 |
| `PONG` | `PING` への応答 |
| `OK` | コマンド成功 |
| `ERR <理由>` | コマンド失敗 |

### PC → Device（`\n` または `\r` 終端）

| コマンド | 動作 |
|---|---|
| `LED RRGGBB` | 16進で色指定して点灯（例: `LED FF8800`） |
| `LED OFF` | 消灯 |
| `PING` | 疎通確認（`PONG` が返る） |

例（点灯 → 疎通 → 消灯）:

```
> LED 00FF00
< OK
> PING
< PONG
> LED OFF
< OK
```

> アプリのログは WARN 以上に絞ってあるが、起動直後はブートローダの
> ログがシリアルに出る。PC 側は既知プレフィックス以外の行は無視すること。

## PC 側の例（Python）

`pc/button_client.py` に pyserial を使った最小クライアントを同梱。
ボタン押下でメッセージを表示し、押している間だけ LED を赤くする。

```bash
cd firmware/atomlite-button/pc
python3 -m pip install pyserial
python3 button_client.py /dev/ttyACM0     # ポートは環境に合わせて
```

## 主なファイル

| ファイル | 役割 |
|---|---|
| [`main/main.c`](main/main.c) | ボタン検出・UART プロトコル・LED 制御 |
| [`main/idf_component.yml`](main/idf_component.yml) | `led_strip` 依存定義（Component Manager） |
| [`Rakefile`](Rakefile) | Docker ESP-IDF ラッパー |
| [`sdkconfig.defaults`](sdkconfig.defaults) | ターゲット esp32・ログ抑制 等 |
| [`pc/button_client.py`](pc/button_client.py) | PC 側の最小クライアント（pyserial） |

## トラブルシュート

- ポートが見つからない → ATOM Lite の USB ドライバ（CH9102/CP210x 等）を確認。
  `rake check-port` で `/dev/ttyUSB*` `/dev/ttyACM*` を自動探索する。
- LED が光らない → GPIO27/SK6812 前提。`led_strip` の取得に失敗していないかビルドログを確認。
- ボタンが反応しない → GPIO39 は押下で LOW。`rake monitor` で `BTN DOWN`/`BTN UP` が出るか確認。
- 文字化け・無反応 → 両側のボーレートが 115200 か確認。
