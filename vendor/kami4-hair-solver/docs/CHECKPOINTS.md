# 復帰できる基準点

## baseline-root2-200f-20260917

ユーザーが速度と品質を今後の改善の基準として採用した状態。全仕様への合格を意味しない。

- [GitHubの復帰用タグ](https://github.com/ysk424/kami4-hair-solver/tree/baseline-root2-200f-20260917)
- [プライベートRelease・バックアップ](https://github.com/ysk424/kami4-hair-solver/releases/tag/baseline-root2-200f-20260917)
- [設定プリセット](../presets/baseline-root2-200f-20260917.json)
- [200F実測値](checkpoints/baseline-root2-200f-20260917/report.json)
- [22F/23Fの交差診断](checkpoints/baseline-root2-200f-20260917/diagnosis_22_23.json)

| 項目 | 基準 |
|---|---|
| 計算コード | `24867c9439bdededd036622737748527536799de` と同一。今回のタグには復帰資料を追加 |
| 入力 | カーブ 6,757本・74,327点、CC_Base_Body 449,472三角形 |
| 根元 | **2点固定**。拡張の初期値は1点なので、タグのソースだけで設定を復元したと思わないこと |
| 計算 | 24fps、1〜200F、substeps/P/I = 4/3/3 |
| 総時間 | 80.795880秒（平均0.403979秒/F）。最終blend保存込み81.195462秒 |
| 完走 | 200F、NaN/Infなし、最終固定点の座標誤差0、全キャッシュCRC確認済み |
| 最大辺長誤差 | 0.0750601% |
| DLL SHA256 | `ea2d71f02a40ee0db6820c097784c8795132edea0dee097b70dbdd445650f0c2` |
| parameter SHA256 | `1a3e001805bf7fcf2b7e95eb7f1141c14d9226c4b2bd6b40984e51a754ac92a5` |

既知の問題: 23Fで身体内へ入る毛が見える。全体の直線区間と三角形の交差診断は22Fで27本・50区間、23Fで55本・92区間。根元2点は両フレームで入力と完全一致し、交差は4点目以降の区間にあった。これは画像中の一本との対応付けや、表示補間後の曲線全体の判定ではない。点間の交差、移動途中の通過、身体内外の扱いを改善する必要がある。現行のunsigned距離によるmin_gapは、身体内部への侵入全体の指標にならない。移動上限違反も残る。

## 復帰方法

1. タグとRelease資産を取得する。現在の作業を壊さないよう、別worktreeに基準ソースを取り出す。

   ```powershell
   git fetch origin --tags
   git worktree add ../kami4-baseline-root2 baseline-root2-200f-20260917
   gh release download baseline-root2-200f-20260917 --repo ysk424/kami4-hair-solver --dir ../kami4-backups/baseline-root2-200f-20260917
   ```

2. `SHA256SUMS.txt` と `Get-FileHash -Algorithm SHA256` でZIPの一致を確認して展開する。中の `verify_backup.py` を実行すると個別ファイルのhashも検査できる。
3. 基準の拡張へ戻す必要がある場合、未保存の作業を保存し、Blenderを終了してロード済みDLLを解放してから、同梱の `kami4_hair_solver-0.1.0-windows-x64.zip` をインストールする。
4. 展開した `baseline.blend` を開く。同じフォルダーに `cache` と `parameters.json` が必要。シーンは相対パスでそれらを参照し、根元2点・200Fの再生を復元する。
5. 再計算は基準シーンのコピーを使い、キャッシュ保存先を新しいフォルダーに変えてから行う。

Releaseには別途 `evaluated-input-200f.zip` も保存する。200Fの評価済み入力、三角形、初期形状を含み、Blenderの表示とは独立して数値比較に使用できる。

環境はBlender 5.2.2 LTS / RTX 5070 Ti / CUDA 12.9.41。129個の画像は元シーンに埋め込み済み。元シーンに残る8件の存在しない標準ノードライブラリ参照は差し替えていない。復帰用コピーで入力評価とキャッシュ再生を検証するが、他のBlender版や異なるGPUでの完全一致までは保証しない。

## 次の実験

基準タグから `experiment/<仮説名>` のブランチまたはworktreeを作り、目的・変更・同条件の比較・採用/NGを記録する。採用時は新しい基準タグを追加する。NGのブランチと測定記録は残し、基準タグは動かさない。GitHub上のソースの復帰と、Blenderにインストール済みのDLLの復帰は別の操作である。
