"""
Google Gemini APIを使用した音声解析サービス
"""
import google.generativeai as genai
import os
import logging
from typing import Dict, Any
import time

logger = logging.getLogger(__name__)

class GeminiService:
    def __init__(self):
        """Gemini APIサービスの初期化"""
        # APIキーの設定（GEMINI_API_KEY と GOOGLE_API_KEY の両方をサポート）
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("APIキーが設定されていません。.envファイルにGEMINI_API_KEYを設定してください")
            raise ValueError(
                "APIキーが見つかりません。.envファイルに以下を設定してください:\n"
                "GEMINI_API_KEY=your-api-key-here"
            )

        # Gemini APIの設定
        try:
            genai.configure(api_key=api_key)
            logger.info("Gemini API設定完了")
        except Exception as e:
            logger.error(f"Gemini API設定エラー: {str(e)}")
            raise

        # モデルの設定
        # 音声ファイルを直接処理できる実績のあるモデルを優先順位順に試す
        # Gemini 2.5シリーズのみが音声処理に対応（GA版）
        model_names = [
            "models/gemini-2.5-flash",          # Gemini 2.5 Flash (音声処理対応・高速・高精度・推奨)
            "models/gemini-2.5-pro",            # Gemini 2.5 Pro (音声処理対応・最高精度・処理時間長)
            "models/gemini-2.5-flash-lite",     # Gemini 2.5 Flash-Lite (音声処理対応・超高速・軽量)
            "models/gemini-flash-latest",       # 最新のFlashモデル (フォールバック)
        ]

        self.model_name = None
        model_initialized = False
        last_error = None

        for model_name in model_names:
            try:
                self.model = genai.GenerativeModel(model_name)
                self.model_name = model_name
                logger.info(f"使用モデル: {model_name}")
                model_initialized = True
                break
            except Exception as e:
                logger.warning(f"{model_name} 利用不可: {str(e)}")
                last_error = e
                continue

        if not model_initialized:
            logger.error(f"すべてのモデルが利用できません。最後のエラー: {str(last_error)}")
            raise ValueError(
                "Geminiモデルを初期化できませんでした。\n"
                "APIキーが正しいか、利用可能なモデルがあるか確認してください。"
            )
        
        # 音声解析プロンプト（議事録を生成）
        self.prompt = """あなたは注文住宅会社の優秀な営業アシスタントです。
この音声ファイルを最初から最後まで完全に聴き、議事録を作成してください。

【最重要指示】
・音声ファイル全体（冒頭から終盤まで）を漏れなく確認し、全ての内容を議事録に含めてください
・出力は必ず「5. 補足メモ」まで完成させてください。途中で終わらせないでください
・長い音声の場合でも、全ての議題を網羅してください

【出力方針】
・全文の文字起こしは不要です。要点を整理してまとめてください
・金額、サイズ、色、品番などの具体的な数値情報は必ず含めてください
・音声で言及された全ての議題・トピックを含めてください

【出力形式】必ず以下の5セクション構成で出力してください。
箇条書きには「・」のみ使用してください。
強調したい語句は【】で囲んでください（例：【ロッカーについて】）。
「*」「#」「**」などの記号は絶対に使用しないでください。
必ず5番まで全て出力を完了してください。

1. 打合せ概要
打合せの目的や主なテーマを2〜3行で記載

2. 打合せ内容
話し合われた主要な内容を議題ごとに箇条書きで記載
・【議題名】についての要点
・間取りや設計に関する要望・変更点
・設備・仕様についての決定・検討事項（キッチン、バス、トイレ、床材、壁紙など）
・予算や費用に関する話
・スケジュール・工期に関する話
・その他話し合われた全ての内容
・各議題は簡潔にまとめ、具体的な数値情報は含める

3. 決定事項
この打合せで確定・決定したことを箇条書きで記載
・決定事項がない場合は「特になし」

4. 次回までの確認・準備事項
【お客様】
・お客様側で確認・準備すること
【当社】
・会社側で確認・準備すること
※該当がなければ「特になし」

5. 補足メモ
その他の気づきや注意点（なければ「特になし」）

【最終確認】
上記5セクション全てを出力してください。「5. 補足メモ」を書き終えるまで出力を続けてください。"""
    
    async def analyze_audio(self, audio_file_path: str) -> str:
        """
        音声ファイルをGemini APIで解析

        Args:
            audio_file_path: 解析する音声ファイルのパス

        Returns:
            解析結果（統合された議事録）
        """
        try:
            # ファイルサイズを取得
            import os
            file_size_mb = os.path.getsize(audio_file_path) / (1024 * 1024)
            logger.info(f"Gemini APIで音声を解析: {audio_file_path} ({file_size_mb:.2f} MB)")
            logger.info(f"使用モデル: {self.model_name}")

            # 音声ファイルをアップロード
            try:
                logger.info("Gemini APIへファイルアップロードを開始...")
                audio_file = genai.upload_file(path=audio_file_path)
                logger.info(f"ファイルアップロード完了: {audio_file.name}")
            except Exception as e:
                logger.error(f"ファイルアップロードエラー: {str(e)}")
                raise ValueError(
                    f"音声ファイルのアップロードに失敗しました。\n"
                    f"ファイル形式を確認してください。\n"
                    f"エラー詳細: {str(e)}"
                )

            # アップロード処理の完了を待機
            max_wait_time = 300  # 最大300秒（5分）待機
            wait_interval = 3  # 3秒ごとにチェック
            elapsed_time = 0
            while audio_file.state.name == "PROCESSING":
                if elapsed_time >= max_wait_time:
                    raise TimeoutError(f"ファイル処理がタイムアウトしました（{max_wait_time}秒経過）")
                logger.info(f"ファイル処理中... ({elapsed_time}秒経過)")
                time.sleep(wait_interval)
                audio_file = genai.get_file(audio_file.name)
                elapsed_time += wait_interval

            if audio_file.state.name == "FAILED":
                raise ValueError(f"ファイル処理に失敗しました: {audio_file.state.name}")

            logger.info(f"ファイル処理完了: {audio_file.state.name}")

            # Geminiで解析
            logger.info("Gemini APIに解析リクエストを送信")
            analysis_start_time = time.time()
            try:
                response = self.model.generate_content(
                    [self.prompt, audio_file],
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,  # 創造性を抑えて正確性を重視
                        max_output_tokens=32000,  # 十分な出力を確保（8000→32000）
                    )
                )
                analysis_time = time.time() - analysis_start_time
                logger.info(f"Gemini API解析完了 - 処理時間: {analysis_time:.2f}秒")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"generate_contentエラー: {error_msg}")

                # より詳細なエラーメッセージを提供
                if "404" in error_msg or "not found" in error_msg.lower():
                    raise ValueError(
                        f"使用中のモデル '{self.model_name}' は音声ファイルの処理に対応していません。\n"
                        f"APIキーの権限を確認するか、Google AI Studioで利用可能なモデルを確認してください。\n"
                        f"エラー詳細: {error_msg}"
                    )
                elif "not supported" in error_msg.lower():
                    raise ValueError(
                        f"このAPIキーでは音声ファイルの処理がサポートされていません。\n"
                        f"有料プランへのアップグレードが必要な可能性があります。"
                    )
                else:
                    raise

            # finish_reasonを確認（出力が途中で切れていないかチェック）
            finish_reason = None
            if response.candidates and len(response.candidates) > 0:
                finish_reason = response.candidates[0].finish_reason
                logger.info(f"finish_reason: {finish_reason}")

                # MAX_TOKENSで終了した場合は警告
                if str(finish_reason) == "FinishReason.MAX_TOKENS" or str(finish_reason) == "2":
                    logger.warning("出力がmax_output_tokensに達して途中で切れた可能性があります")

            # レスポンスのパース
            result_text = response.text
            logger.info(f"解析完了 - 文字数: {len(result_text)}")
            logger.debug(f"解析結果の最初の200文字: {result_text[:200]}")
            logger.debug(f"解析結果の最後の200文字: {result_text[-200:]}")

            # 出力が不完全な場合の警告チェック
            if "5. 補足メモ" not in result_text and "## 5." not in result_text:
                logger.warning("議事録の出力が不完全な可能性があります（セクション5が見つかりません）")

            # アップロードしたファイルを削除
            try:
                genai.delete_file(audio_file.name)
                logger.info("アップロードファイルを削除")
            except Exception as e:
                logger.warning(f"ファイル削除エラー: {str(e)}")

            return result_text.strip()

        except Exception as e:
            logger.error(f"Gemini API解析エラー: {str(e)}")
            raise
    
