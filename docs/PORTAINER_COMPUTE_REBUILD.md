# Portainer 计算容器重建

本文只描述现有计算服务器容器的重建约束。完整目录和生命周期说明见 [COMPUTE_SERVER_DEPLOYMENT.md](COMPUTE_SERVER_DEPLOYMENT.md)。

## 必须保留

- 原 Hunyuan3D 计算镜像及 NVIDIA runtime/device 配置。
- 原共享内存大小、网络模式和必要环境变量。
- 宿主机 `/media/B` 到容器 `/media/B` 的同路径读写挂载。
- SSH 宿主机端口到容器 22 的映射。
- 宿主机 7863 到容器 7863 的 Compute API 映射。
- `unless-stopped` 或适合当前环境的重启策略。

严禁重新初始化 `/media/B`，尤其不得操作 `/media/B/Triority` 之外的数据。

## 当前启动策略

当前选择手动启动 Compute API，以保留 Portainer Web Console 和 SSH 使用方式。容器主命令可保持：

```text
/bin/sh -c "service ssh start && bash"
```

容器重启后通过 SSH 或 Portainer Console 执行：

```bash
cd /media/B/Triority/Hunyuan3D-2.1/app
./start-compute-agent.sh
```

不要同时手动启动两个模型后端。首次任务会按需载入对应模型，默认空闲 10 分钟后卸载。

`compute/container-entrypoint.sh` 仍保留为备用自动启动方案，但当前部署不使用它。该脚本会同时启动模型后端，与现在的按需策略不一致，启用前必须先重新评估并修改。

## 重建后检查

```bash
cd /media/B/Triority/Hunyuan3D-2.1/app
./status-all.sh
ps -ef | grep -E 'compute_agent|gradio_app.py' | grep -v grep
tail -n 100 /media/B/Triority/Hunyuan3D-2.1/compute-agent.log
```

正常空闲状态：

- Compute API 7863 在线。
- 7860 和 7861 可以不监听。
- GPU 只保留其他应用占用，不应长期被 Hunyuan3D 模型占满。

在 Web 设置页使用正确 Compute Token 测试连接，应能读取 GPU 列表和模型生命周期状态。错误 Token 必须返回 HTTP 401。

## 纹理扩展检查

若 PBR 或纯色纹理阶段报 `custom_rasterizer` 缺少 `rasterize`：

```bash
cat /media/B/Triority/Hunyuan3D-2.1/venv/lib/python3.10/site-packages/__editable__.custom_rasterizer-0.1.pth
```

内容应为：

```text
/media/B/Triority/Hunyuan3D-2.1/app/hy3dpaint/custom_rasterizer
```

持久目录中还必须有与当前环境匹配的 `custom_rasterizer_kernel` 扩展。不要依赖容器可写层中的旧 editable 路径。

## Web 连接地址

NAS Web 设置页填写：

```text
http://<计算服务器地址>:7863
```

不要填写 NAS 容器自身的 `127.0.0.1`。仅向可信内网或指定 Web 主机开放 7863。
