import base64
import html
import json
import os
import shutil
import uuid
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import gradio as gr


ROOT = Path(os.environ.get("HUNYUAN_WEB_DATA_DIR", Path(__file__).resolve().parent)).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
CONFIG = ROOT / "local-web-settings.json"
DOWNLOADS = ROOT / "downloads"
LIBRARY = ROOT / "model-library"
IMAGE_LIBRARY = ROOT / "image-library"
TRANSFER_FILE = ROOT / "pending-transfer.json"
SECRET_MASK = "********"


def settings():
    value = {"compute_url": "http://127.0.0.1:17863", "compute_token": "",
             "sub2api_url": "", "sub2api_key": "", "image_model": "gpt-image-1"}
    try: value.update(json.loads(CONFIG.read_text()))
    except Exception: pass
    return value


def save_settings(compute_url, compute_token, api_url, api_key, model):
    old = settings()
    value = {"compute_url": compute_url.rstrip("/"), "compute_token": saved_secret(compute_token, "compute_token"),
             "sub2api_url": api_url.rstrip("/"), "sub2api_key": saved_secret(api_key, "sub2api_key"),
             "image_model": model or old["image_model"]}
    CONFIG.write_text(json.dumps(value, ensure_ascii=False, indent=2)); os.chmod(CONFIG, 0o600)
    return "配置已保存"


def _write_settings(value):
    CONFIG.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.chmod(CONFIG, 0o600)


def saved_secret(value, key):
    return settings()[key] if not value or value == SECRET_MASK else value


def save_compute_settings(compute_url, compute_token):
    value = settings()
    if not compute_url.strip():
        raise gr.Error("请输入计算服务器地址")
    value["compute_url"] = compute_url.rstrip("/")
    if compute_token and compute_token != SECRET_MASK:
        value["compute_token"] = compute_token
    _write_settings(value)
    return "计算服务器配置已保存"


def save_sub2api_settings(api_url, api_key, model):
    value = settings()
    if not api_url.strip():
        raise gr.Error("请输入 Sub2API 地址")
    if not model:
        raise gr.Error("请选择图片模型")
    value["sub2api_url"] = api_url.rstrip("/")
    if api_key and api_key != SECRET_MASK:
        value["sub2api_key"] = api_key
    value["image_model"] = model
    _write_settings(value)
    return "Sub2API 配置已保存"


def request_json(base, path, token, payload=None, method=None, timeout=30):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(base.rstrip("/") + path, data=body, method=method or ("POST" if body else "GET"),
                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as response: return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        try: message = json.loads(detail).get("error", {}).get("message", detail)
        except Exception: message = detail
        if exc.code == 403 and "Image generation is not enabled" in message:
            raise gr.Error("当前 Sub2API 用户组未开启图片生成权限，请管理员启用 Image generation。")
        raise gr.Error(f"远端接口请求失败（HTTP {exc.code}）：{message}")


def test_compute(url, token):
    try:
        data = request_json(url, "/health", saved_secret(token, "compute_token"))
        return f"连接成功，发现 {len(data['gpus'])} 张 GPU"
    except Exception as exc: return f"连接失败：{exc}"


def test_saved_compute(url):
    return test_compute(url, settings()["compute_token"])


def compute_status():
    cfg = settings()
    data = request_json(cfg["compute_url"], "/health", cfg["compute_token"])
    return [{"GPU": x["index"], "型号": x["name"], "计算占用": f"{x['util']}%",
             "显存": f"{x['used']/1024:.1f}/{x['total']/1024:.1f} GB",
             "温度": f"{x['temp']} C", "功耗": f"{x['power']:.0f} W"} for x in data["gpus"]]


def compute_status_for(url, token):
    try:
        data = request_json(url, "/health", saved_secret(token, "compute_token"))
        return [{"GPU": x["index"], "型号": x["name"], "计算占用": f"{x['util']}%",
                 "显存": f"{x['used']/1024:.1f}/{x['total']/1024:.1f} GB",
                 "温度": f"{x['temp']} C", "功耗": f"{x['power']:.0f} W"} for x in data["gpus"]]
    except Exception as exc:
        raise gr.Error(f"GPU 状态读取失败：{exc}")


def compute_status_html_for(url, token):
    try:
        data = request_json(url, "/health", saved_secret(token, "compute_token"))
    except Exception as exc:
        raise gr.Error(f"GPU 状态读取失败：{exc}")
    gpus = data.get("gpus", [])
    if not gpus:
        return '<div class="gpu-empty">计算服务器在线，但没有发现可用 GPU</div>'
    cards = []
    for gpu in gpus:
        used, total = float(gpu.get("used", 0)), float(gpu.get("total", 0))
        memory_percent = min(100, max(0, used / total * 100 if total else 0))
        utilization = min(100, max(0, float(gpu.get("util", 0))))
        index = html.escape(str(gpu.get("index", "-")))
        name = html.escape(str(gpu.get("name", "未知 GPU")))
        cards.append(f'''<article class="gpu-card">
          <header><span>GPU {index}</span><strong>{name}</strong></header>
          <div class="gpu-meter"><div><span>计算占用</span><b>{utilization:.0f}%</b></div>
            <progress max="100" value="{utilization:.1f}"></progress></div>
          <div class="gpu-meter"><div><span>显存</span><b>{used/1024:.1f} / {total/1024:.1f} GB</b></div>
            <progress max="100" value="{memory_percent:.1f}"></progress></div>
          <footer><span>温度 <b>{float(gpu.get('temp', 0)):.0f} C</b></span>
            <span>功耗 <b>{float(gpu.get('power', 0)):.0f} W</b></span></footer>
        </article>''')
    return '<div class="gpu-grid">' + "".join(cards) + "</div>"


def test_sub2api(url, key):
    try:
        data = request_json(url, "/models", saved_secret(key, "sub2api_key"))
        models = sorted(x["id"] for x in data.get("data", []))
        images = [x for x in models if "image" in x.lower() or "dall-e" in x.lower()]
        return gr.update(choices=images, value=images[0] if images else None), f"连接成功；发现 {len(images)} 个图片模型。模型可见不代表用户组已有生成权限。"
    except Exception as exc: return gr.update(), f"连接失败：{exc}"


def create_image(prompt, source, mode):
    if not prompt.strip(): raise gr.Error("请输入提示词")
    cfg = settings(); base, key = cfg["sub2api_url"], cfg["sub2api_key"]
    if not base or not key: raise gr.Error("请先在设置页配置 Sub2API")
    payload = {"model": cfg["image_model"], "prompt": prompt, "size": "1024x1024", "n": 1}
    if mode == "编辑图片":
        if not source: raise gr.Error("请上传待编辑图片")
        boundary=f"----Studio{uuid.uuid4().hex}"; body=bytearray()
        for name,value in payload.items():
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        p=Path(source); body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{p.name}\"\r\nContent-Type: image/png\r\n\r\n".encode()); body.extend(p.read_bytes()); body.extend(f"\r\n--{boundary}--\r\n".encode())
        req=Request(base.rstrip('/')+'/images/edits',data=bytes(body),headers={"Authorization":f"Bearer {key}","Content-Type":f"multipart/form-data; boundary={boundary}"})
        try:
            with urlopen(req,timeout=300) as response: data=json.load(response)
        except HTTPError as exc:
            detail=exc.read().decode(errors="replace")[:1000]
            try: message=json.loads(detail).get("error",{}).get("message",detail)
            except Exception: message=detail
            if exc.code==403 and "Image generation is not enabled" in message:
                raise gr.Error("当前 Sub2API 用户组未开启图片编辑权限，请管理员启用 Image generation 和 images/edits。")
            raise gr.Error(f"图片编辑失败（HTTP {exc.code}）：{message}")
    else: data=request_json(base,"/images/generations",key,payload,timeout=300)
    item=data["data"][0]
    job_id = f"{time.strftime('%Y%m%d')}/{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job_dir = IMAGE_LIBRARY / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    target = job_dir / "image.png"
    if item.get("b64_json"): target.write_bytes(base64.b64decode(item["b64_json"]))
    else:
        with urlopen(item["url"],timeout=300) as response: target.write_bytes(response.read())
    metadata = {"id": job_id, "mode": mode, "prompt": prompt,
                "created": time.time(), "filename": target.name,
                "model": cfg["image_model"]}
    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    return str(target), str(target), str(target), "生成完成"


def _image_jobs():
    result = []
    for metadata in sorted(IMAGE_LIBRARY.glob("*/*/metadata.json"), reverse=True):
        try:
            item = json.loads(metadata.read_text())
            image_path = metadata.parent / item.get("filename", "image.png")
            if not image_path.is_file():
                continue
            item["id"] = str(metadata.parent.relative_to(IMAGE_LIBRARY))
            item["local_image"] = str(image_path)
            result.append(item)
        except Exception:
            continue
    return sorted(result, key=lambda item: (float(item.get("created", 0)), item["id"]), reverse=True)


def migrate_legacy_images():
    marker = IMAGE_LIBRARY / ".legacy-imported"
    if marker.exists():
        return
    IMAGE_LIBRARY.mkdir(parents=True, exist_ok=True)
    for source in sorted(DOWNLOADS.glob("image-*")):
        if not source.is_file():
            continue
        created = source.stat().st_mtime
        job_id = f"{time.strftime('%Y%m%d', time.localtime(created))}/legacy-{source.stem}-{uuid.uuid4().hex[:6]}"
        job_dir = IMAGE_LIBRARY / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        target = job_dir / source.name
        shutil.copy2(source, target)
        metadata = {"id": job_id, "mode": "旧版生成记录", "prompt": "",
                    "created": created, "filename": target.name}
        (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    marker.touch()


def refresh_image_library():
    migrate_legacy_images()
    choices = []
    for item in _image_jobs():
        created = time.strftime("%Y-%m-%d %H:%M", time.localtime(item.get("created", 0)))
        prompt = " ".join(item.get("prompt", "").split())
        label = f"{created}    {item.get('mode', '')}    {prompt[:60]}"
        choices.append((label, item["id"]))
    return gr.update(choices=choices, value=None)


def refresh_image_library_controls():
    return (refresh_image_library(), None,
            gr.update(value=None, interactive=False), gr.update(interactive=False))


def image_job_path(job_id):
    if not job_id:
        raise gr.Error("请先选择一条图片记录")
    item = next((x for x in _image_jobs() if x["id"] == job_id), None)
    if not item:
        raise gr.Error("本机图片文件不存在")
    return item["local_image"]


def select_image_job(job_id):
    path = image_job_path(job_id) if job_id else None
    enabled = bool(path)
    return path, gr.update(value=path, interactive=enabled), gr.update(interactive=enabled)


def image_action_controls(image_path=None):
    enabled = bool(image_path)
    return gr.update(interactive=enabled), gr.update(interactive=enabled)


def delete_image_job(job_id):
    path = Path(image_job_path(job_id))
    job_dir = path.parent.resolve()
    if IMAGE_LIBRARY.resolve() not in job_dir.parents:
        raise gr.Error("无效的本机图片路径")
    shutil.rmtree(job_dir)
    return refresh_image_library_controls()


def prepare_transfer(image_path, target):
    if not image_path or not Path(image_path).is_file():
        raise gr.Error("当前没有可传递的图片")
    source = Path(image_path).resolve()
    allowed = (IMAGE_LIBRARY.resolve(), DOWNLOADS.resolve())
    if not any(root == source.parent or root in source.parents for root in allowed):
        raise gr.Error("只能传递本地生成的图片")
    payload = {"target": target, "path": str(source), "created": time.time(), "id": uuid.uuid4().hex}
    TRANSFER_FILE.write_text(json.dumps(payload, ensure_ascii=False))
    return "图片已准备好"


def consume_image_transfer():
    payload = _consume_transfer("edit")
    if not payload:
        return gr.update(), gr.update(), gr.update()
    return gr.update(value="编辑图片"), gr.update(value=payload["path"], visible=True), gr.update(value=payload["path"])


def consume_model_transfer():
    payload = _consume_transfer("model")
    return gr.update(value=payload["path"] if payload else None)


def _consume_transfer(target):
    try:
        payload = json.loads(TRANSFER_FILE.read_text())
        if payload.get("target") != target or time.time() - payload.get("created", 0) > 3600:
            return None
        TRANSFER_FILE.unlink(missing_ok=True)
        return payload if Path(payload.get("path", "")).is_file() else None
    except Exception:
        return None


def upload(path):
    if not path: return None
    cfg = settings(); p = Path(path)
    data = request_json(cfg["compute_url"], "/uploads", cfg["compute_token"],
                        {"filename": p.name, "data": base64.b64encode(p.read_bytes()).decode()}, timeout=120)
    return data["path"]


def run_3d(image, back, left, right, material, quality, gpu):
    presets = {"快速预览": (10, 256, 8000), "均衡": (30, 384, 12000), "打印精度": (50, 512, 20000)}
    steps, resolution, chunks = presets[quality]; cfg = settings()
    if not image:
        raise gr.Error("请至少上传一张主视图。")
    multiview = any((back, left, right))
    mode = "多视图生成" if multiview else "单图生成"
    main = upload(image)
    payload = {"mode": mode, "prompt": "", "image": None if multiview else main, "front": main if multiview else None,
               "back": upload(back), "left": upload(left), "right": upload(right), "material_mode": material,
               "steps": steps, "resolution": resolution, "chunks": chunks, "gpu_choice": gpu}
    task = request_json(cfg["compute_url"], "/tasks", cfg["compute_token"], payload)
    while True:
        state = request_json(cfg["compute_url"], f"/tasks/{task['id']}", cfg["compute_token"])
        if state["status"] == "complete":
            library = refresh_library()
            yield f'<div class="job-status done" style="background:#f8fafb;color:#34434f"><i></i><span style="color:#34434f">{state["stage"]} · 模型已保存到本机</span></div>', library
            return
        if state["status"] == "failed": raise gr.Error(state["stage"])
        yield f'<div class="job-status" style="background:#f8fafb;color:#34434f"><i></i><span style="color:#34434f">{state["stage"]}</span></div>', gr.update()
        time.sleep(2)


def _remote_file(job_id, filename, target):
    cfg = settings()
    req = Request(f"{cfg['compute_url']}/jobs/{job_id}/files/{filename}",
                  headers={"Authorization": f"Bearer {cfg['compute_token']}"})
    with urlopen(req, timeout=300) as response:
        target.write_bytes(response.read())


def sync_remote_jobs():
    cfg = settings()
    jobs = request_json(cfg["compute_url"], "/jobs", cfg["compute_token"])
    for item in jobs:
        glbs = [x for x in item.get("files", []) if x["name"].endswith(".glb")]
        if not glbs:
            continue
        job_dir = (LIBRARY / item["id"]).resolve()
        if LIBRARY.resolve() not in job_dir.parents:
            continue
        job_dir.mkdir(parents=True, exist_ok=True)
        complete = True
        for remote in glbs:
            target = job_dir / remote["name"]
            if not target.exists() or target.stat().st_size != remote["size"]:
                _remote_file(item["id"], remote["name"], target)
            complete &= target.stat().st_size == remote["size"]
        if complete:
            (job_dir / "metadata.json").write_text(json.dumps(item, ensure_ascii=False, indent=2))
            request_json(cfg["compute_url"], f"/jobs/{item['id']}", cfg["compute_token"], method="DELETE")


def _local_jobs():
    result = []
    for metadata in sorted(LIBRARY.glob("*/*/metadata.json"), reverse=True):
        try:
            item = json.loads(metadata.read_text())
            item["id"] = str(metadata.parent.relative_to(LIBRARY))
            item["local_glb"] = str(next(metadata.parent.glob("*.glb")))
            result.append(item)
        except Exception:
            continue
    return sorted(result, key=lambda item: (
        float(item.get("finished", item.get("created", 0)) or 0), item["id"]
    ), reverse=True)


def refresh_jobs():
    LIBRARY.mkdir(exist_ok=True)
    sync_remote_jobs()
    jobs = _local_jobs()
    rows, choices = [], []
    for item in jobs:
        choices.append(item["id"])
        rows.append([item["id"], item.get("mode"), item.get("material_mode", ""), item.get("seed"),
                     item.get("elapsed_seconds"), round(Path(item["local_glb"]).stat().st_size / 1048576, 1)])
    return gr.update(value=rows), gr.update(choices=choices, value=choices[0] if choices else None)


def refresh_library():
    LIBRARY.mkdir(exist_ok=True)
    try:
        sync_remote_jobs()
    except Exception:
        # The local library remains usable while the compute server is offline.
        pass
    choices = []
    for item in _local_jobs():
        size = Path(item["local_glb"]).stat().st_size / 1048576
        label = (f"{item['id']}    {item.get('mode', '')}    "
                 f"{item.get('material_mode', '')}    {item.get('elapsed_seconds', '-')} 秒    {size:.1f} MB")
        choices.append((label, item["id"]))
    return gr.update(choices=choices, value=None)


def refresh_library_controls():
    disabled = gr.update(interactive=False)
    return refresh_library(), gr.update(value=None, interactive=False), disabled


def download_job(job_id):
    if not job_id: raise gr.Error("请选择记录")
    item = next((x for x in _local_jobs() if x["id"] == job_id), None)
    if not item: raise gr.Error("本机模型文件不存在")
    return item["local_glb"]


def preview_job(job_id):
    if not job_id:
        return None
    return download_job(job_id)


def select_library_job(job_id):
    path = preview_job(job_id)
    enabled = bool(path)
    return path, gr.update(value=path, interactive=enabled), gr.update(interactive=enabled)


def select_job(table, evt: gr.SelectData):
    row = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    try: job_id = table.iloc[row, 0]
    except AttributeError: job_id = table[row][0]
    path = download_job(job_id)
    return job_id, path


def delete_job(job_id):
    if not job_id: raise gr.Error("请选择记录")
    job_dir = (LIBRARY / job_id).resolve()
    if LIBRARY.resolve() not in job_dir.parents or not job_dir.is_dir():
        raise gr.Error("无效的本机任务路径")
    import shutil
    shutil.rmtree(job_dir)
    table, choices = refresh_jobs(); return table, choices, None, None


def delete_library_job(job_id):
    if not job_id:
        raise gr.Error("请先选择一条记录")
    job_dir = (LIBRARY / job_id).resolve()
    if LIBRARY.resolve() not in job_dir.parents or not job_dir.is_dir():
        raise gr.Error("无效的本机任务路径")
    import shutil
    shutil.rmtree(job_dir)
    return (refresh_library(), None, gr.update(value=None, interactive=False),
            gr.update(interactive=False))


CSS = """html,body,gradio-app,.gradio-container{background:#f4f6f8!important}.gradio-container{max-width:none!important;width:100%!important;padding:18px clamp(14px,2vw,38px)!important}.panel{background:#fff;border:1px solid #d8dde3;border-radius:7px;padding:16px!important}.workspace{display:grid!important;grid-template-columns:minmax(420px,5fr) minmax(500px,7fr);gap:18px!important}.workspace>div{min-width:0!important;width:100%!important}.image-inputs{display:grid!important;grid-template-columns:1fr 1fr;gap:14px!important;align-items:start!important}.image-inputs>div{min-width:0!important}.angle-grid{display:grid!important;grid-template-columns:1fr 1fr;gap:8px!important}.angle-grid>div{min-width:0!important}.library-list .wrap{gap:7px!important}.library-list label{display:flex!important;width:100%!important;padding:12px 14px!important;border:1px solid #d8dde3!important;border-radius:6px!important;background:#fff!important;box-shadow:none!important}.library-list label:hover{border-color:#7ba8a3!important;background:#f6fbfa!important}.library-list label:has(input:checked){border-color:#087f72!important;background:#edf8f6!important}.library-list input{flex:0 0 auto}.job-status{display:flex;align-items:center;gap:10px;min-height:42px;padding:8px 12px;border:1px solid #cfd8df;border-radius:6px;background:#f8fafb;color:#34434f}.job-status i{display:block;width:18px;height:18px;flex:0 0 18px;border:3px solid #c9d5d3;border-top-color:#087f72;border-radius:50%;animation:spin .8s linear infinite}.job-status.done i{border:0;background:#148368;animation:none}.job-status.done i:after{content:'✓';display:block;color:#fff;font-size:13px;text-align:center;line-height:18px}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1050px){.workspace{grid-template-columns:1fr!important}}@media(max-width:700px){.image-inputs{grid-template-columns:1fr!important}}footer{display:none!important}"""
cfg = settings()
with gr.Blocks(title="3D 创作工作台") as app:
    gr.Markdown("# 3D 创作工作台")
    with gr.Tabs():
        with gr.Tab("图片生成与编辑"):
            with gr.Row(elem_classes="workspace"):
                with gr.Column(elem_classes="panel"):
                    img_mode=gr.Radio(["文字生成图片","编辑图片"],value="文字生成图片",label="任务类型")
                    img_source=gr.Image(type="filepath",label="待编辑图片",visible=False,
                                        sources=["upload", "clipboard"])
                    img_prompt=gr.Textbox(lines=7,label="提示词 / 修改要求")
                    img_go=gr.Button("生成图片",variant="primary"); img_status=gr.Textbox(label="状态")
                with gr.Column(elem_classes="panel"):
                    img_result=gr.Image(type="filepath",label="生成结果",height=550)
                    img_file=gr.File(label="下载"); to3d=gr.Button("用于生成 3D",variant="primary")
                    img_transfer=gr.State(None)
        with gr.Tab("图片转 3D 模型"):
            with gr.Row(elem_classes="workspace"):
                with gr.Column(elem_classes="panel"):
                    gr.Markdown("### 上传物体视图\n仅上传主视图时使用单图模型；增加任意角度图后自动使用多视图模型。")
                    with gr.Row(elem_classes="image-inputs"):
                        image = gr.Image(type="filepath", label="主视图 / 正面", height=330,
                                         sources=["upload", "clipboard"])
                        with gr.Column(elem_classes="angle-grid"):
                            back=gr.Image(type="filepath",label="背面（可选）",height=155,
                                          sources=["upload", "clipboard"])
                            left=gr.Image(type="filepath",label="左侧（可选）",height=155,
                                          sources=["upload", "clipboard"])
                            right=gr.Image(type="filepath",label="右侧（可选）",height=155,
                                           sources=["upload", "clipboard"])
                    material=gr.Radio(["PBR 材质","纯色无光照","仅几何白模"],value="纯色无光照",label="材质")
                    quality=gr.Radio(["快速预览","均衡","打印精度"],value="打印精度",label="质量")
                    gpu=gr.Dropdown(["自动选择","GPU 0","GPU 1","GPU 2"],value="自动选择",label="GPU")
                    go=gr.Button("开始生成",variant="primary"); state=gr.HTML('<div class="job-status done"><i></i><span>等待任务</span></div>')
                with gr.Column(elem_classes="panel"):
                    gr.Markdown("### 历史模型")
                    history=gr.Dataframe(headers=["任务","模式","材质","种子","秒","MB"],interactive=False)
                    selected=gr.Dropdown(label="选择任务")
                    with gr.Row(): refresh=gr.Button("刷新"); get=gr.Button("下载/预览"); delete=gr.Button("删除",variant="stop")
                    preview=gr.Model3D(label="预览",height=460); file=gr.File(label="下载")
        with gr.Tab("设置与配置"):
            with gr.Row(elem_classes="workspace"):
                with gr.Column(elem_classes="panel"):
                    compute_url=gr.Textbox(value=cfg["compute_url"],label="计算服务器地址")
                    compute_token=gr.Textbox(type="password",label="计算服务器令牌")
                    test_c=gr.Button("测试计算服务器")
                    c_status=gr.Textbox(label="状态")
                    gpu_refresh=gr.Button("刷新 GPU 状态")
                    gpu_status=gr.JSON(label="远端 GPU")
                with gr.Column(elem_classes="panel"):
                    api_url=gr.Textbox(value=cfg["sub2api_url"],label="Sub2API 地址")
                    api_key=gr.Textbox(type="password",label="Sub2API 密钥")
                    model=gr.Dropdown([cfg["image_model"]],value=cfg["image_model"],allow_custom_value=True,label="图片模型")
                    test_a=gr.Button("测试 Sub2API"); save=gr.Button("保存全部设置",variant="primary")
                    a_status=gr.Textbox(label="状态")
    go.click(run_3d,[image,back,left,right,material,quality,gpu],[state,history],concurrency_limit=1,show_progress="hidden")
    img_mode.change(lambda x:gr.update(visible=x=="编辑图片"),img_mode,img_source,queue=False)
    img_go.click(create_image,[img_prompt,img_source,img_mode],[img_result,img_file,img_transfer,img_status],concurrency_limit=1)
    to3d.click(lambda x:x,img_transfer,image,queue=False)
    refresh.click(refresh_jobs,outputs=[history,selected]); get.click(download_job,selected,[preview,file])
    delete.click(delete_job,selected,[history,selected,preview,file])
    test_c.click(test_compute,[compute_url,compute_token],c_status); test_a.click(test_sub2api,[api_url,api_key],[model,a_status])
    gpu_refresh.click(compute_status,outputs=gpu_status)
    save.click(save_settings,[compute_url,compute_token,api_url,api_key,model],a_status)

if __name__ == "__main__":
    app.queue(default_concurrency_limit=1).launch(
        server_name="127.0.0.1", server_port=7864,
        theme=gr.themes.Base(primary_hue="teal"), css=CSS,
        allowed_paths=[str(DOWNLOADS), str(IMAGE_LIBRARY), str(LIBRARY)],
    )
