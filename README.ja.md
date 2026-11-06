# cad2swmm

[English](README.md) | [中文](README.zh.md) | [한국어](README.ko.md) | **日本語**

**CAD の排水図面を、コマンドひとつで実行可能な EPA SWMM モデルに変換します。**

GitHub 上の SWMM 自動化ツールはすべて GIS データから出発します。しかし技術者は排水管網を
GIS で描きません — CAD で描きます。`cad2swmm` はその橋渡しです。マンホールと管路が描かれた
DXF を渡せば、EPA SWMM 5 で開いてそのまま実行できる完全な `.inp` モデルファイルが返ってきます。

```bash
pip install ezdxf
python cad2swmm.py my_network.dxf -o my_network.inp
```

## 何をするものか

| 図面にあるもの | モデルに生成されるもの |
|---|---|
| ノードレイヤー上のマンホールブロック / 点 / 円 | `[JUNCTIONS]`（+ `[OUTFALLS]`） |
| ブロック属性 `ID`、`INV` / `IL` / `ELEV`、または `IL=12.34` テキスト | ノード名と管底高 |
| 管路レイヤー上の `LINE` / `LWPOLYLINE` | 実測の幾何長を持つ `[CONDUITS]` |
| 管路近くの `DN300` / `D300` / `Φ300` / `300mm` テキスト | `[XSECTIONS]` 円形管径 |
| 管底高 | 流向を自動判定（高い方 → 低い方） |

黙って欠落するものはありません。管端点がマンホールにスナップしない場合は自動ノードを作成し、
デフォルト値で代替した箇所（管径ラベルなし、管底高なし）は、どの管・どのマンホールかを
添えて一件ずつ警告として報告します。

## クイックスタート

```bash
# 同梱のサンプル図面を生成してから変換（図面単位はメートル、デフォルト）
python examples/make_example.py
python cad2swmm.py examples/example.dxf -o examples/example.inp

# 図面単位がミリメートルの場合、スモークテスト用流入量を追加
python cad2swmm.py site.dxf -o site.inp --scale 0.001 --design-flow 50
```

同梱サンプルはノード 5 個・管路 4 本の小さな管網で、技術者が実際に描く方法そのままで
描かれています（DXF は `examples/make_example.py` が生成）。

```
nodes: 5 (junctions 4 + outfall OUT1)
conduits: 4, total length 115.0 m
```

出力は自分で検証できます:

```bash
python tests/validate.py     # 構造チェック: 管長、管径、流向
pip install pyswmm
python tests/run_swmm.py     # 本物の EPA SWMM エンジンでモデルを実行
```

エンジン実行はスクリーンショットではなくテストの一部です。生成されたモデルは 50 L/s の
設計流入量を最初から最後まで送り届けます（放流口のピーク流入は約 54 L/s、動的波の影響を含む。
流量ルーティングの連続性誤差 < 0.1%）。

## 主なオプション

```
--scale 0.001         図面単位 → メートル（図面が mm 単位なら 0.001）
--node-layers 井,MANHOLE   マンホール/ノードのあるレイヤー
--pipe-layers 管线,PIPE    管路のあるレイヤー
--default-diameter 0.3     DN ラベルがない場合のデフォルト管径 (m)
--default-invert 0.0       管底高がない場合のデフォルト値 (m)
--outfall J9               放流口ノード名（なければ最も低いノード）
--roughness 0.013          粗度係数（デフォルト: コンクリート管）
--design-flow 50           最も高い接続点に定常流入 (L/s) を追加、スモークテスト用
--snap 2.0                 端点とノードのスナップ許容差（図面単位）
```

## 作図の約束事

普段どおり描けば大丈夫です。デフォルトで英語と中国語の CAD レイヤー慣習の両方を認識します。

- **ノード**: `MANHOLE`、`NODE`、`检查井`、`井` などのレイヤー上のブロック参照、点、円
- **管路**: `PIPE`、`SEWER`、`管线`、`管道`、`排水` などのレイヤー上の線分 / ポリライン
- **放流口**: 属性 `TYPE=OUTFALL` を持つノードブロック、または `--outfall` で指定
- DWG ファイル: CAD で DXF 形式に名前を付けて保存するか、ODA File Converter で一括変換

Agent Skill としても使えます（`SKILL.md` 参照）。SKILL.md に対応するツール
（Claude Code、DeepSeek Harness など）に導入し、「この CAD 図面を SWMM モデルに変換して」
と伝えるだけです。

## ロードマップ

- DWG の直接読み込み（ODA / LibreDWG）
- CAD のハッチングと注記から集水区と降雨を生成
- 汚水 + 雨水の二重排水、ポンプ/バルブブロック
- シミュレーション実行と Word レポートのための [agentic-swmm-workflow](https://github.com/Zhonghao1995/agentic-swmm-workflow) との連携（任意）

## License

MIT
