# PC 側サービス（ATOM Lite 外部ボタン）

ATOM Lite（ファームは [`../atomlite-button/`](../atomlite-button/)）と USB シリアルで
つながり、次の動きをする常駐サービス。Docker Compose で起動する。

- **正常時（接続できている間）は LED を緑で点灯**
- **ボタンが押されている間は赤**（離すと緑に戻る）
- USB を抜き差ししても自動で再接続する

## 使い方

```bash
cd pc
cp .env.example .env          # SERIAL_PORT を実機に合わせる（任意）
docker compose up -d --build
docker compose logs -f        # ボタンイベントを確認（Ctrl-C で抜ける）
docker compose down           # 停止
```

## 設定（`.env` または compose の environment）

| 変数 | 既定 | 意味 |
|---|---|---|
| `SERIAL_PORT` | `/dev/ttyACM0` | シリアルポート |
| `SERIAL_BAUD` | `115200` | ボーレート（ファーム固定値） |
| `NORMAL_COLOR` | `00FF00` | 正常時の色（緑） |
| `PRESSED_COLOR` | `FF0000` | 押下時の色（赤） |

## USB デバイスをコンテナへ渡す注意

- **Linux**: `docker-compose.yml` の `devices:` でホストの `SERIAL_PORT` を
  そのままコンテナに渡す。ポートが `/dev/ttyUSB0` などの場合は `.env` で変更する。
- **WSL2**: WSL からは USB シリアルが直接見えない。Windows 側で
  [usbipd-win](https://github.com/dorssel/usbipd-win) を使い
  `usbipd attach --wsl --busid <BUSID>` で WSL にアタッチしてから `docker compose up`。
- **macOS / Windows の Docker Desktop**: USB パススルー非対応。ホストで直接
  `python app.py` を実行する（`pip install -r requirements.txt` 後）。

## プロトコル

デバイスとのやり取りは行単位のテキスト。詳細は
[`../atomlite-button/README.md`](../atomlite-button/README.md#通信プロトコル行単位テキスト) を参照。

- Device→PC: `READY` / `BTN DOWN` / `BTN UP` / `PONG` / `OK` / `ERR ...`
- PC→Device: `LED RRGGBB` / `LED OFF` / `PING`

## ファイル

| ファイル | 役割 |
|---|---|
| [`app.py`](app.py) | サービス本体（正常=緑/押下=赤・自動再接続） |
| [`docker-compose.yml`](docker-compose.yml) | Docker で常駐させる構成 |
| [`Dockerfile`](Dockerfile) | イメージ定義 |
| [`requirements.txt`](requirements.txt) | 依存（pyserial） |
