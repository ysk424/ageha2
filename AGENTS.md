# 髪4 保全ルール

- `kami4_solver/` の数値計算コード、設定、動的ライブラリは採用タグ `baseline-local-fk-adopted-20260917` の `extension/` と無改変。数値結果を保つため編集しない。説明用マークダウンだけは日本語正本とする。
- `vendor/kami4-hair-solver/` は終了タグ `session-end-20260917` の保存物。数値コードと検証資産は編集せず、マークダウンの説明文だけを日本語正本として保守する。
- 完全設定は `presets/local-fk-contact-20260917.json`。最小計算長30センチメートルを含み、部分的な既定ジェイソンで置き換えない。
- 統合は揚羽側の `__init__.py` と `ui.py` だけで行う。
- 変更後は `python -m unittest tests.test_vendor_integrity tests.test_markdown_language` で数値実行部の同一性と日本語文書を確認する。
- 実シーンの検証では元 `.blend` と既存キャッシュへ上書き保存しない。
