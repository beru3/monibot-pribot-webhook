# Git ワークフロー（検証環境 → 本番環境）

## 1. 検証環境で修正

```
C:\Users\miyake2107\Desktop\MoniBot_PriBot\MoniBot\src\core\
```
このフォルダ内のファイルを編集・テスト

---

## 2. 変更をGitにコミット＆プッシュ

```bash
# 検証フォルダに移動
cd C:/Users/miyake2107/Desktop/MoniBot_PriBot

# 変更内容を確認
git status

# すべての変更をステージング
git add .

# コミット（変更内容を記述）
git commit -m "修正内容の説明"

# GitHubにプッシュ
git push origin main
```

---

## 3. 本番環境に適用

```bash
# 本番環境に移動
cd W:/

# GitHubから最新を取得して適用
git pull origin main
```

**`git pull` が行うこと：**
- GitHubの最新コミットをダウンロード
- ローカルファイルを最新状態に更新
- つまり、検証環境でpushした変更が本番に反映される

---

## 図解

```
┌─────────────────────────────────────────────────────────────┐
│  検証環境                                                    │
│  C:\Users\miyake2107\Desktop\MoniBot_PriBot\                │
│                                                             │
│  ファイル編集 → git add → git commit → git push             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │     GitHub      │
                    │  (リモート)      │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  本番環境                                                    │
│  W:/ (\\SVR-MONIBOT\wk)                                     │
│                                                             │
│                    git pull                                 │
│                       ↓                                     │
│              ファイルが自動更新される                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 具体例：clinics_monitor.py を修正する場合

```bash
# 1. 検証環境でファイルを編集
#    C:\Users\miyake2107\Desktop\MoniBot_PriBot\MoniBot\src\core\clinics_monitor.py

# 2. 検証環境でテスト完了後、gitでコミット
cd C:/Users/miyake2107/Desktop/MoniBot_PriBot
git status                              # 変更ファイルを確認
git add .                               # 変更をステージング
git commit -m "clinics_monitor: ○○を修正"  # コミット
git push origin main                    # GitHubにプッシュ

# 3. 本番環境に適用
cd W:/
git pull origin main                    # 本番のclinics_monitor.pyが更新される
```

---

## 注意点

- **本番で直接編集しない** - 必ず検証環境で編集してgit経由で反映
- **git pull前に本番で変更があると競合する** - 本番は常にgit pullのみ
- `git pull` は変更があるファイルのみ更新（全ファイル上書きではない）

---

## 環境情報

| 環境 | パス | 用途 |
|------|------|------|
| 検証環境 | `C:\Users\miyake2107\Desktop\MoniBot_PriBot\` | 編集・テスト |
| 本番環境 | `W:/` (`\\SVR-MONIBOT\wk`) | 実運用 |
| リモート | `https://github.com/beru3/monibot-pribot-webhook.git` | GitHub |

---

*作成日: 2025-12-29*
