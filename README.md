![uroboroSQL formatter](image/uroboroSQLformatter_logo.png)

# uroboroSQL formatter


* SublimeText3  
[![Package Control](https://img.shields.io/github/release/future-architect/Sublime-uroboroSQL-formatter.svg?label=package%20control) ![Package Control](https://img.shields.io/packagecontrol/dt/uroboroSQL%20Formatter.svg)](https://packagecontrol.io/packages/uroboroSQL%20Formatter)    
* IntelliJ   
[![JetBrains plugins](https://img.shields.io/jetbrains/plugin/v/9614.svg) ![JetBrains plugins](https://img.shields.io/jetbrains/plugin/d/9614.svg)](https://plugins.jetbrains.com/plugin/9614)   
* Eclipse  
[![Eclipse Marketplace](https://img.shields.io/eclipse-marketplace/v/eclipse-uroborosql-formatter.svg) ![Eclipse Marketplace](https://img.shields.io/eclipse-marketplace/dt/eclipse-uroborosql-formatter.svg)](https://marketplace.eclipse.org/content/eclipse-uroborosql-formatter)  
[![Drag to your running Eclipse* workspace. *Requires Eclipse Marketplace Client](https://marketplace.eclipse.org/sites/all/themes/solstice/public/images/marketplace/btn-install.png)](http://marketplace.eclipse.org/marketplace-client-intro?mpc_install=3434118 "Drag to your running Eclipse* workspace. *Requires Eclipse Marketplace Client")    


uroboroSQL formatterは、フューチャーアーキテクトが作成するSQLコーディング規約に従い、SQL文を整形するツールです。  
SQL文のインデント、改行、大文字・小文字の区分などを即時変換し、可読性・管理性を高めます。

[uroboroSQL](https://github.com/future-architect/uroborosql)のために作られたものですが、DBFluteやDOMAといった2Way-SQLをサポートするライブラリをお使いの方でも利用できます。

## 利用方法

### 利用例

Python:
```python
import uroborosqlfmt

sql = u"""
select column1 as column1, --column1
column2 as column2 --column2
,long_column_3 as long_column_3 --column3
from foo_table --table
where column1 = 'sample' --column1
and long_column_3 is not null
"""

formatted = uroborosqlfmt.format_sql(sql)

print(formatted)
```
出力結果:
```text
SELECT
	COLUMN1			AS	COLUMN1			-- column1
,	COLUMN2			AS	COLUMN2			-- column2
,	LONG_COLUMN_3	AS	LONG_COLUMN_3	-- column3
FROM
	FOO_TABLE	-- table
WHERE
	COLUMN1			=	'sample'	-- column1
AND	LONG_COLUMN_3	IS	NOT NULL
```

uroboroSQL formatterはPython 2.7 および 3（3.5+）上で利用できます。  
uroboroSQL formatter is compatible with Python versions 2.7 and 3 (3.5+).  

### SublimeText3のプラグインの利用

`Package Control`の`Install Package`から  
**uroboroSQL Formatter**を検索しInstallを行ってください。

設定方法や、利用方法は下記のgithubリポジトリのREADMEをご覧ください。  

[Sublime-uroboroSQL-formatter](https://github.com/future-architect/Sublime-uroboroSQL-formatter)  
[日本語Readme](https://github.com/future-architect/Sublime-uroboroSQL-formatter/blob/master/Readme.ja.md)

### EXEファイルの実行

[release](https://github.com/future-architect/uroboroSQL-formatter/releases)から`usqlfmt.exe`をダウンロードし任意のフォルダに配置してください。

Note: 開発中の最新版を試したい場合は[bin](https://github.com/future-architect/uroboroSQL-formatter/tree/bin)ブランチからバイナリを取得してください。

#### EXEファイルの実行方法

1. コマンドプロンプトにて「usqlfmt.exe」があるフォルダまで移動します。
1. 下記の実行引数を入力しEnterを押下します。
※引数とファイルパスは適切に変更してください。

#### 実行引数

```bash
usqlfmt.exe input_path output_path
```

```text
usage: usqlfmt [-h] [-v] [-m {file,directory}] [-N] [-B]
               [-c {uroborosql,doma2,uroboro,doma}]
               [-r reserved_words_file_path]
               input_path output_path

uroboroSQL formatter API

positional arguments:
  input_path            整形したいファイルのファイルパス、または、ディレクトリパスを指定する。
  output_path           整形後の成果物を保存するパスを指定する。

optional arguments:
  -h, --help            ヘルプを表示する.
  -v, --version         versionを表示する.
  -m {file,directory}, --mode {file,directory}
                        １つのファイルを対象に整形するか(file)、指定ディレクトリ配下の全ファイルを対象に整形するか(directory)を選択する.指定しない場合"file"として処理する
  -N, --nochange_case   予約語と識別子を大文字に変換しない.
  -B, --escapesequence_u005c
                        SQLでバックスラッシュによるエスケープシーケンスを使用している.
  -c {uroborosql,doma2,uroboro,doma}, --comment_syntax {uroborosql,doma2,uroboro,doma}
                        コメントのシンタックス形式を選択する.
  -r reserved_words_file_path, --reserved_words_file_path reserved_words_file_path
                        予約語一覧ファイルに存在する予約語のみを大文字変換するオプション.
                        予約語一覧ファイルのファイルパスを指定する.
                        なお、予約語のみを大文字にしたい場合は「-N」オプション指定せず、当オプションを指定すること。
                        （予約語一覧ファイルはユーザーが提供すること.また、予約語一覧は「改行区切り」とすること.）
```

#### 予約語一覧ファイルの例

予約語一覧は「改行区切り」とすること：
```text
SELECT
INSERT
FROM
AS
・・・
・・・
```

#### 例

1つのファイルを対象に整形する場合:
```text
usqlfmt.exe -m file C:/Documents/sqlfiles/inputfiles/test.sql C:/Documents/sqlfiles/output/files
```

ディレクトリを対象に整形する場合（複数ファイル指定）:
```text
usqlfmt.exe -m directory C:/Documents/sqlfiles/inputfiles C:/Documents/sqlfiles/output/files
```

1つのファイルを対象に整形するとともに、予約語のみ大文字に変換する場合:
```text
usqlfmt.exe -m file C:/Documents/sqlfiles/inputfiles/test.sql C:/Documents/sqlfiles/output/files -r C:/Documents/sqlfiles/reserved_words_list.txt
```

## 関連情報

### uroboroSQL

* https://github.com/future-architect/uroborosql

### Future Enterprise Coding Standards
* https://future-architect.github.io/coding-standards/

### フューチャーアーキテクト株式会社
* http://www.future.co.jp/  

### フューチャーアーキテクト開発者ブログ - Tech Blog
* https://future-architect.github.io/  

## ライセンス
[LICENSE](https://github.com/future-architect/uroboroSQL-formatter/blob/master/LICENSE)をご参照ください。

---

[python-sqlparse library](https://github.com/andialbrecht/sqlparse) and this code are both on [3-Clause BSD](https://opensource.org/licenses/BSD-3-Clause)  
[enum34 library](https://bitbucket.org/stoneleaf/enum34) and this code are both on [3-Clause BSD](https://opensource.org/licenses/BSD-3-Clause)  
