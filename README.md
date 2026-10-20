# Zircon Mining Bot

Discordで常設の採掘ボタンを押し、個人のログインポイントとして💎ジルコンを獲得するBotです。

## 使い方

採掘チャンネルには次の2投稿を常設します。

- 採掘所：採掘ボタン
- 保有数・ランキング：自分の保有数、ジルコン所持数ランキング、Excellentランキング

結果はすべてエフェメラル（本人のみ表示）です。ランキングは10件ずつ前後に移動できます。所持数ランキングは現在の残高・名前・所属国の絵文字、Excellentランキングは名前・Excellent回数・採掘回数を表示します。所属国がない場合は「—」、取得できないユーザーはIDを表示します。

採掘権は個人単位です。国別の採掘済みフラグや国別集計は使用せず、国ロール変更で追加採掘はできません。国ロールは所属表示とExcellent通知先の選択にのみ使います（複数ある場合の選択順は従来通り）。Excellent通知には、採掘した本人に表示した結果画像と同じファイルをサムネイルとして添付します。

## コマンド

| コマンド | 権限 | 用途 |
| --- | --- | --- |
| `/zmsettings` | Administrator | 設定ビューを開く |
| `/zmadd user amount` | Administrator | 残高を付与 |
| `/zmremove user amount` | Administrator | 残高を引き去る |
| `/zmtransfer source target amount` | Administrator | 任意のユーザー間で転送 |
| `/zmdonate amount` | 一般ユーザー | 自分から設定済み国庫への寄付 |

管理チャンネルにいるだけでは管理操作できません。設定ビュー・選択メニュー・入力フォームでも権限を再確認します。すべての操作は採掘チャンネルが属するサーバーに限定します。

設定ビューでは開閉、リセットの時・分、リセット間の採掘回数、採掘可能ロール、寄付先、未所属Excellent通知先、共通確率・獲得数、ロール別確率を確認・変更できます。常設投稿が削除された場合の復旧ボタンもあります。

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

`.env.example` を参考に `.env.production` または `.env.development` を設定します。既存の環境変数とDBパスは引き継ぎます。

- `CHID_MINING`：採掘・保有数の常設投稿先
- `MINING_ROLE`：採掘可能ロールの初期値
- `MINING_EXCELLENT_CHAT`：未所属者のExcellent通知先初期値
- `TREASURY_USER_ID`：国庫アカウント初期値。省略時は暫定値 `0`（寄付を無効化）
- 各国の `*_ROLE` / `*_CHAT` / `*_EMOJI`：所属判定・国別Excellent通知・所属表示
- `DB_USERS`：個人残高・採掘権・取引履歴DB
- `DB_MINING`：旧採掘DB。移行時の読み取りとバックアップ用
- `CWD`：既存のアプリ配置先

設定ビューで保存した値は `data/user_setting.json` に永続化され、環境変数の初期値より優先します。ロール別確率は既存の `data/role_probabilities.json` を使います。

Developer Portalの **Server Members Intent** を有効にしてください。Botには投稿先の閲覧・履歴閲覧・メッセージ送信・埋め込み・ファイル添付権限が必要です。

```sh
ENV=production python zrmine.py
```

本番配置先 `/home/zircon-mining`、cronの `scripts/checkps.sh`、起動ファイル `zrmine.py` は変更しません。

```sh
/bin/bash /home/zircon-mining/scripts/checkps.sh --check
```

## データとリセット

既存の `USERS.curr_total` を残高として維持し、採掘時だけ生涯採掘量・回数・Excellent回数を増やします。管理者操作と寄付は採掘実績に加算しません。旧バージョンで既に加算された実績は推測で補正しません。

リセット時刻は日本時間の「時 × 分」の組み合わせです。例：時 `0,12`、分 `0` は1日2回、時 `0,12`、分 `0,30` は1日4回。各期間の採掘回数は既定1回、1〜100回で設定できます。未使用分は次期間へ繰り越しません。CLOSE中も時間は進み、OPEN時には現在の期間が適用されます。時刻変更は直ちに適用され、最新の境界が変わる場合は新期間になります。

投稿し直す定時処理はありません。採掘時に最新の期間境界を判定するため、Botがリセット時刻に停止していても次の採掘から正常に処理します。常設投稿のIDを保存し、再起動時は既存投稿を編集します。投稿が削除されていたときだけ再作成します。403や通信エラーでは重複投稿を作りません。

残高、採掘権、取引履歴は1つのSQLiteトランザクションで更新し、二重実行、同時採掘、残高不足、自己送金、非正整数、上限超過を防ぎます。履歴にはDiscord操作ID・実行者・送金元・送金先・数量・種類・日時を保存します。

## 検証

```sh
python -m unittest discover -s tests -v
python -m compileall -q config models services views utils zrmine.py
git diff --check
```

GitHub ActionsはWindows / Ubuntu、Python 3.11 / 3.12で実行します。移行と本番確認手順は [管理者マニュアル](docs/ADMIN_MANUAL.md) を参照してください。
