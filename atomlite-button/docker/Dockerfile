# M5 Atom Lite 外部ボタン ファーム用の ESP-IDF ビルド環境。
#
# ESP-IDF v5.5 をベースに固定する。ホストに入っている別バージョン
# （v6 系など）に左右されず、再現性のあるビルドを行うためのプロジェクト専用イメージ。
#
# ビルド: rake image   （= docker build -t atomlite-button-idf:v5.5 docker/）
FROM espressif/idf:v5.5

# 追加のツールが要る場合はここに apt-get で足す（現状は idf.py のみで十分）。

# espressif/idf イメージの entrypoint が export.sh を読み込み idf.py を使える状態にする。
WORKDIR /project
