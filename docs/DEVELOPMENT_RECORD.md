# 3D Creation Studio 开发与维护记录

最后核对：2026-09-16

## 1. 当前目标

项目提供从图片创作到 3D 打印模型生成的单用户工作流：

1. 通过图片 API 生成或修改图片。
2. 将图片直接作为主视图或指定侧视图送入 Hunyuan3D。
3. 在 GPU 计算服务器串行生成带材质的 GLB。
4. 在 Web 主机持久保存、预览、下载和删除图片及模型。

Web 主机拥有最终文件和配置；计算服务器只负责 GPU 计算及临时中转。该职责边界是后续开发必须保持的基本原则。

## 2. 当前架构

```text
浏览器
  -> Vue 3 / Three.js
  -> FastAPI Web :7864
       |- /data：密码、配置、图片、GLB、元数据
       |- Sub2API：图片生成与编辑
       `- Compute API :7863（Bearer Token）
            |- 串行任务与 GPU 调度
            |- 单图后端 :7860（按需启动）
            `- 多视图后端 :7861（按需启动）
```

代码在一个 monorepo 的同一 `main` 分支中维护：

- `web/`：正式用户界面和 Web API。
- `compute/`：应用到 Hunyuan3D-2.1 上游 checkout 的覆盖层。
- `docs/`：部署和维护文档。

公开仓库：`https://github.com/Triority/3d-creation-studio`

## 3. Web 端现状

### 技术组成

- `web/web-src/`：Vue 3、Vite、Three.js、Lucide 源码。
- `web/web-dist/`：已构建静态资源，运行时不依赖 Node 或 CDN。
- `web/vue_web.py`：FastAPI、登录鉴权、REST API 和静态资源托管。
- `web/local_web.py`：图片 API、Compute API、本地历史和文件同步逻辑。
- `web/start-local-web.sh`：源码部署启动入口，默认监听 `0.0.0.0:7864`。

页面使用独立路由：

```text
/login       登录
/image       图片生成、编辑和图片历史
/model       图片转 3D、GLB 预览和模型历史
/settings    服务配置、GPU 状态和密码修改
```

### 图片工作流

- 文字生成模式不显示上传框；编辑模式支持文件选择和剪贴板读取。
- 生成结果自动进入预览和最新优先的图片历史。
- 结果区可直接下载、继续编辑或作为 3D 输入。
- “用于生成 3D”会把当前图片设为主视图。
- “作为其他视图”可选择左侧、右侧或背面；跳转后保留已有主视图，只更新对应槽位。
- 历史图片可重新选中、下载和删除。
- 图片采用 `contain` 等比例显示，竖图不会被居中裁切。

### 3D 工作流

- 主视图必填；背面、左侧和右侧可选，最多四张视图。
- 只有主视图时走单图后端；存在任一其他视图时自动走多视图后端。
- 默认材质为纯色无光照，默认质量为打印精度。
- 材质支持纯色无光照、PBR 和仅几何白模。
- 质量预设分别控制推理步数、分辨率和网格分块参数。
- 可自动选择 GPU，也可指定 GPU。
- 任务完成后 Web 自动同步 GLB 到本地模型库并立即预览最新结果。
- Three.js 使用环境贴图预览 PBR，支持旋转和缩放。

### 设置与鉴权

- 登录密码使用 scrypt 加盐哈希，不保存明文。
- 密码文件存在时优先使用持久化密码，`HUNYUAN_INITIAL_PASSWORD` 只用于首次初始化。
- Compute API 和图片 API 分开保存、分开测试，错误来源不会混淆。
- 密钥不会回传浏览器，设置页只显示固定掩码。
- GPU 状态以响应式卡片展示，支持不同数量的 GPU。
- 界面强制使用亮色方案，不跟随浏览器黑夜模式改变控件颜色。

## 4. Web 数据持久化

容器内数据根目录为 `/data`，源码运行时由 `web/start-local-web.sh` 指向仓库根目录。需要备份：

```text
.web-password             登录密码哈希
.web-session-secret       会话签名密钥
local-web-settings.json   Compute API、图片 API 和模型选择
image-library/            图片及 metadata.json
model-library/            GLB 及 metadata.json
downloads/                旧数据兼容目录
pending-transfer.json     旧版一次性页面传递状态
```

这些文件均被 `.gitignore` 排除。重建容器时必须继续挂载原 `/data`，否则会表现为设置和历史记录消失。

## 5. 计算服务器现状

持久根目录：

```text
/media/B/Triority/Hunyuan3D-2.1/
```

严禁修改 `/media/B/Triority` 之外的 `/media/B` 内容。运行源码在持久目录的 `app/`；模型、虚拟环境、缓存、任务、令牌和日志也都在上述持久根内，不依赖容器可写层。

核心组件：

- `compute_agent.py`：Compute API，监听 7863，全部接口要求 Bearer Token。
- `unified_app.py`：生成流程、GPU 选择、后端生命周期和阶段进度。
- `gradio_app.py`：Hunyuan3D 单图/多视图模型后端，不是正式 Web UI。
- `hy3dpaint/.../mesh_utils.py`：GLB 材质与 `KHR_materials_unlit` 处理。
- `hy3dpaint/.../multiview_utils.py`：多视图输入处理。

Compute API 使用进程内互斥锁串行执行任务。模型仅在任务到来时启动，默认空闲 600 秒后停止后端进程释放 CUDA 显存。自动选卡会优先复用已加载且利用率低于阈值的 GPU，避免无意义的同卡迁移。

冷启动模型通常需要约 1 到 3 分钟。空闲状态下 7860/7861 不监听是正常现象，应以 7863 和授权后的 `/health` 为准。

## 6. 当前发布物

Web 镜像：

```text
hunyuan3d-web:2026.09.16-vue.4
```

本机导出文件：

```text
hunyuan3d-web-2026.09.16-vue.4.tar
SHA-256: 07402534ed11ebce04d49de8d8081c792253f6173bdd056ed804332c04a67d29
```

tar 是本地交付物，由 Git 忽略。镜像包含 FastAPI Web 和 `web-dist`，不包含用户数据、真实密钥、Node 依赖或 Hunyuan3D 权重。

计算端以覆盖层发布：

```bash
./compute/package-overlay.sh
```

生成的压缩包只包含 `compute/compute-release-files.txt` 列出的定制文件，需要覆盖到干净的 Tencent Hunyuan3D-2.1 上游源码中。它不是完整模型仓库，也不包含权重、虚拟环境或 CUDA 编译产物。

## 7. 日常命令

启动本机 Web：

```bash
cd /path/to/3d-creation-studio
./web/start-local-web.sh
```

构建前端和 Web 镜像：

```bash
cd web/web-src
npm ci
npm run build
cd ../..
docker build -t hunyuan3d-web:2026.09.16-vue.4 ./web
```

计算容器重启后手动启动：

```bash
cd /media/B/Triority/Hunyuan3D-2.1/app
./start-compute-agent.sh
./status-all.sh
```

## 8. 发布前验证

1. `npm run build` 成功，`web/web-dist/` 与源码同步。
2. Python 核心文件通过 `py_compile`。
3. 三个业务路由刷新后保持不变，未登录访问跳转登录页。
4. 图片结果下载、继续编辑、主视图和三种其他视图传递均正确。
5. 单图、多视图、三种材质及代表性质量预设完成端到端测试。
6. GLB 可预览、直接下载和删除；图片历史同样可管理。
7. 错误 Compute Token 和图片 API Key 分别被正确服务拒绝。
8. 重建 Web 容器并复用 `/data` 后，密码、设置和历史保持不变。
9. 模型超过空闲超时后退出，显存释放。
10. Git 暂存内容不包含密码、密钥、私有网络地址、生成文件和镜像包。

## 9. 已知边界

- 生成进度和 ETA 是阶段与历史耗时估算，并非模型内部的逐步进度。
- 页面间视图传递当前保存在浏览器内存中，刷新模型页会清空尚未提交的上传槽位。
- Web 面向可信内网单用户；公网部署需要额外的 TLS、反向代理、账户体系和限流。
- 计算端任务状态主要保存在进程内并落盘归档，Compute API 重启时不恢复正在执行的任务。
- 上游模型权重、CUDA/PyTorch 环境和第三方许可不属于本仓库发布物。
