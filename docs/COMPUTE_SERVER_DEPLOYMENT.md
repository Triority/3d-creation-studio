# Hunyuan3D 计算服务器部署

## 1. 部署模型

计算服务器运行完整的 Tencent Hunyuan3D-2.1 上游源码，本仓库 `compute/` 只是定制覆盖层，不是完整上游仓库。

部署顺序：

1. 准备兼容的 Hunyuan3D-2.1 上游 checkout、模型权重和 CUDA/PyTorch 环境。
2. 将 `compute/` 中 `compute-release-files.txt` 列出的文件按相对路径覆盖到上游根目录。
3. 确保所有需要长期保留的内容都在持久根目录中。
4. 创建 Compute Token 文件并限制权限。
5. 只启动 Compute API，模型后端由它按需管理。

生成覆盖包：

```bash
./compute/package-overlay.sh
```

## 2. 持久目录

当前服务器约定：

```text
/media/B/Triority/Hunyuan3D-2.1/
```

不得修改 `/media/B/Triority` 之外的 `/media/B` 内容。目录职责：

```text
app/                    完整上游源码和本项目覆盖文件
models/                 单图、多视图、纹理和背景移除权重
venv/                   Python 环境与已编译 CUDA 扩展
cache/                  Hugging Face 等模型缓存
jobs/                   等待 Web 下载的临时生成结果
api-tasks/              Compute API 任务状态归档
api-uploads/            Web 上传的临时图片
outputs/                单图后端中间输出
outputs-mv/             多视图后端中间输出
compute-api.token       Compute API Bearer Token
*.log / *.pid / *.gpu   日志、进程与 GPU 分配状态
releases/               可选的迁移包归档
```

容器重建时必须继续将宿主机 `/media/B` 挂载到容器相同路径。不要将源码、权重、虚拟环境或令牌只保存在容器可写层。

## 3. 服务端口

```text
7863  Compute API，对 Web/NAS 提供
7860  单图模型后端，仅按需在计算容器内部启动
7861  多视图模型后端，仅按需在计算容器内部启动
22    SSH，按实际宿主机映射管理
```

Compute API 所有业务接口，包括 `/health`，都要求：

```http
Authorization: Bearer <compute-token>
```

7863 只应发布在可信内网，最好通过防火墙限制为 Web/NAS 来源地址。

## 4. 启动和停止

容器重启后只需手动启动 Compute API：

```bash
cd /media/B/Triority/Hunyuan3D-2.1/app
./start-compute-agent.sh
```

检查：

```bash
./status-all.sh
tail -n 100 /media/B/Triority/Hunyuan3D-2.1/compute-agent.log
```

停止：

```bash
./stop-compute-agent.sh
./stop-hunyuan3d.sh
./stop-hunyuan3d-mv.sh
```

不要在按需模式下预先启动 `start-hunyuan3d.sh` 和 `start-hunyuan3d-mv.sh`。Compute API 会根据任务类型和 GPU 选择自动启动所需后端。

## 5. 模型生命周期与 GPU

默认配置：

```text
HUNYUAN_IDLE_TIMEOUT=600
HUNYUAN_IDLE_CHECK_INTERVAL=30
```

任务到来后：

1. Compute API 串行锁定执行槽位。
2. 自动模式选择 GPU，优先复用已加载且利用率合理的设备。
3. 如后端未加载，启动单图或多视图模型。
4. 生成完成后暂时保留模型，便于短时间内复用。
5. 连续空闲达到超时时间后停止模型进程并释放 CUDA 显存。

冷启动通常增加约 1 到 3 分钟。此时 Web 应显示“正在 GPU N 加载模型”，不应误报同一 GPU 之间迁移。

自定义空闲时间：

```bash
export HUNYUAN_IDLE_TIMEOUT=900
./start-compute-agent.sh
```

## 6. custom_rasterizer

纹理生成依赖已编译的 `custom_rasterizer`。持久虚拟环境的 editable 路径应指向：

```text
/media/B/Triority/Hunyuan3D-2.1/app/hy3dpaint/custom_rasterizer
```

检查文件：

```bash
cat /media/B/Triority/Hunyuan3D-2.1/venv/lib/python3.10/site-packages/__editable__.custom_rasterizer-0.1.pth
```

若容器镜像没有 `nvcc`，不要在重建后盲目重新编译。应复用与当前 Python、PyTorch 和 CUDA 匹配的持久化扩展。验证导入时先导入 `torch`，再导入 `custom_rasterizer`，与实际模型加载顺序一致。

## 7. 不进入 Git 的内容

- 模型权重和缓存
- `venv/`
- `compute-api.token`
- 上传、任务、输出和生成结果
- 日志、PID 和 GPU 分配文件
- CUDA 编译缓存和服务器专用二进制环境

迁移到新服务器时，这些内容必须另行准备或从受控备份恢复。
