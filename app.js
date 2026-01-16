// API設定
const API_BASE_URL = window.location.origin.includes('localhost') 
    ? 'http://localhost:8080' 
    : window.location.origin;

// グローバル変数
let selectedFile = null;
let metadata = {};
let confirmationItems = [];

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

    // ファイルサイズチェック（500MB）
    const maxSize = 500 * 1024 * 1024;
    if (file.size > maxSize) {
        alert('ファイルサイズは500MB以下にしてください');
        return;
    }

    selectedFile = file;

    // ファイル情報表示
    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatFileSize(file.size);
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

// 音声アップロードと解析（GCS経由）
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
        progressSection.classList.remove('hidden');
        updateProgress(5, '署名付きURLを取得中...');

        // ステップ1: 署名付きURLを取得
        const signedUrlFormData = new FormData();
        signedUrlFormData.append('filename', selectedFile.name);
        signedUrlFormData.append('content_type', selectedFile.type || 'audio/*');

        const signedUrlResponse = await fetch(`${API_BASE_URL}/api/upload/signed-url`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: signedUrlFormData
        });

        if (!signedUrlResponse.ok) {
            const error = await signedUrlResponse.json();
            throw new Error(error.detail || '署名付きURLの取得に失敗しました');
        }

        const { upload_url, filename } = await signedUrlResponse.json();

        updateProgress(15, 'Google Cloud Storageにアップロード中...');

        // ステップ2: GCSに直接アップロード
        const uploadResponse = await fetch(upload_url, {
            method: 'PUT',
            headers: {
                'Content-Type': selectedFile.type || 'audio/*'
            },
            body: selectedFile
        });

        if (!uploadResponse.ok) {
            throw new Error('ファイルのアップロードに失敗しました');
        }

        updateProgress(40, '音声ファイルを処理中...');

        // ステップ3: バックエンドでファイルを処理
        const processFormData = new FormData();
        processFormData.append('filename', filename);

        const processResponse = await fetch(`${API_BASE_URL}/api/process-gcs-file`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: processFormData
        });

        if (!processResponse.ok) {
            const error = await processResponse.json();
            throw new Error(error.detail || 'ファイル処理に失敗しました');
        }

        updateProgress(70, 'AIで解析中...');

        const result = await processResponse.json();

        updateProgress(100, '完了！');

        // 結果を表示
        setTimeout(() => {
            displayResults(result);
        }, 500);

    } catch (error) {
        console.error('Upload error:', error);
        alert(`エラーが発生しました: ${error.message}`);
        uploadBtn.disabled = false;
        progressSection.classList.add('hidden');
    }
}

function updateProgress(percent, message) {
    document.getElementById('progressBar').style.width = `${percent}%`;
    document.getElementById('progressPercent').textContent = `${percent}%`;
    document.getElementById('progressMessage').textContent = message;
}

// 解析結果の表示
function displayResults(result) {
    // 要約をテキストエリアに表示
    document.getElementById('summaryText').value = result.summary;

    // 確認事項を表示
    confirmationItems = result.confirmation_items;
    const container = document.getElementById('confirmationItems');
    container.innerHTML = '';

    if (confirmationItems.length === 0) {
        container.innerHTML = '<p class="text-gray-500">確認事項はありません</p>';
    } else {
        confirmationItems.forEach((item, index) => {
            const div = document.createElement('div');
            div.className = 'flex items-start space-x-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg';
            div.innerHTML = `
                <input type="checkbox" id="item${index}" class="mt-1 h-5 w-5 text-indigo-600 rounded focus:ring-indigo-500">
                <label for="item${index}" class="flex-1 text-gray-800 cursor-pointer">${item}</label>
            `;
            container.appendChild(div);
        });
    }

    // ステップ3へ移動
    document.getElementById('uploadSection').classList.add('hidden');
    document.getElementById('editSection').classList.remove('hidden');
    updateStepIndicator(3);
}

// ドキュメントのエクスポート
async function exportDocument(format) {
    const token = localStorage.getItem('access_token');
    const summary = document.getElementById('summaryText').value;

    // 選択された確認事項を取得
    const selectedItems = [];
    confirmationItems.forEach((item, index) => {
        const checkbox = document.getElementById(`item${index}`);
        if (checkbox && checkbox.checked) {
            selectedItems.push(item);
        }
    });

    try {
        const response = await fetch(`${API_BASE_URL}/api/export`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                summary: summary,
                selected_items: selectedItems,
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
