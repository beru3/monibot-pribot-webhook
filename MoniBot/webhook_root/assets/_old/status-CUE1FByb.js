import "./common-dBFvgQiY.js";

// 設定ファイルから値を取得
let u = null, m = null, r = null, c = null;
let webhookEventSource = null;

document.addEventListener("DOMContentLoaded", async () => {
    console.log(sessionStorage);
    h();
    D();
    R();
    $();
    M();
    setupWebhookListener(); // WebhookリスナーのSEE接続を設定
    await E();
    await f();
    setInterval(f, 6e4);
});

function D() {
    sessionStorage.getItem("userId");
    const t = sessionStorage.getItem("userName");
    h();
    document.getElementById("user-name").textContent = t;
    const s = document.getElementById("status-card"),
        e = document.getElementById("status-label");
    s.classList.add("bg-red-100");
    e.textContent = "不在";
    e.classList.add("text-red-700");
}

function R() {
    const t = document.getElementById("toggle-status"),
        s = document.getElementById("status-card"),
        e = document.getElementById("status-label"),
        n = document.getElementById("toggle-dot");
    
    t.addEventListener("change", async () => {
        // 設定ファイルからステータスIDを取得
        const statusIdPresent = window.appConfig ? window.appConfig.statusIds.present : 276518;
        const statusIdAbsent = window.appConfig ? window.appConfig.statusIds.absent : 276517;
        
        const o = t.checked ? statusIdPresent : statusIdAbsent,
              i = t.checked ? "在席" : "不在";
        
        if (t.checked ?
            g(s, e, n, "在席", "bg-green-100", "bg-red-100", "text-green-700", "text-red-700", "translate-x-8") :
            g(s, e, n, "不在", "bg-red-100", "bg-green-100", "text-red-700", "text-green-700", "translate-x-0"),
            u) {
            try {
                await p(u, o, !1);
                console.log(`在席情報を「${i}」に変更しました。`);
                f();
            } catch(a) {
                console.error("ステータス更新エラー:", a);
                alert("ステータスの変更に失敗しました。");
                t.checked = !t.checked;
            }
        } else {
            console.warn("ステータスの課題IDが見つかりませんでした。");
        }
    });
}

function g(t, s, e, n, o, i, a, d, l) {
    t.classList.remove(i);
    t.classList.add(o);
    s.textContent = n;
    s.classList.remove(d);
    s.classList.add(a);
    e.classList.toggle("translate-x-8", l === "translate-x-8");
    e.classList.toggle("translate-x-0", l === "translate-x-0");
}

function $() {
    document.getElementById("logout-button").addEventListener("click", () => {
        confirm("ログアウトします。よろしいですか？") && (sessionStorage.clear(), h());
    });
}

// Webhook SSEリスナーを設定
function setupWebhookListener() {
    console.log("Webhookリスナーをセットアップしています...");
    
    // 既存の接続を閉じる
    if (webhookEventSource) {
        webhookEventSource.close();
    }
    
    // 新しいSSE接続を作成
    webhookEventSource = new EventSource('/events');
    
    webhookEventSource.onopen = function() {
        console.log("WebhookのSSE接続が開きました");
    };
    
    webhookEventSource.onerror = function(err) {
        console.error("WebhookのSSE接続エラー:", err);
        // 再接続を試みる
        setTimeout(setupWebhookListener, 5000);
    };
    
    // Webhookイベントを購読
    webhookEventSource.addEventListener('webhook', function(e) {
        try {
            const eventData = JSON.parse(e.data);
            console.log("新しいWebhookイベントを受信:", eventData);
            
            // 現在のユーザーが「在席」状態の場合のみイベントを処理
            if (document.getElementById("status-label").textContent === "在席") {
                // Webhookイベントをチケットとして処理
                processWebhookAsTicket(eventData);
            } else {
                console.log("ユーザーが不在のため、Webhookイベントを無視します");
            }
        } catch (err) {
            console.error("Webhookイベント処理エラー:", err);
        }
    });


    // 接続イベントを購読
    webhookEventSource.addEventListener('connected', function(e) {
        try {
            const data = JSON.parse(e.data);
            console.log("Webhookストリームに接続しました:", data);
        } catch (err) {
            console.error("接続イベント処理エラー:", err);
        }
    });
}

// Webhookイベントを処理する関数
function processWebhookEvent(event) {
    // Webhookデータをコンソールに出力
    console.log("Webhookイベントデータ:", event);

    // APIから取得したチケット形式に変換
    const backlogTicket = convertWebhookToTicket(event);

    // 変換したチケットをリストに表示
    const ticketList = document.getElementById('ticket-list');

    // 通知音を再生
    if (r && !r.muted) {
        r.play().catch(err => {
            console.error("通知音の再生に失敗しました:", err);
        });
    }
    
    // ユーザーに通知を表示
    const notification = document.createElement('div');
    notification.className = 'fixed top-4 right-4 bg-blue-500 text-white px-6 py-4 rounded-lg shadow-lg z-50 animate-fade-in';
    notification.innerHTML = `
        <div class="flex items-center">
            <i class="bi bi-bell mr-2"></i>
            <div>
                <p class="font-bold">新しいWebhookを受信しました</p>
                <p class="text-sm">${event.timestamp || new Date().toLocaleTimeString()}</p>
            </div>
        </div>
    `;
    document.body.appendChild(notification);
    
    // 3秒後に通知を削除
    setTimeout(() => {
        notification.classList.add('animate-fade-out');
        setTimeout(() => notification.remove(), 500);
    }, 3000);
}

// WebhookイベントをBacklogチケット形式に変換
function convertWebhookToTicket(event) {
    return {
        id: event.id || event.event_id || Math.floor(Math.random() * 10000),
        description: `電子カルテ名: ${event.data?.ehrName || 'TestEHR'}\n` +
                     `病院名: ${event.data?.department || '不明'}病院\n` +
                     `患者ID: ${event.data?.patient_id || 'P0000'}\n` +
                     `診察日: 2025-04-07\n` +
                     `取得時間: ${event.timestamp || new Date().toISOString()}`
    };
}

// WebhookイベントをBacklogチケットとして処理
function processWebhookAsTicket(event) {
    console.log("WebhookイベントをBacklogチケットとして処理:", event);
    
    // イベントにassigneeIdが含まれているか確認
    // 現在のユーザーIDと一致または未指定の場合のみ処理
    const currentUserId = sessionStorage.getItem("userId");
    if (event.assigneeId && event.assigneeId != currentUserId) {
        console.log(`このチケットは別のユーザー(${event.assigneeId})に割り当てられているため無視します`);
        return;
    }
    
    // チケットデータを作成
    const ticket = {
        id: event.id || event.event_id || Date.now(),
        description: event.description || "詳細情報がありません",
    };
    
    // チケット一覧を表示
    const tickets = [ticket];
    O(tickets);
    
    // 通知音を再生
    if (r && !r.muted) {
        r.play().catch(err => {
            console.error("通知音の再生に失敗しました:", err);
        });
    }
    
    // 通知を表示
    showNotification("新しいWebhookを受信しました", `チケットID: ${ticket.id}`);
}

// 画面上部に通知を表示する関数
function showNotification(title, message) {
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
    
    // アニメーションのためのスタイルを追加
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fadeOut {
            from { opacity: 1; transform: translateY(0); }
            to { opacity: 0; transform: translateY(-20px); }
        }
    `;
    document.head.appendChild(style);
    
    document.body.appendChild(notification);
    
    // 5秒後に自動で消える
    setTimeout(() => {
        notification.style.animation = 'fadeOut 0.3s ease-in-out';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

async function E() {
    const t = sessionStorage.getItem("userId");
    const s = document.getElementById("status-label");
    const e = document.querySelector(".team-list");
    const n = document.getElementById("status-card");
    const o = document.getElementById("toggle-dot");
    
    if (!t) return;
    
    // 設定ファイルからAPI情報を取得
    const apiBaseUrl = window.appConfig ? window.appConfig.apiBaseUrl : "https://oasis-inn.backlog.com/api/v2";
    const apiKey = window.appConfig ? window.appConfig.apiKey : "rc57YrOQFnfP11Rde8rcnV1Wj9DxKfaahjKngY6HMNNgYJS2yfCmbpkSvmCHpvmz";
    const projectId = window.appConfig ? window.appConfig.projectIds.staff : "601236";
    
    const i = new URLSearchParams({
        apiKey: apiKey,
        "projectId[]": projectId,
        "assigneeId[]": t
    });
    
    try {
        const d = await (await fetch(`${apiBaseUrl}/issues?${i.toString()}`)).json();
        if (d.length > 0) {
            const l = d[0];
            u = l.id;
            l.status.name === "在席" ?
                (g(n, s, o, "在席", "bg-green-100", "bg-red-100", "text-green-700", "text-red-700", "translate-x-8"),
                document.getElementById("toggle-status").checked = !0) :
                (g(n, s, o, "不在", "bg-red-100", "bg-green-100", "text-red-700", "text-green-700", "translate-x-0"),
                document.getElementById("toggle-status").checked = !1);
            e.innerHTML = "";
            l.category.forEach(T => {
                const I = document.createElement("li");
                I.textContent = T.name;
                I.className = "text-sm text-gray-700";
                e.appendChild(I);
            });
        } else {
            s.textContent = "データなし";
            e.innerHTML = '<li class="text-gray-500">チーム情報がありません。</li>';
        }
    } catch(a) {
        console.error("APIリクエストエラー:", a);
        s.textContent = "エラー発生";
    }
}

async function p(t, s, e = !1) {
    // 設定ファイルからAPI情報を取得
    const apiBaseUrl = window.appConfig ? window.appConfig.apiBaseUrl : "https://oasis-inn.backlog.com/api/v2";
    const adminApiKey = window.appConfig ? window.appConfig.adminApiKey : "rc57YrOQFnfP11Rde8rcnV1Wj9DxKfaahjKngY6HMNNgYJS2yfCmbpkSvmCHpvmz";
    
    const n = { statusId: s };
    try {
        if (!(await fetch(`${apiBaseUrl}/issues/${t}?apiKey=${adminApiKey}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(n)
        })).ok)
            throw new Error("ステータス更新に失敗しました");
        console.log("ステータスが正常に更新されました");
        e && location.reload();
    } catch(o) {
        throw console.error("ステータス更新エラー:", o), o;
    }
}

async function b() {
    const t = sessionStorage.getItem("userId");
    if (!t) return;
    
    // 設定ファイルからAPI情報を取得
    const apiBaseUrl = window.appConfig ? window.appConfig.apiBaseUrl : "https://oasis-inn.backlog.com/api/v2";
    const adminApiKey = window.appConfig ? window.appConfig.adminApiKey : "rc57YrOQFnfP11Rde8rcnV1Wj9DxKfaahjKngY6HMNNgYJS2yfCmbpkSvmCHpvmz";
    const billingProjectId = window.appConfig ? window.appConfig.projectIds.billing : "601233";
    const statusIdProcessing = window.appConfig ? window.appConfig.statusIds.processing : 2;
    
    const s = new URLSearchParams({
        apiKey: adminApiKey,
        "projectId[]": billingProjectId,
        "assigneeId[]": t,
        "statusId[]": statusIdProcessing,
        sort: "created",
        order: "asc"
    });
    
    try {
        const n = await (await fetch(`${apiBaseUrl}/issues?${s.toString()}`)).json();
        O(n);
        n.length > 0 && r && r.play().catch(o => {
            console.error("通知音の再生に失敗しました:", o);
        });
        n.length === 0 ? k() : clearInterval(m);
    } catch(e) {
        console.error("チケット取得エラー:", e);
        alert("チケット情報の取得に失敗しました。");
    }
}

function O(t) {
    const s = document.getElementById("ticket-list");
    if (s.innerHTML = "", t.length === 0) {
        s.innerHTML = `
            <div class="bg-gray-50 shadow-md rounded-lg p-6 mb-6 text-center">
                <p class="text-gray-500 text-lg">現在割り当てられているチケットはありません。</p>
            </div>
        `;
        return;
    }
    t.forEach(e => {
        const n = _(e.description);
        const o = document.createElement("div");
        o.className = "bg-gray-50 shadow-md rounded-lg p-6 mb-6";
        o.innerHTML = `
            <h6 class="text-3xl font-bold mb-4">${n.hospitalName || '不明'} - 患者ID:${n.patientId || '不明'}</h6>
            <h6 class="text-2xl font-bold mb-4"><i class="bi bi-clock mr-2"></i>取得時間 ${n.acquisitionTime || '不明'}</h6>

            <div class="flex items-center justify-between mt-5">
                <!-- 左側: 電子カルテ名など -->
                <div class="text-xl mb-4 mr-4 space-y-5 flex-grow">
                    <p>電子カルテ名: ${n.ehrName || '不明'}</p>
                    <p>診察日: ${n.consultationDate || '不明'}</p>
                </div>

                <!-- 右側: 完了・差戻ボタン -->
                <div class="flex justify-end items-end">
                    <!-- 完了ボタン -->
                    <button data-ticket-id="${e.id}" class="complete-button bg-green-500 text-white py-16 px-16 rounded-lg shadow-lg text-3xl lg:text-5xl mr-8 whitespace-nowrap">
                        <i class="bi bi-check-circle mr-4"></i>完了
                    </button>
                    <!-- 差戻ボタン -->
                    <button data-ticket-id="${e.id}" class="return-button bg-red-500 text-white py-4 px-8 rounded-lg shadow-md text-lg whitespace-nowrap">
                        <i class="bi bi-arrow-counterclockwise mr-2"></i>差戻
                    </button>
                </div>
            </div>
        `;
        s.appendChild(o);
    });
}

function _(t) {
    if (!t) return { ehrName: '不明', hospitalName: '不明', patientId: '不明', consultationDate: '不明', acquisitionTime: '不明' };
    
    const s = t.split(`\n`);
    const e = {};
    
    s.forEach(n => {
        if (!n || !n.includes(':')) return;
        
        const [o, ...i] = n.split(":");
        const a = i.join(":").trim();
        
        switch(o.trim()) {
            case "電子カルテ名": e.ehrName = a; break;
            case "病院名": e.hospitalName = a; break;
            case "患者ID": e.patientId = a; break;
            case "診察日": e.consultationDate = a; break;
            case "取得時間": e.acquisitionTime = a; break;
            default: console.warn(`未処理のキー: ${o}`);
        }
    });
    
    return e;
}

function k() {
    clearInterval(m);
    m = setInterval(b, 5e3);
}

async function f() {
    await E();
    document.getElementById("status-label").textContent === "在席" ?
        (b(), k()) :
        (clearInterval(m), console.log("ユーザーが不在のため、チケット取得を停止しました"));
}

async function U(t) {
    if (confirm("差戻しますか？")) {
        j();
        try {
            // 設定ファイルからステータスIDを取得
            const statusIdReturn = window.appConfig ? window.appConfig.statusIds.return : 276515;
            const statusIdAbsent = window.appConfig ? window.appConfig.statusIds.absent : 276517;
            
            await Promise.all([p(t, statusIdReturn, !1), p(u, statusIdAbsent, !1)]);
            await new Promise(e => setTimeout(e, 2e4));
            x();
            location.reload();
        } catch(e) {
            console.error("差戻処理エラー:", e);
            alert("差戻処理中にエラーが発生しました。");
            x();
            f();
        }
    }
}

function j() {
    const t = document.getElementById("processing-modal");
    if (!t) {
        console.error("モーダル要素が見つかりません");
        return;
    }
    t.classList.remove("hidden");
    t.style.display = "flex";
    console.log("モーダル表示: OPEN");
}

function x() {
    const t = document.getElementById("processing-modal");
    if (!t) {
        console.error("モーダル要素が見つかりません");
        return;
    }
    t.classList.add("hidden");
    t.style.display = "none";
    console.log("モーダル表示: CLOSE");
}

document.getElementById("ticket-list").addEventListener("click", async t => {
    if (t.target && t.target.matches("button[data-ticket-id].complete-button")) {
        const s = t.target.dataset.ticketId;
        try {
            // 設定ファイルからステータスIDを取得
            const statusIdCompleted = window.appConfig ? window.appConfig.statusIds.completed : 4;
            
            await p(s, statusIdCompleted, !1);
            await b();
        } catch(e) {
            console.error("完了ボタン処理エラー:", e);
            alert("チケットの完了処理に失敗しました。");
        }
    }
    if (t.target && t.target.matches("button[data-ticket-id].return-button")) {
        const s = t.target.dataset.ticketId;
        await U(s);
    }
});

window.addEventListener("pageshow", () => { h(); });

function h() {
    sessionStorage.getItem("userId") || (window.location.href = "index.html");
}

function M() {
    c = new Audio("/assets/sounds/default.mp3");
    r = new Audio(sessionStorage.getItem("userSound") || "/assets/sounds/ticket.mp3");
    const t = !0;
    c.muted = t;
    r.muted = t;
    
    document.addEventListener("click", () => {
        c.play().then(() => c.pause());
        r.play().then(() => r.pause());
        console.log("音声初期化完了");
    }, { once: !0 });
    
    const s = document.getElementById("mute-toggle");
    const e = s.querySelector("i");
    e.className = "bi bi-volume-mute text-xl";
    
    s.addEventListener("click", () => {
        const n = !r.muted;
        c.muted = n;
        r.muted = n;
        e.className = n ? "bi bi-volume-mute text-xl" : "bi bi-volume-up text-xl";
        c.muted ? c.pause() : c.play().catch(o => {
            console.error("音声再生エラー:", o);
            alert("音声を再生できませんでした。ブラウザの設定を確認してください。");
        });
    });
}

// グローバルスコープでアクセスできるように関数をエクスポート
window.f = f;