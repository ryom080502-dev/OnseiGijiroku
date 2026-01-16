@echo off
echo ========================================
echo Google Cloud Storage セットアップ
echo ========================================
echo.

REM プロジェクトIDを入力
set /p PROJECT_ID="Google CloudのプロジェクトID (例: gen-lang-client-0553940805): "

echo.
echo プロジェクトを設定中...
gcloud config set project %PROJECT_ID%

echo.
echo [1/3] Cloud Storage APIを有効化中...
gcloud services enable storage.googleapis.com

echo.
echo [2/3] バケットを作成中...
set BUCKET_NAME=%PROJECT_ID%-audio-uploads
gsutil mb -l asia-northeast1 gs://%BUCKET_NAME%

echo.
echo [3/3] バケットのCORS設定を適用中...
echo [{"origin": ["*"], "method": ["GET", "POST", "PUT", "DELETE"], "responseHeader": ["Content-Type"], "maxAgeSeconds": 3600}] > cors.json
gsutil cors set cors.json gs://%BUCKET_NAME%
del cors.json

echo.
echo ========================================
echo セットアップが完了しました！
echo ========================================
echo.
echo バケット名: %BUCKET_NAME%
echo.
pause
