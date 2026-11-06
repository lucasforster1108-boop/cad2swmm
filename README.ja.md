# cad2swmm

[English](README.md) | [中文](README.zh.md) | [한국어](README.ko.md) | **日本語**

私は建築の排水設計をしている人間です。プロジェクトの最後はいつも同じ
作業が残ります。CAD 図面は描き終わったのに、SWMM を開いてマンホール、
管、管径、管底高を最初から打ち直す。データは図面の中にもうあるのに、
です。その作業を何度か繰り返して、これを作りました。

cad2swmm は DXF の排水図面を読み、EPA SWMM 5 でそのまま開いて実行できる
`.inp` ファイルを書き出します。やることはこれ一つだけですが、いちばん
面倒な 1 時間が消えます。GitHub の他の SWMM ツールはどれも GIS データ
から始まりますが、エンジニアは排水管網を GIS で描かないので、CAD の
一段が抜けていました。

```bash
pip install ezdxf
python cad2swmm.py my_network.dxf -o my_network.inp
```

## 図面から読むもの

- マンホール：ノードレイヤー上のブロック・点・円 → ジャンクションと放流口
- ノード名と管底高：ブロック属性（`ID`、`INV` / `IL` / `ELEV`）、または
  `IL=12.34` のような文字
- 管：管レイヤー上の線分とポリライン → 管路（長さはジオメトリから実測）
- 管径：管の近くの `DN300` / `D300` / `Φ300` / `300mm` ラベル
- 流向：管底高に従い、高い方から低い方へ自動で決定

管の端点がマンホールに吸着しない場合は、ノードを自動で作ります。管径
ラベルや管底高がなくて推定した値は、どの管・どのマンホールか名前付きで
警告として出力します。黙って数字をでっち上げることはしません。

## まず例を動かす

`examples` フォルダにノード 5 個、管 4 本の小さな管網が入っています
（DXF はスクリプト生成なので、最初のコマンドを先に実行してください）。

```bash
python examples/make_example.py
python cad2swmm.py examples/example.dxf -o examples/example.inp

# 図面の単位が mm で、50 L/s のテスト流入を入れる場合
python cad2swmm.py site.dxf -o site.inp --scale 0.001 --design-flow 50
```

変換結果：

```
nodes: 5 (junctions 4 + outfall OUT1)
conduits: 4, total length 115.0 m
```

テストスクリプトが 2 つあるのは、スクリーンショットではなく証拠が
欲しかったからです。`tests/validate.py` は構造（管長、管径、流向）を
検査し、`tests/run_swmm.py` は pyswmm 経由で本物の EPA SWMM エンジンで
生成モデルを実行します。50 L/s の設計流入が最後まで流れ、放流口の
ピークは動力波の影響込みで約 54 L/s、流量ルーティングの連続性誤差は
0.1% 未満です。

## 主なオプション

```
--scale 0.001         drawing units -> metres (0.001 if the drawing is in mm)
--node-layers 井,MANHOLE   layers that hold manholes/nodes
--pipe-layers 管线,PIPE    layers that hold pipes
--default-diameter 0.3     fallback diameter (m) when no DN label is found
--default-invert 0.0       fallback invert elevation (m)
--outfall J9               name of the outfall node (else: lowest node)
--roughness 0.013          Manning's n (default: concrete pipe)
--design-flow 50           add a constant inflow (L/s) at the highest junction
--snap 2.0                 endpoint-to-node snap tolerance (drawing units)
```

## 図面の描き方

普段の描き方で大丈夫です。デフォルトで英語と中国語のレイヤー名の両方を
認識します。

- ノード：`MANHOLE`、`NODE`、`检查井`、`井` などのレイヤー上のブロック
  参照、点、円
- 管：`PIPE`、`SEWER`、`管线`、`管道`、`排水` などのレイヤー上の線分 /
  ポリライン
- 放流口：`TYPE=OUTFALL` 属性を持つノードブロック、または `--outfall`
- DWG ファイル：先に CAD で DXF に別名保存（または ODA File Converter
  で一括変換）

## まだできないこと

- DWG の直接読み込み
- 集水区と降雨 — ここはまだ自分で区切る必要があります
- ポンプ、バルブ、雨水・汚水の二重システム

SKILL.md に対応するツール（Claude Code、DeepSeek Harness など）では、
エージェントスキルとしても使えます（`SKILL.md` 参照）。

## License

MIT
