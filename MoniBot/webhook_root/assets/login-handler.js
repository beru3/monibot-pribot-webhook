// login-handler.js - ログインとセッション管理を処理

class LoginHandler {
    constructor() {
        this.setupEventListeners();
        
        // 初期化ログ
        console.log('LoginHandler初期化完了');
        console.log('設定情報:', window.appConfig || '設定ファイルが読み込まれていません');
    }
    
    setupEventListeners() {
        const loginForm = document.getElementById('login-form');
        const loginButton = document.getElementById('login-button');
        const loginIdField = document.getElementById('login-id');
        
        // フォームのsubmitイベントとボタンのクリックイベントの両方を処理
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const loginId = loginIdField?.value?.trim() || '';
                this.handleLogin(loginId);
            });
        }
        
        if (loginButton && loginIdField) {
            loginButton.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleLogin(loginIdField.value.trim());
            });
        }
    }
    
    handleLogin(loginId) {
        if (!loginId) {
            this.showError('ログインIDを入力してください。');
            return;
        }
        
        console.log(`ログイン処理開始: "${loginId}"`);
        
        // ローディング表示を追加
        this.showLoading(true);
        
        // デバッグモードのチェック
        if (loginId === "debug") {
            this.handleDebugMode();
            return;
        }
        
        // 設定を取得
        const apiBaseUrl = window.appConfig?.apiBaseUrl;
        const apiKey = window.appConfig?.apiKey;
        
        // すべてのプロジェクトID
        const projectIds = [];
        if (window.appConfig?.projectIds?.staff) {
            projectIds.push(window.appConfig.projectIds.staff);
        }
        if (window.appConfig?.projectIds?.billing) {
            projectIds.push(window.appConfig.projectIds.billing);
        }
        if (window.appConfig?.projectIds?.hospital) {
            projectIds.push(window.appConfig.projectIds.hospital);
        }
        
        console.log("API設定情報:", { 
            apiBaseUrl: apiBaseUrl || "未設定", 
            apiKeyLength: apiKey ? apiKey.length : 0,
            projectIds: projectIds 
        });
        
        if (!apiBaseUrl || !apiKey || projectIds.length === 0) {
            this.showError('システム設定が不正です。管理者にお問い合わせください。');
            this.showLoading(false);
            return;
        }
        
        // 複数プロジェクトから一括でユーザーを取得
        this.fetchUsersFromMultipleProjects(apiBaseUrl, apiKey, projectIds, loginId);
    }
    
    // 複数プロジェクトからユーザーを取得
    fetchUsersFromMultipleProjects(apiBaseUrl, apiKey, projectIds, loginId) {
        console.log(`${projectIds.length}つのプロジェクトからユーザーを取得します`);
        
        // 各プロジェクトのユーザー取得をPromiseの配列に変換
        const fetchPromises = projectIds.map(projectId => {
            const apiUrl = `${apiBaseUrl}/projects/${projectId}/users?apiKey=${apiKey}`;
            console.log(`APIリクエスト: プロジェクト ${projectId}`);
            
            return fetch(apiUrl)
                .then(response => {
                    if (!response.ok) {
                        console.warn(`プロジェクト ${projectId} の取得でエラー: ${response.status}`);
                        return []; // エラー時は空配列を返す
                    }
                    return response.json();
                })
                .then(users => {
                    console.log(`プロジェクト ${projectId} から ${users.length}人のユーザーを取得`);
                    return users;
                })
                .catch(error => {
                    console.error(`プロジェクト ${projectId} 取得エラー:`, error);
                    return []; // エラー時は空配列を返す
                });
        });
        
        // すべてのプロジェクトのリクエストを実行
        Promise.all(fetchPromises)
            .then(userArrays => {
                // すべてのユーザー配列を結合
                const allUsers = [].concat(...userArrays);
                
                // 重複ユーザーを削除（IDをキーとして使用）
                const uniqueUsers = this.removeDuplicateUsers(allUsers);
                
                console.log(`合計 ${uniqueUsers.length}人のユニークユーザーを取得しました`);
                this.processUsers(uniqueUsers, loginId);
            })
            .catch(error => {
                console.error('ユーザー取得中にエラーが発生しました:', error);
                this.showError(`システムエラーが発生しました: ${error.message}`);
                this.showLoading(false);
            });
    }
    
    // 重複ユーザーを削除
    removeDuplicateUsers(users) {
        const uniqueUsers = [];
        const seenIds = new Set();
        
        for (const user of users) {
            if (!seenIds.has(user.id)) {
                seenIds.add(user.id);
                uniqueUsers.push(user);
            }
        }
        
        return uniqueUsers;
    }
    
    // デバッグモード
    handleDebugMode() {
        const apiBaseUrl = window.appConfig?.apiBaseUrl;
        const apiKey = window.appConfig?.apiKey;
        
        // すべてのプロジェクトID
        const projectIds = [];
        if (window.appConfig?.projectIds?.staff) {
            projectIds.push(window.appConfig.projectIds.staff);
        }
        if (window.appConfig?.projectIds?.billing) {
            projectIds.push(window.appConfig.projectIds.billing);
        }
        if (window.appConfig?.projectIds?.hospital) {
            projectIds.push(window.appConfig.projectIds.hospital);
        }
        
        if (!apiBaseUrl || !apiKey || projectIds.length === 0) {
            this.showError('設定エラー: APIの設定情報が不足しています');
            this.showLoading(false);
            return;
        }
        
        // 複数プロジェクトから一括でユーザーを取得
        const fetchPromises = projectIds.map(projectId => {
            return fetch(`${apiBaseUrl}/projects/${projectId}/users?apiKey=${apiKey}`)
                .then(response => {
                    if (!response.ok) {
                        return { projectId, error: `${response.status} ${response.statusText}`, users: [] };
                    }
                    return response.json().then(users => ({ projectId, users, error: null }));
                })
                .catch(error => ({ projectId, error: error.message, users: [] }));
        });
        
        Promise.all(fetchPromises)
            .then(results => {
                // デバッグ情報を表示
                const debugInfo = document.createElement('div');
                debugInfo.className = 'bg-gray-100 p-4 mt-4 rounded overflow-auto text-xs';
                debugInfo.style.maxHeight = '300px';
                
                const safeApiKey = apiKey.substring(0, 5) + '...' + apiKey.substring(apiKey.length - 5);
                
                let html = `
                    <h3 class="font-bold mb-2">デバッグ情報:</h3>
                    <p>API URL: ${apiBaseUrl}</p>
                    <p>API Key: ${safeApiKey}</p>
                    <p>Project IDs: ${projectIds.join(', ')}</p>
                    <hr class="my-2">
                `;
                
                // 各プロジェクトのユーザー情報
                let allUsers = [];
                
                results.forEach(({ projectId, users, error }) => {
                    html += `<h4 class="font-bold mt-3">プロジェクト ${projectId}:</h4>`;
                    
                    if (error) {
                        html += `<p class="text-red-500">エラー: ${error}</p>`;
                    } else {
                        html += `<p>ユーザー数: ${users.length}人</p>`;
                        html += `<ul class="list-disc pl-5 mt-1">`;
                        users.forEach(user => {
                            const prefix = user.mailAddress.split('@')[0];
                            html += `<li>${user.name} (${user.mailAddress}) - ID: ${user.id} - Prefix: ${prefix}</li>`;
                        });
                        html += `</ul>`;
                        
                        // すべてのユーザーリストに追加
                        allUsers = allUsers.concat(users);
                    }
                });
                
                // ユニークユーザーを計算
                const uniqueUsers = this.removeDuplicateUsers(allUsers);
                
                html += `
                    <hr class="my-2">
                    <h4 class="font-bold mt-3">統合ユーザー情報:</h4>
                    <p>合計ユニークユーザー: ${uniqueUsers.length}人</p>
                    <hr class="my-2">
                    <p class="mt-2 font-bold">特定ユーザー検索:</p>
                    <p>akihiro.furuie: ${uniqueUsers.find(u => u.mailAddress.split('@')[0] === 'akihiro.furuie') ? '✅ 見つかりました' : '❌ 見つかりません'}</p>
                    <p>f.soda: ${uniqueUsers.find(u => u.mailAddress.split('@')[0] === 'f.soda') ? '✅ 見つかりました' : '❌ 見つかりません'}</p>
                `;
                
                debugInfo.innerHTML = html;
                
                // フォームに追加
                document.getElementById('login-form').appendChild(debugInfo);
                this.showLoading(false);
            })
            .catch(error => {
                this.showError(`デバッグモードエラー: ${error.message}`);
                this.showLoading(false);
            });
    }
    
    processUsers(users, loginId) {
        console.log(`ユーザー検索: "${loginId}"`);
        
        // 検索方法1: メールアドレスの@前と完全一致（オリジナルの方法）
        let user = users.find(u => u.mailAddress.split('@')[0] === loginId);
        
        // 検索方法2: 大文字小文字を区別しない比較
        if (!user) {
            user = users.find(u => u.mailAddress.split('@')[0].toLowerCase() === loginId.toLowerCase());
            if (user) console.log(`大文字小文字を区別しない検索で見つかりました: ${user.name}`);
        }
        
        // 検索方法3: メールアドレスに含まれる場合
        if (!user) {
            user = users.find(u => u.mailAddress.toLowerCase().includes(loginId.toLowerCase()));
            if (user) console.log(`メールアドレスに含まれる検索で見つかりました: ${user.name}`);
        }
        
        if (user) {
            console.log(`ユーザーが見つかりました: ${user.name} (ID: ${user.id})`);
            
            // ユーザー情報をセッションに保存
            sessionStorage.setItem('userId', user.id);
            sessionStorage.setItem('userName', user.name);
            
            // ユーザー固有の通知音を設定
            const soundPath = `/assets/sounds/usertones/${loginId.replace(/\./g, '_')}.mp3`;
            sessionStorage.setItem('userSound', soundPath);
            
            // ステータスページにリダイレクト (拡張子付き)
            window.location.href = 'status.html';
        } else {
            console.log(`ユーザー "${loginId}" は見つかりませんでした`);
            this.showError('ログインIDが一致しません。');
            this.showLoading(false);
        }
    }
    
    showError(message) {
        const errorElement = document.getElementById('error-message');
        if (errorElement) {
            errorElement.textContent = message;
            errorElement.classList.remove('hidden');
        }
        
        // ローディング表示を解除
        this.showLoading(false);
    }
    
    // ローディング表示
    showLoading(isLoading) {
        const loginButton = document.getElementById('login-button');
        if (loginButton) {
            if (isLoading) {
                loginButton.innerHTML = '<i class="bi bi-hourglass-split mr-3"></i>ログイン中...';
                loginButton.disabled = true;
            } else {
                loginButton.innerHTML = '<i class="bi bi-box-arrow-in-right mr-3"></i>ログイン';
                loginButton.disabled = false;
            }
        }
    }
}

// ページ読み込み時にログインハンドラーを初期化
document.addEventListener('DOMContentLoaded', () => {
    window.loginHandler = new LoginHandler();
});