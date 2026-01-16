@echo off
echo ========================================
echo Google Cloud APIの有効化
echo ========================================
echo.

REM プロジェクトIDを入力
set /p PROJECT_ID="Google CloudのプロジェクトID: "

echo.
echo プロジェクトを設定中...
gcloud config set project %PROJECT_ID%

echo.
echo 必要なAPIを有効化中...
echo.

echo [1/3] Cloud Run API を有効化中...
gcloud services enable run.googleapis.com

echo [2/3] Container Registry API を有効化中...
gcloud services enable containerregistry.googleapis.com

echo [3/3] Cloud Build API を有効化中...
gcloud services enable cloudbuild.googleapis.com

echo.
echo ========================================
echo APIの有効化が完了しました！
echo ========================================
echo.
echo 次のステップ: デプロイを実行してください
echo.
pause
