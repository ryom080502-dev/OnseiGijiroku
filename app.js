// API設定
const API_BASE_URL = window.location.origin.includes('localhost') 
    ? 'http://localhost:8080' 
    : window.location.origin;

// グローバル変数
let selectedFile = null;
let metadata = {};

// 初期化
document.addEventListener('DOMContentLoaded', () => {
    // 認証チェック
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = 'index.html';
        return;
    }

    // ユーザー名表示
    const username = localStorage.getItem('username');
    document.getElementById('currentUser').textContent = username || 'ユーザー';

    // 今日の日付をデフォルト設定
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('createdDate').value = today;

    // イベントリスナー設定
    setupEventListeners();
    updateDynamicTitle();
});

// イベントリスナーの設定
function setupEventListeners() {
    // メタデータ入力の変更を監視
    ['createdDate', 'creator', 'customerName', 'meetingPlace'].forEach(id => {
        document.getElementById(id).addEventListener('input', updateDynamicTitle);
    });

    // ファイルアップロード関連
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('audioFile');

    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);

    // ドラッグ&ドロップ
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });
}

// 動的タイトルの更新
function updateDynamicTitle() {
    const date = document.getElementById('createdDate').value.replace(/-/g, '');
    const customer = document.getElementById('customerName').value;

    const title = `${date}_${customer}_議事録`;
    document.getElementById('dynamicTitle').textContent = title || '（入力してください）';
}

// ステップ遷移
function goToStep2() {
    // バリデーション
    const requiredFields = ['createdDate', 'creator', 'customerName', 'meetingPlace'];
    for (const field of requiredFields) {
        if (!document.getElementById(field).value) {
            alert('すべての項目を入力してください');
            return;
        }
    }

    // メタデータを保存
    metadata = {
        created_date: document.getElementById('createdDate').value,
        creator: document.getElementById('creator').value,
        customer_name: document.getElementById('customerName').value,
        meeting_place: document.getElementById('meetingPlace').value
    };

    // UI更新
    document.getElementById('metadataSection').classList.add('hidden');
    document.getElementById('uploadSection').classList.remove('hidden');
    updateStepIndicator(2);
}

function goToStep1() {
    document.getElementById('uploadSection').classList.add('hidden');
    document.getElementById('metadataSection').classList.remove('hidden');
    updateStepIndicator(1);
}

function updateStepIndicator(step) {
    const steps = [1, 2, 3];
    steps.forEach(s => {
        const element = document.getElementById(`step${s}`);
        if (s <= step) {
            element.querySelector('div').classList.remove('border-gray-300', 'text-gray-400');
            element.querySelector('div').classList.add('border-indigo-600', 'bg-indigo-600', 'text-white');
            element.classList.remove('text-gray-400');
            element.classList.add('text-indigo-600');
        } else {
            element.querySelector('div').classList.add('border-gray-300');
            element.querySelector('div').classList.remove('border-indigo-600', 'bg-indigo-600', 'text-white');
            element.classList.add('text-gray-400');
            element.classList.remove('text-indigo-600');
        }
    });
}

// ファイル処理
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        handleFile(file);
    }
}

function handleFile(file) {
    // ファイルタイプチェック
    if (!file.type.startsWith('audio/') && !file.type.startsWith('video/')) {
        alert('音声ファイルまたは動画ファイルを選択してください');
        return;
    }

    // ファイルサイズチェック（最大500MB）
    const maxSize = 500 * 1024 * 1024; // 500MB
    if (file.size > maxSize) {
        alert(`ファイルサイズが大きすぎます (${formatFileSize(file.size)})。500MB以下のファイルを選択してください。`);
        return;
    }

    selectedFile = file;

    // ファイル情報表示
    const fileSizeText = formatFileSize(file.size);
    const cloudRunLimit = 30 * 1024 * 1024;

    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = fileSizeText;

    // 30MB超の場合は自動分割の案内を表示
    if (file.size > cloudRunLimit) {
        document.getElementById('fileSize').textContent = `${fileSizeText} (自動的に5分ごとに分割してアップロードします)`;
    }

    document.getElementById('fileInfo').classList.remove('hidden');
    document.getElementById('uploadBtn').disabled = false;
}

function clearFile() {
    selectedFile = null;
    document.getElementById('audioFile').value = '';
    document.getElementById('fileInfo').classList.add('hidden');
    document.getElementById('uploadBtn').disabled = true;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// 音声アップロードと解析（自動分割対応）
async function uploadAudio() {
    if (!selectedFile) {
        alert('ファイルを選択してください');
        return;
    }

    const token = localStorage.getItem('access_token');
    const uploadBtn = document.getElementById('uploadBtn');
    const progressSection = document.getElementById('uploadProgress');
    const cloudRunLimit = 30 * 1024 * 1024; // 30MB

    try {
        uploadBtn.disabled = true;
        progressSection.classList.remove('hidden');

        let finalResult;

        // 30MB以下の場合は通常アップロード（サーバー側で分割・統合）
        if (selectedFile.size <= cloudRunLimit) {
            updateProgress(10, 'ファイルをアップロード中...');
            updateProgress(50, 'AIが音声を解析中...');
            finalResult = await uploadSingleFile(selectedFile, token);
            updateProgress(100, '完了！');
        } else {
            // 30MB以上の場合は5分ごとに分割してアップロード
            updateProgress(5, 'ファイルを分割中...');
            const segments = await splitAudioFile(selectedFile);

            if (!segments || segments.length === 0) {
                throw new Error('ファイルの分割に失敗しました');
            }

            updateProgress(10, `${segments.length}個のセグメントをアップロード中...`);

            // 各セグメントをアップロードして解析
            const allResults = [];
            for (let i = 0; i < segments.length; i++) {
                const progress = 10 + ((i + 1) / segments.length) * 60;
                updateProgress(progress, `セグメント ${i + 1}/${segments.length} を処理中...`);

                const result = await uploadSingleFile(segments[i], token);
                allResults.push(result);
            }

            updateProgress(75, 'AIが議事録を1つにまとめています...');

            // 結果を統合
            finalResult = await mergeResults(allResults);

            updateProgress(100, '完了！');
        }

        // 結果を表示
        setTimeout(() => {
            displayResults(finalResult);
        }, 500);

    } catch (error) {
        console.error('Upload error:', error);
        alert(`エラーが発生しました: ${error.message}`);
        uploadBtn.disabled = false;
        progressSection.classList.add('hidden');
    }
}

// 単一ファイルのアップロード
async function uploadSingleFile(file, token) {
    console.log(`ファイルをアップロード: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('created_date', metadata.created_date);
    formData.append('creator', metadata.creator);
    formData.append('customer_name', metadata.customer_name);
    formData.append('meeting_place', metadata.meeting_place);

    const uploadStartTime = Date.now();

    const response = await fetch(`${API_BASE_URL}/api/upload`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`
        },
        body: formData
    });

    const uploadTime = ((Date.now() - uploadStartTime) / 1000).toFixed(2);
    console.log(`アップロード完了: ${uploadTime}秒`);

    if (!response.ok) {
        const contentType = response.headers.get('content-type');
        let errorMessage = 'アップロードに失敗しました';

        if (contentType && contentType.includes('application/json')) {
            try {
                const error = await response.json();
                errorMessage = error.detail || errorMessage;
            } catch (e) {
                console.error('JSONパースエラー:', e);
            }
        } else {
            const text = await response.text();
            console.error('サーバーエラー:', text);
            errorMessage = `サーバーエラー (ステータス: ${response.status})`;
        }

        throw new Error(errorMessage);
    }

    return await response.json();
}

// 音声ファイルを5分ごとに分割（WAVファイルサイズを10MB程度に保つため）
async function splitAudioFile(file) {
    try {
        const arrayBuffer = await file.arrayBuffer();
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

        const duration = audioBuffer.duration; // 秒
        const segmentDuration = 5 * 60; // 5分 = 300秒（モノラル16kHz変換で約10MB）
        const numSegments = Math.ceil(duration / segmentDuration);

        console.log(`音声ファイル: ${duration}秒, ${numSegments}セグメントに分割`);

        const segments = [];
        const sampleRate = audioBuffer.sampleRate;

        for (let i = 0; i < numSegments; i++) {
            const startTime = i * segmentDuration;
            const endTime = Math.min((i + 1) * segmentDuration, duration);
            const startSample = Math.floor(startTime * sampleRate);
            const endSample = Math.floor(endTime * sampleRate);
            const segmentLength = endSample - startSample;

            // 新しいAudioBufferを作成
            const segmentBuffer = audioContext.createBuffer(
                audioBuffer.numberOfChannels,
                segmentLength,
                sampleRate
            );

            // データをコピー
            for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
                const sourceData = audioBuffer.getChannelData(channel);
                const segmentData = segmentBuffer.getChannelData(channel);
                for (let j = 0; j < segmentLength; j++) {
                    segmentData[j] = sourceData[startSample + j];
                }
            }

            // WAVファイルに変換
            const wavBlob = await audioBufferToWav(segmentBuffer);
            const segmentFile = new File([wavBlob], `segment_${i + 1}.wav`, { type: 'audio/wav' });
            console.log(`セグメント ${i + 1}: ${(segmentFile.size / (1024 * 1024)).toFixed(2)} MB`);
            segments.push(segmentFile);
        }

        console.log(`合計 ${segments.length} セグメント作成完了`);
        return segments;
    } catch (error) {
        console.error('ファイル分割エラー:', error);
        throw new Error('ファイルの分割に失敗しました。ブラウザがWeb Audio APIをサポートしていない可能性があります。');
    }
}

// AudioBufferをWAVファイルに変換（モノラル・16kHzで圧縮）
async function audioBufferToWav(audioBuffer) {
    // モノラルに変換してサイズを削減
    const numChannels = 1; // モノラル
    const targetSampleRate = 16000; // 16kHz（音声認識に十分）
    const format = 1; // PCM
    const bitDepth = 16;

    // ダウンサンプリング
    const originalSampleRate = audioBuffer.sampleRate;
    const sampleRateRatio = originalSampleRate / targetSampleRate;
    const newLength = Math.floor(audioBuffer.length / sampleRateRatio);

    // モノラルデータを作成（複数チャンネルの場合は平均化）
    const monoData = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
        const originalIndex = Math.floor(i * sampleRateRatio);
        let sum = 0;
        for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
            sum += audioBuffer.getChannelData(channel)[originalIndex];
        }
        monoData[i] = sum / audioBuffer.numberOfChannels;
    }

    const bytesPerSample = bitDepth / 8;
    const blockAlign = numChannels * bytesPerSample;

    const data = [];
    for (let i = 0; i < newLength; i++) {
        const sample = monoData[i];
        const int16 = Math.max(-1, Math.min(1, sample)) * 0x7FFF;
        data.push(int16);
    }

    const dataLength = data.length * bytesPerSample;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);

    // WAVヘッダーを書き込む
    const writeString = (offset, string) => {
        for (let i = 0; i < string.length; i++) {
            view.setUint8(offset + i, string.charCodeAt(i));
        }
    };

    writeString(0, 'RIFF');
    view.setUint32(4, 36 + dataLength, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true); // fmt chunk size
    view.setUint16(20, format, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, targetSampleRate, true);
    view.setUint32(28, targetSampleRate * blockAlign, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitDepth, true);
    writeString(36, 'data');
    view.setUint32(40, dataLength, true);

    // PCMデータを書き込む
    let offset = 44;
    for (let i = 0; i < data.length; i++) {
        view.setInt16(offset, data[i], true);
        offset += 2;
    }

    return new Blob([buffer], { type: 'audio/wav' });
}

// 複数セグメントの解析結果を統合（サーバーAPIで統合）
async function mergeResults(results) {
    const token = localStorage.getItem('access_token');

    console.log(`統合処理開始: ${results.length}個のセグメント`);

    // 全てのサマリーを収集
    const allSummaries = results.map(r => r.summary);

    console.log('各セグメントの要約文字数:', allSummaries.map(s => s.length));

    // 各セグメントの最初の100文字を表示
    allSummaries.forEach((summary, i) => {
        console.log(`セグメント ${i + 1} の内容 (最初の100文字):`, summary.substring(0, 100));
    });

    // サーバーAPIを呼び出して統合
    try {
        console.log('サーバーに統合リクエストを送信中...');
        const response = await fetch(`${API_BASE_URL}/api/merge`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                summaries: allSummaries
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('統合API エラーレスポンス:', errorText);
            throw new Error(`統合APIの呼び出しに失敗しました: ${response.status}`);
        }

        const mergedResult = await response.json();
        console.log('統合完了 - 統合後の文字数:', mergedResult.summary.length);

        return {
            summary: mergedResult.summary,
            dynamic_title: results[0].dynamic_title
        };
    } catch (error) {
        console.error('統合エラー:', error);
        console.warn('フォールバック処理: 単純結合を使用');
        // フォールバック：単純結合
        return {
            summary: allSummaries.join('\n\n---\n\n'),
            dynamic_title: results[0].dynamic_title
        };
    }
}

function updateProgress(percent, message) {
    document.getElementById('progressBar').style.width = `${percent}%`;
    document.getElementById('progressPercent').textContent = `${percent}%`;
    document.getElementById('progressMessage').textContent = message;
}

// 解析結果の表示
function displayResults(result) {
    // 議事録をテキストエリアに表示
    document.getElementById('summaryText').value = result.summary;

    // ステップ3へ移動
    document.getElementById('uploadSection').classList.add('hidden');
    document.getElementById('editSection').classList.remove('hidden');
    updateStepIndicator(3);
}

// ドキュメントのエクスポート
async function exportDocument(format) {
    const token = localStorage.getItem('access_token');
    const summary = document.getElementById('summaryText').value;

    try {
        const response = await fetch(`${API_BASE_URL}/api/export`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                summary: summary,
                metadata: metadata,
                format: format
            })
        });

        if (!response.ok) {
            throw new Error('エクスポートに失敗しました');
        }

        // ファイルをダウンロード
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        // 日付からハイフンを除去してファイル名を生成
        const dateForFilename = metadata.created_date.replace(/-/g, '');
        a.download = `${dateForFilename}_${metadata.customer_name}_議事録.${format === 'word' ? 'docx' : 'pdf'}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

    } catch (error) {
        console.error('Export error:', error);
        alert(`エクスポートエラー: ${error.message}`);
    }
}

// フォームリセット
function resetForm() {
    if (confirm('新規作成しますか? 現在の内容は失われます。')) {
        window.location.reload();
    }
}

// ログアウト
function logout() {
    if (confirm('ログアウトしますか?')) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        window.location.href = 'index.html';
    }
}
