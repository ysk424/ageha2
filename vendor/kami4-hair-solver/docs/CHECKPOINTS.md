# 復帰できる基準点

## session-end-20260917（作業終了・電源断用）

局所FK v2の採用設定と200F結果を維持したまま、ユーザーが確認していた87F・PERSPビューを別名保存。独立したBlenderで開き直し、完全設定・DLL、200F cacheのCRC、87/1/200Fの自動再生を確認した。数値処理変更・再シミュレーションはなし。採用タグと元シーンは保持している。

- [再開用の記録](RESUME_JA.md)
- [終了用Release](https://github.com/ysk424/kami4-hair-solver/releases/tag/session-end-20260917)
- [保存時の状態](sessions/session-end-20260917/session_state.json)、[開き直し検証](sessions/session-end-20260917/reopen_verification.json)、[バックアップhash](sessions/session-end-20260917/backup.json)

## baseline-local-fk-adopted-20260917（ユーザー採用・現在の基準点）

2026-09-17、ユーザーが「現時点で満足できる性能」と局所FK v2を採用し、PUSHを指示。下記 `review-local-fk-200f-20260917` と同じソース実装・拡張0.3.0・DLL・完全設定・200Fキャッシュ・保存シーンを新しい基準点とする。採用記録のみ追加し、数値処理、パラメータ、既存シーンの設定を変更せず、再計算もしない。既知の残留交差などの測定記録を保持する。

- [採用済み復帰点](https://github.com/ysk424/kami4-hair-solver/releases/tag/baseline-local-fk-adopted-20260917)
- [変更していない200Fバックアップ](https://github.com/ysk424/kami4-hair-solver/releases/tag/review-local-fk-200f-20260917)
- [採用記録とhash](experiments/local-fk-contact-20260917/adoption.json)

復帰にはレビューReleaseの `review-local-fk-200f-20260917.zip` を展開し、同梱拡張0.3.0をインストールして `scene.blend` を開く。cache・parameters.jsonも同梱される。以後の実験はこの採用タグから分岐し、基準資産を上書きしない。

## review-local-fk-200f-20260917（局所FK衝突修復・後にユーザー採用）

曲げ5e-7の採用版に局所FK修復を追加。200Fの交差区間545→0、全200F中の最大6区間（76F、2本）。200F計算＋保存106.9436秒（変更前61.4487秒）。固定2点を維持。表示の長さ誤差は改善したが、最大移動量・最終速度は増加し、半径込みの残留接触と少数の交差がある。今回の変更前の採用値へは下記 `baseline-bending50-adopted-20260917` から復帰できる。

- [実装・測定・残課題と復帰方法](experiments/local-fk-contact-20260917/README.md)
- [確認用Release](https://github.com/ysk424/kami4-hair-solver/releases/tag/review-local-fk-200f-20260917)

全体を同じ回転で動かした最初の試行v1は毛先変位の増幅により不採用。タグ `experiment-local-fk-v1-20260917` は履歴保存のみ。

## baseline-bending50-adopted-20260917（ユーザー採用・衝突修復前の復帰点）

2026-09-17、ユーザーが曲げ剛性5e-7を新しい既定値として採用。衝突の残課題は別に修正する指示。拡張0.2.3は既定の曲げ剛性のみ変更し、数値DLL・200Fの結果は下記試行2と同一。ほかの既定値は変更しない。実シーンを復元する完全設定は `presets/trial2-bending50-20260917.json`（根元2点、最小計算長30cm、length_passes=8）。

復帰にはこのタグのソースと拡張0.2.3、および下記試行2Releaseの保存済みscene.blend・cache・parameters.jsonを使用する。試行2Releaseの拡張0.2.2でも同じ数値結果を再生できる。DLL SHA256は `1cd10bd1bcd301f798d7394e30aef8d30e156bc0e7026c59500baaeedaf4d9be`。採用時に再計算していない。交差区間545は交差した毛545本という意味ではなく、200Fの交差した直線区間数。

## trial2-bending50-200f-20260917（パラメータ調整2回目・後にユーザー採用）

基準から曲げ剛性だけ1e-6→5e-7。200F計算後71Fを表示。頭頂の上下差は3.8993→3.6251cm、外側の距離p95は4.1590→3.4729cmだが約2cmの目標には未達。200F交差区間104→545、表示部分の最大辺長誤差1.7943→3.3019%。モデル・DLL・根元2点固定などの変更なし。

- [試行2の仮説・結果・復帰方法](experiments/trial2-bending50-20260917/README.md)
- [プライベートRelease](https://github.com/ysk424/kami4-hair-solver/releases/tag/trial2-bending50-200f-20260917)
- [パラメータ試行一覧](PARAMETER_TRIALS.md)

## trial1-bending80-200f-20260917（パラメータ調整1回目・不採用、復帰済み）

ユーザー確認では見た目の違いが小さく、2026-09-17に復帰を指示された。曲げ剛性1e-6と30cm版の既存200Fキャッシュに戻し、102Fの座標一致を確認して別名保存した。次の条件は検討段階で、追加シミュレーションはしていない。[復帰記録](experiments/trial1-bending80-20260917/restoration.json)。以下は試行時点の測定。

30cm版＋日本語ACESパネル `be8fd53` から、曲げ剛性だけ `1e-6 → 8e-7`（20%減）。200Fを1回計算し102Fを表示。NaN/Infなし、根元2点固定は維持したが、23Fの交差区間は37→116、200Fは104→245、表示部分の最大辺長誤差は1.7943%→2.5672%。見た目の変化はあるが改善版として採用せず、比較結果を残して打合せのため停止する。

- [仮説・変更量・測定と復帰方法](experiments/trial1-bending80-20260917/README.md)
- [比較用のプライベートRelease](https://github.com/ysk424/kami4-hair-solver/releases/tag/trial1-bending80-200f-20260917)
- 直前の数値状態：[30cm版Release](https://github.com/ysk424/kami4-hair-solver/releases/tag/review-bvh-extension-30cm-200f-20260917)。Nパネルのソースは `be8fd53`。

## review-bvh-extension-200f-20260917（確認用・正式採用は保留）

BVH全区間接触と最小20cmの非表示延長。ユーザーの中断指示で画面確認用に保存した版。

- [実験と残課題](EXPERIMENT_20260917.md)
- [200F測定](experiments/review-bvh-extension-200f-20260917/report.json)
- [全200Fの固定点・長さ・CRC検査](experiments/review-bvh-extension-200f-20260917/all_frames_validation.json)
- [164F・基準](experiments/review-bvh-extension-200f-20260917/baseline_164.png) / [164F・確認用](experiments/review-bvh-extension-200f-20260917/bvh_extension_164.png)

23Fの交差0、200Fの交差39（基準716）。前髪の立ち上がりと後半の交差が残る。表示部分の最大辺長誤差1.00853%、内部を含め1.12977%。固定2点の評価座標との差は最大0.0000001192m（約0.12µm）。厳密な全受入条件への合格ではない。

別拡張 `kami4_bvh_hair_solver`（Kami4 BVHパネル）を使う。ReleaseのZIPを展開し、同梱拡張をインストールしてscene.blendを開く。cacheとparameters.jsonは同梱され、相対パスで再生できる。基準への復帰は、従来のKami4拡張と下記基準シーンを使う。両方のソース・DLL・シーンを混ぜない。

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
