# 群晖 Container Manager 部署

## 镜像和持久化

镜像名称：`hunyuan3d-web:2026.09.06-vue.3`

建议先在群晖创建目录：

```text
/volume1/docker/hunyuan3d-web
```

创建容器时配置：

- 端口：本地端口 `7864` 映射容器端口 `7864`，协议 TCP。
- 存储空间：群晖目录 `/volume1/docker/hunyuan3d-web` 映射到容器 `/data`，读写权限。
- 重启策略：除非手动停止，否则始终重新启动。
- 环境变量 `HUNYUAN_INITIAL_PASSWORD`：填写首次登录密码。
- 环境变量 `HUNYUAN_WEB_DATA_DIR`：保持 `/data`。
- 环境变量 `TZ`：建议填写 `Asia/Shanghai`。

启动后访问：

```text
http://群晖IP:7864/login
```

`HUNYUAN_INITIAL_PASSWORD` 只在 `/data/.web-password` 不存在时用于初始化密码。首次登录后可在设置页修改密码；之后重启容器不会重置密码。若复用已有 `/data`，应使用该数据目录中原来的密码，而不是环境变量值。

## 计算服务器连接

容器中的 `127.0.0.1` 指容器自身，不能使用当前电脑上的 `127.0.0.1:17863` SSH 隧道。群晖必须能够访问 Compute API，可选择：

1. 在设置页填写群晖能直接访问的 Compute API 地址，例如 `http://<计算服务器地址>:7863`。
2. 在群晖上另行建立 SSH 隧道，并填写该隧道在容器网络中可访问的地址。

Compute API 仍要求正确令牌。不要把令牌写入镜像或 Compose 文件，应在 Web 设置页填写并保存。

Sub2API 地址同样必须从群晖容器网络可达，例如 `http://<图片API地址>:<端口>`。

## 导入镜像

若使用导出的 tar 文件：

1. 打开 Container Manager。
2. 进入“映像”。
3. 选择“新增”或“从文件添加”。
4. 上传镜像 tar 文件并等待导入完成。
5. 从 `hunyuan3d-web:2026.09.06-vue.3` 创建容器，并按上述内容配置端口、卷和环境变量。

也可以在支持 Compose 的 Container Manager“项目”中使用 `docker-compose.synology.yml`，创建前按实际群晖卷路径和密码修改配置。

## 备份和升级

所有持久数据都位于映射的 `/data`：

- `.web-password`：登录密码哈希
- `.web-session-secret`：登录会话密钥
- `local-web-settings.json`：Compute API 和 Sub2API 设置
- `downloads/`：生成图片
- `image-library/`：图片生成与编辑历史（图片和元数据）
- `model-library/`：GLB 模型与元数据
- `pending-transfer.json`：页面间一次性图片传递（使用后自动删除）

重新安装或重建容器时，必须继续把原来的群晖目录挂载到 `/data`。配置、密码、图片历史和模型历史都以该目录中的持久化文件为准。即使新容器设置了不同的 `HUNYUAN_INITIAL_PASSWORD`，只要 `/data/.web-password` 已存在，程序仍使用已保存的密码；环境变量仅负责首次初始化。

升级镜像前备份群晖的 `/volume1/docker/hunyuan3d-web`。替换容器时继续挂载同一目录即可保留设置和历史文件。
