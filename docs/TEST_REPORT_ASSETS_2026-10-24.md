# アセット管理 検証記録 2026-10-24

## 対象と隔離

- ベース：PR #9を取り込んだdev、ブランチ `codex/asset-management`。
- Bot：my-test（1215282644699447318）。本番とは別トークン。
- サーバー：ジルコンテストサーバー（1263066878545367121）のみ。
- Botテストカテゴリの既存検証用 `mining-rework-20261022`（1562521914986070237）と `mining-excellent-20261022`（1562522045051310130）のみを操作。
- 既存カテゴリ・ロール・権限の変更なし。ウォレット・設定・アセット・バックアップを `.local-test-20261022/assets-test/` に分離。
- Windows DiscordアプリをComputer Useで実操作。検証後にローカルテストBotを停止。

## 自動検証

`python -m unittest discover -s tests -q`：79件成功。実SQLiteと画像バイト列で容量境界、1px/600px許可、601px/非正方形拒否、初回取り込み、元ファイル保持、セリフ重み、非表示・復帰・完全削除、キャラ削除時のセリフ削除、最後の有効候補保護、古い画面からの更新拒否、採掘中の画像保持、ZIP復元を確認。

Discordアダプターのテストで管理者・画面所有者・対象サーバーの制限、ページ送り、フォーム保存、削除確認と実削除、キャンセル、添付の読取前容量拒否、警告、パネル更新時の採掘権維持を確認。OSのファイルロックで不要画像を削除できなくても、DBの更新成功を誤って失敗報告しないことも検証した。

## 実Discordの結果

| 操作 | 結果 | スクリーンショット |
| --- | --- | --- |
| `/assets manage` | 本人限定、キャラ34件、25件ずつの一覧 | 01-assets-manage.png |
| ページ送り | 2ページ目へ移動、前へ有効・次へ無効 | 02-assets-page-two.png |
| キャラ選択・プレビュー | 実画像を本人限定で表示 | 03-asset-preview.png |
| 名前変更 | モーダルから保存成功 | 04-character-name-saved.png |
| セリフ管理 | 登録済み2件の一覧 | 05-dialogue-manage.png |
| セリフ追加 | 3件に増加 | 06-dialogue-added.png |
| セリフ非表示 | 保存成功、DB enabled=0 | 07-dialogue-hidden.png |
| `/assets upload` 600×600px・658,964 bytes | 登録成功、659.0KBの警告 | 08-upload-warning.png |
| 600×599px | 正方形条件のエラー、DBへの登録なし | 09-upload-dimensions-rejected.png |
| 常設採掘ボタン | Excellent、保有数10→20、結果画像表示 | 10-mining-result.png |
| Excellent通知 | 指定テストチャンネルに同じ画像のサムネイル | 11-excellent-same-image.png |
| Bot停止→再起動→管理画面 | 変更したキャラ名を保持 | 12-character-retained-after-restart.png |
| 完全削除ボタン | 対象名と復元不可の確認画面 | 13-delete-confirmation.png |
| 削除キャンセル | キャンセル応答、DB行を保持 | 14-delete-cancelled.png |

画像はローカルの `docs/evidence/2026-10-24/` に保存。Discordの参加者表示を含むためGitには追加しない。完全削除の確定・一般ユーザーによる拒否・画像差し替え・非表示からの復帰は自動テストで確認し、この実操作では未実施。

採掘のアップロードログは演出0.672秒・結果1.172秒（意図した3秒待機を除く）。これは利用者側の表示速度測定ではない。

## 再起動と保全

再起動後のSQLiteで変更名、追加セリフの非表示、2枚の新規画像を保持し、`integrity_check=ok`。walletの `balance=20,total_mined=20,mining_count=2,excellent_count=2`。常設投稿IDを維持。起動時ZIPの整合性検査に成功し、DBと参照画像71枚が含まれた。

`.env.production`、利用者所有の `data/user_setting.json` と `data/role_probabilities.json`、前のfresh-schema検証DBは開始時と終了時のSHA-256が一致。これらはコミット対象外。

## 既存画像の取り込み対象外

元キャラ40件中34件、演出・結果画像36件中36件を登録。次の6件は寸法不適合のため対象外。元画像の変更・変換・削除は行っていない。必要なら運用側で正方形に調整した画像を新規キャラとして登録する。

| 元ファイル | 寸法 |
| --- | --- |
| assets_character/0.png | 652×652 |
| assets_character/143.png | 399×397 |
| assets_character/173.png | 399×397 |
| assets_character/267.png | 397×399 |
| assets_character/278.png | 395×399 |
| assets_character/72.png | 398×401 |

初回の容量警告用画像はPNG末尾にゼロを加えて500,001 bytesにしたが、Discord受信時は2,336 bytesだった。警告が出ないのは期待通りで、実画像データ自体が658,964 bytesの画像に置き換えて警告を再確認した。
