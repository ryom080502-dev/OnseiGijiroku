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
この音声ファイルを聴いて、議事録を作成してください。

【絶対禁止事項】
・同じ内容や文章を繰り返し出力しないでください
・一度書いた項目を再度書かないでください
・類似の箇条書きを連続して並べないでください
・「屋外」「設置」などの単語を連続で繰り返さないでください

【出力方針】
・全文の文字起こしは不要です。要点を整理してまとめてください
・金額、サイズ、色、品番などの具体的な数値情報は必ず含めてください
・各議題は1回だけ簡潔に記載してください
・出力は必ず「5. 補足メモ」まで完成させてください

【出力形式】必ず以下の5セクション構成で出力してください。
箇条書きには「・」のみ使用してください。
強調したい語句は【】で囲んでください（例：【ロッカーについて】）。
「*」「#」「**」などの記号は絶対に使用しないでください。

1. 打合せ概要
打合せの目的や主なテーマを2〜3行で記載

2. 打合せ内容
話し合われた主要な内容を議題ごとに箇条書きで記載
・【議題名】についての要点
・間取りや設計に関する要望・変更点
・設備・仕様についての決定・検討事項
・予算や費用に関する話
・スケジュール・工期に関する話

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
その他の気づきや注意点（なければ「特になし」）"""
    
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
                        temperature=0.1,  # 創造性を最小限に抑えて重複を防止
                        max_output_tokens=32000,  # 5時間の会議に対応（約45,000文字分）
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
            output_truncated = False
            if response.candidates and len(response.candidates) > 0:
                finish_reason = response.candidates[0].finish_reason
                logger.info(f"finish_reason: {finish_reason}")

                # MAX_TOKENSで終了した場合は警告
                if str(finish_reason) == "FinishReason.MAX_TOKENS" or str(finish_reason) == "2":
                    logger.warning("【警告】出力がmax_output_tokensに達して途中で切れました")
                    output_truncated = True

            # レスポンスのパース
            result_text = response.text
            logger.info(f"解析完了 - 文字数: {len(result_text)}")
            logger.debug(f"解析結果の最初の200文字: {result_text[:200]}")
            logger.debug(f"解析結果の最後の200文字: {result_text[-200:]}")

            # 出力が不完全な場合の警告チェック
            if "5. 補足メモ" not in result_text and "## 5." not in result_text:
                logger.warning("議事録の出力が不完全な可能性があります（セクション5が見つかりません）")

            # 重複行を検出・削除する後処理
            result_text = self._remove_duplicate_lines(result_text)

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

    def _remove_duplicate_lines(self, text: str) -> str:
        """
        重複行を検出・削除する後処理

        Args:
            text: 入力テキスト

        Returns:
            重複を削除したテキスト
        """
        lines = text.split('\n')
        result_lines = []
        seen_lines = set()
        consecutive_similar_count = 0
        prev_line_normalized = ""

        for line in lines:
            # 空行はそのまま追加
            if not line.strip():
                result_lines.append(line)
                consecutive_similar_count = 0
                continue

            # 正規化（比較用）- 空白を除去して比較
            normalized = line.strip()

            # 完全に同じ行が連続している場合はスキップ
            if normalized == prev_line_normalized:
                consecutive_similar_count += 1
                if consecutive_similar_count >= 2:
                    logger.debug(f"重複行をスキップ: {line[:50]}...")
                    continue
            else:
                consecutive_similar_count = 0

            # 類似度チェック（同じ接頭辞で始まる箇条書きの連続）
            if normalized.startswith('・') and prev_line_normalized.startswith('・'):
                # 箇条書きの内容部分を比較
                current_content = normalized[1:].strip()
                prev_content = prev_line_normalized[1:].strip() if prev_line_normalized else ""

                # 同じ内容が繰り返されている場合はスキップ
                if current_content and prev_content:
                    # 80%以上同じ場合は重複とみなす
                    if self._similarity_ratio(current_content, prev_content) > 0.8:
                        logger.debug(f"類似行をスキップ: {line[:50]}...")
                        continue

            # セクション見出し（1. 2. 3. など）は重複チェックを厳格に
            if len(normalized) > 0 and normalized[0].isdigit() and '. ' in normalized[:5]:
                section_key = normalized[:5]
                if section_key in seen_lines:
                    logger.debug(f"重複セクションをスキップ: {line[:50]}...")
                    continue
                seen_lines.add(section_key)

            result_lines.append(line)
            prev_line_normalized = normalized

        result = '\n'.join(result_lines)

        # 削除された行数をログ出力
        removed_count = len(lines) - len(result_lines)
        if removed_count > 0:
            logger.info(f"重複行を{removed_count}行削除しました")

        return result

    def _similarity_ratio(self, str1: str, str2: str) -> float:
        """
        2つの文字列の類似度を計算（簡易版）

        Args:
            str1: 文字列1
            str2: 文字列2

        Returns:
            類似度（0.0〜1.0）
        """
        if not str1 or not str2:
            return 0.0

        # 短い方の文字列を基準に
        shorter = str1 if len(str1) <= len(str2) else str2
        longer = str2 if len(str1) <= len(str2) else str1

        # 共通の文字数をカウント
        common_chars = sum(1 for c in shorter if c in longer)

        return common_chars / len(longer) if longer else 0.0
    
