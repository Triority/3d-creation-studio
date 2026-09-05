# Portainer 计算容器重建配置

当前计算端代码已经持久化到：

```text
/media/B/Triority/Hunyuan3D-2.1/app
```

模型、Python 环境、缓存、日志、令牌和任务数据位于：

```text
/media/B/Triority/Hunyuan3D-2.1
```

## 重建时必须保留

- 原镜像及原有 GPU 配置（包含 NVIDIA runtime/device requests）。
- 原有共享内存大小、环境变量和网络模式。
- SSH 映射：宿主机 `25500` 到容器 `22`。
- 新增 Compute API 映射：宿主机 `7863` 到容器 `7863`。
- `/media/B` 必须继续以相同路径挂载到容器 `/media/B`。
- 不要修改或重新初始化 `/media/B`，尤其不能操作 `/media/B/Triority` 之外的数据。
- 重启策略设为 `Unless stopped` 或 `Always`。

## 当前采用：手动启动

保留镜像原来的容器启动命令，以便 SSH 和 Portainer Web Console 正常使用：

```text
/bin/sh -c "service ssh start && bash"
```

容器重启后，通过 SSH 登录：

```bash
ssh -p <SSH端口> <用户>@<计算服务器地址>
```

按需加载模式只需执行：

```bash
cd /media/B/Triority/Hunyuan3D-2.1/app
./start-compute-agent.sh
```

也可以在 Portainer 的 Console 中选择 `/bin/bash`、用户 `root`，再执行相同命令。

单图和多视图模型不再随 Compute API 启动。首次任务会按需加载对应模型，通常需要约 1 到 3 分钟；任务结束后默认保留 10 分钟，期间收到同类任务可直接复用，继续空闲则停止模型进程并完整释放显存。可通过 `HUNYUAN_IDLE_TIMEOUT` 调整秒数。

持久 Python 环境中的 `custom_rasterizer` editable 路径已经改到持久化 app。若纹理阶段出现 `no attribute rasterize`，检查：

```bash
cat /media/B/Triority/Hunyuan3D-2.1/venv/lib/python3.10/site-packages/__editable__.custom_rasterizer-0.1.pth
```

其内容必须是：

```text
/media/B/Triority/Hunyuan3D-2.1/app/hy3dpaint/custom_rasterizer
```

需要检查状态时执行：

```bash
cd /media/B/Triority/Hunyuan3D-2.1/app
./status-all.sh
tail -n 50 /media/B/Triority/Hunyuan3D-2.1/hunyuan3d.log
tail -n 50 /media/B/Triority/Hunyuan3D-2.1/hunyuan3d-mv.log
tail -n 50 /media/B/Triority/Hunyuan3D-2.1/compute-agent.log
```

`container-entrypoint.sh` 作为备用自动启动入口保留，但当前不要求 Portainer 使用它。

## 重建后验证

```bash
ssh -p <SSH端口> <用户>@<计算服务器地址>
ps -ef | grep -E 'gradio_app.py|compute_agent' | grep -v grep
curl -I http://127.0.0.1:7860/config
curl -I http://127.0.0.1:7861/config
```

按需模式空闲时，后两个模型端口不可访问属于正常现象。应以 Compute API `7863` 在线和 `/health` 中 `models_loaded` 状态为准。

Compute API `/health` 需要 Bearer token，应从 Web 设置页使用正确令牌测试。NAS Web 的计算服务器地址改为：

```text
http://<计算服务器地址>:7863
```

仅在可信内网发布 7863；如有主机防火墙，限制为 NAS/Web 主机来源地址。
