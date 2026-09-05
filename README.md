# Hunyuan3D Studio

一个整合图片生成/编辑、Hunyuan3D-2.1 图片转 3D、GLB 预览与历史管理的局域网工作台。

## 组件

- Vue 3 + Vite + Three.js 前端
- FastAPI Web 服务（7864）
- 独立 Compute API（7863）
- 按需加载的 Hunyuan3D 单图和多视图后端
- Sub2API 兼容的图片生成与编辑接口

Web 保存配置、图片和 GLB；GPU 服务器仅负责串行计算及临时文件。支持 PBR、纯色无光照和白模 GLB，自动/手动选 GPU，并在空闲后卸载模型释放显存。

## 运行 Web

```bash
cd web-src
npm ci
npm run build
cd ..
python -m pip install -r requirements-local.txt
HUNYUAN_INITIAL_PASSWORD='请设置强密码' python vue_web.py
```

访问 `http://localhost:7864/login`，登录后在设置页填写 Compute API 和图片 API 地址及密钥。

Docker：

```bash
docker build -t hunyuan3d-web:latest .
docker run -d --name hunyuan3d-web \
  -p 7864:7864 \
  -v /path/to/persistent-data:/data \
  -e HUNYUAN_INITIAL_PASSWORD='请设置强密码' \
  -e HUNYUAN_WEB_DATA_DIR=/data \
  --restart unless-stopped \
  hunyuan3d-web:latest
```

不要将服务直接暴露到公网。真实密钥、密码和生成文件不得提交到 Git。

## 文档

- `DEVELOPMENT_RECORD.md`：架构、功能、进度和维护原则
- `SYNOLOGY_DEPLOYMENT.md`：群晖 Container Manager 部署
- `COMPUTE_SERVER_DEPLOYMENT.md`：计算服务器持久目录与运行方式
- `PORTAINER_COMPUTE_REBUILD.md`：计算容器重建及手动恢复
- `COMPUTE_RELEASE_README.md`：计算端覆盖层发布说明

Hunyuan3D 模型本体及其许可请以上游 Tencent Hunyuan3D-2.1 项目为准。
