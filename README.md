# Zircon Mining Bot - Discord Bot

Discord サーバー用の採掘ゲームボットです。ユーザーは国に所属してジルコンを採掘し、ランキングを競うことができます。

## リポジトリ名と配置先

リポジトリは `palkeeno/zircon-mining-bot` です。

```bash
git clone https://github.com/palkeeno/zircon-mining-bot.git
cd zircon-mining-bot
```

既存チェックアウトでは、取得先を更新します。

```bash
git remote set-url origin https://github.com/palkeeno/zircon-mining-bot.git
```

リポジトリ名と本番の配置先は別です。既存の `/home/zircon-mining`、cron、DB、環境設定はそのまま使用します。起動ファイルは引き続き `zrmine.py` です。配置先を変更する場合は、Botを停止したうえで `CWD`、DB・画像のパス、cronやサービスのパス、仮想環境を確認してください。

## プロジェクト構造

```
zircon-mining-bot/
├── zrmine.py                    # メインエントリーポイント
├── config/                      # 設定関連
│   ├── config.py               # 環境変数・定数設定
│   ├── settings_manager.py     # 動的設定管理
│   └── role_manager.py         # ロール確率管理
├── utils/                      # ユーティリティ
│   ├── helpers.py              # 汎用ヘルパー関数
│   ├── backup.py               # バックアップ機能
│   └── db_utils.py             # データベース操作
├── models/                     # データベースモデル
│   ├── mining.py               # 採掘DBモデル
│   └── users.py                # ユーザーDBモデル
├── services/                   # ビジネスロジック
│   ├── embeds.py               # Discord Embed生成
│   ├── mining_service.py       # 採掘処理ロジック
│   └── stats_service.py        # 統計・ランキング処理
├── views/                      # Discord UI Views
│   ├── mine_status_view.py     # 鉱山営業状況UI
│   ├── rank_view.py            # ランキング表示UI
│   └── reset_confirm_view.py   # リセット確認UI
├── consts/                     # 定数定義
│   ├── characters.py           # キャラクター情報
│   ├── cids.py                 # カスタムID定数
│   ├── const.py                # 共通定数
│   └── sysmsg.py               # システムメッセージ
├── data/                       # 設定データ
│   ├── role_probabilities.json # ロール別確率設定
│   └── user_setting.json       # ユーザー設定
├── assets/                     # 画像アセット
├── assets_character/           # キャラクター画像
├── backups/                    # DBバックアップ（gitignore済み）
├── mining.db                   # 採掘データベース（gitignore済み）
└── users.db                    # ユーザーデータベース（gitignore済み）
```

## 機能

### ユーザー機能
- **採掘システム**: ボタンを押してジルコンを採掘
- **統計表示**: 個人の採掘統計とランキング表示
- **国別統計**: 所属国の採掘統計とランキング表示

### 管理者機能
- **鉱山営業管理**: 鉱山の開閉状態を管理
- **ジルコン付与**: 指定ユーザーにジルコンを付与
- **メッセージ投稿**: 採掘チャンネルにメッセージを投稿
- **アナウンス送信**: 採掘アナウンスを手動送信
- **データベースリセット**: 採掘データのリセット
- **時間設定**: 採掘アナウンス時間の設定
- **確率設定**: 採掘確率とジルコン数の設定
- **ロール確率設定**: ロール別採掘確率の設定

## セットアップ

### 必要な環境
- Python 3.8+
- Discord Bot Token

### インストール
```bash
pip install -r requirements.txt
```

### 環境変数設定
`.env.development` または `.env.production` ファイルを作成し、以下の変数を設定：

```env
DISCORD_TOKEN=your_discord_bot_token
DB_MINING=mining.db
DB_USERS=users.db
CWD=/path/to/project
MCH=management_channel_id
CHID_MINING=mining_channel_id
BRAVE_CHAT=brave_chat_channel_id
FREEDOM_CHAT=freedom_chat_channel_id
GLORY_CHAT=glory_chat_channel_id
PEACEFUL_CHAT=peaceful_chat_channel_id
MINING_EXCELLENT_CHAT=unaffiliated_user_excellent_channel_id
BRAVE_ROLE=brave_role_id
FREEDOM_ROLE=freedom_role_id
GLORY_ROLE=glory_role_id
PEACEFUL_ROLE=peaceful_role_id
BRAVE_EMOJI=brave_emoji
FREEDOM_EMOJI=freedom_emoji
GLORY_EMOJI=glory_emoji
PEACEFUL_EMOJI=peaceful_emoji
```

`MINING_EXCELLENT_CHAT` は、国に所属していないユーザーがExcellentを出したときの投稿先です。

### 実行
```bash
python zrmine.py
```

本番設定を使って直接起動する場合は、`ENV=production` を明示します。

```bash
ENV=production python zrmine.py
```

### 本番環境での監視起動

本番環境では、cronから直接Pythonを起動せず、監視スクリプトを使用します。
監視スクリプトはプロジェクトディレクトリへ移動し、`ENV=production`、非バッファリング出力、PID管理を設定して起動します。

```cron
* * * * * /bin/bash /home/zircon-mining/scripts/checkps.sh
```

cronへ登録する前に、production設定と実行ファイルを検証できます。この確認ではBotを起動しません。

```bash
/bin/bash /home/zircon-mining/scripts/checkps.sh --check
```

標準の配置先は以下です。

- Botログ: `/home/zircon-mining/nohup.out`
- 監視ログ: `/home/zircon-mining/log/checkps.log`
- PID・ロックファイル: `/home/zircon-mining/run/`

Pythonやログの場所を変更する場合は、`ZIRCON_PYTHON_BIN`、`ZIRCON_APP_LOG`、`ZIRCON_WATCHDOG_LOG`をcron側で指定できます。

## コマンド

### 管理者コマンド
- `/zmst` - 鉱山の営業状況を表示・変更
- `/zmrank` - ランキング情報を表示
- `/zmadd <amount> <user>` - 指定ユーザーにジルコンを付与
- `/zmmsg <message>` - 採掘チャンネルにメッセージを投稿
- `/zmannounce` - 採掘アナウンスを手動送信
- `/zmreset <mining/all>` - データベースをリセット
- `/zmtime [hours] [minutes]` - 採掘時間を設定
- `/zmprob [id] [prob] [zirnum]` - 採掘確率とジルコン数を設定
- `/zmrole [ロール名] [Great確率] [Excellent確率] [優先度]` - ロール別採掘確率を設定
- `/zmhelp` - ヘルプを表示

## データベース

### 採掘データベース (mining.db)
- ユーザーごとの採掘記録
- 国別の採掘統計
- 採掘済みフラグ管理

### ユーザーデータベース (users.db)
- ユーザーの生涯採掘統計
- 累積採掘量と回数
- Excellent回数の記録

## バックアップ

- 24時間ごとに自動バックアップが実行されます
- バックアップファイルは `backups/` フォルダに保存されます
- 古いバックアップは自動的に削除されます

## 開発

### リポジトリ名と配置先

リポジトリは `palkeeno/zircon-mining-bot` です。

```bash
git clone https://github.com/palkeeno/zircon-mining-bot.git
cd zircon-mining-bot
```

既存チェックアウトでは、取得先を更新します。

```bash
git remote set-url origin https://github.com/palkeeno/zircon-mining-bot.git
```

リポジトリ名と本番の配置先は別です。既存の `/home/zircon-mining`、cron、DB、環境設定はそのまま使用します。起動ファイルは引き続き `zrmine.py` です。配置先を変更する場合は、Botを停止したうえで `CWD`、DB・画像のパス、cronやサービスのパス、仮想環境を確認してください。

## プロジェクト構造の説明
- **config/**: 設定関連のファイルを集約
- **utils/**: 汎用ユーティリティとシステム機能
- **models/**: データベースモデルとデータアクセス層
- **services/**: ビジネスロジックとDiscord関連サービス
- **views/**: Discord UIコンポーネント
- **consts/**: 定数定義とシステムメッセージ

### 新機能追加時の指針
- 設定関連 → `config/`
- 汎用ユーティリティ → `utils/`
- データベース操作 → `models/`
- ビジネスロジック → `services/`
- Discord UI → `views/`
- 定数・メッセージ → `consts/`

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。
