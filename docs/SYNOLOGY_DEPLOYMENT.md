# 群晖 Container Manager 部署

当前 Web 镜像：

```text
hunyuan3d-web:2026.09.16-vue.4
```

本地导出文件：

```text
hunyuan3d-web-2026.09.16-vue.4.tar
SHA-256: 07402534ed11ebce04d49de8d8081c792253f6173bdd056ed804332c04a67d29
```

## 1. 准备持久目录

在 NAS 上创建一个只供本项目使用的目录，例如：

```text
/volume1/docker/hunyuan3d-web
```

该目录将挂载为容器 `/data`，其中保存登录密码哈希、会话密钥、服务配置、图片历史和 GLB 历史。升级或重建容器时必须继续使用同一目录。

## 2. 导入镜像

1. 打开 Container Manager 的“映像”。
2. 从文件导入 `hunyuan3d-web-2026.09.16-vue.4.tar`。
3. 等待出现镜像 `hunyuan3d-web:2026.09.16-vue.4`。
4. 从该镜像创建容器。

也可以在仓库根目录构建：

```bash
docker build -t hunyuan3d-web:2026.09.16-vue.4 ./web
```

## 3. 容器配置

端口：

```text
NAS 7864/TCP -> 容器 7864/TCP
```

存储空间：

```text
/volume1/docker/hunyuan3d-web -> /data（读写）
```

环境变量：

```text
HUNYUAN_WEB_DATA_DIR=/data
HUNYUAN_INITIAL_PASSWORD=<首次部署强密码>
TZ=Asia/Shanghai
```

重启策略使用 `unless-stopped`。镜像默认启动命令已经是 `python vue_web.py`，无需额外填写命令。

`HUNYUAN_INITIAL_PASSWORD` 仅在 `/data/.web-password` 不存在时生效。若复用旧持久目录，应使用原密码登录；修改环境变量不会重置已保存密码。

仓库提供 `web/docker-compose.synology.yml` 作为模板，其中密码占位值必须在部署前修改。

## 4. 配置外部服务

启动后访问：

```text
http://<群晖地址>:7864/login
```

登录后在设置页配置：

- Compute API：`http://<计算服务器地址>:7863`
- Compute Token：读取计算服务器持久目录中的令牌，通过安全渠道填写。
- 图片 API：填写 NAS 容器网络能够访问的 Sub2API 地址。
- 图片 API Key 和图片模型：保存后再测试并读取模型。

容器内的 `127.0.0.1` 指容器自身，不能代表个人电脑或计算服务器。所有地址必须从 NAS 容器网络实际可达。

计算端只需向 NAS 开放 7863。7860 和 7861 是计算容器内部的按需模型后端，不需要直接提供给 Web。

## 5. 持久数据

`/data` 包含：

```text
.web-password             登录密码哈希
.web-session-secret       会话签名密钥
local-web-settings.json   Compute 和图片 API 配置
image-library/            图片及元数据
model-library/            GLB 及元数据
downloads/                旧版兼容文件
pending-transfer.json     旧版一次性传递状态
```

密钥目前保存在 `local-web-settings.json`，应限制 NAS 目录权限并纳入加密备份策略。不要将 `/data` 内容提交到 Git 或打入镜像。

## 6. 升级

1. 备份 `/volume1/docker/hunyuan3d-web`。
2. 导入新镜像。
3. 停止并重建 Web 容器。
4. 继续挂载原目录到 `/data`。
5. 保持 7864 端口映射和环境变量。
6. 登录后检查设置、图片历史、模型历史和 Compute API 连接。

只要 `/data` 挂载正确，重建容器不会丢失配置和历史。
