# 新規DB版の検証（2026-10-23）

旧DBを引き継がない仕様への変更を検証した。指定サーバー `1263066878545367121` の検証専用チャンネル `1562521914986070237` とExcellent用 `1562522045051310130` を使用した。チャンネル・ロール・権限の変更や他サーバーでの操作は行っていない。

## 自動検証

65件成功。新スキーマの初期値・再初期化時のデータ保持・未バージョン管理DBと未対応バージョンの拒否、非負／整数／NOT NULL／実績整合性／外部キー／操作種別の制約を検証した。

残高更新すべての日時と履歴日時の一致、採掘だけがtotal_minedを増やすこと、累計上限超過と二重採掘時の全体ロールバック、国集計用予約IDの撤去を検証した。既存の同時実行・寄付・回数制限・手動リセット・ランキング・選択CSV・権限のテストは新スキーマで成功。バックアップ整理が旧DB名・無関係なファイルを削除しないことも確認した。

compileall、git diff --checkも成功。

## 実Discord検証

Computer UseでWindows版Discordを操作した。`.local-test-20261022/fresh-schema/` に新しいDB・設定・ロール確率・バックアップを分離。起動前に新DBファイルが存在しないことを確認した。

| 操作 | 結果 | ローカル証跡 |
| --- | --- | --- |
| 自分の保有数 | 残高0・Excellent0回・採掘0回 | `13-fresh-wallet-zero.png` |
| 採掘 | Excellent10を獲得。balance=10、total_mined=10、mining_count=1、excellent_count=1 | `14-fresh-mining-result.png` |
| `/exportwallet` | 日本語の複数選択を維持。「採掘リセットの現在状態」を表示 | `15-fresh-export-options.png` |
| 保有数と採掘状態を選択して取得 | wallets.csvとmining_state.csvだけを本人限定で取得。CSV内に新しいカラム名・値を確認 | `16-fresh-csv-columns.png` |
| Botを停止・再起動後に再採掘 | 同期間の回数制限で拒否。残高・実績は10/10/1/1のまま | `17-fresh-restart-quota.png` |

スクリーンショットは `docs/evidence/2026-10-23/` に保存し、個人情報を含むためGitには含めていない。

最終DBはuser_version=1、wallets1件、wallet_ledger1件、mining_claims1件、integrity_check=ok、foreign_key_checkは空。詳細はローカルの `.local-test-20261022/fresh-schema/verification.json` に保存した。再起動後も同じ2つの常設投稿を使用した。既存テストDBとユーザーの設定2ファイルは開始前後のSHA-256が一致した。

今回の実画面検証は新規作成・採掘・CSV・再起動に絞った。付与／引き去り／転送／寄付の新カラムと更新日時は実SQLiteの自動テストで確認した。手動リセットとランキングも新スキーマの自動テストで確認しており、今回の画面操作では繰り返していない。

検証後にテストBotを停止した。本番DB・本番環境設定の変更、デプロイ、マージは行っていない。


Windows CIでは、旧来の日本語printがcp1252の標準出力でUnicodeEncodeErrorになる問題を検出した。バックアップ整理のログを標準loggingへ変更し、cp1252出力環境を使う回帰検証を追加した。
