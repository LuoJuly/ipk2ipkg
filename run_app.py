"""PyInstaller / 双击启动入口。使用绝对导入，避免打包后相对导入失败。"""

from ipk2ipkg.__main__ import main

if __name__ == "__main__":
    main()
