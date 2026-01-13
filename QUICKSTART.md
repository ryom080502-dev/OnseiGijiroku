# クイックスタート - Google Cloud Run デプロイ

このガイドに従って、音声議事録AIをGoogle Cloud Runに素早くデプロイできます。

## 前提条件

- GitHubアカウント
- Google Cloudアカウント（課金有効）
- Gemini APIキー

## ステップ1: Google Cloudの準備（5分）

### 1.1 プロジェクトの作成

```bash
# Google Cloud SDKをインストール済みの場合
gcloud projects create voice-minutes-prod --name="Voice Minutes Generator"
gcloud config set project voice-minutes-prod

# 課金を有効化（GCPコンソールで実施）
```

### 1.2 必要なAPIを有効化

```bash
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### 1.3 サービスアカウントの作成

```bash
# サービスアカウントを作成
gcloud iam service-accounts create github-actions \
  --display-name="GitHub Actions Deploy"

# プロジェクトIDを取得
PROJECT_ID=$(gcloud config get-value project)

# 必要な権限を付与
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# JSONキーを作成
gcloud iam service-accounts keys create key.json \
  --iam-account=github-actions@${PROJECT_ID}.iam.gserviceaccount.com

# key.jsonの内容を表示（後でGitHub Secretsに設定）
cat key.json
```

## ステップ2: GitHubリポジトリの作成（3分）

### 2.1 GitHubでリポジトリを作成

1. GitHubにログイン
2. 「New repository」をクリック
3. リポジトリ名: `voice-minutes-generator`（任意）
4. プライベートリポジトリを選択
5. 「Create repository」をクリック

### 2.2 GitHub Secretsの設定

リポジトリの Settings > Secrets and variables > Actions で以下を追加:

| Secret名 | 値 | 取得方法 |
|---------|---|---------|
| **GCP_PROJECT_ID** | `voice-minutes-prod` | Google CloudのプロジェクトID |
| **GCP_SA_KEY** | `{"type":"service_account",...}` | 上記で作成したkey.jsonの全内容 |
| **GEMINI_API_KEY** | `AIza...` | [Google AI Studio](https://aistudio.google.com/app/apikey)で取得 |

## ステップ3: コードをプッシュ（2分）

```bash
# 現在のディレクトリに移動
cd "C:\Users\r-moc\Desktop\AI作成\音声議事録AI"

# リモートリポジトリを追加（YOUR_USERNAMEを自分のGitHubユーザー名に置き換え）
git remote add origin https://github.com/YOUR_USERNAME/voice-minutes-generator.git

# ブランチ名をmainに変更
git branch -M main

# プッシュ
git push -u origin main
```

## ステップ4: デプロイの確認（5分）

### 4.1 GitHub Actionsを確認

1. GitHubリポジトリの「Actions」タブを開く
2. 「Deploy to Cloud Run」ワークフローが実行中であることを確認
3. 完了するまで待機（約3-5分）

### 4.2 デプロイURLを確認

ワークフローが完了したら、ログの最後に表示されるURLをコピー:

```
https://minutes-generator-xxxxxxxxxx-an.a.run.app
```

### 4.3 アプリケーションにアクセス

ブラウザでURLを開き、ログイン画面が表示されることを確認:

- **ユーザー名**: demo
- **パスワード**: demo123

## トラブルシューティング

### デプロイが失敗する場合

#### エラー: "Permission denied"
→ サービスアカウントの権限を確認してください

```bash
# 権限を再付与
PROJECT_ID=$(gcloud config get-value project)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"
```

#### エラー: "API not enabled"
→ 必要なAPIが有効になっているか確認

```bash
# APIを有効化
gcloud services enable run.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

#### エラー: "Invalid GEMINI_API_KEY"
→ GitHub SecretsのGEMINI_API_KEYが正しいか確認

1. [Google AI Studio](https://aistudio.google.com/app/apikey)でAPIキーを再確認
2. GitHub Secretsを更新
3. 再度プッシュして再デプロイ

### ログの確認方法

```bash
# Cloud Runのログを表示
gcloud run logs read --service minutes-generator --region asia-northeast1

# リアルタイムでログを追跡
gcloud run logs tail --service minutes-generator --region asia-northeast1
```

## 次のステップ

### カスタムドメインの設定

```bash
# ドメインをマッピング
gcloud run domain-mappings create \
  --service minutes-generator \
  --domain your-domain.com \
  --region asia-northeast1
```

### 認証の設定（デモモードを無効化）

本番環境では、Firebase Authenticationを設定してデモモードを無効にすることを推奨します。詳細は [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) を参照してください。

### コスト最適化

```bash
# 最小インスタンス数を0に設定（使用していない時は課金されない）
gcloud run services update minutes-generator \
  --min-instances 0 \
  --region asia-northeast1

# 最大インスタンス数を制限
gcloud run services update minutes-generator \
  --max-instances 5 \
  --region asia-northeast1
```

## サポート

- 詳細なデプロイ手順: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- README: [README.md](README.md)
- 問題報告: GitHubのIssuesで報告

## 所要時間まとめ

| ステップ | 所要時間 |
|---------|---------|
| Google Cloudの準備 | 5分 |
| GitHubリポジトリの作成 | 3分 |
| コードのプッシュ | 2分 |
| デプロイの確認 | 5分 |
| **合計** | **約15分** |

おめでとうございます！音声議事録AIが本番環境にデプロイされました。
