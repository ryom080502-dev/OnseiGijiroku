// API設定
const API_BASE_URL = window.location.origin.includes('localhost')
    ? 'http://localhost:8080'
    : window.location.origin;

// グローバル変数
let selectedFile = null;
let metadata = {};

// トークンの有効期限をチェック
function isTokenExpired(token) {
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        // exp はUNIXタイムスタンプ（秒）
        return payload.exp * 1000 < Date.now();
    } catch (e) {
        return true;
    }
}

// 認証切れ時のリダイレクト処理
function handleAuthExpired() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
    alert('セッションの有効期限が切れました。再度ログインしてください。');
    window.location.href = 'index.html';
}

// APIレスポンスの認証エラーチェック（各API呼び出しで使用）
function checkAuthResponse(response) {
    if (response.status === 401) {
        handleAuthExpired();
        throw new Error('認証エラー');
    }
}

// 初期化
document.addEventListener('DOMContentLoaded', () => {
    // 認証チェック（トークンの存在 + 有効期限）
    const token = localStorage.getItem('access_token');
    if (!token || isTokenExpired(token)) {
        if (token) {
            // トークンはあるが期限切れ
            handleAuthExpired();
        } else {
            window.location.href = 'index.html';
        }
        return;
    }

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

function updateStepIndicator(currentStep) {
    // ステップの状態を更新
    [1, 2, 3].forEach(s => {
        const stepElement = document.getElementById(`step${s}`);
        if (!stepElement) return;

        // クラスをリセット
        stepElement.classList.remove('active', 'completed');

        if (s < currentStep) {
            // 完了したステップ
            stepElement.classList.add('completed');
        } else if (s === currentStep) {
            // 現在のステップ
            stepElement.classList.add('active');
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

    // ファイルサイズチェック（最大2GB - GCS経由）
    const maxSize = 2 * 1024 * 1024 * 1024; // 2GB
    if (file.size > maxSize) {
        alert(`ファイルサイズが大きすぎます (${formatFileSize(file.size)})。2GB以下のファイルを選択してください。`);
        return;
    }

    selectedFile = file;

    // ファイル情報表示
    const fileSizeText = formatFileSize(file.size);

    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = fileSizeText;

    document.getElementById('fileInfo').classList.add('show');
    document.getElementById('uploadBtn').disabled = false;
}

function clearFile() {
    selectedFile = null;
    document.getElementById('audioFile').value = '';
    document.getElementById('fileInfo').classList.remove('show');
    document.getElementById('uploadBtn').disabled = true;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// 音声アップロードと解析（署名付きURL経由でGCSへ）
async function uploadAudio() {
    if (!selectedFile) {
        alert('ファイルを選択してください');
        return;
    }

    const token = localStorage.getItem('access_token');
    const uploadBtn = document.getElementById('uploadBtn');
    const progressSection = document.getElementById('uploadProgress');

    try {
        uploadBtn.disabled = true;
        progressSection.classList.add('show');

        // ステップ1: 署名付きURLを取得
        updateProgress(5, '署名付きURLを取得中...');
        const { upload_url, blob_name } = await generateUploadUrl(selectedFile, token);

        // ステップ2: GCSへ直接アップロード（Cloud Run制限を回避）
        updateProgress(10, 'GCSへファイルをアップロード中...');
        await uploadToGCS(upload_url, selectedFile);
        updateProgress(30, 'アップロード完了');

        // ステップ3: バックエンドで音声解析
        updateProgress(40, 'AIが音声を解析中...（数分かかる場合があります）');
        const finalResult = await processAudioFromGCS(blob_name, token);
        updateProgress(100, '完了！');

        // 結果を表示
        setTimeout(() => {
            displayResults(finalResult);
        }, 500);

    } catch (error) {
        console.error('Upload error:', error);
        alert(`エラーが発生しました: ${error.message}`);
        uploadBtn.disabled = false;
        progressSection.classList.remove('show');
    }
}

// 署名付きURL取得
async function generateUploadUrl(file, token) {
    console.log(`署名付きURL取得: ${file.name}`);

    const formData = new FormData();
    formData.append('filename', file.name);
    formData.append('content_type', file.type || 'audio/mpeg');

    const response = await fetch(`${API_BASE_URL}/api/generate-upload-url`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`
        },
        body: formData
    });

    checkAuthResponse(response);

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '署名付きURLの取得に失敗しました');
    }

    return await response.json();
}

// GCSへ直接アップロード
async function uploadToGCS(uploadUrl, file) {
    console.log(`GCSへアップロード: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`);

    const response = await fetch(uploadUrl, {
        method: 'PUT',
        headers: {
            'Content-Type': file.type || 'audio/mpeg'
        },
        body: file
    });

    if (!response.ok) {
        const errorText = await response.text();
        console.error('GCSアップロードエラー:', errorText);
        throw new Error(`GCSアップロードに失敗しました (ステータス: ${response.status})`);
    }

    console.log('GCSアップロード完了');
}

// バックエンドで音声解析
async function processAudioFromGCS(blobName, token) {
    console.log(`音声解析開始: ${blobName}`);

    const formData = new FormData();
    formData.append('blob_name', blobName);
    formData.append('created_date', metadata.created_date);
    formData.append('creator', metadata.creator);
    formData.append('customer_name', metadata.customer_name);
    formData.append('meeting_place', metadata.meeting_place);

    const startTime = Date.now();

    // タイムアウトを15分に設定（大容量ファイル対応）
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        console.warn('リクエストがタイムアウトしました（15分経過）');
        controller.abort();
    }, 15 * 60 * 1000); // 15分

    try {
        const response = await fetch(`${API_BASE_URL}/api/upload`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData,
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        checkAuthResponse(response);

        const processingTime = ((Date.now() - startTime) / 1000).toFixed(2);
        console.log(`処理完了: ${processingTime}秒`);

        if (!response.ok) {
            const contentType = response.headers.get('content-type');
            let errorMessage = '音声解析に失敗しました';

            if (response.status === 503) {
                errorMessage = 'サーバーが一時的に利用できません。ファイルサイズが大きい場合は、数分後に再度お試しください。';
            } else if (response.status === 504) {
                errorMessage = '処理がタイムアウトしました。ファイルサイズを小さくするか、音声を分割してお試しください。';
            } else if (contentType && contentType.includes('application/json')) {
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
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error('処理がタイムアウトしました（15分）。音声ファイルが非常に長い可能性があります。');
        }
        throw error;
    }
}

function updateProgress(percent, message) {
    document.getElementById('progressBar').style.width = `${percent}%`;
    document.getElementById('progressPercent').textContent = `${percent}%`;
    document.getElementById('progressMessage').textContent = message;
}

// Markdown記号を変換する関数
function convertMarkdownSymbols(text) {
    // **テキスト** → 【テキスト】
    text = text.replace(/\*\*(.+?)\*\*/g, '【$1】');
    // ## テキスト → テキスト（行頭の##を削除）
    text = text.replace(/^##\s*/gm, '');
    return text;
}

// 解析結果の表示
function displayResults(result) {
    // Markdown記号を変換してから表示　
    const convertedSummary = convertMarkdownSymbols(result.summary);
    document.getElementById('summaryText').value = convertedSummary;

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

        checkAuthResponse(response);

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
