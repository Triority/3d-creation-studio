# Hunyuan3D 计算服务器部署

## 持久化目录

计算端所有需要保留的文件统一放在：

```text
/media/B/Triority/Hunyuan3D-2.1/
```

目录职责：

- `app/`：Hunyuan3D 源码、Compute API、启动停止脚本。
- `models/`：单图、多视图、纹理和背景移除模型权重。
- `venv/`：Python 运行环境和已编译扩展。
- `cache/`：Hugging Face 等缓存。
- `jobs/`：等待 Web 下载的任务结果。
- `api-tasks/`：任务状态归档。
- `api-uploads/`：计算输入的临时上传文件。
- `outputs/`、`outputs-mv/`：模型服务中间输出。
- `compute-api.token`：Compute API 令牌。
- `*.log`、`*.pid`、`*.gpu`：服务日志和运行状态。

容器重建时必须把宿主机 `/media/B` 继续挂载为容器内 `/media/B`。不要将任何必要文件只放在容器层或 `/Bots` 下。

## 日常启动

新的按需加载模式只需启动 Compute API：

```bash
cd /media/B/Triority/Hunyuan3D-2.1/app
./start-compute-agent.sh
```

不要预先运行 `start-hunyuan3d.sh` 或 `start-hunyuan3d-mv.sh`。收到任务后，Compute API 会根据单图或多视图模式及 GPU 选择自动启动对应模型服务。默认任务结束 600 秒无新任务后停止模型进程并释放显存。

可在启动前调整空闲时间：

```bash
export HUNYUAN_IDLE_TIMEOUT=900
./start-compute-agent.sh
```

## 发布到 GitHub

Git 仓库只提交 `app/` 中的源码、配置模板、启动脚本以及本文档。不要提交模型权重、虚拟环境、缓存、输出、任务、令牌、日志或 PID 文件。部署到新服务器时先创建同样的持久化根目录，再单独放置模型和 Python 环境。

建议发布包至少包含：

```text
app/compute_agent.py
app/unified_app.py
app/gradio_app.py
app/hy3dshape/
app/hy3dpaint/
app/assets/
app/start-compute-agent.sh
app/stop-compute-agent.sh
app/start-hunyuan3d.sh
app/stop-hunyuan3d.sh
app/start-hunyuan3d-mv.sh
app/stop-hunyuan3d-mv.sh
app/status-all.sh
docs/COMPUTE_SERVER_DEPLOYMENT.md
```
