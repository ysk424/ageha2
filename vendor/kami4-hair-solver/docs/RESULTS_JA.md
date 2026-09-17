# Kami4 実行結果 — 2026-09-17

> 初版0.1.0の実測記録です。現行の採用版・局所FK v2の結果と検証範囲は [ACES現行設計書](ACES_DESIGN_JA.md) と [局所FK実験記録](experiments/local-fk-contact-20260917/README.md) を参照してください。下記の結果を現在の完全設定で再実行した結果とは扱いません。

**一括受入: 不合格。** 動作するBlender拡張、200frameの計算・cache再生、3試験、10万点benchmarkを作成した。未達を成功とは扱わない。機械可読の全判定は [acceptance.json](../outputs/acceptance.json)。

## 保存場所と入力

- 新規repo: `C:/Users/azoo/git/kami4-hair-solver`
- [現在のBlenderと同じ入力を接続したシーン](../outputs/kami4_current_scene.blend)
- [拡張のBake操作で検証したシーン](../outputs/kami4_verified_bake.blend)
- [インストール用ZIP](../dist/kami4_hair_solver-0.1.0-windows-x64.zip)
- [共通parameter JSON](../extension/parameters.json)

保存シーンの操作用cacheは `outputs/scene_cache`。検証結果の原本 `outputs/real_final` とは別にしている。現在のBlenderで Reset → Simulate → Replay を実行し、保存済み1Fと座標が完全一致することを確認した。[実操作の確認](../outputs/live_verification.json)

ヘアーは「カーブ」6,757本・74,327点。コライダーは「CC_Base_Body」225,184頂点・449,472三角形。原ファイル `C:\Users\azoo\gitlocal\bln_Lumi-1\pipleline-test\Lumi-1-HOU-HAIRFINISHED 4.blend` は上書きしていない。元のkami / kami3のcode・cacheも変更していない。

## 判定表

| 項目 | 実測 | 判定 |
|---|---|---|
| T1 中央圧縮 | 高さ 0.223093 m、頂点x 0.000003 m、主要airborne region 1個 | 試験条件合格 |
| T2 円柱落下 | 最高点 0.240040 m、左右材料長差 3.58e-07 m | 試験条件合格 |
| T3 片側引張り | 左側材料長 0.154226 m減少、摩擦ありslip 347F、mu=0は 1F | 試験条件合格 |
| 3試験の共通設定 | B=1e-6、damping=8、mu=0.35、substeps/P/I=4/3/3 | 合格 |
| 実髪完走 | 200/200F、NaN/Inf・strand脱落・fatal errorなし | 合格 |
| 実髪長さ | 最大 0.80832%、p99 0.003886% | 合格 |
| 実髪node接触 | 最大 31.609 µm侵入、許容10 µm | **不合格** |
| 移動上限 | 最大8分割でも指定root移動が上限の 22.94倍 | **不合格** |
| 合成10万点 | warm-up 120 + 計測600F、接触点 [90909, 90909] | 合格 |
| 合成性能 | native中央値 1.240 ms、Blender書き戻し込み 3.145 ms | 合格 |
| cache | 別Blenderプロセスで200frame CRC検査、1/7/100/200Fを実再生 | 合格 |
| CPU/GPU最終形 | 高さ・左右材料長は2%以内、slip開始は一致、T1微小残差の相対2%は未達 | **厳密比較は不合格** |

3試験はXY拘束した同一3D kernelで実行した。試験fps=240、T1=8秒、T2=5秒、T3=8秒。T1は100辺・L=1mの共通rest lengthで中央seedから開始し、0.36m圧縮する。T3はT2の位置と速度を引き継ぎ、右端を0.18m引く。試験内の移動上限違反は {'T1': 0, 'T2': 0, 'T3': 0, 'T3_mu0': 0}。

![3試験](figures/three_tests.png)

## 実シーンの速度

評価済み入力を再生した実髪200Fは、native中央値 **2.493 ms**、CPU転送・位置取得込み **4.887 ms**。

Blender拡張のBake操作では、身体と髪の評価を含め200Fを **85.38秒**、平均 **0.427秒/frame**、中央値 **422.28 ms/frame**。その実行中のnative中央値は **26.89 ms**。独立ベンチマークと実シーン内の時間を混同しない。この実シーン全体は24fps動作ではない。native時間差の原因はここでは断定していない。ここで測定したのはヘアー計算・cache保存であり、Cycles/Eeveeの画像レンダリング時間は未測定。

拡張Bakeの最終座標と評価済み入力を使ったnative実行との差は **0.0 m**。入力の評価座標も抽出時から2e-7m以内で一致した。

![実髪診断](figures/real_diagnostics.png)

入力評価だけを1〜15Fで計測した別のprobeでは、frame変更252.46ms、髪取得67.56ms、mesh取得58.38ms、合計378.34msだった。非入力objectを隠した場合380.53ms、評価済みmeshを直接読む場合380.08msで改善しなかったため、これらの変更は採用していない。[測定値](../outputs/blender_evaluation_probe.json)

## 未達の再現

1. 最短辺は 0.000273042m、移動上限は 0.000068261m/substep。102Fの指定root移動は 0.012527951m/frame。8分割でも 0.001565994m。strandごとの最短辺で条件を緩めても、strand 1794で 20.81倍。これはsolve前に決まるkinematic入力の問題であり、収束反復では解消できない。[数値と最小入力](../outputs/motion_bound_proof.json)
2. mesh接触の失敗はstrand 5396、11点、42,421三角形へ縮小して再現した。7Fで約31.6µmのsurface侵入が残る。`python tools/replay_failure.py` でBlenderなしに再現できる。[fixture](../outputs/minimal_mesh_failure/fixture.npz)
3. T1の最終max辺長残差はCPU 1.59e-07、GPU 1.31e-06。両者とも物理試験の1%を十分下回るが、残差自体を分母にした2%相対一致は満たさない。許容条件を変更して合格にはしていない。[全scalar比較](../outputs/cpu_gpu_comparison.json)

## 実装と検証の範囲

- C++20/CUDA、opaque handleのC ABI。C11 consumerによる作成・prepare・step・download・破棄を検証した。
- 独立oracle等のPython 15テストが合格。非均一辺長、全6bucket、曲げ、長さ、全解析形状、摩擦、動くplane、無接触全経路、修復したroot tangent、CRC破損を含む。
- 全frameでdevice allocation=0、実髪のkernel数=[129]。CUDA Graphは初期化時に一度だけ作成。
- 短strandは1 thread、長strandはblockでaffine prefix/PCR。profileは [bucket_profile.json](../outputs/bucket_profile.json)。
- Initialize / Simulate / Reset / Bake / Replayと、再起動後のcache再生を検証した。
- mesh接触はユーザーの入力指定を優先して追加した両面node/surface方式。edge接触・体積内外保証・CCDはない。
- 投影による支持impulseの整合処理を明示的に加えている。[数式上の補足と構造](ARCHITECTURE.md)

次の方式は [ADR](ADR-001-acceptance.md) に一つだけ記した。原仕様を変更した合格版や、CPU fallback・表示補正で隠した結果としては提出しない。

## 環境・hash

NVIDIA GeForce RTX 5070 Ti, 616.92 / Blender 5.2.2 LTS / CUDA Toolkit 12.9.41 / MSVC 19.44。

- binary SHA256: `ea2d71f02a40ee0db6820c097784c8795132edea0dee097b70dbdd445650f0c2`
- parameter SHA256: `1a3e001805bf7fcf2b7e95eb7f1141c14d9226c4b2bd6b40984e51a754ac92a5`
- package SHA256: `e969b9d267a6cd13362a721a79a00353f3cb70be42d6d85068515b94bb69bb0f`
