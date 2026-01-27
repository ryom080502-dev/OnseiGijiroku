"""
議事録自動生成システム - FastAPI Backend
"""
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
import tempfile
import logging
import asyncio
from datetime import datetime, timedelta
import jwt
from dotenv import load_dotenv
from google.cloud import storage
from google.auth import default
import uuid

# .envファイルから環境変数を読み込み
load_dotenv()

from audio_processor import AudioProcessor
from gemini_service import GeminiService
from auth_service import AuthService
from document_generator import DocumentGenerator

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPIアプリケーション初期化
app = FastAPI(
    title="議事録自動生成システム",
    description="音声ファイルから議事録を自動生成するAPI",
    version="1.0.0"
)

# ファイルアップロードサイズ制限を200MBに設定
app.state.max_upload_size = 200 * 1024 * 1024  # 200MB

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では特定のドメインに制限
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# セキュリティ
security = HTTPBearer()

# GCS設定
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
if GCS_BUCKET_NAME:
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        logger.info(f"GCS初期化成功: バケット名 = {GCS_BUCKET_NAME}")
    except Exception as e:
        logger.warning(f"GCS初期化エラー: {str(e)}")
        storage_client = None
        bucket = None
else:
    logger.warning("GCS_BUCKET_NAMEが設定されていません。GCS機能は無効です。")
    storage_client = None
    bucket = None

# サービスの初期化
audio_processor = AudioProcessor()
gemini_service = GeminiService()
auth_service = AuthService()
doc_generator = DocumentGenerator()

# リクエスト/レスポンスモデル
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MetadataInput(BaseModel):
    created_date: str
    creator: str
    customer_name: str
    meeting_place: str

class MinutesResponse(BaseModel):
    summary: str
    dynamic_title: str

class ExportRequest(BaseModel):
    summary: str
    metadata: MetadataInput
    format: str  # "word" or "pdf"

class MergeRequest(BaseModel):
    summaries: List[str]

class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str

class UploadUrlResponse(BaseModel):
    upload_url: str
    blob_name: str

# 認証用のデコレータ
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """JWTトークンから現在のユーザーを取得"""
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, 
            os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production"),
            algorithms=["HS256"]
        )
        username = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="無効な認証トークンです"
            )
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンの有効期限が切れています"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なトークンです"
        )

# 静的ファイルの配信（HTMLファイル）
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """ルートパスでログインページを表示"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Welcome to 議事録自動生成システム</h1><p>index.htmlが見つかりません</p>", status_code=404)

@app.get("/dashboard.html", response_class=HTMLResponse)
async def read_dashboard():
    """ダッシュボードページを表示"""
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)

@app.get("/app.js")
async def read_app_js():
    """JavaScriptファイルを配信"""
    return FileResponse("app.js", media_type="application/javascript")

@app.get("/health")
async def health_check():
    """ヘルスチェック用エンドポイント"""
    return {"status": "healthy", "service": "議事録自動生成システム"}

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """ログインエンドポイント"""
    try:
        user = await auth_service.authenticate_user(request.username, request.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="ユーザー名またはパスワードが正しくありません"
            )

        # JWTトークンの生成
        access_token = auth_service.create_access_token(
            data={"sub": user["username"]}
        )

        return LoginResponse(access_token=access_token)

    except Exception as e:
        logger.error(f"ログインエラー: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ログイン処理中にエラーが発生しました"
        )

@app.post("/api/generate-upload-url", response_model=UploadUrlResponse)
async def generate_upload_url(
    request: UploadUrlRequest,
    current_user: str = Depends(get_current_user)
):
    """
    GCSへの署名付きアップロードURLを生成
    """
    try:
        if not bucket:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GCSが設定されていません"
            )

        logger.info(f"ユーザー {current_user} が署名付きURL生成をリクエスト: {request.filename}")

        # 一意のblob名を生成（ユーザー名とUUIDを含む）
        file_extension = os.path.splitext(request.filename)[1]
        blob_name = f"{current_user}/{uuid.uuid4()}{file_extension}"

        # GCSのblobオブジェクトを作成
        blob = bucket.blob(blob_name)

        # GCS resumable upload sessionを作成
        # これならCloud Runのデフォルト認証情報で動作する
        from google.auth import default as google_auth_default
        from google.auth.transport import requests as google_auth_requests

        credentials, _ = google_auth_default()
        auth_request = google_auth_requests.Request()
        credentials.refresh(auth_request)

        # Resumable upload sessionを開始
        upload_url_endpoint = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET_NAME}/o?uploadType=resumable&name={blob_name}"

        session_response = auth_request.session.post(
            upload_url_endpoint,
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
                "X-Upload-Content-Type": request.content_type
            },
            json={"name": blob_name}
        )

        if session_response.status_code not in [200, 201]:
            logger.error(f"Resumable upload session作成エラー: {session_response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="アップロードセッションの作成に失敗しました"
            )

        # session URLを取得
        upload_url = session_response.headers.get("Location")
        if not upload_url:
            logger.error("Location headerが見つかりません")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="アップロードURLの取得に失敗しました"
            )

        logger.info(f"署名付きURL生成成功: {blob_name}")

        return UploadUrlResponse(
            upload_url=upload_url,
            blob_name=blob_name
        )

    except Exception as e:
        logger.error(f"署名付きURL生成エラー: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"署名付きURLの生成中にエラーが発生しました: {str(e)}"
        )

@app.post("/api/upload", response_model=MinutesResponse)
async def upload_audio(
    blob_name: str = Form(...),
    created_date: str = Form(...),
    creator: str = Form(...),
    customer_name: str = Form(...),
    meeting_place: str = Form(...),
    current_user: str = Depends(get_current_user)
):
    """
    GCSから音声ファイルを取得して議事録を生成
    """
    try:
        if not bucket:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GCSが設定されていません"
            )

        logger.info(f"ユーザー {current_user} がGCSから音声ファイルを処理: {blob_name}")

        # 動的タイトルの生成
        dynamic_title = f"{created_date}_{creator}_{customer_name}_{meeting_place}_議事録"

        # 変数の初期化
        temp_file_path = None
        processed_files = []

        try:
            # GCSからファイルをダウンロード
            blob = bucket.blob(blob_name)

            # 一時ファイルに保存
            file_extension = os.path.splitext(blob_name)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                blob.download_to_file(temp_file)
                temp_file_path = temp_file.name

            logger.info(f"GCSからダウンロード完了: {blob_name} -> {temp_file_path}")

            # 音声ファイルの処理（必要に応じて圧縮・分割）
            # 大容量ファイルでもGCS経由なので、分割は最小限に
            logger.info("音声ファイルの処理を開始")
            processed_files = audio_processor.process_audio(temp_file_path)

            logger.info(f"処理結果: {len(processed_files)} 個のファイルに分割されました")

            # Gemini APIで各セグメントを並列解析
            logger.info(f"{len(processed_files)} 個のセグメントをGeminiで並列解析開始")

            # 並列処理でGemini APIを呼び出し
            tasks = [gemini_service.analyze_audio(audio_file) for audio_file in processed_files]
            summaries = await asyncio.gather(*tasks)

            logger.info(f"並列解析完了: {len(summaries)} セグメント")

            # 各セグメントの文字数をログ出力
            for i, summary in enumerate(summaries):
                logger.info(f"セグメント {i+1} の解析結果文字数: {len(summary)}")

            # 複数のセグメントがある場合は統合
            if len(summaries) > 1:
                logger.info(f"{len(summaries)} 個のセグメントを統合します")
                final_summary = await gemini_service.merge_summaries(summaries)
                logger.info(f"統合完了 - 最終議事録の文字数: {len(final_summary)}")
            else:
                logger.info("セグメントは1つのみのため、統合はスキップします")
                final_summary = summaries[0]

            # GCSからファイルを削除（処理完了後）
            try:
                blob.delete()
                logger.info(f"GCSファイル削除: {blob_name}")
            except Exception as e:
                logger.warning(f"GCSファイル削除エラー: {blob_name} - {str(e)}")

            return MinutesResponse(
                summary=final_summary,
                dynamic_title=dynamic_title
            )

        finally:
            # 一時ファイルのクリーンアップ
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                    logger.debug(f"一時ファイル削除: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"一時ファイル削除エラー: {temp_file_path} - {str(e)}")

            for processed_file in processed_files:
                if os.path.exists(processed_file):
                    try:
                        os.unlink(processed_file)
                        logger.debug(f"処理済みファイル削除: {processed_file}")
                    except Exception as e:
                        logger.warning(f"処理済みファイル削除エラー: {processed_file} - {str(e)}")

    except Exception as e:
        logger.error(f"音声処理エラー: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"音声ファイルの処理中にエラーが発生しました: {str(e)}"
        )

@app.post("/api/merge")
async def merge_summaries(
    request: MergeRequest,
    current_user: str = Depends(get_current_user)
):
    """
    複数セグメントの要約を統合して1つの議事録にまとめる
    """
    try:
        logger.info(f"ユーザー {current_user} が {len(request.summaries)} 個の要約を統合")

        if len(request.summaries) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="統合する要約がありません"
            )

        # 1つだけの場合はそのまま返す
        if len(request.summaries) == 1:
            final_summary = request.summaries[0]
        else:
            # Gemini APIで統合
            final_summary = await gemini_service.merge_summaries(request.summaries)

        return {
            "summary": final_summary
        }

    except Exception as e:
        logger.error(f"要約統合エラー: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"要約の統合中にエラーが発生しました: {str(e)}"
        )

@app.post("/api/export")
async def export_minutes(
    request: ExportRequest,
    current_user: str = Depends(get_current_user)
):
    """
    議事録をWord/PDF形式でエクスポート
    """
    try:
        logger.info(f"ユーザー {current_user} が {request.format} 形式でエクスポート")

        # ドキュメント生成
        if request.format.lower() == "word":
            output_path = doc_generator.generate_word(
                request.summary,
                request.metadata.model_dump()
            )
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"{request.metadata.created_date}_{request.metadata.customer_name}_議事録.docx"

        elif request.format.lower() == "pdf":
            output_path = doc_generator.generate_pdf(
                request.summary,
                request.metadata.model_dump()
            )
            media_type = "application/pdf"
            filename = f"{request.metadata.created_date}_{request.metadata.customer_name}_議事録.pdf"

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="サポートされていないフォーマットです"
            )

        return FileResponse(
            path=output_path,
            media_type=media_type,
            filename=filename
        )

    except Exception as e:
        logger.error(f"エクスポートエラー: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"エクスポート中にエラーが発生しました: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
