# 設計方針

現在の仕様には **Service Layer + Transaction Script** を採用する。Discordコマンド・ボタン・定時更新が同じ残高操作を利用し、SQLiteの原子的な更新を共有する構成である。

## 比較と判断

| 候補 | このBotへの適合性 | 判断 |
| --- | --- | --- |
| Service Layer | コマンド・ボタンから共通のユースケースへ入れる。寄付先判定やリセット、出力の窓口を集約できる | 採用 |
| Transaction Script | 残高・回数・履歴の更新は少数の明確な手続き。複雑なオブジェクトモデルは不要 | 採用 |
| Repository | オブジェクト集合を表現する豊かなドメインモデルがなく、現状では追加の抽象化になる | 専用のクラス階層・ORMは導入しない |
| Table Data Gateway | SQLをUIから隔離する考え方は有効。ただしこのBotの操作は複数テーブルを同時更新する | 薄いSQLiteゲートウェイとして適用 |
| Hexagonal Architecture | DiscordやDBを交換する境界の考え方は有効。完全なports/adapters化は現在の規模には大きい | 期間計算の純粋化とサービスへの依存注入を先に適用 |

これは仕様と規模に基づく設計判断であり、全用途に最適なパターンという主張ではない。

## 実際の責務

| ファイル | 責務 |
| --- | --- |
| `zrmine.py` | クライアント生成、依存の接続、起動、定期タスク |
| `commands/wallet_commands.py` | コマンド登録、権限、Discord入出力 |
| `views/` | ボタン・フォーム・ページ送り、利用時の権限確認 |
| `services/wallet_service.py` | 残高操作の共通窓口、所属国からの寄付先決定、リセット・出力の委譲 |
| `services/runtime.py` | 実行時サービスの構築 |
| `models/wallet.py` | SQLite読み書き、残高と採掘権と履歴の一括更新、操作IDの重複防止 |
| `models/wallet_schema.py` | 新規スキーマ作成とバージョン確認。旧DBの取り込みは行わない |
| `domain/mining_period.py` | Discord・設定・DBに依存しない日本時間の期間計算 |
| `services/panel_service.py` | 常設投稿の取得・更新・復旧、期間ごとのキャラ選択と再試行 |
| `services/mining_service.py` | 採掘演出・抽選・結果・Excellent通知の調整 |
| `services/wallet_export.py` | 読み取りスナップショットのCSV化、添付サイズへの対応 |

依存は基本的にコマンド／ビュー → サービス → SQLiteゲートウェイ → 純粋な期間計算へ流れる。サービスは設定とゲートウェイを受け取る。SQLトランザクション境界はゲートウェイ側に残し、サービスから複数の独立更新を呼んで残高と履歴を分離しない。設定UIや描画サービスにはDiscord依存があり、完全なHexagonal Architectureではない。

定時更新は期間またはアセットの操作履歴番号が変わった場合だけHTTP編集する。キャラ選択は通信前に保存し、更新完了の期間は通信後に保存するため、失敗後も同じキャラで再試行できる。手動リセットはDB内で完了させ、その後のパネル更新失敗で二重リセットしない。採掘側は期間判定も更新トランザクション内で実行する。

旧イベント採掘・国別統計・旧リセット画面など、現仕様から参照されないコードを削除した。既存DBや利用者の設定ファイルは削除しない。

## 検証の境界

実SQLiteテストで初期化・制約・再起動時の保持・旧形式拒否・同時更新・二重操作・期間・手動リセットを検証する。Discordアダプターのテストで権限・本人限定表示・ファイルの解放・通信失敗時の挙動を検証する。実Discordの画面操作は別の検証記録に残す。

## 参考にした一次資料

- Martin Fowler: [Service Layer](https://martinfowler.com/eaaCatalog/serviceLayer.html)
- Martin Fowler: [Transaction Script](https://martinfowler.com/eaaCatalog/transactionScript.html)
- Martin Fowler: [Repository](https://martinfowler.com/eaaCatalog/repository.html)
- Martin Fowler: [Table Data Gateway](https://martinfowler.com/eaaCatalog/tableDataGateway.html)
- Alistair Cockburn: [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture)

## アセットの境界

`commands/asset_commands.py` と `views/assets_view.py` は管理者本人限定の入出力を担当し、`services/asset_catalog.py` が画像検証、SQL、初回取り込み、セリフ抽選、バックアップをまとめる。現規模ではサービスとSQLiteゲートウェイを同じクラスに置き、ORMやRepository階層は追加しない。ウォレットとは別DBで、画像変更が残高処理のスキーマへ影響しない。

画像はランダムなファイル名で不変ファイルとして保存し、DBの参照をトランザクションで差し替える。更新にはrevisionを要求して古い画面からの上書きを防ぐ。画像参照の読み取り期間はファイル内容をbytesへ読み終えるまで保持する。採掘開始時に演出と結果画像のbytesを確定し、途中の差し替え・削除がその採掘やExcellent通知に影響しない。`services/asset_delivery.py` がDiscord添付とストリームの解放を扱う。

非表示は抽選から除外し、完全削除はDB行とキャラのセリフを消す。履歴に削除内容そのものを残さず、操作種別・対象ID・実行者・時刻だけを保持する。古いバックアップや既存Discord投稿は別の保存物として残る。アセットZIPは読み取り期間を保持してDBと参照画像を取得し、未参照ファイルを含めない。
