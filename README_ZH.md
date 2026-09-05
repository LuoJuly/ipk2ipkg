# IPK转IPKG

把 **OpenWrt `.ipk`** 转成爱快 4.0 应用市场可本地安装的 **`.ipkg`**。

爱快 4.0 应用中心的包不是 OpenWrt 的 opkg 格式，而是带 `manifest.json` + `docker-compose.yaml` 的 tar.gz。本工具会：

1. 解析 IPK（支持 `ar` 和 `tar.gz` 两种常见封装）
2. 读出包名、版本、架构、可执行文件
3. 把文件树放进 Alpine 容器的 `/opt/pkg`
4. 打成爱快本地安装用的 `.ipkg`

English: [README.md](README.md)

## 使用

运行 `dist\IPK2IPKG.exe`：

1. 添加一个或多个 `.ipk`（多个会合并进同一个应用）
2. 核对名称、版本、端口、启动命令
3. 点「开始转换」
4. 到爱快：**高级应用 → 应用市场 → 本地安装**

命令行：

```text
python -m ipk2ipkg --inspect app.ipk
python -m ipk2ipkg app.ipk -o D:\out
python -m ipk2ipkg app.ipk --port 16601 --command "/opt/pkg/usr/bin/lucky"
```

## 注意

- 需要爱快已启用 **Docker**（64 位系统）
- 路由器要能拉取 `alpine:3.20`（或你改成的镜像）
- **LuCI 插件**依赖 OpenWrt 后台，不能当爱快应用跑
- 爱快 3.x 加密 `.ipk` 没有密钥，不能转 4.0 包
- 版本号会被规范成 `x.y.z`，否则爱快可能拒装

## 自己打包 exe

```powershell
python -m pip install -r requirements-build.txt
powershell -File .\build.ps1
```
