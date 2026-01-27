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
        # 音声ファイルを直接処理できるモデルを優先順位順に試す
        # 処理速度を重視し、Flashシリーズのみを使用
        model_names = [
            "gemini-3-flash",                   # Gemini 3 Flash (最新・最優先)
            "models/gemini-3-flash",            # Gemini 3 Flash (代替パス)
            "gemini-3-flash-preview",           # Gemini 3 Flash Preview
            "models/gemini-3-flash-preview",    # Gemini 3 Flash Preview (代替パス)
            "models/gemini-2.5-flash",          # Gemini 2.5 Flash (高速・実績あり)
            "models/gemini-2.5-flash-lite",     # Gemini 2.5 Flash-Lite (超高速・低コスト)
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

【重要な指示】
・分割された記録の内容を全て確認し、重要な情報は漏らさず含めてください
・重複する内容は1回のみ記載してください
・具体的な数字、品番、色、サイズなどの情報は必ず残してください
・出力はA4用紙2枚程度（約2000〜2500文字）を目安にしてください

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

上記の全ての記録内容を確認し、情報を漏らさないよう注意して議事録を作成してください。"""
    
    async def analyze_audio(self, audio_file_path: str) -> Dict[str, Any]:
        """
        音声ファイルをGemini APIで解析

        Args:
            audio_file_path: 解析する音声ファイルのパス

        Returns:
            解析結果（要約と確認事項）
        """
        try:
            logger.info(f"Gemini APIで音声を解析: {audio_file_path}")
            logger.info(f"使用モデル: {self.model_name}")

            # 音声ファイルをアップロード
            try:
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
            max_wait_time = 60  # 最大60秒待機
            wait_count = 0
            while audio_file.state.name == "PROCESSING":
                if wait_count >= max_wait_time / 2:
                    raise TimeoutError("ファイル処理がタイムアウトしました")
                logger.info("ファイル処理中...")
                time.sleep(2)
                audio_file = genai.get_file(audio_file.name)
                wait_count += 1

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
                        max_output_tokens=4096,
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
            logger.info("解析完了")
            
            # 確認事項の抽出
            confirmation_items = self._extract_confirmation_items(result_text)
            
            # 確認事項部分を要約から除去
            summary = self._remove_confirmation_section(result_text)
            
            # アップロードしたファイルを削除
            try:
                genai.delete_file(audio_file.name)
                logger.info("アップロードファイルを削除")
            except Exception as e:
                logger.warning(f"ファイル削除エラー: {str(e)}")
            
            return {
                "summary": summary.strip(),
                "confirmation_items": confirmation_items
            }
        
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
            logger.info(f"{len(summaries)} 個の要約を統合")

            # 要約を番号付きで結合
            numbered_summaries = "\n\n".join(
                [f"--- セグメント {i+1}/{len(summaries)} ---\n{summary}"
                 for i, summary in enumerate(summaries)]
            )

            prompt = self.merge_prompt.format(summaries=numbered_summaries)

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,  # より確実性を重視
                    max_output_tokens=4000,  # A4 2枚程度（約2000-2500文字）に収める
                )
            )

            merged_summary = response.text
            logger.info("要約の統合完了")

            return merged_summary.strip()

        except Exception as e:
            logger.error(f"要約統合エラー: {str(e)}")
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
    
    def _extract_confirmation_items(self, text: str) -> List[str]:
        """
        テキストから確認事項を抽出

        Args:
            text: 解析結果テキスト

        Returns:
            確認事項のリスト
        """
        items = []

        # 確認事項を含む可能性のあるキーワード
        keywords = [
            "確認", "準備", "次回まで", "タスク", "宿題",
            "検討", "調べる", "調査", "確認事項", "お客様",
            "【当社】", "【お客様】"
        ]

        # 「4. 次回までの確認・準備事項」セクションを探す
        section_markers = [
            "4. 次回までの確認",
            "4.次回までの確認",
            "次回までの確認・準備",
            "確認・準備事項",
            "【💡確認事項】",
            "💡確認事項"
        ]

        confirmation_section = None
        for marker in section_markers:
            if marker in text:
                parts = text.split(marker, 1)
                if len(parts) >= 2:
                    confirmation_section = parts[1]
                    # 次のセクション（数字.や##で始まる）までを取得
                    for end_marker in ["\n5.", "\n5 .", "\n##", "\n---"]:
                        end_idx = confirmation_section.find(end_marker)
                        if end_idx != -1:
                            confirmation_section = confirmation_section[:end_idx]
                    break

        if confirmation_section:
            # 箇条書きを抽出
            for line in confirmation_section.split("\n"):
                line = line.strip()
                if not line or line.lower() == "なし" or line == "特になし":
                    continue

                # 箇条書き記号を除去
                for prefix in ["• ", "- ", "* ", "・"]:
                    if line.startswith(prefix):
                        line = line[len(prefix):].strip()
                        break

                # 数字付き箇条書き（1. 2. など）を除去
                if line and line[0].isdigit() and ". " in line[:4]:
                    line = line.split(". ", 1)[1].strip()

                # セクションヘッダーをスキップ
                if line.startswith("【") and line.endswith("】"):
                    continue

                if line and len(line) > 3:
                    items.append(line)

        # テキスト全体から確認キーワードを含む行も抽出
        if len(items) == 0:
            for line in text.split("\n"):
                line = line.strip()
                for prefix in ["• ", "- ", "* ", "・"]:
                    if line.startswith(prefix):
                        line = line[len(prefix):].strip()
                        break

                if any(kw in line for kw in ["確認する", "検討する", "調べる", "準備する"]):
                    if line and len(line) > 5 and line not in items:
                        items.append(line)

        logger.info(f"確認事項を {len(items)} 件抽出")
        return items[:10]  # 最大10件に制限
    
    def _remove_confirmation_section(self, text: str) -> str:
        """
        テキストから確認事項セクションを除去
        （セグメント解析では確認事項セクションは生成されないため、そのまま返す）

        Args:
            text: 元のテキスト

        Returns:
            確認事項を除去したテキスト
        """
        # 新しいプロンプトでは確認事項は議事録本文に含まれるため、除去しない
        return text
