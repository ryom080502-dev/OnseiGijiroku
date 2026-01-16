# Python 3.13をベースイメージとして使用
FROM python:3.13-slim

# 作業ディレクトリを設定
WORKDIR /app

# システムパッケージの更新とffmpegのインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# requirements.txtをコピーして依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルをコピー
COPY main.py .
COPY gemini_service.py .
COPY audio_processor.py .
COPY document_generator.py .
COPY auth_service.py .
COPY index.html .
COPY dashboard.html .
COPY app.js .
COPY .env.example .env

# ポート8080を公開
EXPOSE 8080

# 環境変数の設定
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# uvicornでアプリケーションを起動（200MBまでのファイルアップロードを許可）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--limit-max-requests", "1000", "--timeout-keep-alive", "120"]
