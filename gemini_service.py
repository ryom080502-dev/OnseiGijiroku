"""
Google Gemini APIを使用した音声解析サービス
"""
import google.generativeai as genai
import os
import logging
from typing import Dict, List, Any
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
        
        # プロンプトテンプレート
        # 分割されたセグメントごとのプロンプト（詳細記録用）
        self.segment_prompt = """あなたは注文住宅の営業打合せを記録する専門の書記です。
この音声の内容を詳細に聞き取り、打合せの内容を漏れなく記録してください。

【記録すべき内容】
・話し合われた全ての議題と内容
・間取りや設計に関する要望・変更点の詳細
・設備・仕様についての話（キッチン、バス、トイレ、床材、壁紙など）
・予算や費用に関する具体的な話
・スケジュール・工期に関する話
・お客様からの質問や要望
・営業担当からの説明や提案
・決定した事項
・保留・検討事項
・次回までの宿題や確認事項

【出力ルール】
・箇条書きには「・」のみ使用してください
・「*」「#」「##」は絶対に使用しないでください
・話された内容を具体的に記録してください
・金額、サイズ、色、品番などの具体的な情報は必ず含めてください
・お客様の発言と営業の発言が区別できる場合は明記してください

音声内容を解析して、打合せ記録を作成してください。"""

        # 統合プロンプト（A4用紙2枚程度に収める）
        self.merge_prompt = """あなたは注文住宅会社の優秀な営業アシスタントです。
以下は同じ打合せを分割して記録した内容です。これを1つの読みやすい議事録にまとめてください。

【最重要指示】
・分割された記録の内容を「全て」確認し、話し合われた情報は「漏らさず全て」含めてください
・重複する内容のみ1回にまとめ、それ以外は全て記載してください
・具体的な数字、品番、色、サイズなどの情報は必ず残してください
・打合せの流れに沿って、時系列で記載してください
・長くなっても構いません。情報を省略せず、詳細に記録することを最優先してください

【出力形式】必ず以下の5セクション構成で出力してください。
箇条書きには「・」のみ使用し、「*」「#」は使用しないでください。

1. 打合せ概要
打合せの目的や主なテーマを2〜3行で記載

2. 打合せ内容
話し合われた内容を具体的に箇条書きで記載してください。
・議題ごとに内容をまとめる
・具体的な仕様、金額、サイズなどの情報を含める
・お客様の要望や質問も記載する
・営業からの説明や提案も記載する
・セグメント間で話題が変わる場合は、全ての話題を記載する

3. 決定事項
この打合せで確定・決定したことを明確に箇条書きで記載
・決定した仕様や選択
・合意した内容

4. 次回までの確認・準備事項
【お客様】
・お客様側で確認・準備すること
【当社】
・会社側で確認・準備すること

5. 補足メモ
その他の気づきや注意点（なければ「特になし」）

---
【分割された記録】
{summaries}

上記の全ての記録内容を確認し、情報を漏らさないよう注意して議事録を作成してください。
繰り返しますが、情報の省略は避け、全ての内容を詳細に記載してください。"""
    
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

            # Geminiで解析（セグメント用のプロンプトを使用）
            logger.info("Gemini APIに解析リクエストを送信")
            try:
                response = self.model.generate_content(
                    [self.segment_prompt, audio_file],
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,  # 創造性を抑えて正確性を重視
                        max_output_tokens=8000,  # 出力トークン数を増やす（4096→8000）
                    )
                )
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

            # レスポンスのパース
            result_text = response.text
            logger.info(f"解析完了 - 文字数: {len(result_text)}")
            logger.debug(f"解析結果の最初の200文字: {result_text[:200]}")
            logger.debug(f"解析結果の最後の200文字: {result_text[-200:]}")

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
    
    async def merge_summaries(self, summaries: List[str]) -> str:
        """
        複数の議事録要約を統合（A4用紙2枚程度に収める）

        Args:
            summaries: 統合する要約のリスト

        Returns:
            統合された要約
        """
        try:
            logger.info(f"{len(summaries)} 個の要約を統合開始")

            # 各要約の文字数をログ出力
            for i, summary in enumerate(summaries):
                logger.info(f"セグメント {i+1} の文字数: {len(summary)}")

            # 要約を番号付きで結合
            numbered_summaries = "\n\n".join(
                [f"--- セグメント {i+1}/{len(summaries)} ---\n{summary}"
                 for i, summary in enumerate(summaries)]
            )

            logger.info(f"統合前の総文字数: {len(numbered_summaries)}")

            prompt = self.merge_prompt.format(summaries=numbered_summaries)

            logger.info("Gemini APIに統合リクエストを送信")
            logger.info(f"プロンプトの文字数: {len(prompt)}")

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,  # より確実性を重視
                    max_output_tokens=8000,  # 出力トークン数を増やす（4000→8000）
                )
            )

            merged_summary = response.text
            logger.info(f"要約の統合完了 - 統合後の文字数: {len(merged_summary)}")

            # レスポンスの最初の500文字をログ出力（デバッグ用）
            logger.debug(f"統合結果の最初の500文字: {merged_summary[:500]}")

            return merged_summary.strip()

        except Exception as e:
            logger.error(f"要約統合エラー: {str(e)}")
            logger.warning("フォールバック処理を使用します")
            # エラーの場合はフォールバック処理
            return self._fallback_merge(summaries)

    def _fallback_merge(self, summaries: List[str]) -> str:
        """
        API呼び出し失敗時のフォールバック統合
        """
        # 各セグメントから重要な行だけ抽出
        important_lines = []
        for summary in summaries:
            for line in summary.split('\n'):
                line = line.strip()
                if line and line.startswith('・'):
                    important_lines.append(line)

        # 重複を除去
        unique_lines = list(dict.fromkeys(important_lines))

        return "【打合せ内容】\n" + "\n".join(unique_lines[:20])
