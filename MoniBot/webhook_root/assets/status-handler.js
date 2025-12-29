// status-handler.js - ウェブフックイベントとステータス更新を処理

class StatusHandler {
    constructor() {
        // 状態管理
        this.isPresent = false;
        this.userId = sessionStorage.getItem('userId');
        this.userName = sessionStorage.getItem('userName');
        this.statusEventSource = null;
        this.ticketList = [];
        this.statusIssueId = sessionStorage.getItem('statusIssueId');
        this.teamList = []; // ユーザーのチーム/カテゴリーリスト
        
        // Backlogから取得したステータスID
        this.statusIds = {
            present: null, // 在席ID（Backlogから取得）
            absent: null,  // 不在ID（Backlogから取得）
            processing: null, // 処理中ID（Backlogから取得）
            completed: null,  // 完了ID（Backlogから取得）
            return: null      // 差戻ID（Backlogから取得）
        };
        
        // デフォルト設定（config.jsが読み込めない場合のフォールバック）
        this.defaultConfig = {
            apiBaseUrl: "https://oasis-inn.backlog.com/api/v2",
            apiKey: "rc57YrOQFnfP11Rde8rcnV1Wj9DxKfaahjKngY6HMNNgYJS2yfCmbpkSvmCHpvmz",
            adminApiKey: "rc57YrOQFnfP11Rde8rcnV1Wj9DxKfaahjKngY6HMNNgYJS2yfCmbpkSvmCHpvmz",
            projectIds: {
                staff: "601236",
                billing: "601233"
            }
        };
        
        // DOM要素
        this.statusLabel = document.getElementById('status-label');
        this.statusToggle = document.getElementById('toggle-status');
        this.ticketListElement = document.getElementById('ticket-list');
        
        // 初期化
        this.init();
    }
    
    // 設定を取得する補助メソッド
    getConfig(path, defaultValue) {
        const keys = path.split('.');
        let value = window.appConfig || {};
        
        try {
            for (const key of keys) {
                value = value[key];
                if (value === undefined) {
                    // window.appConfigから取得できない場合はデフォルト設定を使用
                    let defaultVal = this.defaultConfig;
                    for (const k of keys) {
                        defaultVal = defaultVal[k];
                        if (defaultVal === undefined) return defaultValue;
                    }
                    return defaultVal;
                }
            }
            return value;
        } catch (error) {
            console.warn(`設定パス ${path} の取得に失敗しました:`, error);
            return defaultValue;
        }
    }

    async init() {
        console.log("StatusHandlerを初期化中...");
        console.log("設定情報:", {
            appConfig: window.appConfig || 'undefined',
            sessionStorage: {
                userId: this.userId,
                userName: this.userName,
                statusIssueId: this.statusIssueId
            }
        });
        
        // config.jsから直接ステータスIDをロード
        if (window.appConfig && window.appConfig.statusIds) {
            // 全てのIDを数値型に変換
            Object.keys(window.appConfig.statusIds).forEach(key => {
                if (this.statusIds.hasOwnProperty(key)) {
                    this.statusIds[key] = parseInt(window.appConfig.statusIds[key]);
                }
            });
            console.log("config.jsからロードしたステータスID:", this.statusIds);
        }
        
        // statusIssueIdがない場合は、APIから取得を試みる
        if (!this.statusIssueId) {
            console.log("ステータスチケットIDが見つかりません。APIから取得を試みます...");
            await this.fetchStatusIssueId();
        }
        
        // ステータスIDをBacklogから取得
        await this.fetchStatusDefinitions();
        
        // 初期状態を設定
        this.updateUserInfo();
        
        // ストレージからチケットデータを復元
        const savedTickets = sessionStorage.getItem('userTickets');
        if (savedTickets) {
            try {
                this.ticketList = JSON.parse(savedTickets);
                console.log("セッションストレージからチケットを復元:", this.ticketList.length, "件");
            } catch (error) {
                console.error("チケットデータの復元に失敗:", error);
                this.ticketList = [];
            }
        }
        
        // 保存されたチケットがなく、ユーザーIDがある場合は最新のチケットを取得
        if ((!this.ticketList || this.ticketList.length === 0) && this.userId) {
            console.log("保存されたチケットがないため、APIから取得を試みます");
            this.refreshTickets();
        } else {
            // 保存されたチケットの表示を更新
            this.updateTicketDisplay();
        }
        
        // イベントリスナーを設定
        this.setupToggleListener();
        this.setupTicketActions();
        this.setupLogoutHandler();
        this.setupMuteToggle(); // ミュートボタン機能を追加
        
        // ユーザーがログイン済みならSSEに接続
        if (this.userId) {
            this.connectEventSource();
        }

        // リロード警告を設定（ブラウザの仕様により、カスタムメッセージは表示されない場合があります）
        window.addEventListener('beforeunload', (event) => {
            // チケットがある場合のみ警告を表示
            if (this.ticketList && this.ticketList.length > 0) {
                // 標準的なブラウザの確認ダイアログを表示
                event.preventDefault();
                // カスタムメッセージ（多くのモダンブラウザでは無視され、ブラウザ標準のメッセージが表示されます）
                event.returnValue = 'ページをリロードすると表示中のチケットが消えてしまいます。続けますか？';
                return event.returnValue;
            }
        });        
    }
    
    // Backlogからステータス定義を取得
    async fetchStatusDefinitions() {
        const apiBaseUrl = this.getConfig('apiBaseUrl');
        const apiKey = this.getConfig('apiKey');
        const staffProjectId = this.getConfig('projectIds.staff');
        
        try {
            console.log("プロジェクトのステータス定義を取得中...");
            
            const response = await fetch(`${apiBaseUrl}/projects/${staffProjectId}/statuses?apiKey=${apiKey}`);
            
            if (!response.ok) {
                throw new Error(`API呼び出しエラー: ${response.status} ${response.statusText}`);
            }
            
            const statuses = await response.json();
            console.log("取得したステータス定義:", statuses);
            
            // ステータス名に基づいてIDをマッピング
            statuses.forEach(status => {
                if (status.name === '在席') this.statusIds.present = parseInt(status.id);
                else if (status.name === '不在') this.statusIds.absent = parseInt(status.id);
                else if (status.name === '処理中') this.statusIds.processing = parseInt(status.id);
                else if (status.name === '完了') this.statusIds.completed = parseInt(status.id);
                else if (status.name === '差戻') this.statusIds.return = parseInt(status.id);
            });
            
            console.log("マッピングされたステータスID:", this.statusIds);
            
            // 必須のステータスが見つからない場合はconfig.jsの値を使用
            if (!this.statusIds.present && window.appConfig && window.appConfig.statusIds && window.appConfig.statusIds.present) {
                this.statusIds.present = parseInt(window.appConfig.statusIds.present);
            }
            if (!this.statusIds.absent && window.appConfig && window.appConfig.statusIds && window.appConfig.statusIds.absent) {
                this.statusIds.absent = parseInt(window.appConfig.statusIds.absent);
            }
            
            // それでも見つからない場合はデフォルト値を設定
            if (!this.statusIds.present) this.statusIds.present = 3; // 仮のID
            if (!this.statusIds.absent) this.statusIds.absent = 4;   // 仮のID
            if (!this.statusIds.processing) this.statusIds.processing = 2; // 仮のID
            if (!this.statusIds.completed) this.statusIds.completed = 3;   // 仮のID
            if (!this.statusIds.return) this.statusIds.return = 4;         // 仮のID
            
            return true;
        } catch (error) {
            console.error("ステータス定義取得エラー:", error);
            // エラー時はconfig.jsの値を使用
            if (window.appConfig && window.appConfig.statusIds) {
                this.statusIds = {
                    present: parseInt(window.appConfig.statusIds.present || 3),
                    absent: parseInt(window.appConfig.statusIds.absent || 4),
                    processing: parseInt(window.appConfig.statusIds.processing || 2),
                    completed: parseInt(window.appConfig.statusIds.completed || 3),
                    return: parseInt(window.appConfig.statusIds.return || 4)
                };
                console.log("config.jsから読み込んだステータスID:", this.statusIds);
                return true;
            }
            // config.jsも利用できない場合はデフォルト値を設定
            this.statusIds = {
                present: 3,
                absent: 4,
                processing: 2,
                completed: 3,
                return: 4
            };
            return false;
        }
    }

    // ミュートボタンの機能
    setupMuteToggle() {
        const muteButton = document.getElementById('mute-toggle');
        if (muteButton) {
            // セッションからミュート状態を復元
            const isMuted = sessionStorage.getItem('isMuted') === 'true';
            this.updateMuteButtonState(isMuted);
            
            // ミュートボタンのクリックイベント
            muteButton.addEventListener('click', () => {
                const newMuteState = !this.isMuted;
                this.isMuted = newMuteState;
                sessionStorage.setItem('isMuted', newMuteState);
                this.updateMuteButtonState(newMuteState);
                
                // 通知を表示
                if (newMuteState) {
                    this.showNotification('通知音', 'ミュートにしました');
                } else {
                    // ミュート解除時は音を鳴らす
                    this.playTestSound();
                    this.showNotification('通知音', 'オンにしました');
                }
            });
        }
    }

    // テスト用の音声再生（ミュート解除時に使用）
    playTestSound() {
        // ミュートを一時的に無視して、必ず音を鳴らす
        const originalMuteState = this.isMuted;
        this.isMuted = false;
        
        try {
            this.playNotificationSound();
            
            // 元のミュート状態を復元（実際にはfalseになるはず）
            this.isMuted = originalMuteState;
        } catch (error) {
            console.error("テスト音声の再生に失敗しました:", error);
            // 元のミュート状態を復元
            this.isMuted = originalMuteState;
        }
    }

    // ミュートボタンの状態を更新
    updateMuteButtonState(isMuted) {
        const muteButton = document.getElementById('mute-toggle');
        if (muteButton) {
            this.isMuted = isMuted;
            // アイコンを更新
            const icon = muteButton.querySelector('i');
            if (icon) {
                if (isMuted) {
                    icon.className = 'bi bi-volume-mute';
                } else {
                    icon.className = 'bi bi-volume-up';
                }
            }
        }
    }

    // ログアウトボタンのイベントハンドラを設定
    setupLogoutHandler() {
        const logoutButton = document.getElementById('logout-button');
        if (logoutButton) {
            logoutButton.addEventListener('click', () => {
                // 確認ダイアログを表示
                this.showConfirmationDialog(
                    'ログアウト確認', 
                    'ログアウトしますか？',
                    () => {
                        // ユーザーがYESを選択した場合の処理
                        sessionStorage.clear();
                        window.location.href = '/';
                    },
                    () => {
                        // ユーザーがNOを選択した場合の処理
                        console.log("ログアウトをキャンセルしました");
                    }
                );
            });
        }
    }

    // 確認ダイアログを表示する関数
    showConfirmationDialog(title, message, onConfirm, onCancel) {
        // すでに表示されているモーダルがあれば削除
        const existingModal = document.getElementById('confirmation-dialog');
        if (existingModal) {
            existingModal.remove();
        }
        
        // モーダルの作成
        const modal = document.createElement('div');
        modal.id = 'confirmation-dialog';
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        
        // モーダルの内容
        modal.innerHTML = `
            <div class="bg-white rounded-lg p-6 max-w-md w-full">
                <h3 class="text-xl font-bold mb-4">${title}</h3>
                <p class="mb-6">${message}</p>
                <div class="flex justify-end space-x-4">
                    <button id="confirm-no" class="px-4 py-2 bg-gray-300 hover:bg-gray-400 rounded">いいえ</button>
                    <button id="confirm-yes" class="px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded">はい</button>
                </div>
            </div>
        `;
        
        // ボディに追加
        document.body.appendChild(modal);
        
        // ボタンのイベントリスナー
        document.getElementById('confirm-yes').addEventListener('click', () => {
            modal.remove();
            if (onConfirm) onConfirm();
        });
        
        document.getElementById('confirm-no').addEventListener('click', () => {
            modal.remove();
            if (onCancel) onCancel();
        });
        
        // モーダル外をクリックした場合もキャンセル扱い
        modal.addEventListener('click', (event) => {
            if (event.target === modal) {
                modal.remove();
                if (onCancel) onCancel();
            }
        });
    }

    // ユーザーの在席状態課題IDを取得
    async fetchStatusIssueId() {
        if (!this.userId) {
            console.warn("ユーザーIDが不明なため、ステータス課題IDを取得できません");
            return null;
        }
        
        const apiBaseUrl = this.getConfig('apiBaseUrl');
        const apiKey = this.getConfig('apiKey');
        const staffProjectId = this.getConfig('projectIds.staff');
        
        try {
            console.log("在席状態チケットの検索中...");
            console.log("検索パラメータ:", {
                apiBaseUrl,
                apiKey: apiKey ? "設定あり" : "未設定",
                staffProjectId,
                userId: this.userId
            });
            
            const params = new URLSearchParams({
                apiKey: apiKey,
                "projectId[]": staffProjectId,
                "assigneeId[]": this.userId
            });
            
            const response = await fetch(`${apiBaseUrl}/issues?${params.toString()}`);
            
            if (!response.ok) {
                throw new Error(`API呼び出しエラー: ${response.status} ${response.statusText}`);
            }
            
            const issues = await response.json();
            console.log("取得したチケット:", issues);
            
            if (issues && issues.length > 0) {
                // 最初のチケットをユーザーのステータスチケットと見なす
                const statusIssue = issues[0];
                this.statusIssueId = statusIssue.id;
                sessionStorage.setItem('statusIssueId', statusIssue.id);
                console.log(`ステータスチケットID ${statusIssue.id} を保存しました`);
                
                // カテゴリー（チーム）情報があれば保存
                if (statusIssue.category && statusIssue.category.length > 0) {
                    this.teamList = statusIssue.category;
                    console.log("カテゴリー/チーム情報を取得:", this.teamList);
                }
                
                // チケットの現在のステータスを取得
                if (statusIssue.status) {
                    // 在席ステータスIDを取得
                    if (statusIssue.status.name === '在席') {
                        this.statusIds.present = parseInt(statusIssue.status.id);
                    } else if (statusIssue.status.name === '不在') {
                        this.statusIds.absent = parseInt(statusIssue.status.id);
                    }
                    
                    console.log("チケットから取得したステータスID:", {
                        present: this.statusIds.present,
                        absent: this.statusIds.absent
                    });
                    
                    // チケットのステータスに基づいてUIを更新
                    const isPresent = statusIssue.status.name === '在席';
                    this.updateStatusDisplay(isPresent, false); // APIは呼び出さない
                }
                
                return statusIssue.id;
            } else {
                console.warn("ユーザーのステータスチケットが見つかりませんでした");
                return null;
            }
        } catch (error) {
            console.error("ステータスチケットID取得エラー:", error);
            return null;
        }
    }
    
    updateUserInfo() {
        // ユーザー名表示
        const userNameEl = document.getElementById('user-name');
        if (userNameEl && this.userName) {
            userNameEl.textContent = this.userName;
        }
        
        // チーム/カテゴリーの表示
        this.updateTeamList();
        
        // ステータス情報の更新
        if (this.statusIssueId) {
            // ステータスチケットIDがある場合はBacklogから最新状態を取得
            this.fetchCurrentStatus();
        } else {
            // 取得に失敗した場合はセッションのステータスを使用
            const savedStatus = sessionStorage.getItem('userStatus') || 'absent';
            this.updateStatusDisplay(savedStatus === 'present', false);
        }
    }
    
    // チームリストを表示する
    updateTeamList() {
        const teamListEl = document.querySelector('.team-list');
        if (!teamListEl) return;
        
        // チームリストをクリア
        teamListEl.innerHTML = '';
        
        // チーム情報がない場合
        if (!this.teamList || this.teamList.length === 0) {
            const noTeamItem = document.createElement('li');
            noTeamItem.className = 'text-sm text-gray-500';
            noTeamItem.textContent = 'チーム情報がありません。';
            teamListEl.appendChild(noTeamItem);
            return;
        }
        
        // 各チームを表示（完全に透過に変更）
        this.teamList.forEach(category => {
            const teamItem = document.createElement('li');
            
            // グレー背景を削除して透過に（必要に応じて細い境界線を追加）
            teamItem.className = 'text-sm text-gray-700 rounded px-2 py-1 mr-2 mb-1';
            // teamItem.style.border = '1px solid #e5e7eb';
            
            teamItem.textContent = category.name;
            teamListEl.appendChild(teamItem);
        });
    }
    
    // Backlogから現在のステータスを取得
    async fetchCurrentStatus() {
        if (!this.statusIssueId) {
            console.warn("ステータスチケットIDがないため、現在のステータスを取得できません");
            return;
        }
        
        const apiBaseUrl = this.getConfig('apiBaseUrl');
        const apiKey = this.getConfig('apiKey');
        
        try {
            console.log(`ステータスチケット ${this.statusIssueId} の状態を取得中...`);
            
            const response = await fetch(`${apiBaseUrl}/issues/${this.statusIssueId}?apiKey=${apiKey}`);
            
            if (!response.ok) {
                throw new Error(`API呼び出しエラー: ${response.status} ${response.statusText}`);
            }
            
            const issue = await response.json();
            console.log("取得したステータス:", issue.status);
            
            // カテゴリー（チーム）情報を更新
            if (issue.category && issue.category.length > 0) {
                this.teamList = issue.category;
                this.updateTeamList();
                console.log("カテゴリー/チーム情報を更新:", this.teamList);
            }
            
            if (issue && issue.status) {
                // ステータス名に基づいてUIを更新
                const isPresent = issue.status.name === '在席';
                
                // 現在のステータスIDを保存
                if (isPresent) {
                    this.statusIds.present = parseInt(issue.status.id);
                } else {
                    this.statusIds.absent = parseInt(issue.status.id);
                }
                
                this.updateStatusDisplay(isPresent, false); // APIは呼び出さない
            }
        } catch (error) {
            console.error("現在のステータス取得エラー:", error);
        }
    }
    
    updateStatusDisplay(isPresent, updateBacklog = true) {
        // 状態に基づいてUI要素を更新
        this.isPresent = isPresent;
        this.statusToggle.checked = isPresent;
        
        const statusCard = document.getElementById('status-card');
        const statusDot = document.getElementById('toggle-dot');
        
        if (isPresent) {
            statusCard.classList.remove('bg-red-100');
            statusCard.classList.add('bg-green-100');
            this.statusLabel.textContent = '在席';
            this.statusLabel.classList.remove('text-red-700');
            this.statusLabel.classList.add('text-green-700');
            statusDot.classList.add('translate-x-8');
            statusDot.classList.remove('translate-x-0');
        } else {
            statusCard.classList.remove('bg-green-100');
            statusCard.classList.add('bg-red-100');
            this.statusLabel.textContent = '不在';
            this.statusLabel.classList.remove('text-green-700');
            this.statusLabel.classList.add('text-red-700');
            statusDot.classList.remove('translate-x-8');
            statusDot.classList.add('translate-x-0');
        }
        
        // ステータスをセッションに保存
        sessionStorage.setItem('userStatus', isPresent ? 'present' : 'absent');
        
        // ユーザーがログイン済みで、バックエンド更新が要求された場合
        if (this.userId && updateBacklog) {
            this.updateBacklogStatus(isPresent);
        }
    }
    
    updateBacklogStatus(isPresent) {
        // 設定を取得
        const apiBaseUrl = this.getConfig('apiBaseUrl');
        const adminApiKey = this.getConfig('adminApiKey');
        
        // statusIssueIdがなければfetchStatusIssueIdを呼び出す
        if (!this.statusIssueId) {
            this.fetchStatusIssueId().then(issueId => {
                if (issueId) {
                    this.updateBacklogStatus(isPresent);
                } else {
                    console.warn('ステータスチケットIDを取得できないため、Backlogステータスを更新できません');
                    this.showNotification('警告', 'ステータスの更新ができませんでした。ステータスIDが不明です。');
                }
            });
            return;
        }
        
        // ステータスIDを決定
        const statusId = isPresent ? this.statusIds.present : this.statusIds.absent;
        
        console.log("Backlogステータス更新:", {
            apiBaseUrl,
            adminApiKey: adminApiKey ? "設定あり" : "未設定",
            statusIssueId: this.statusIssueId,
            isPresent,
            statusId
        });
        
        // ステータスIDが見つからない場合
        if (!statusId) {
            console.error("有効なステータスIDがありません。更新をスキップします。");
            this.showNotification('警告', 'ステータスの更新ができませんでした。ステータスIDが不明です。');
            return;
        }
        
        // APIを通じてステータスを更新
        fetch(`${apiBaseUrl}/issues/${this.statusIssueId}?apiKey=${adminApiKey}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ statusId: statusId })
        })
        .then(response => {
            if (!response.ok) {
                // エラーレスポンスの詳細を取得
                return response.text().then(text => {
                    throw new Error(`ステータス更新に失敗しました (${response.status}): ${text}`);
                });
            }
            console.log('Backlogステータスが正常に更新されました');
            
            // 新しいステータスに基づいてチケット表示を更新
            if (isPresent) {
                this.refreshTickets(); // 在席時にチケットを表示
            }
        })
        .catch(error => {
            console.error('ステータス更新エラー:', error);
            // エラー内容を表示
            this.showNotification('エラー', `ステータス更新に失敗しました: ${error.message}`);
        });
    }
    
    setupToggleListener() {
        // 在席/不在切り替えスイッチ
        this.statusToggle.addEventListener('change', () => {
            this.updateStatusDisplay(this.statusToggle.checked, true);
        });
    }
    
    connectEventSource() {
        // リアルタイム更新用にSSEに接続
        this.statusEventSource = new EventSource('/events');
        
        // 新しいウェブフックイベント処理
        this.statusEventSource.addEventListener('webhook', event => {
            const eventData = JSON.parse(event.data);
            
            // チケット関連ウェブフックを処理
            if (eventData.is_ticket && this.isPresent) {
                this.processTicketEvent(eventData);
            }
        });
        
        // 接続処理
        this.statusEventSource.addEventListener('connected', event => {
            console.log('イベントストリームに接続しました');
        });
        
        // エラー処理
        this.statusEventSource.onerror = () => {
            console.error('SSE接続エラー');
        };
    }
    
    processTicketEvent(event) {
        console.log('イベント全体:', event);
        console.log('イベントデータ:', event.data);
        
        // このチケットが現在のユーザーに割り当てられているか確認
        if (event.data && event.data.assigneeId && event.data.assigneeId.toString() === this.userId) {
            console.log('ユーザーIDが一致しました！チケットを追加します');
            
            // ユーザー通知を積極的に行う
            // 1. 通知音を再生
            console.log("通知音再生を試みます");
            this.playNotificationSound();
            
            // 2. 視覚的通知も生成（音が鳴らなかった場合のバックアップ）
            setTimeout(() => this.createVisualNotification(), 100);
            
            // 3. チケットリストに追加して表示を更新
            this.ticketList.push(event.data);
            this.updateTicketDisplay();

            // チケットデータをセッションストレージに保存
            sessionStorage.setItem('userTickets', JSON.stringify(this.ticketList));

            // 4. タブが非アクティブの場合、タイトルを点滅させる
            this.flashPageTitle("新しいチケットが届きました");
        } else {
            console.log('ユーザーIDが一致しません:',
                'イベントのassigneeId=', event.data?.assigneeId,
                'this.userId=', this.userId);
        }
    }
    
    // ページタイトルを点滅させる
    flashPageTitle(message) {
        if (document.hidden) {
            // 元のタイトルを保存
            if (!this.originalTitle) {
                this.originalTitle = document.title;
            }
            
            // タイトル点滅用変数
            if (!this.titleFlashing) {
                this.titleFlashing = true;
                let flashCount = 0;
                const maxFlashes = 10; // 最大点滅回数
                
                // タイトル点滅インターバル
                this.titleInterval = setInterval(() => {
                    document.title = document.title === this.originalTitle ? message : this.originalTitle;
                    flashCount++;
                    
                    // 最大回数に達したらタイトル点滅を停止
                    if (flashCount >= maxFlashes * 2) {
                        clearInterval(this.titleInterval);
                        document.title = this.originalTitle;
                        this.titleFlashing = false;
                    }
                }, 1000); // 1秒ごとに切り替え
                
                // タブがアクティブになったら点滅を止める
                document.addEventListener('visibilitychange', () => {
                    if (!document.hidden && this.titleFlashing) {
                        clearInterval(this.titleInterval);
                        document.title = this.originalTitle;
                        this.titleFlashing = false;
                    }
                });
            }
        }
    }
    
    updateTicketDisplay() {
        // 現在の表示をクリア
        this.ticketListElement.innerHTML = '';
        
        if (this.ticketList.length === 0) {
            this.ticketListElement.innerHTML = `
                <div class="bg-gray-50 shadow-md rounded-lg p-6 mb-6 text-center">
                    <p class="text-gray-500 text-lg">現在割り当てられているチケットはありません。</p>
                </div>
            `;
            return;
        }
        
        // 各チケットを表示に追加
        this.ticketList.forEach(ticket => {
            // 説明からデータを抽出
            const ticketInfo = this.parseTicketDescription(ticket.description);
            
            const ticketElement = document.createElement('div');
            ticketElement.className = 'bg-gray-50 shadow-md rounded-lg p-6 mb-6';
            ticketElement.innerHTML = `
                <h6 class="text-3xl font-bold mb-4">${ticketInfo.hospitalName || '不明'} - 患者ID:${ticketInfo.patientId || '不明'}</h6>
                <h6 class="text-2xl font-bold mb-4"><i class="bi bi-clock mr-2"></i>取得時間 ${ticketInfo.acquisitionTime || '不明'}</h6>

                <div class="flex items-center justify-between mt-5">
                    <div class="text-xl mb-4 mr-4 space-y-5 flex-grow">
                        <p>電子カルテ名: ${ticketInfo.ehrName || '不明'}</p>
                        <p>診察日: ${ticketInfo.consultationDate || '不明'}</p>
                    </div>

                    <div class="flex justify-end items-end">
                        <button data-ticket-id="${ticket.id}" class="complete-button bg-green-500 text-white py-16 px-16 rounded-lg shadow-lg text-3xl lg:text-5xl mr-8 whitespace-nowrap">
                            <i class="bi bi-check-circle mr-4"></i>完了
                        </button>
                        <button data-ticket-id="${ticket.id}" class="return-button bg-red-500 text-white py-4 px-8 rounded-lg shadow-md text-lg whitespace-nowrap">
                            <i class="bi bi-arrow-counterclockwise mr-2"></i>差戻
                        </button>
                    </div>
                </div>
            `;
            this.ticketListElement.appendChild(ticketElement);
        });

    // チケットデータをセッションストレージに保存
    sessionStorage.setItem('userTickets', JSON.stringify(this.ticketList));
    }
    
    parseTicketDescription(description) {
        const lines = description ? description.split('\n') : [];
        const result = {};
        
        lines.forEach(line => {
            const parts = line.split(':');
            if (parts.length >= 2) {
                const key = parts[0].trim();
                const value = parts.slice(1).join(':').trim();
                
                switch (key) {
                    case '電子カルテ名': result.ehrName = value; break;
                    case '病院名': result.hospitalName = value; break;
                    case '患者ID': result.patientId = value; break;
                    case '診察日': result.consultationDate = value; break;
                    case '取得時間': result.acquisitionTime = value; break;
                }
            }
        });
        
        return result;
    }
    
    setupTicketActions() {
        // チケットボタンのイベント委任
        this.ticketListElement.addEventListener('click', event => {
            const target = event.target.closest('button');
            if (!target) return;
            
            const ticketId = target.dataset.ticketId;
            if (!ticketId) return;
            
            if (target.classList.contains('complete-button')) {
                this.completeTicket(ticketId);
            } else if (target.classList.contains('return-button')) {
                this.returnTicket(ticketId);
            }
        });
    }
    
    completeTicket(ticketId) {
        // 設定を取得
        const apiBaseUrl = this.getConfig('apiBaseUrl');
        const adminApiKey = this.getConfig('adminApiKey');
        const statusIdCompleted = this.statusIds.completed;
        
        console.log("チケット完了処理:", {
            apiBaseUrl,
            adminApiKey: adminApiKey ? "設定あり" : "未設定",
            ticketId,
            statusIdCompleted
        });
        
        if (!statusIdCompleted) {
            console.error("完了ステータスIDが見つかりません");
            this.showNotification('エラー', '完了ステータスIDが見つかりません');
            return;
        }
        
        // 該当チケットの情報を取得
        const ticket = this.ticketList.find(t => t.id.toString() === ticketId);
        
        // チケット情報の解析
        let ticketSummary = ticketId;
        let ticketInfo = null;
        
        if (ticket) {
            ticketSummary = ticket.summary || ticketId;
            ticketInfo = this.parseTicketDescription(ticket.description);
        }
        
        // チケットステータスを更新
        fetch(`${apiBaseUrl}/issues/${ticketId}?apiKey=${adminApiKey}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ statusId: statusIdCompleted })
        })
        .then(response => {
            if (!response.ok) throw new Error('チケットの完了に失敗しました');
            
            // リストから削除して表示を更新
            this.ticketList = this.ticketList.filter(ticket => ticket.id.toString() !== ticketId);
            this.updateTicketDisplay();

            // 更新されたチケットリストを保存
            sessionStorage.setItem('userTickets', JSON.stringify(this.ticketList));            

            // 完了通知（チケットの件名を表示）
            this.showNotification('チケットを完了しました', ticketSummary);
        })
        .catch(error => {
            console.error('チケット完了エラー:', error);
            this.showNotification('エラー', 'チケットの完了処理に失敗しました');
        });
    }

    returnTicket(ticketId) {
        if (!confirm('差し戻ししますか？')) return;
        
        // 処理中モーダルを表示
        this.showProcessingModal();
        
        // 設定を取得
        const apiBaseUrl = this.getConfig('apiBaseUrl');
        const adminApiKey = this.getConfig('adminApiKey');
        const statusIdReturn = this.statusIds.return;
        const statusIdAbsent = this.statusIds.absent;
        
        console.log("チケット差戻処理:", {
            apiBaseUrl,
            adminApiKey: adminApiKey ? "設定あり" : "未設定",
            ticketId,
            statusIssueId: this.statusIssueId,
            statusIdReturn,
            statusIdAbsent
        });
        
        if (!statusIdReturn || !statusIdAbsent) {
            console.error("差戻または不在ステータスIDが見つかりません");
            this.hideProcessingModal();
            this.showNotification('エラー', '差戻または不在ステータスIDが見つかりません');
            return;
        }
        
        // チケットを差戻しし、ユーザーを不在に設定
        Promise.all([
            // チケットステータスを更新
            fetch(`${apiBaseUrl}/issues/${ticketId}?apiKey=${adminApiKey}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ statusId: statusIdReturn })
            }),
            // ユーザーステータスを更新
            fetch(`${apiBaseUrl}/issues/${this.statusIssueId}?apiKey=${adminApiKey}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ statusId: statusIdAbsent })
            })
        ])
        .then(responses => {
            if (!responses.every(r => r.ok)) {
                throw new Error('チケットの差戻しに失敗しました');
            }
            
            // 5秒待機
            return new Promise(resolve => setTimeout(resolve, 5000));
        })
        .then(() => {
            // UIを更新
            this.updateStatusDisplay(false, false);
            
            // チケットリストから差し戻したチケットを削除
            this.ticketList = this.ticketList.filter(ticket => ticket.id.toString() !== ticketId);
            this.updateTicketDisplay();
            
            // 重要: セッションストレージも更新
            sessionStorage.setItem('userTickets', JSON.stringify(this.ticketList));
            
            this.hideProcessingModal();
            
            // 差戻通知
            this.showNotification('チケットを差戻しました', `チケットID: ${ticketId}`);
        })
        .catch(error => {
            console.error('チケット差戻エラー:', error);
            this.hideProcessingModal();
            this.showNotification('エラー', '差戻処理中にエラーが発生しました');
        });
    }    

    showProcessingModal() {
        const modal = document.getElementById('processing-modal');
        if (modal) {
            modal.classList.remove('hidden');
            modal.style.display = 'flex';
        }
    }
    
    hideProcessingModal() {
        const modal = document.getElementById('processing-modal');
        if (modal) {
            modal.classList.add('hidden');
            modal.style.display = 'none';
        }
    }
    
    playNotificationSound() {
        console.log("通知音再生メソッドが呼び出されました"); 
        
        // ミュート状態なら何もしない
        if (this.isMuted) {
            console.log("通知音はミュートされています");
            return;
        }
    
        // オーディオコンテキストを使用して通知音を再生
        try {
            // オーディオコンテキストの初期化（シングルトンとして再利用）
            if (!this.audioContext) {
                // AudioContextはユーザー操作で起動する必要があるので事前に作成
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
                
                // 初回のみ起動しておく（ページの読み込み後に一度サスペンド状態になる場合がある）
                if (this.audioContext.state === 'suspended') {
                    this.audioContext.resume().then(() => {
                        console.log("AudioContext resumed successfully");
                    });
                }
                
                // オーディオファイルを事前にロード
                this.loadNotificationSound();
            }
            
            // すでに音源データがロードされていれば再生
            if (this.notificationBuffer) {
                this.playLoadedSound();
            } else {
                // まだロードされていない場合は読み込んでから再生
                this.loadNotificationSound().then(() => {
                    this.playLoadedSound();
                });
                
                // フォールバック: 通常のAudioも試みる
                const backupSound = new Audio('/assets/sounds/usertones/akihiro_furuie.mp3');
                backupSound.volume = 1.0;
                backupSound.play().catch(e => console.log("Backup playback failed:", e));
            }
        } catch (error) {
            console.error("音声処理中のエラー:", error);
            
            // フォールバック: 従来の方法も試す
            try {
                const fallbackSound = new Audio('/assets/sounds/usertones/akihiro_furuie.mp3');
                fallbackSound.volume = 1.0;
                fallbackSound.play().catch(e => {
                    console.log("Fallback playback failed:", e);
                    // 最終手段：CSSアニメーションで視覚的フィードバック
                    this.createVisualNotification();
                });
            } catch (finalError) {
                console.error("すべての通知方法が失敗しました:", finalError);
                // 視覚的フィードバック
                this.createVisualNotification();
            }
        }
    }
    
    // 通知音を事前にロードする
    async loadNotificationSound() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        
        if (this.notificationBuffer) {
            return Promise.resolve(); // すでにロード済み
        }
        
        try {
            // 音声ファイルをフェッチ
            const response = await fetch('/assets/sounds/usertones/akihiro_furuie.mp3');
            const arrayBuffer = await response.arrayBuffer();
            
            // AudioBufferに変換
            this.notificationBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
            console.log("通知音のロードに成功しました");
            return Promise.resolve();
        } catch (error) {
            console.error("通知音のロード中にエラーが発生しました:", error);
            return Promise.reject(error);
        }
    }
    
    // ロード済みの音を再生
    playLoadedSound() {
        if (!this.audioContext || !this.notificationBuffer) {
            console.error("オーディオコンテキストまたは音声バッファが利用できません");
            return;
        }
        
        // もし前の音がまだ再生中なら停止
        if (this.currentSound) {
            this.currentSound.stop();
        }
        
        try {
            // Resumeが必要な場合
            if (this.audioContext.state === 'suspended') {
                this.audioContext.resume();
            }
            
            // 音源を作成
            const source = this.audioContext.createBufferSource();
            source.buffer = this.notificationBuffer;
            
            // ゲインノードを作成して音量調整
            const gainNode = this.audioContext.createGain();
            gainNode.gain.value = 1.0; // 最大音量
            
            // 接続
            source.connect(gainNode);
            gainNode.connect(this.audioContext.destination);
            
            // 再生
            source.start(0);
            this.currentSound = source;
            
            console.log("通知音の再生に成功しました");
        } catch (error) {
            console.error("通知音の再生中にエラーが発生しました:", error);
            // 視覚的フィードバック
            this.createVisualNotification();
        }
    }
    
    // 音が出ない場合のための視覚的通知（代替手段）
    createVisualNotification() {
        // すでに視覚的通知が表示されている場合は何もしない
        if (document.getElementById('visual-notification')) {
            return;
        }
        
        // 視覚的な点滅効果を作成
        const notification = document.createElement('div');
        notification.id = 'visual-notification';
        notification.style.position = 'fixed';
        notification.style.top = '0';
        notification.style.left = '0';
        notification.style.width = '100%';
        notification.style.height = '100%';
        notification.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
        notification.style.zIndex = '9999';
        notification.style.pointerEvents = 'none'; // クリックをスルーさせる
        notification.style.animation = 'flash 0.5s 3'; // 3回点滅
        
        // アニメーションスタイルを追加
        const style = document.createElement('style');
        style.textContent = `
            @keyframes flash {
                0%, 100% { opacity: 0; }
                50% { opacity: 1; }
            }
        `;
        document.head.appendChild(style);
        
        // ページに追加
        document.body.appendChild(notification);
        
        // 1.5秒後に削除
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 1500);
    }
        
    refreshTickets() {
        // 現在のユーザーのチケットを読み込み
        if (!this.userId) return;
        
        const apiBaseUrl = this.getConfig('apiBaseUrl');
        const adminApiKey = this.getConfig('adminApiKey');
        const billingProjectId = this.getConfig('projectIds.billing');
        const statusIdProcessing = this.statusIds.processing;
        
        console.log("チケット更新:", {
            apiBaseUrl,
            adminApiKey: adminApiKey ? "設定あり" : "未設定",
            billingProjectId,
            statusIdProcessing
        });
        
        if (!statusIdProcessing) {
            console.warn("処理中ステータスIDが見つかりません");
            return;
        }
        
        // クエリパラメータを構築
        const params = new URLSearchParams({
            apiKey: adminApiKey,
            "projectId[]": billingProjectId,
            "assigneeId[]": this.userId,
            "statusId[]": statusIdProcessing,
            sort: "created",
            order: "asc"
        });
        
        // チケットを取得
        fetch(`${apiBaseUrl}/issues?${params.toString()}`)
            .then(response => response.json())
            .then(tickets => {
                this.ticketList = tickets;
                this.updateTicketDisplay();
            })
            .catch(error => {
                console.error('チケット取得エラー:', error);
                this.showNotification('エラー', 'チケット情報の取得に失敗しました');
            });
    }
    
    // 通知を表示
    showNotification(title, message) {
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-blue-500 text-white px-4 py-3 rounded-lg shadow-lg z-50 notification-popup';
        notification.style.animation = 'fadeIn 0.3s ease-in-out';
        
        notification.innerHTML = `
            <div class="flex items-center">
                <i class="bi bi-bell mr-2"></i>
                <div>
                    <p class="font-bold">${title}</p>
                    <p class="text-sm">${message}</p>
                </div>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // アニメーションスタイルを追加
        if (!document.querySelector('#notification-style')) {
            const style = document.createElement('style');
            style.id = 'notification-style';
            style.textContent = `
                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(-20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                .notification-popup {
                    pointer-events: none; /* iPadでのポップアップ問題を回避 */
                }
            `;
            document.head.appendChild(style);
        }
        
        // 5秒後に自動で消える
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.3s ease-in-out';
            setTimeout(() => notification.remove(), 300);
        }, 5000);
    }
    
    // ページがアンロードされるときのクリーンアップメソッド
    cleanup() {
        if (this.statusEventSource) {
            this.statusEventSource.close();
        }
    }
}

// ページ読み込み時に初期化
document.addEventListener('DOMContentLoaded', () => {
    window.statusHandler = new StatusHandler();
    
    // オーディオコンテキストを初期化するための操作処理
    const initAudio = () => {
        // AudioContextを作成して保存
        if (!window.statusHandler.audioContext) {
            window.statusHandler.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        }
        
        // オーディオを事前にロード
        window.statusHandler.loadNotificationSound()
            .then(() => console.log("初期音声のロードに成功しました"))
            .catch(error => console.error("初期音声のロード中にエラー:", error));
    };
    
    // ユーザーの操作（クリック）でオーディオを初期化
    document.body.addEventListener('click', function bodyClickHandler() {
        initAudio();
        // イベントリスナーを削除
        document.body.removeEventListener('click', bodyClickHandler);
    }, { once: true });
    
    // iPadのSafariなど一部のブラウザでは、ページ読み込み直後のタッチイベントにも対応
    document.body.addEventListener('touchstart', function touchHandler() {
        initAudio();
        // イベントリスナーを削除
        document.body.removeEventListener('touchstart', touchHandler);
    }, { once: true });
    
    // 5秒後に自動的にロード試行（バックグラウンドで準備）
    setTimeout(() => {
        // まだ初期化されていない場合のみ実行
        if (!window.statusHandler.audioContext) {
            initAudio();
        }
    }, 5000);
});

// ページアンロード時のクリーンアップ
window.addEventListener('beforeunload', () => {
    if (window.statusHandler) {
        window.statusHandler.cleanup();
    }
});