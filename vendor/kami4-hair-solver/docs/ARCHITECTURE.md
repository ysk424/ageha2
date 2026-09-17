# K4-FBS 実装構造

> この文書は初版の構造を記録した履歴資料です。現在のBVH区間接触、非表示延長、局所FK、採用設定と原仕様との差分は [ACES現行設計書](ACES_DESIGN_JA.md) を参照してください。以下の固定回数・転送経路の説明を、そのまま現行版の説明として使用しないでください。

## 入力と所有権

元のCurvesのsplineをstrandとして取り込み、点数とstrand数を保つ。ゼロ長辺を含むstrandのみ、始点・終点・点数を保って弧長で再標本化する。今回の対象は0始まりID 2089、2422。根元2点を固定する場合は、再標本化した点の材料位置を評価済み入力へ対応付け、元の長い第1辺へ飛び戻らないようにする。

出力は独立したHair Curves。ソースのpositionは書き換えない。入力の評価・フレーム変更・Curves更新はBlenderメインスレッドで実行する。modal Bakeも1フレームずつメインスレッドで進む。

## Native life cycle

```text
k4_create(config, positions, offsets, kinematic_mask)
  → optional k4_set_mesh(vertices, triangles)
  → k4_prepare(analytic_collider_count)
  → repeated k4_step / k4_download
  → k4_destroy
```

createで点・strand・接触・scratchを確保し、質量とrest辺長から五重対角bending matrixを作ってCholesky分解する。meshのBVH topologyはset_meshで一度だけCPU上で構築する。prepareでは固定フレーム経路をCUDA Graphへcaptureしてinstantiateする。step中にdevice allocation、graph再構築、反復数の増加はない。コライダー数が変化した場合は再初期化を要求する。

GPU転送はlegacy stream、計算は専用nonblocking streamを使用し、Graph起動前に明示的に転送完了を待つ。グラフ終了eventを待ってから診断と位置を取得する。CUDA error、NaN/Inf、BVH stack overflowを明示的なエラーとして返す。

## 計算経路

`substeps=4、P=3、I=3` を全試験・実髪・benchmarkに共通使用する。

1. 減衰と重力で予測。
2. 事前分解した線形bendingを前進・後退代入。
3. 長さだけのtridiagonal solveとcontact projectionをP回。
4. 最終contact projection。
5. 速度再構成と位置接触impulseの整合処理。
6. accumulated normal/tangent Coulomb impulseをI回。
7. 診断とcommit。

曲げ係数・分解と代入はFP64。短い髪の剛性と質量の比が大きいため、FP32 factorではCPU基準との差が増大した。strandの根元を基準に座標を平行移動して代入する。GPUの位置・速度・長さ・接触はFP32。CPU oracleは別のNumPy/SciPy実装でFP64計算する。

2–8、9–16、17–32、33–64、65–128、129–256点の6bucketへ初期化時に分類する。32点までは1 thread/strand、長いstrandは64/128/256 threadのblockを使う。長いstrandのbendingは2×2 affine prefix、lengthはparallel cyclic reductionで全threadが計算に参加する。プロフィールは `outputs/bucket_profile.json`。

## 接触と原仕様との差

plane、sphere、capsule、infinite cylinderは解析的なnode projection。位置とquaternionをsubstepで補間する。接線impulseは接平面上のベクトルで、半径 `mu * jn` の円板へ投影する。永続anchor、Aitken、KKT、CCD、自己衝突は導入していない。

原仕様の速度再構成後に、そのまま法線相対速度だけを測ると、位置投影が既に床方向速度を消しており、支持impulseが0となって摩擦上限も0になる場合がある。本実装では、各位置投影の法線変位から `j_support = delta / (h * inverse_mass)` を累積し、一旦その運動量を速度から差し引いてからwarm startと法線impulse solveを行う。これにより位置投影の支持を二重計上せずCoulomb摩擦へ渡す。これは原仕様§6の擬似コードに明記されていない整合処理であり、実装上の判断としてここに明記する。CPU oracleも同じ収支を検証する。

ユーザーの「現在のkami-hair-solverと同じコライダー入力」を優先し、身体を解析proxyへ置換せず、元の449,472三角形へのnode/surface接触を追加した。BVHは固定topologyをGPUで各substepにrefitする。メッシュ接触は両面の離散surface距離であり、閉じた体積の内外判定や連続衝突判定ではない。接触距離より遠いqueryは枝刈りし、meshの診断gapはcontact tolerance以上をその値で下限表示する。meshのchord penetration boundは解析円柱の式では評価できず、0というnativeの値を「保証された0侵入」と解釈してはならない。

## 診断とcache

各frameにGPU時間、転送時間、点・strand・接触数、max/p99辺長誤差、node gap、円柱chord bound、substep最大移動、移動上限超過数、法線/接線impulse、摩擦円錐違反、NaN/Inf、overflow、allocation/launch数を記録する。長さ・gapはframe内substepの最大/最小を取る。p99はstrandの末尾sentinelを除いた辺のlower percentile。移動上限は全入力の最短辺を使う原仕様の条件であり、超過を停止や補正で隠さず数として記録する。

`K4C1` frameファイルにはschema、frame、点数、topology SHA256、parameter SHA256、payload CRC32を格納する。ファイルは一時ファイルからatomic replaceする。manifestにはbinary hash、Blender版、入力、補正strand IDも保存する。異なるtopology/parameterのcacheは拒否する。Resetは既存cacheを保ち、Initialize/Bakeは新しいgenerationのframe一覧と診断を開始する。

T1～T3のXY拘束は一般的なplane-axis設定であり、test IDによる物理式の切替ではない。実髪ではこの拘束を無効にする。
