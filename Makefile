.PHONY: install build

install:
	apt install upx-ucl
	pip install pyinstaller

build:
	pyinstaller --onefile --name usqlfmt --icon=image/uroboroSQL_icon.ico python/uroborosqlfmt/api.py
