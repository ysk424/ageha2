# Kami4 保全ルール

- `kami4_solver/` は採用タグ `baseline-local-fk-adopted-20260917` の `extension/` と無改変。数値結果を保つため編集しない。
- `vendor/kami4-hair-solver/` は終了タグ `session-end-20260917` の追跡ファイルの無改変コピー。編集しない。
- 完全設定は `presets/local-fk-contact-20260917.json`。最小計算長30cmを含み、部分的な既定JSONで置き換えない。
- 統合は揚羽側の `__init__.py` と `ui.py` だけで行う。
- 変更後は `python -m unittest tests.test_vendor_integrity` で同一性を確認する。
- 実シーンの検証では元 `.blend` と既存キャッシュへ上書き保存しない。
