# PC 側サービス（ATOM Lite 外部ボタン）のコンテナイメージ。
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# -u で標準出力をアンバッファ化し、docker logs に即時反映させる。
CMD ["python", "-u", "app.py"]
