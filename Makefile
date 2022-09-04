.PHONY: install build

install:
	apt install upx-ucl
	pip install pyinstaller

build:
	mkdir -p tmp
	cp -r python tmp
	rm -r tmp/python/enum
	pyinstaller --onefile --name usqlfmt --icon=image/uroboroSQL_icon.ico tmp/python/uroborosqlfmt/api.py
	rm -r tmp
