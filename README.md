# 3D Creation Studio

一个面向个人局域网的 3D 创作工作台，将 AI 图片生成与编辑、Hunyuan3D-2.1 图片转 3D、GLB 预览和历史文件管理串成完整流程。

项目采用 Web 与 GPU 计算分离架构：Web 可以部署在个人电脑或 NAS，计算服务器只负责按需加载模型和执行任务。

## 功能

- 文字生成图片和参考图编辑，兼容 OpenAI 风格的 Sub2API 图片接口。
- 图片历史保存在 Web 主机，支持预览、直接下载和删除。
- 生成图片可直接继续编辑，或作为主视图、左侧、右侧、背面传入 3D 页面。
- 单张主视图自动使用单图模型，增加任一其他视图后自动使用多视图模型。
- 输出 GLB，支持 PBR 材质、纯色无光照材质和仅几何白模。
- Three.js 在线预览 GLB，模型历史支持直接下载和删除。
- 计算任务串行执行，支持查看 GPU 状态以及自动或手动选卡。
- 模型按需载入，空闲超时后卸载并释放 CUDA 显存。
- 登录保护，Compute API、图片 API 和密码在独立设置页管理。

## 界面

### 图片生成与编辑

![图片生成与编辑页面](docs/image-workspace.png)

### 图片转 3D

![图片转 3D 页面](docs/model-workspace.png)

### 设置与配置

![设置页面](docs/settings-workspace.png)

## 仓库结构

```text
web/       Vue 3 前端、FastAPI Web、Dockerfile 和群晖 Compose
compute/   覆盖到腾讯 Hunyuan3D-2.1 上游源码的计算端文件
docs/      当前架构、部署和运维文档
```

Web 和计算端必须同时演进，因此共同维护在一个仓库的 `main` 分支，而不是放在两个长期分支。

## 快速启动 Web

```bash
cd web/web-src
npm ci
npm run build
cd ../..
python -m pip install -r web/requirements-local.txt
HUNYUAN_INITIAL_PASSWORD='请设置强密码' ./web/start-local-web.sh
```

浏览器打开 `http://localhost:7864/login`，登录后在设置页填写 Compute API 和图片 API 配置。

Docker 构建：

```bash
docker build -t hunyuan3d-web:2026.09.16-vue.4 ./web
```

容器运行时必须将持久目录挂载到 `/data`：

```bash
docker run -d --name hunyuan3d-web \
  -p 7864:7864 \
  -v /path/to/persistent-data:/data \
  -e HUNYUAN_INITIAL_PASSWORD='请设置强密码' \
  -e HUNYUAN_WEB_DATA_DIR=/data \
  --restart unless-stopped \
  hunyuan3d-web:2026.09.16-vue.4
```

## 文档

- [当前开发与维护记录](docs/DEVELOPMENT_RECORD.md)
- [群晖 Container Manager 部署](docs/SYNOLOGY_DEPLOYMENT.md)
- [计算服务器部署](docs/COMPUTE_SERVER_DEPLOYMENT.md)
- [Portainer 计算容器重建](docs/PORTAINER_COMPUTE_REBUILD.md)
- [Compute Overlay (English)](compute/README.md)

## 安全说明

项目按单用户可信内网设计，不应直接暴露到公网。真实登录密码、API 密钥、Compute Token、运行配置、生成文件、模型权重和镜像 tar 均不进入 Git。

Hunyuan3D 模型本体及许可请以 [Tencent Hunyuan3D-2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1) 上游项目为准。
