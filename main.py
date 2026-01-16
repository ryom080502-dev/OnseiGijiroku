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
from datetime import datetime, timedelta
import jwt
from dotenv import load_dotenv

# .envファイルから環境変数を読み込み
load_dotenv()

from audio_processor import AudioProcessor
from gemini_service import GeminiService
from auth_service import AuthService
from document_generator import DocumentGenerator
from gcs_service import GCSService

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

# サービスの初期化
audio_processor = AudioProcessor()
gemini_service = GeminiService()
auth_service = AuthService()
doc_generator = DocumentGenerator()

# GCSサービスの初期化（GCP_PROJECT_IDが設定されている場合のみ）
gcs_service = None
if os.getenv("GCP_PROJECT_ID"):
    try:
        gcs_service = GCSService()
        logger.info("GCSサービスを初期化しました")
    except Exception as e:
        logger.warning(f"GCSサービスの初期化に失敗: {str(e)}")
else:
    logger.info("GCP_PROJECT_IDが設定されていないため、GCSは無効です")

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
    confirmation_items: List[str]
    dynamic_title: str

class ExportRequest(BaseModel):
    summary: str
    selected_items: List[str]
    metadata: MetadataInput
    format: str  # "word" or "pdf"

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

@app.post("/api/upload/signed-url")
async def get_upload_signed_url(
    filename: str = Form(...),
    content_type: str = Form("audio/*"),
    current_user: str = Depends(get_current_user)
):
    """
    GCS署名付きURLを生成
    クライアントはこのURLを使って直接GCSにファイルをアップロードする
    """
    if not gcs_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Cloud Storageが利用できません"
        )

    try:
        # ユニークなファイル名を生成
        import uuid
        unique_filename = f"{current_user}/{uuid.uuid4()}_{filename}"

        # 署名付きURLを生成
        signed_url = gcs_service.generate_upload_signed_url(unique_filename, content_type)

        return {
            "upload_url": signed_url,
            "filename": unique_filename
        }

    except Exception as e:
        logger.error(f"署名付きURL生成エラー: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"署名付きURLの生成に失敗しました: {str(e)}"
        )

@app.post("/api/process-gcs-file", response_model=MinutesResponse)
async def process_gcs_file(
    filename: str = Form(...),
    current_user: str = Depends(get_current_user)
):
    """
    GCSにアップロードされたファイルを処理して議事録を生成
    """
    if not gcs_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Cloud Storageが利用できません"
        )

    temp_file_path = None

    try:
        logger.info(f"GCSファイル処理開始: {filename}")

        # 一時ファイルにダウンロード
        with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as temp_file:
            temp_file_path = temp_file.name

        if not gcs_service.download_to_temp(filename, temp_file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="ファイルが見つかりません"
            )

        # 音声ファイルを処理
        processed_audio_path = audio_processor.process_audio(temp_file_path)

        # Gemini APIで文字起こしと要約を生成
        summary, confirmation_items, dynamic_title = gemini_service.transcribe_and_summarize(
            processed_audio_path
        )

        # 処理済みファイルを削除
        if processed_audio_path and os.path.exists(processed_audio_path):
            os.remove(processed_audio_path)

        # GCSからファイルを削除（オプション）
        # gcs_service.delete_file(filename)

        logger.info(f"GCSファイル処理完了: {filename}")

        return MinutesResponse(
            summary=summary,
            confirmation_items=confirmation_items,
            dynamic_title=dynamic_title
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GCSファイル処理エラー: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"ファイル処理中にエラーが発生しました: {str(e)}"
        )
    finally:
        # 一時ファイルのクリーンアップ
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass

@app.post("/api/upload", response_model=MinutesResponse)
async def upload_audio(
    file: UploadFile = File(...),
    created_date: str = Form(...),
    creator: str = Form(...),
    customer_name: str = Form(...),
    meeting_place: str = Form(...),
    current_user: str = Depends(get_current_user)
):
    """
    音声ファイルをアップロードして議事録を生成
    """
    try:
        logger.info(f"ユーザー {current_user} が音声ファイルをアップロード: {file.filename}")

        # 動的タイトルの生成
        dynamic_title = f"{created_date}_{creator}_{customer_name}_{meeting_place}_議事録"

        # 変数の初期化
        temp_file_path = None
        processed_files = []

        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name

        try:
            # 音声ファイルの処理（圧縮・分割）
            logger.info("音声ファイルの処理を開始")
            processed_files = audio_processor.process_audio(temp_file_path)
            
            # Gemini APIで各セグメントを解析
            logger.info(f"{len(processed_files)} 個のセグメントをGeminiで解析")
            all_summaries = []
            all_confirmations = []
            
            for idx, audio_file in enumerate(processed_files):
                logger.info(f"セグメント {idx + 1}/{len(processed_files)} を処理中")
                result = await gemini_service.analyze_audio(audio_file)
                all_summaries.append(result["summary"])
                all_confirmations.extend(result["confirmation_items"])
            
            # 複数のセグメントがある場合は統合
            if len(all_summaries) > 1:
                final_summary = await gemini_service.merge_summaries(all_summaries)
            else:
                final_summary = all_summaries[0]
            
            # 重複する確認事項を除去
            unique_confirmations = list(dict.fromkeys(all_confirmations))
            
            return MinutesResponse(
                summary=final_summary,
                confirmation_items=unique_confirmations,
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
        
        # 最終的な議事録テキストを作成（選択された確認事項を含む）
        final_text = request.summary
        if request.selected_items:
            final_text += "\n\n【💡確認事項】\n"
            for item in request.selected_items:
                final_text += f"• {item}\n"
        
        # ドキュメント生成
        if request.format.lower() == "word":
            output_path = doc_generator.generate_word(
                final_text, 
                request.metadata.model_dump()
            )
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"{request.metadata.created_date}_{request.metadata.customer_name}_議事録.docx"
        
        elif request.format.lower() == "pdf":
            output_path = doc_generator.generate_pdf(
                final_text,
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
