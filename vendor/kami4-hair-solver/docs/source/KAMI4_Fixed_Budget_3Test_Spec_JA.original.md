# `kami4-hair-solver` 

## 0. 研究としての位置づけ

`kami3-hair-solver` 完全連成に近いactive-set KKT、非線形摩擦予測、Aitken緩和、CCD、適応分割を組み合わせると、今回の目的に対して計算量と収束条件が大きくなりすぎることを示した研究結果として保存する。

`kami4-hair-solver` 別リポジトリで新しく作る。

研究では仮説が通らないこと自体も成果であり結果を残して次のバージョンを設計しなおします。


## 1. kami3から確定した事実

添付レポートから、次をkami4の出発点とする。

1. 6,757本・74,327点の全髪は、64 substepsでも8フレームまでで停止した。
2. 1フレーム約5.8～28秒で、実時間用途から大きく離れた。
3. CPU FP64でも別のstrandで停止したため、CUDA精度だけが原因ではない。
4. 無接触のCPU/GPUは一致したが、接触後の長時間軌道は一致しなかった。
5. 摩擦なしの円柱落下は通ったが、摩擦ありで停止した。
6. 重力あり圧縮では中央ではなく左右に山が生まれた。中央ruckは自動的に一意ではない。
7. 現行CUDAでは、strand内solveの主処理をwarp内のほぼ1 threadが担当していた。
8. 最長到達条件は最大64 substeps、64 SQP、64 outer、CCD最大128であり、固定予算ではなかった。

したがってkami4は、収束判定を改良して同じ構成を延命する研究ではない。**収束するまで回す構造そのものを外す。**

---

## 2. 研究質問と最終完成像

kami4が答える質問は1つだけである。

> 厳密な連成KKTを使わず、計算回数を固定した分割解法で、同じ1次元材料モデルが「圧縮」「円柱落下」「片側引張り」の3試験を、実用的な誤差と速度で通せるか。

最終成果物は、Windows 11・RTX 5070 Ti・Blender 5.2 LTSで動作する `kami4_hair_solver` 拡張である。3D Curves、動くroot、kinematicな解析コライダー、GPU計算、cache再生を持ち、次を同時に満たす。

- 3D実装を同一平面へ拘束してT1～T3を実行できる。
- 6,757本・74,327点の実髪を200 frame計算できる。
- 100,000点の合成データで固定計算量を維持する。
- 接触数によってNewton/outer反復回数が増えない。
- 失敗をCPU fallbackや事後的な見た目補正で隠さない。

---

## 3. 3試験に本当に必要な条件

### 3.1 共通して必要

| 条件 | 必要な理由 |
| --- | --- |
| ほぼ一定の辺長 | 押した長さが伸びに逃げず、落下時にも全長が保たれるため |
| 曲げ抵抗 | 鋭い折れだけで解を作らず、丸いruckと円柱沿いの形を作るため |
| 質量と重力 | 円柱の左右へ垂れ、tableへ落ち着くため |
| 速度減衰 | 最終形と引張応答を有限時間で観測するため |
| table/cylinderの片側接触 | 障害物の内部へ見た目上入り込まないため |
| 端点のkinematic制御 | 圧縮と引張りを同じ材料へ与えるため |
| cylinderとの接線抵抗 | 試験3で、引いた側と反対側の長さが変わるため |

### 3.2 試験1だけに必要

- 左右端を同じ量だけ、十分ゆっくり動かす。
- 上向きの中央imperfectionを初期条件として明示する。
- tableの摩擦を0または十分小さくする。
- 中央へ山ができることを要求するなら、中央を選ぶ初期条件が必要である。

完全に平らで左右対称なrodは、上と下、さらに床上のどの位置にruckを作るかが一意でない。中央seedなしで「必ず中央へ盛り上がる」をソルバーの合格条件にするのは不適切である。

### 3.3 試験2だけに必要

- 静止した円柱とtable。
- 重力。
- 円柱法線方向の接触補正。
- 落下後に振動を減らす減衰。

T2では動くコライダー用CCDは必要ない。1 substepの最大移動を制限し、静止円柱への離散接触を使う。

### 3.4 試験3だけに必要

- 試験2の最終状態を初期状態として使う。
- 片側端点を十分ゆっくり動かす。
- 接触点で法線impulseと接線impulseを求める。
- 接線impulseをCoulomb上限内へclampする。
- 前回の接触impulseをwarm startできる安定したcontact ID。

試験3の最小条件は「摩擦ありで抵抗し、上限へ達したら滑る」ことである。静止摩擦係数と動摩擦係数を別々にし、永続anchor、Aitken緩和、非線形摩擦energyを同時に持つことは必要条件ではない。

---

## 4. kami4の範囲外にする条件

次は、kami4の最終完成像に含めない。

- 完全連成KKT
- active contactを含むNewton/SQP外側収束ループ
- KKT residual `1e-5` を合格の中心にすること
- CPU/GPUの200フレーム全頂点軌道 `1e-4` 一致
- 静止摩擦と動摩擦の別係数
- 永続的な接線anchor
- Aitken緩和
- 摩擦方向の非線形予測solve
- 一般CCD
- 一般mesh collider
- edge-cylinder接触の常時solve
- 自己衝突
- twist
- exact elastica Hessian

---

## 5. 新しい数値仮説: K4-FBS

方式名を **K4-FBS: Kami4 Fixed-Budget Split solver** とする。これはkami3のACES-KKTとは別方式である。

構成は次の3つに分ける。

1. 事前分解可能な線形implicit bending
2. chain専用の長さ補正と局所contact projection
3. 速度レベルの局所Coulomb impulse

「残差が小さくなるまで反復」しない。substep数、長さ/contact pass数、impulse sweep数を最初に固定する。

### 5.1 状態

点 `x_i in R^3`、速度 `v_i`、質量 `m_i`、rest辺長 `l_i`、kinematic maskを持つ。実髪では先頭点をroot位置へ固定し、必要なら先頭2点をroot transformで動かしてroot tangentも固定できる。T1～T3では全点、外力、コライダーをXY平面へ置き、完成した同じ3D kernelを平面問題として検査する。2D専用solverは作らない。

### 5.2 外力予測

```math
y_i=x_i+h v_i+h^2 g
```

速度減衰は

```math
v_i\leftarrow\exp(-d h)v_i
```

とする。

### 5.3 線形implicit bending

辺長が異なる場合にも直線でenergyが0になるよう、rest lengthから線形離散曲率

```math
q_i(x)=\frac{2}{l_{i-1}+l_i}
\left(
\frac{x_{i+1}-x_i}{l_i}
-\frac{x_i-x_{i-1}}{l_{i-1}}
\right)
```

を作り、ロングストレート用の最小曲げenergyを

```math
E_b(x)=\frac{1}{2}\sum_i B_i\bar{l}_i\|q_i(x)\|^2,
\qquad
\bar{l}_i=\frac{l_{i-1}+l_i}{2}
```

とする。等間隔 `l` では `B/(2l^3)` を係数とする二階差分energyに一致する。1 substepの曲げ位置は

```math
(M+h^2 K_b)z=M y
```

で求める。

`A=M+h^2 K_b` はtopology、質量、`h`、`k_b` が同じ間は一定なので、最初にbanded CholeskyまたはLDLT分解を1回だけ行い、各substepではforward/back substitutionだけ行う。

この曲げは完全なDiscrete Elastic Rodではない。しかし直線rest shape、丸いruck、円柱drapeの3試験に必要な「曲率を嫌う性質」は持つ。完全な回転frameやtwistは現在の必要条件ではない。

### 5.4 chain専用の辺長補正

各辺の拘束を

```math
c_i(x)=\|x_{i+1}-x_i\|-l_i=0
```

とする。現在位置で線形化した

```math
(J W J^T+\alpha I)\lambda=-c
```

を解き、

```math
\Delta x=WJ^T\lambda
```

で補正する。

1本のchainでは `J W J^T` はtridiagonalである。小規模CPU oracleはThomas法、完成版GPU runtimeはstrandごとの事前確保されたtridiagonal solveを使う。非線形性のため、1 passで厳密にしようとせず固定2～4 passだけ行う。

これは全変数・全contactのKKTではない。長さだけに限定した `O(points)` の直接solveである。

### 5.5 table/cylinderの位置contact

kami4はnode contactを基本方式とする。

- table: `y_i >= r_h`
- circle断面: `||x_i-c|| >= R+r_h`

侵入nodeは、最近表面へ法線方向に直接戻す。table/circle投影後に辺長が変わるため、長さ補正とcontact投影を固定回数だけ交互に行い、最後はcontact投影で終える。

node間のchordが円柱へ入る最大量は、おおよそ

```math
s=R-\sqrt{R^2-(l/2)^2}
```

で評価する。`s <= contact_tolerance` なら、3試験ではnode contactを十分条件とする。満たさなければ、最初にuniform resamplingで `l` を短くする。それでも満たせない場合だけedge contactを追加する。

100辺、`L=1`、`l=0.01`、`R=0.12` では `s` は約0.000104 mである。許容値を0.15 mm以上に設定するなら、最初からedge contactを連成系へ入れる必要はない。

### 5.6 速度レベルの接触impulse

位置補正後に

```math
v_i=(x_i^{new}-x_i^{old})/h
```

を作る。collider表面速度をframe間transformから求め、`v_rel=v_hair-v_collider` とする。接触点の法線相対速度を `v_n`、接線相対速度を `v_t`、effective inverse massを `w_c` とする。

法線impulseの更新:

```math
\Delta j_n=(v_n^{target}-v_n)/w_c
```

```math
j_n^{new}=\max(0,j_n^{old}+\Delta j_n)
```

接線impulseの更新:

```math
\Delta j_t=-v_t/w_c
```

```math
j_t^{new}=\operatorname{clamp}
(j_t^{old}+\Delta j_t,-\mu j_n^{new},+\mu j_n^{new})
```

実際に速度へ与えるのは、新旧impulseの差である。`|j_t| < mu*j_n` なら接線速度を0へ近づけ、上限に達すれば滑る。別のstick/slip状態機械、永続anchor、非線形摩擦solveを持たない。

3Dでは接線impulseを接平面内のベクトルとして保持し、半径 `mu*j_n` の円板へprojectする。T1～T3の平面条件では、このベクトルの一成分だけが非ゼロになる。

---

## 6. 1 substepの固定処理

```text
1. damping と重力で y を予測
2. 事前分解済みAでimplicit bendingを1回solve
3. root位置を設定
4. 次をP回だけ繰り返す（初期値 P=3）
   a. chain length tridiagonal solveを1回
   b. table/cylinder node projectionを1回
5. contact projectionを最後に1回
6. 新位置から速度を再構成
7. normal/tangent sequential impulseをI sweep（初期値 I=3）
8. root速度をkinematic目標へ設定
9. 状態をcommit
```

固定初期予算:

```text
substeps per frame = 4
length/contact passes P = 3
impulse sweeps I = 3
```

最終設定として許可する値は `substeps in {2,4,8}`、`P in {2,3,4}`、`I in {2,3,4}` に限る。64 substeps、64 outerのような設定は禁止する。

### 6.1 安全条件

一般CCDを使わない代わりに、各substepで

```math
\max_i\|x_i^{new}-x_i^{old}\|
\le 0.25\min(l_{min},R)
```

を試験プロトコル側で満たす。超えた場合はソルバーを収束させるのではなく、端点速度またはframe stepを下げて試験条件をやり直す。

---

## 7. 同じモデルであることの定義

3試験で同じにするもの:

- point/edge数とrest length
- 質量と重力
- 曲げ係数 `k_b`
- damping
- cylinderとの摩擦係数 `mu`
- substeps、P、I
- 長さ、曲げ、contact、frictionのコード経路

変えてよいもの:

- 初期位置
- kinematic端点の軌道
- table/cylinderの有無
- tableとcylinderのcontact material
- 試験2の最終状態を試験3へ渡すこと

ソルバー内で `if test_id == ...` により物理式を切り替えることは禁止する。

---

## 8. 3試験の固定プロトコル

### T1: 左右圧縮

```text
L = 1.0 m
segments = 100
table y = 0
gravity = 9.80665 m/s^2
total compression = 0.36 L
table friction = 0
```

中央 `0.2L` の範囲に、最大高さ `0.02L` の滑らかな上向きimperfectionを作り、arc lengthがLになるよう再sampleする。左右端を対称に、少なくとも240 frameかけて近づける。

合格:

- 中央を含む1つの主要なairborne regionができる。
- 最大点が中央から `0.08L` 以内。
- 最終最大高さが `0.10L` 以上。
- max辺長相対誤差 `<= 1%`、p99 `<= 0.5%`。
- table penetration `<= 0.1l`。
- NaN/Infなし。

要求しない:

- 高さ0.2564Lとの一致
- 全frameで高さが厳密単調
- exact equilibrium
- seedなしで中央を自動選択

### T2: 円柱落下

```text
L = 1.0 m
segments = 100
R = 0.12 L
cylinder center y = R
table y = 0
initial strand y = 0.36 L
```

T1と同じ質量、曲げ、damping、solver budgetを使う。左右対称な水平状態から落とし、平均速度が十分小さくなるまで最大5秒計算する。cylinder摩擦 `mu` はT3と同じ値を使う。

合格:

- 左右の材料長差が `0.03L` 以下。
- 円柱の左右へ両端が垂れる。
- 最高点が円柱上端＋guide radiusの `0.02L` 以内。
- node penetration `<= 0.1l`。
- chord penetrationの理論上限がcontact tolerance以内。
- 最終0.5秒の平均速度 `<= 0.01L/s`。
- max辺長相対誤差 `<= 1%`。

要求しない:

- CPU/GPUの時刻ごとの同一軌道
- 端点 `+-0.4068L` との一致
- exact KKT residual
- 一般CCD

### T3: T2から片側引張り

T2の合格状態から右端を `0.18L`、一定の低速度で右へ動かす。cylinder、材料値、`mu`、solver budgetは変更しない。

本試験に加え、同じ状態で `mu=0` の対照runを1回だけ行う。これはモデル調整用ではなく、摩擦効果の有無を判別するcontrolである。

合格:

- `mu>0` で、初期区間に接線relative speedが抑えられる。
- その後 `|j_t|` が `mu*j_n` の上限へ達し、滑りが始まる。
- 右へ0.18L引いた後、左側の垂れ下がり材料長が少なくとも `0.05L` 減る。
- `mu>0` の滑り開始が `mu=0` より遅い。
- 全接触で `|j_t| <= mu*j_n + tolerance`。
- cylinder/table penetrationと辺長誤差がT2の条件内。
- NaN/Infなし。

要求しない:

- 静止摩擦係数と動摩擦係数の分離
- capstan方程式への厳密一致
- 接触anchorの長期保存
- 摩擦力と法線力の完全Newton連成

---

## 9. 正しさの比較方法を変更する

接触の追加・解除は不連続なので、FP32とFP64で1つの接触時刻がずれると、長時間後の全頂点位置は大きく離れ得る。したがって、長時間の点ごとの軌道一致を3試験の必要条件にしない。

CPU/GPUで比較するもの:

- 1 substep・無接触の位置と速度
- 1回のlength solve
- 1回のcontact projection
- 1回のnormal/tangent impulse
- 各試験の最終height、左右材料長、min gap、辺長誤差
- T3のslip開始時間またはpull displacement

許容差:

- 単一kernel/単一substep: normalized RMS `<= 1e-5`
- 最終形のscalar指標: 相対差 `<= 2%`
- slip開始: `<= 2 frame` またはpull量 `<= 0.01L`

両方が各試験の合格範囲に入っていれば、長時間の全頂点座標が一致しなくても不合格にしない。

---

## 10. パラメータ過多を防ぐ

調整してよい主要値は5つだけとする。

1. `k_b`
2. damping
3. cylinder friction `mu`
4. substeps
5. 固定pass数 `P/I`

contact tolerance、数値regularization、速度閾値を見た目調整用parameterとして扱わない。数値値はscene scaleから決め、変更した場合は理由を記録する。

最終提出では、T1～T3、実髪、100,000点benchmarkのすべてが、1つのmaterial/solver parameter JSONを参照する。T1専用の曲げ係数、T2専用のdamping、T3専用の反復数を作らない。Astraの内部実装順は指定しない。

---

## 11. 最終システム契約

完成時に、次の要素がすべて1つの `kami4-hair-solver` に存在する。

### 11.1 ネイティブコア

- C++20 / CUDAの `kami4_hair_core.dll`
- opaque handleを使うC ABI
- 3D position、velocity、mass、rest length、strand offsets
- pointごとのkinematic maskとroot/root-tangent target
- 事前分解済みlinear bending
- chain専用tridiagonal length solve
- plane、sphere、capsule、cylinderのanalytic projection
- moving rootとkinematic collider transformのsubstep補間
- accumulated normal/tangent impulse
- 固定 `substeps / P / I`
- device bufferの事前確保
- frame statsと明示的なerror code

### 11.2 Blender拡張

- Extension ID: `kami4_hair_solver`
- 対象: Blender 5.2 LTS、Windows x64
- Curvesの各splineを1 strandとして読み込む
- 各strandの先頭pointをmoving rootにする
- zero-length edgeを検出したstrandは、root・tip・point数を保ったarc-length resamplingで正規化し、対象IDを記録する
- collider collectionからanalytic proxyを取得する
- `Initialize / Simulate / Reset / Bake / Replay` を持つ
- GPU結果を一括でCurvesへ書き戻す
- kami3と異なるcache rootを使う
- topology hash、parameter hash、frame、CRCをcacheへ記録する
- Blender dataをworker threadから変更しない

### 11.3 固定データフロー

```text
Blender evaluated roots/colliders
            ↓
substep interpolation
            ↓
implicit linear bending
            ↓
P x (chain length solve → analytic contact projection)
            ↓
final contact projection
            ↓
velocity reconstruction
            ↓
I x accumulated Coulomb impulse
            ↓
GPU state commit → position download → Curves/cache
```

contact数や残差に応じて、この経路を追加反復してはならない。

### 11.4 診断値

各frameで最低限、次を取得する。

- native / upload / download時間
- point、strand、contact数
- max / p99 length error
- minimum node gap
- chord penetration bound
- maximum displacement per substep
- motion-bound violation数
- accumulated normal/tangent impulse最大値
- friction-cone violation最大値
- NaN/Inf、buffer overflow、CUDA error

---

## 12. GPU実装

kami3の平均点数は約11点/strandである。最初から巨大な疎行列や汎用KKT solverを使わない。

- strand topologyとband factorは初期化時に作る。
- bending substitutionとtridiagonal length solveはstrand単位。
- gravity、projection、impulseはpoint/contact単位。
- frame中のdevice allocationは禁止。
- 固定回数なのでkernel launch数も固定。
- 短strandは1 thread/strandまたはsub-warp、長strandはwarp/blockで処理する。最終選択はprofile結果を提出する。
- 2～8、9～16、17～32、33～64、65～128、129～256点でbucket化する。

次のsceneを完成版で測る。

```text
100,000 points
約9,000 short strandsまたは2,000 x 51 points
4 substeps, P=3, I=3
RTX 5070 Ti
```

合格値:

- native計算 `<= 20 ms/frame`
- Blender転送を含め `<= 41.7 ms/frame`
- frameごとのmalloc 0
- iteration数のデータ依存増加 0

測定はwarm-up 120 frame後の600 frameとし、GPU、driver、Blender、binary hash、parameter hashを結果JSONへ含める。

---

## 13. 一括最終受入

途中合格は設けない。完成成果物に対し、次を同時に判定する。

| 対象 | 最終合格条件 |
| --- | --- |
| T1 | §8の中央ruck、長さ、table gap条件を満たす |
| T2 | §8の左右drape、静止、円柱gap条件を満たす |
| T3 | §8のstick相当、slip、材料移動、摩擦円錐条件を満たす |
| 共通parameter | T1～T3が同じ `k_b`、damping、`mu`、substeps、P、Iを参照する |
| 実髪 | 6,757本・74,327点をframe 1～200まで、strand脱落・NaN・fatal errorなしで計算する |
| 実髪長さ | max相対誤差 `<=2%`、p99 `<=0.5%` |
| 実髪接触 | node penetration `<=0.25 guide radius`、motion-bound violation 0 |
| 合成負荷 | 100,000点で200 frame完走 |
| 性能 | native `<=20 ms/frame`、Blender転送込み `<=41.7 ms/frame` のmedian |
| 計算予算 | `substeps<=8, P<=4, I<=4`、データ依存の追加反復0 |
| cache | 200 frameを再起動後に同一topology/parameterで再生可能 |

実髪の接触対象は、kami3研究sceneと同等の頭、首、胸、左右肩のanalytic proxyとする。rootとcollider transformはevaluated animationから取得する。

---

## 14. 仮説の不合格条件

次のどれかが残れば、kami4は不合格である。別方式を混ぜて成功扱いにしない。

1. `substeps<=8, P<=4, I<=4` では3試験を同時に通せない。
2. T3のためにAitken、永続anchor、非線形摩擦Newtonが必要になる。
3. 同じmaterial/solver JSONではT1～T3を通せない。
4. 固定予算では実髪の誤差が発散する。
5. 性能合格値を満たさない。
6. CPU fallback、strand drop、事後的な描画補正が必要になる。
7. motion boundを実髪animationが満たせず、一般CCDなしでは利用できない。

不合格でも次を研究成果物として提出する。

- 最小失敗ケース
- parameter JSON
- frameごとのscalar診断
- どの必要条件が不足したか
- 次に試す方式を1つだけ記したADR

「もっと反復すれば通る」はkami4の成功ではない。

---

## 15. Astraへの一括実行指示

1. `kami4-hair-solver` を新規作成する。
2. 本書の最終構造を一体として実装し、途中milestoneやGateを成果物にしない。
3. 3D CUDA core、Blender拡張、T1～T3、実髪200 frame、benchmarkを完成状態で提出する。
4. 3試験と実髪のsolver parameterを1つのJSONに置く。
5. 数式、CPU上の小さなoracle、CUDA kernelで同じ符号と単位を使う。
6. 反復上限はcompile時または設定読込み時に固定し、frame中に増やさない。
7. 合格条件を実装中に変更しない。変更が必要なら結果とは別に提案として記す。
8. 合格なら全項目の証拠を、未達なら不合格項目と最小再現を提出する。
9. kami3のコードやcacheを修正してkami4へ見せない。
10. 実装過程の説明より、最終architecture、実測値、再現コマンドを優先する。

---

## 16. kami4に含めない将来項目

- 一般triangle mesh collider
- 一般CCD
- `mu_s != mu_k`
- 常時edge contact solve
- twist
- hair-hair collision
- cloth shell
- macOS/Metal backend

これらは最終kami4の合格に必要ない。文書内で将来実装の順番も指定しない。

