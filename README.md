# Zircon Mining Bot

Discordで常設の採掘ボタンを押し、個人のログインポイントとして💎ジルコンを獲得するBotです。

## 使い方

採掘チャンネルには次の2投稿を常設します。

- 採掘所：キャラクターの名前・セリフ・アイコン・サムネイルと採掘ボタン
- 保有数・ランキング：自分の保有数、ジルコン所持数ランキング、Excellentランキング

結果はすべてエフェメラル（本人のみ表示）です。ランキングは10件ずつ前後に移動できます。所持数ランキングは現在の残高・名前・所属国の絵文字、Excellentランキングは名前・Excellent回数・採掘回数を表示します。所属国がない場合は「—」、取得できないユーザーはIDを表示します。

採掘権は個人単位です。国別の採掘済みフラグや国別集計は使用せず、国ロール変更で追加採掘はできません。国ロールは所属表示・Excellent通知先・寄付先国庫の判定に使います。Excellent通知の複数国所属時の選択順は従来通りです。通知には、採掘した本人に表示した結果画像と同じファイルをサムネイルとして添付します。

## コマンド

| コマンド | 権限 | 用途 |
| --- | --- | --- |
| `/help` | Administrator | 本人限定の管理コマンドの使い方案内 |
| `/settings` | Administrator | 設定ビューを開く |
| `/add user amount` | Administrator | 残高を付与 |
| `/remove user amount` | Administrator | 残高を引き去る |
| `/transfer source target amount` | Administrator | 任意のユーザー間で転送 |
| `/resetmining` | Administrator | 全員の採掘回数を即時リセット（残高・実績は維持） |
| `/exportwallet` | Administrator | 必要な情報を複数選択してCSVで取得 |
| `/wipewallet` | Administrator | 全員のウォレットを初期化（確認2回・事前バックアップ必須） |
| `/donate amount` | 一般ユーザー | 自分の所属国の国庫へ自動で寄付 |

管理チャンネルにいるだけでは管理操作できません。設定ビュー・選択メニュー・入力フォームでも権限を再確認します。すべての操作は採掘チャンネルが属するサーバーに限定します。

設定ビューでは開閉、リセットの時・分、リセット間の採掘回数、採掘可能ロール、寄付先、未所属Excellent通知先、共通確率・獲得数、ロール別確率を確認・変更できます。常設投稿が削除された場合の復旧ボタンもあります。

国庫はBrave / Freedom / Glory / Peacefulの国ロールに1対1で対応する4アカウントです。「4か国の国庫」から国ごとに設定します。同一アカウントの重複登録は拒否します。未所属・複数国所属・所属国の国庫未設定時は寄付できません。寄付時に任意ユーザーや他国の国庫を指定することはできません。

旧設定コマンド（`/zmst`、`/zmtime`、`/zmprob`、`/zmrole` など）は設定ビューへ統合しました。旧イベントDBリセット・国ランキング・任意メッセージ投稿コマンドは新バージョンでは登録しません。

## セットアップ

Python 3.11または3.12を推奨します。

```sh
git clone https://github.com/palkeeno/zircon-mining-bot.git
cd zircon-mining-bot
python -m venv .venv
# 仮想環境を有効にして実行
python -m pip install -r requirements.txt
```

`.env.example` を参考に `.env.production` または `.env.development` を設定します。DBは新規作成します。`DB_WALLET` に新しい保存先を指定してください。旧DBの取り込みは行いません。

- `CHID_MINING`：採掘・保有数の常設投稿先
- `MINING_ROLE`：採掘可能ロールの初期値
- `MINING_EXCELLENT_CHAT`：未所属者のExcellent通知先初期値
- `BRAVE_TREASURY_USER_ID` / `FREEDOM_TREASURY_USER_ID` / `GLORY_TREASURY_USER_ID` / `PEACEFUL_TREASURY_USER_ID`：各国の国庫アカウント初期値。省略時は暫定値 `0`（その国への寄付を無効化）
- 各国の `*_ROLE` / `*_CHAT` / `*_EMOJI`：所属判定・国別Excellent通知の初期値・所属表示。通知先は `/settings` →「国別Excellent通知先」で変更でき、保存値を優先
- `DB_WALLET`：個人残高・採掘権・操作履歴をまとめた新規SQLite DB。省略時はプロジェクト直下の `wallet.db`。旧 `DB_USERS` / `DB_MINING` は使用しません。
- `ASSET_DATA_DIR`：アセットDBと画像の永続保存先。省略時はプロジェクト直下の `asset-data`。テストと本番で別ディレクトリを指定してください。
- `CWD`：既存のアプリ配置先
- `GUILD_ID`：指定時はこのサーバーだけにコマンドを同期し、採掘チャンネルの所属を検証。省略・0は従来のグローバル同期
- `SETTINGS_FILE` / `ROLE_SETTINGS_FILE` / `BACKUP_DIR`：環境別の設定・ロール確率・バックアップ保存先

設定ビューで保存した値は `data/user_setting.json` に永続化され、環境変数の初期値より優先します。ロール別確率は既存の `data/role_probabilities.json` を使います。

テスト環境では `DB_WALLET` と上記3つの保存先をすべて分離してください。`GUILD_ID` を設定した起動では既存グローバルコマンドを変更・削除しません。過去のグローバル登録が残るテストBotでは候補が重複する場合があります。

Developer Portalの **Server Members Intent** を有効にしてください。Botには投稿先の閲覧・履歴閲覧・メッセージ送信・埋め込み・ファイル添付権限が必要です。

```sh
ENV=production python zrmine.py
```

本番配置先 `/home/zircon-mining`、cronの `scripts/checkps.sh`、起動ファイル `zrmine.py` は変更しません。

```sh
/bin/bash /home/zircon-mining/scripts/checkps.sh --check
```

## データとリセット

`wallets.balance` は現在の保有数です。`total_mined` は採掘で獲得した累計で、寄付・転送・引き去りで減らず、管理者からの付与も含みません。採掘時だけ `total_mined`・`mining_count`・`excellent_count` を増やします。残高を変更した全アカウントの `updated_at` は、対応する操作履歴と同じ日時に更新します。

リセット時刻は日本時間の「時 × 分」の組み合わせです。例：時 `0,12`、分 `0` は1日2回、時 `0,12`、分 `0,30` は1日4回。各期間の採掘回数は既定1回、1〜100回で設定できます。未使用分は次期間へ繰り越しません。CLOSE中も時間は進み、OPEN時には現在の期間が適用されます。時刻変更は直ちに適用され、最新の境界が変わる場合は新期間になります。

5秒ごとに期間境界とアセット編集を確認し、リセット後は同じ採掘投稿の演出embedを別のランダムなキャラへ書き換えます。初回のみ `consts/characters.py` と既存画像からアセットDBへ取り込み、以後はDBのキャラ・セリフ・画像を使います。セリフ単位の抽選を維持し、登録セリフが多いキャラほど選ばれやすくなります。アイコンとサムネイルに同じ画像を表示します。期間内の再起動・更新失敗の再試行では選択したキャラを維持します。停止中の境界をすべて再生せず、復帰時の現在期間へ更新します。

投稿し直す定時処理はありません。採掘時に最新の期間境界を判定するため、Botがリセット時刻に停止していても次の採掘から正常に処理します。常設投稿のIDを保存し、再起動時は既存投稿を編集します。投稿が削除されていたときだけ再作成します。403や通信エラーでは重複投稿を作りません。

残高、採掘権、取引履歴は1つのSQLiteトランザクションで更新し、二重実行、同時採掘、残高不足、自己転送、非正整数、上限超過を防ぎます。履歴にはDiscord操作ID・実行者・転送元・転送先・数量・種類・日時を保存します。

`/resetmining` は全員の採掘権を回復し、新しい期間境界を永続化します。定時スケジュール・OPEN/CLOSE・残高・実績は変えません。次の定時境界から通常の期間に戻ります。操作IDと実行者を `mining_resets` に記録し、同じ操作の二重実行を防ぎます。新規DBを初期化し、再起動時はそのデータを保持します。旧形式・未対応バージョンのDBは変更せず起動を停止します。

`/exportwallet` は本人限定の日本語の複数選択メニューを開きます。必要な情報を1〜5種類選び、「選択した情報をダウンロード」を押すと、`wallets`、`mining_claims`、`wallet_ledger`、`mining_state`、`mining_resets` のうち選んだテーブルだけを1つの読み取りスナップショットからUTF-8 BOM付きCSVにして本人限定で返します。添付上限を超えるCSVがあればZIP化し、それでも超える場合はエラーを返します。Discord IDは表計算ソフトで文字列として読み込んでください。CSVからの復元機能は含みません。

テーブル・制約・バージョン管理は [DB仕様](docs/DATABASE.md) を参照してください。

設計の選定理由と依存関係は [アーキテクチャ](docs/ARCHITECTURE.md) を参照してください。

## アセット管理

管理者の `/assets manage` で画像・キャラ・セリフの確認、編集、非表示・再表示、完全削除を行えます。画像追加・差し替えは `/assets upload` から添付します。画像は正方形・最大600×600px・1MB未満、500KB以下を推奨します。操作方法、既存画像の取り込みと復元は [アセット管理](docs/ASSETS.md) を参照してください。

## 検証

```sh
python -m unittest discover -s tests -v
python -m compileall -q commands domain config models services views utils zrmine.py
git diff --check
```

GitHub ActionsはWindows / Ubuntu、Python 3.11 / 3.12で実行します。新DBへの切り替えと本番確認手順は [管理者マニュアル](docs/ADMIN_MANUAL.md) を参照してください。
