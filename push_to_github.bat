@echo off
echo ========================================
echo GitHub リポジトリへのプッシュスクリプト
echo ========================================
echo.

REM 現在のリモート設定を確認
echo 現在のリモート設定:
git remote -v
echo.

REM 新しいリモートURLを入力
set /p REPO_URL="GitHubリポジトリのURL (例: https://github.com/username/repo-name.git): "

REM 既存のoriginを削除
echo.
echo 既存のリモート設定を削除中...
git remote remove origin

REM 新しいoriginを追加
echo 新しいリモート設定を追加中...
git remote add origin %REPO_URL%

REM ブランチ名をmainに変更
echo.
echo ブランチ名をmainに変更中...
git branch -M main

REM プッシュ
echo.
echo GitHubにプッシュ中...
git push -u origin main

echo.
echo ========================================
echo プッシュが完了しました！
echo ========================================
echo.
echo 次のステップ:
echo 1. GitHubリポジトリのSettingsを開く
echo 2. Secrets and variables ^> Actionsを選択
echo 3. 以下のSecretsを追加:
echo    - GCP_PROJECT_ID
echo    - GCP_SA_KEY
echo    - GEMINI_API_KEY
echo.
echo 詳細は QUICKSTART.md を参照してください。
echo.
pause
