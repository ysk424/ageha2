# Kami4 保全ルール

- `kami4_solver/` は `../kami4-hair-solver/extension/` の無改変コピー。数値結果を保つため編集しない。
- `vendor/kami4-hair-solver/` は元リポジトリの追跡ファイルの無改変コピー。編集しない。
- 統合は揚羽側の `__init__.py` と `ui.py` だけで行う。
- 変更後は `python -m unittest tests.test_vendor_integrity` で同一性を確認する。
- 実シーンの検証では元 `.blend` と既存キャッシュへ上書き保存しない。
