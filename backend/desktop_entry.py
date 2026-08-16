"""PyInstaller 打包入口（保持与 app 包解耦）。"""
from app.desktop import main

if __name__ == "__main__":
    main()
