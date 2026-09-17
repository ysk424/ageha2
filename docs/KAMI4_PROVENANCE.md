# Kami4 由来情報

- コピー元: `C:\Users\azoo\git\kami4-hair-solver`
- 採用実装コミット: `eab0400d5615f3c1abe833398ab05d9f15dbf21f`
- 採用タグ: `baseline-local-fk-adopted-20260917`（記録コミット `54a6e33146509a78a93cad43f23f7cbaa7d8e327`）
- 終了・引継ぎタグ: `session-end-20260917`（`9344a2645888388b4596846a2e8c1a259a5e6638`）
- 採用 DLL SHA-256: `0c5db7c3cc80ca80b86394d25e4ff5541bb7e1af5362efd9c2245a86962a221e`
- 完全設定ファイル SHA-256: `555c8379d40805f7b9ee474e4c70d33e00de9eb4abf4633472ee484355c8b06a`
- canonical parameter hash: `f9473015f35d7d081ab5be07e23fe2b100288552af3a35456e039f6888fcd29b`

`kami4_solver/` は採用版 `extension/` とバイト単位で同一です。`tests/test_vendor_integrity.py` がランタイム全ファイルの SHA-256 を固定し、意図しない変更を検出します。

`vendor/kami4-hair-solver/` には終了タグ時点の追跡ファイルをそのまま収録しています。数値ソルバーを変更せず、揚羽側がパネル登録と入力設定だけを統合します。
