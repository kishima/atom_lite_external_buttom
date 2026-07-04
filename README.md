# atom_lite_external_buttom

M5 Atom Lite を **PC の外部ボタン**にするプロジェクト。ATOM Lite を USB で PC に
つなぎ、ボタン押下を PC へ通知したり、PC から本体 RGB LED を任意の色に光らせたりする。

```
PC ── USB(UART 115200) ── ATOM Lite（ボタン + RGB LED）
```

## 構成

| ディレクトリ | 内容 |
|---|---|
| [`atomlite-button/`](atomlite-button/) | ATOM Lite 側ファームウェア（ESP-IDF / C、Docker ビルド） |
| [`pc/`](pc/) | PC 側サービス（Docker Compose。正常時=緑 / ボタン押下時=赤） |

- ファームのビルド・書き込み・プロトコル仕様 → [`atomlite-button/README.md`](atomlite-button/README.md)
- PC 側サービスの起動方法 → [`pc/README.md`](pc/README.md)

> `ref/` はビルド環境の参照元リポジトリ（`.gitignore` 済み・非コミット）。
