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
                    this.showNotification('通知音', 'オンにしました');
                }
            });
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
                // セッションストレージをクリア
                sessionStorage.clear();
                // ログインページにリダイレクト
                window.location.href = '/';
            });
        }
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
        // ユーザー情報を表示に反映
        if (this.userName) {
            document.getElementById('user-name').textContent = this.userName;
        }
        
        if (this.statusIssueId) {
            // ステータスチケットIDがある場合はBacklogから最新状態を取得
            this.fetchCurrentStatus();
        } else {
            // 取得に失敗した場合はセッションのステータスを使用
            const savedStatus = sessionStorage.getItem('userStatus') || 'absent';
            this.updateStatusDisplay(savedStatus === 'present', false);
        }
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
            } else {
                this.clearTickets(); // 不在時にチケットを非表示
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
            
            // 通知音を再生 - 必ず呼び出されるようにする
            console.log("通知音再生を試みます");
            this.playNotificationSound();
            
            // チケットリストに追加して表示を更新
            this.ticketList.push(event.data);
            this.updateTicketDisplay();
        } else {
            console.log('ユーザーIDが一致しません:',
                'イベントのassigneeId=', event.data?.assigneeId,
                'this.userId=', this.userId);
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
            
            // 完了通知
            this.showNotification('チケットを完了しました', `チケットID: ${ticketId}`);
        })
        .catch(error => {
            console.error('チケット完了エラー:', error);
            this.showNotification('エラー', 'チケットの完了処理に失敗しました');
        });
    }
    
    returnTicket(ticketId) {
        if (!confirm('差戻しますか？')) return;
        
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
            this.ticketList = this.ticketList.filter(ticket => ticket.id.toString() !== ticketId);
            this.updateTicketDisplay();
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
        console.log("通知音再生メソッドが呼び出されました"); // デバッグログを追加
        
        // ミュート状態なら何もしない
        if (this.isMuted) {
            console.log("通知音はミュートされています");
            return;
        }
    
        // 通知音を再生
        try {
            const userSound = new Audio('/assets/sounds/usertones/akihiro_furuie.mp3'); // 直接パスを指定
            console.log("音声ファイル作成: ", userSound);
            
            // 音量を最大に設定
            userSound.volume = 1.0;
            
            // ユーザー操作が必要なケースに対応するため、クリックイベントをトリガー
            document.addEventListener('click', function clickHandler() {
                userSound.play()
                    .then(() => console.log("音声再生成功"))
                    .catch(error => console.error("音声再生エラー:", error));
                document.removeEventListener('click', clickHandler);
            }, { once: true });
            
            // 直接再生も試す
            const playPromise = userSound.play();
            if (playPromise !== undefined) {
                playPromise
                    .then(() => console.log("音声再生成功"))
                    .catch(error => {
                        console.error("音声再生エラー:", error);
                        if (error.name === "NotAllowedError") {
                            console.log("ページ上でクリックして音声を有効にしてください");
                            alert("通知音を再生するには、ページ上で一度クリックしてください");
                        }
                    });
            }
        } catch (error) {
            console.error("音声処理中のエラー:", error);
        }
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
    
    clearTickets() {
        // ユーザーが不在の場合はチケットリストをクリア
        this.ticketList = [];
        this.updateTicketDisplay();
    }
    
    // 通知を表示
    showNotification(title, message) {
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-blue-500 text-white px-4 py-3 rounded-lg shadow-lg z-50';
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
    
    // ユーザーインタラクションを待機
    document.body.addEventListener('click', function bodyClickHandler() {
        // 音声を事前にロード
        const preloadSound = new Audio('/assets/sounds/usertones/akihiro_furuie.mp3');
        preloadSound.volume = 0.1;  // 音量を小さく
        preloadSound.play()
            .then(() => console.log("初期音声再生成功"))
            .catch(error => console.error("初期音声再生エラー:", error));
        
        // イベントリスナーを削除
        document.body.removeEventListener('click', bodyClickHandler);
    }, { once: true });
    
    ユーザーに一度クリックを促す通知
    setTimeout(() => {
        const notification = document.createElement('div');
        notification.className = 'fixed top-4 right-4 bg-blue-500 text-white px-4 py-3 rounded-lg shadow-lg z-50';
        notification.style.animation = 'fadeIn 0.3s ease-in-out';
        
        notification.innerHTML = `
            <div class="flex items-center">
                <i class="bi bi-bell mr-2"></i>
                <div>
                    <p class="font-bold">通知音を有効にするには</p>
                    <p class="text-sm">ページのどこかをクリックしてください</p>
                </div>
            </div>
        `;
        
        document.body.appendChild(notification);
        
        // 10秒後に自動で消える
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transition = 'opacity 0.3s ease-in-out';
            setTimeout(() => notification.remove(), 300);
        }, 10000);
    }, 2000);
});

// ページアンロード時のクリーンアップ
window.addEventListener('beforeunload', () => {
    if (window.statusHandler) {
        window.statusHandler.cleanup();
    }
});

