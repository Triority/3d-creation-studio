# Hunyuan3D 工作台开发与维护记录

最后核对：2026-09-06

## 1. 目标与当前状态

本项目面向个人局域网使用，将 AI 图片生成/编辑与 Hunyuan3D-2.1 图片转 3D 串成完整工作流。Web 服务负责登录、配置、历史、预览和文件管理；GPU 计算服务器只接收任务、运行模型并提供临时结果。

当前能力：

- 文字生成图片、参考图编辑图片，并保存本地历史。
- 图片结果可直接送入编辑页或图片转 3D 页。
- 按上传数量自动选择单图或多视图，支持正、后、左、右最多四张图。
- 输出 GLB，支持 PBR、纯色无光照和白模。
- Three.js 预览、直接下载和删除本地模型。
- 串行计算、GPU 状态展示、自动或手动选卡。
- 登录保护、修改密码、Compute API 与图片 API 独立配置和测试。
- 图片与模型历史最新优先，完成后自动预览最新结果。

## 2. 架构

```text
浏览器
  -> Vue 3 / Three.js
  -> FastAPI Web :7864
       |- Web 持久卷：配置、密码哈希、图片、GLB、元数据
       |- Sub2API：图片生成和编辑
       `- Compute API :7863
            |- 串行任务与 GPU 选择
            |- 单图后端 :7860（按需）
            `- 多视图后端 :7861（按需）
```

Web 与计算端通过带 Bearer Token 的 HTTP API 通信。计算完成后，Web 下载并校验结果、写入本地模型库，再清理计算端任务。因此最终用户文件应备份 Web 持久卷，GPU 服务器只承担短期中转。

## 3. Web 端

### 技术与入口

- `web/web-src/`：Vue 3、Vite、Three.js、Lucide 源码。
- `web/web-dist/`：构建产物，随 Git 和 Docker 镜像发布。
- `web/vue_web.py`：FastAPI API、鉴权和静态资源入口。
- `web/local_web.py`：Sub2API、Compute API、历史及兼容业务逻辑。
- `web/start-local-web.sh`：源码环境启动脚本。
- 路由：`/login`、`/image`、`/model`、`/settings`。
- 监听：`0.0.0.0:7864`。

图片采用等比例 `contain` 预览，竖图不会裁切；GLB 使用 Three.js 和环境光照预览。纯色模式写入 `KHR_materials_unlit`，PBR 金属材质也能在预览器中正常显示。

### 持久化

源码运行默认使用项目目录；容器中 `HUNYUAN_WEB_DATA_DIR=/data`。必须持久化：

```text
.web-password             scrypt 加盐密码哈希
.web-session-secret       会话签名密钥
local-web-settings.json   Compute/Sub2API 地址、密钥和模型选择
image-library/            图片与 metadata.json
model-library/            GLB 与 metadata.json
downloads/                兼容下载目录
pending-transfer.json     页面间一次性传递状态
```

`HUNYUAN_INITIAL_PASSWORD` 仅在密码文件不存在时初始化。已有持久卷以保存的密码哈希为准。生产部署必须设置强初始密码。上述凭据和用户数据均由 `.gitignore` 排除；密钥输入框只回显掩码。

## 4. 计算服务器端

### 持久目录约束

本项目在计算端的所有文件必须位于：

```text
/media/B/Triority/Hunyuan3D-2.1/
```

不得修改 `/media/B/Triority` 之外的 `/media/B` 内容。目录职责：

```text
app/           源码、Compute API、启停脚本
models/        模型权重
venv/          Python 环境与 CUDA 扩展
cache/         模型缓存
jobs/          等待 Web 获取的临时结果
api-tasks/     任务状态
api-uploads/   临时输入
outputs*/      模型中间输出
```

令牌、日志、PID 和 GPU 分配文件也放在该持久根目录，不进入 Git 或发布包。

### 服务生命周期

- `compute_agent.py`：监听 `0.0.0.0:7863`，全部接口要求 Bearer Token。
- `unified_app.py`：生成流程、GPU 选择、后端启动与进度信息。
- `gradio_app.py`：模型后端，不是现行用户 Web 前端。
- 单图后端使用 7860，多视图后端使用 7861。

Compute API 使用互斥锁串行运行任务。任务到来时才加载对应模型；自动选卡优先复用已加载且利用率合理的 GPU，同卡冷启动显示“正在 GPU N 加载模型”。默认空闲 600 秒后停止模型后端并释放显存，可用 `HUNYUAN_IDLE_TIMEOUT` 调整。

容器重启后当前采用手动恢复：

```bash
cd /media/B/Triority/Hunyuan3D-2.1/app
./start-compute-agent.sh
./status-all.sh
```

冷启动通常额外需要约 1 到 3 分钟。空闲时 7860/7861 不监听属于正常现象，应以 7863 和授权后的 `/health` 为准。

## 5. Docker 镜像与 NAS 部署

Web 镜像只包含 Python Web 服务和 `web/web-dist/`，不包含模型权重、Node 依赖、用户数据或真实密钥。当前发布标签：

```text
hunyuan3d-web:2026.09.06-vue.3
```

构建与导出：

```bash
cd web/web-src
npm ci
npm run build
cd ../..
docker build -t hunyuan3d-web:2026.09.06-vue.3 ./web
docker save -o hunyuan3d-web-2026.09.06-vue.3.tar hunyuan3d-web:2026.09.06-vue.3
```

镜像 tar 是交付制品，不进入 Git。群晖 Container Manager 至少配置：

- TCP：宿主机 `7864` -> 容器 `7864`。
- 持久卷：NAS 专用目录 -> 容器 `/data`，读写。
- `HUNYUAN_WEB_DATA_DIR=/data`。
- `HUNYUAN_INITIAL_PASSWORD=<首次部署强密码>`。
- `TZ=Asia/Shanghai`。
- 重启策略 `unless-stopped`。

容器中的 `127.0.0.1` 是容器自身。Compute API 必须填写 NAS 容器能访问的服务器或隧道地址。计算服务器只需向 NAS 提供 TCP 7863；7860/7861 无需暴露。详见 `docs/SYNOLOGY_DEPLOYMENT.md` 和 `docs/PORTAINER_COMPUTE_REBUILD.md`。

## 6. 计算端迁移

`compute/` 是对腾讯 Hunyuan3D-2.1 上游的覆盖层，迁移时将其内容按相对路径复制到干净的上游 checkout。`compute/compute-release-files.txt` 定义清单，`compute/package-overlay.sh` 生成迁移包，`compute/README.md` 提供说明。

当前计算服务器持久目录中另有日期化迁移包。包不包含权重、虚拟环境、缓存、令牌、任务、结果或日志；这些内容须在目标机器单独准备。纹理功能依赖已编译的 `custom_rasterizer`，持久虚拟环境的 editable 路径必须指向持久 app，检查方法见 `docs/PORTAINER_COMPUTE_REBUILD.md`。

## 7. 开发与验证

```bash
cd web/web-src && npm ci && npm run build
cd ../..
python -m py_compile web/vue_web.py web/local_web.py compute/compute_agent.py compute/unified_app.py compute/gradio_app.py
```

发布前验证：

1. 三个业务路由刷新保持不变，未登录访问跳转登录。
2. 错误 Compute Token 与图片 API Key 分别被对应服务拒绝。
3. 单图、多视图及三种材质模式完成代表性测试。
4. 图片和模型完成后自动预览，历史最新优先，下载与删除正确。
5. Web 重建并复用 `/data` 后，密码、设置和历史仍存在。
6. 计算端超过空闲时间后模型退出且显存释放。
7. 提交前扫描暂存区，确认没有密码、密钥、私钥、运行配置和生成文件。

## 8. 边界与维护原则

- 进度和 ETA 是阶段与历史耗时估算，不是模型内部逐步进度。
- 当前面向单用户可信内网；公网使用需补充 TLS、反向代理、账户和限流。
- Compute Token 与图片 API Key 只放持久配置，不写入源码、镜像、Compose 或文档。
- Web 主机拥有最终历史，计算服务器只负责计算和短期中转。
- 网络故障不应影响本地历史的预览、下载和删除。
- 所有输入、任务和下载路径必须限制在允许根目录。
- Vue 迁移后已删除旧 `routed_web.py` 及一体化 Web 启停脚本；模型计算后端继续保留。
