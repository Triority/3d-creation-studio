import json
import os
import base64
import struct
from concurrent.futures import ThreadPoolExecutor
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request
from urllib.request import urlopen

import gradio as gr
from gradio_client import Client, handle_file


DATA_DIR = Path("/media/B/Triority/Hunyuan3D-2.1")
JOBS_DIR = DATA_DIR / "jobs"
IMAGE_DIR = DATA_DIR / "generated-images"
SETTINGS_FILE = DATA_DIR / "web-settings.json"
SINGLE_URL = "http://127.0.0.1:7860"
MULTIVIEW_URL = "http://127.0.0.1:7861"
APP_DIR = Path(os.environ.get("HUNYUAN_APP_DIR", "/Bots/Hunyuan3D-2.1"))
PREP_EXECUTOR = ThreadPoolExecutor(max_workers=1)


def load_settings():
    defaults = {"api_url": "", "api_key": "", "image_model": "gpt-image-1", "image_size": "1024x1024"}
    try:
        defaults.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return defaults


def save_settings(api_url, api_key, image_model, image_size):
    previous = load_settings()
    key = api_key.strip() or previous.get("api_key", "")
    settings = {"api_url": api_url.rstrip("/"), "api_key": key,
                "image_model": image_model.strip(), "image_size": image_size}
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(SETTINGS_FILE, 0o600)
    return "设置已保存。密钥已写入权限为 600 的本地配置文件。"


def _api_request(path, payload=None, method=None):
    settings = load_settings()
    if not settings["api_url"] or not settings["api_key"]:
        raise gr.Error("请先在“设置与配置”页面填写 API 地址和密钥。")
    url = settings["api_url"].rstrip("/") + "/" + path.lstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=data, method=method or ("POST" if data else "GET"), headers={
        "Authorization": f"Bearer {settings['api_key']}", "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=180) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:800]
        raise gr.Error(f"API 请求失败（HTTP {exc.code}）：{detail}")


def test_api(api_url, api_key):
    old = load_settings()
    key = api_key.strip() or old.get("api_key", "")
    if not api_url or not key:
        return gr.update(), "请填写 API 地址和密钥。"
    url = api_url.rstrip("/") + "/models"
    try:
        request = Request(url, headers={"Authorization": f"Bearer {key}"})
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
        models = sorted(item["id"] for item in data.get("data", []) if item.get("id"))
        image_models = [m for m in models if any(x in m.lower() for x in ("image", "dall-e"))]
        message = f"连接成功，共发现 {len(models)} 个模型，其中 {len(image_models)} 个名称像图片模型。"
        if not image_models:
            message += " 未发现图片模型，请向管理员申请 gpt-image-1 或手动填写服务商提供的图片模型名。"
        return gr.update(choices=image_models, value=image_models[0] if image_models else None), message
    except Exception as exc:
        return gr.update(), f"连接失败：{exc}"


def _save_api_image(item):
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = IMAGE_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.png"
    if item.get("b64_json"):
        target.write_bytes(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        with urlopen(item["url"], timeout=180) as response:
            target.write_bytes(response.read())
    else:
        raise gr.Error("API 响应中没有图片数据。")
    return str(target)


def make_glb_unlit(path):
    """Add KHR_materials_unlit while preserving the binary buffer and textures."""
    glb_path = Path(path)
    data = glb_path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError("输出文件不是有效的 GLB。")
    magic, version, _ = struct.unpack_from("<4sII", data, 0)
    offset, chunks = 12, []
    while offset < len(data):
        length, kind = struct.unpack_from("<I4s", data, offset)
        payload = data[offset + 8:offset + 8 + length]
        chunks.append((kind, payload))
        offset += 8 + length
    document = json.loads(chunks[0][1].rstrip(b" \x00"))
    used = document.setdefault("extensionsUsed", [])
    if "KHR_materials_unlit" not in used:
        used.append("KHR_materials_unlit")
    for material in document.get("materials", []):
        material.setdefault("extensions", {})["KHR_materials_unlit"] = {}
        pbr = material.setdefault("pbrMetallicRoughness", {})
        pbr["metallicFactor"] = 0.0
        pbr["roughnessFactor"] = 1.0
    json_payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    json_payload += b" " * ((4 - len(json_payload) % 4) % 4)
    chunks[0] = (b"JSON", json_payload)
    total = 12 + sum(8 + len(payload) for _, payload in chunks)
    output = bytearray(struct.pack("<4sII", magic, version, total))
    for kind, payload in chunks:
        output.extend(struct.pack("<I4s", len(payload), kind))
        output.extend(payload)
    glb_path.write_bytes(output)


def _multipart_edit(settings, prompt, source_image):
    boundary = f"----HunyuanStudio{uuid.uuid4().hex}"
    fields = {"model": settings["image_model"], "prompt": prompt, "size": settings["image_size"], "n": "1"}
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    source = Path(source_image)
    body.extend(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{source.name}\"\r\n"
        "Content-Type: image/png\r\n\r\n".encode()
    )
    body.extend(source.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    url = settings["api_url"].rstrip("/") + "/images/edits"
    request = Request(url, data=bytes(body), method="POST", headers={
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urlopen(request, timeout=300) as response:
            return json.load(response)
    except HTTPError as exc:
        raise gr.Error(f"图片编辑失败（HTTP {exc.code}）：{exc.read().decode(errors='replace')[:800]}")


def generate_image(prompt, source_image, mode):
    if not (prompt or "").strip():
        raise gr.Error("请输入图片提示词。")
    settings = load_settings()
    if mode == "编辑图片":
        if not source_image:
            raise gr.Error("编辑图片模式需要上传原图。")
        data = _multipart_edit(settings, prompt.strip(), source_image)
    else:
        payload = {"model": settings["image_model"], "prompt": prompt.strip(),
                   "size": settings["image_size"], "n": 1}
        data = _api_request("images/generations", payload)
    path = _save_api_image(data["data"][0])
    return path, path, path, f"图片已生成并保存至 {path}"


def gpu_info():
    command = [
        "nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
        "--format=csv,noheader,nounits",
    ]
    output = subprocess.run(command, check=True, capture_output=True, text=True, timeout=5).stdout
    result = []
    for line in output.strip().splitlines():
        index, name, util, used, total, temp, power = [part.strip() for part in line.split(",")]
        result.append({
            "index": int(index), "name": name, "util": int(util), "used": int(used),
            "total": int(total), "temp": int(temp), "power": float(power),
        })
    return result


def gpu_panel():
    try:
        cards = []
        assignments = {"0": "", "1": ""}
        for filename, label in (("hunyuan3d.gpu", "2.1"), ("hunyuan3d-mv.gpu", "2mv")):
            path = DATA_DIR / filename
            if path.exists():
                assignments.setdefault(path.read_text().strip(), "")
                assignments[path.read_text().strip()] += (" · " if assignments[path.read_text().strip()] else "") + label
        for gpu in gpu_info():
            percent = round(gpu["used"] / gpu["total"] * 100)
            binding = assignments.get(str(gpu["index"]), "") or "未绑定模型"
            load_class = "hot" if gpu["util"] >= 80 or percent >= 85 else ""
            cards.append(f'''<div class="gpu-card {load_class}">
              <div class="gpu-head"><b>GPU {gpu['index']}</b><span>{binding}</span></div>
              <div class="gpu-name">{gpu['name']}</div>
              <div class="meters"><span>计算 <strong>{gpu['util']}%</strong></span><span>显存 <strong>{gpu['used'] / 1024:.1f} / {gpu['total'] / 1024:.1f} GB</strong></span></div>
              <div class="meter"><i style="width:{percent}%"></i></div>
              <small>{gpu['temp']}°C · {gpu['power']:.0f} W</small>
            </div>''')
        return '<div class="gpu-grid">' + "".join(cards) + "</div>"
    except Exception as exc:
        return f'<div class="gpu-error">无法读取 GPU 状态：{exc}</div>'


def _assigned_gpu(mode):
    filename = "hunyuan3d-mv.gpu" if mode == "多视图生成" else "hunyuan3d.gpu"
    path = DATA_DIR / filename
    if path.exists():
        return int(path.read_text().strip())
    return 1 if mode == "多视图生成" else 0


def _choose_gpu(mode, choice):
    gpus = gpu_info()
    if choice != "自动选择":
        return int(choice.rsplit(" ", 1)[-1])
    current = _assigned_gpu(mode)
    current_info = next((gpu for gpu in gpus if gpu["index"] == current), None)
    backend_url = MULTIVIEW_URL if mode == "多视图生成" else SINGLE_URL
    # A loaded backend already owns most of the memory it needs. Reuse it while
    # it is not busy instead of mistaking model memory for external pressure.
    if current_info and _backend_ready(backend_url) and current_info["util"] < 70:
        return current
    if current_info and current_info["total"] - current_info["used"] >= 18000 and current_info["util"] < 70:
        return current
    eligible = [gpu for gpu in gpus if gpu["total"] - gpu["used"] >= 18000]
    if not eligible:
        raise gr.Error("没有 GPU 拥有至少 18 GB 可用显存，请释放显存或手动选择。")
    return min(eligible, key=lambda gpu: (gpu["util"], gpu["used"]))["index"]


def _backend_ready(url):
    try:
        return urlopen(f"{url}/config", timeout=2).status == 200
    except Exception:
        return False


def _prepare_backend(mode, choice):
    target = _choose_gpu(mode, choice)
    is_mv = mode == "多视图生成"
    url = MULTIVIEW_URL if is_mv else SINGLE_URL
    current = _assigned_gpu(mode)
    if target == current and _backend_ready(url):
        return target, False
    stop_script = APP_DIR / ("stop-hunyuan3d-mv.sh" if is_mv else "stop-hunyuan3d.sh")
    start_script = APP_DIR / ("start-hunyuan3d-mv.sh" if is_mv else "start-hunyuan3d.sh")
    subprocess.run([str(stop_script)], cwd=APP_DIR, check=True, timeout=20)
    env = os.environ.copy()
    env["HUNYUAN_GPU"] = str(target)
    subprocess.run([str(start_script)], cwd=APP_DIR, env=env, check=True, timeout=20)
    deadline = time.time() + 180
    while time.time() < deadline:
        if _backend_ready(url):
            return target, True
        time.sleep(2)
    raise gr.Error(f"模型迁移到 GPU {target} 后未能在 180 秒内启动，请检查后端日志。")


def health():
    rows = []
    for name, url, gpu in (("Hunyuan3D-2.1", SINGLE_URL, "GPU 0"),
                           ("Hunyuan3D-2mv", MULTIVIEW_URL, "GPU 1")):
        try:
            with urlopen(f"{url}/config", timeout=2) as response:
                ok = response.status == 200
        except Exception:
            ok = False
        state = "运行中" if ok else "离线"
        state_class = "online" if ok else "offline"
        rows.append(
            f'<span class="service"><i class="dot {state_class}"></i>'
            f'<b>{name}</b><small>{state} · {gpu} · 端口 {url.rsplit(":", 1)[-1]}</small></span>'
        )
    return '<div class="services">' + "".join(rows) + "</div>"


def apply_preset(preset):
    values = {
        "快速预览": (10, 256, 5.0, 8000),
        "均衡": (30, 384, 5.5, 12000),
        "打印精度": (50, 512, 7.0, 20000),
    }
    return values[preset]


def _file_arg(path):
    return handle_file(path) if path else None


def _result_path(value):
    if isinstance(value, dict):
        return value.get("value") or value.get("path")
    return value


def _eta_seconds(mode, texture, resolution):
    shape = 50 if mode == "文字生成" else 24
    shape *= max(1.0, resolution / 256 * 0.7)
    return int(shape + (130 if texture else 0))


def _running_status(started, estimate, gpu_index, phase):
    elapsed = int(time.time() - started)
    if elapsed < estimate:
        timing = f"预计剩余约 {estimate - elapsed} 秒"
    else:
        timing = "已超过历史估时，仍在处理中"
    try:
        gpu = next(item for item in gpu_info() if item["index"] == gpu_index)
        resource = f"显存 {gpu['used'] / 1024:.1f}/{gpu['total'] / 1024:.1f} GB · 计算 {gpu['util']}%"
    except Exception:
        resource = "GPU 状态暂不可用"
    return f"{phase} · 已用 {elapsed} 秒 · {timing} · GPU {gpu_index} · {resource}"


def generate(mode, prompt, image, front, back, left, right, material_mode,
             steps, guidance, seed, random_seed, resolution, remove_bg, chunks, gpu_choice):
    if mode == "文字生成" and not (prompt or "").strip():
        raise gr.Error("请输入文字提示词。")
    if mode == "单图生成" and not image:
        raise gr.Error("请上传一张物体图片。")
    if mode == "多视图生成" and not front:
        raise gr.Error("请至少上传正面图；背面、左侧和右侧图可选。")

    started = time.time()
    texture = material_mode != "仅几何白模"
    estimate = _eta_seconds(mode, texture, int(resolution))
    target_gpu = _choose_gpu(mode, gpu_choice)
    current_gpu = _assigned_gpu(mode)
    backend_ready = _backend_ready(MULTIVIEW_URL if mode == "多视图生成" else SINGLE_URL)
    if target_gpu == current_gpu and backend_ready:
        prepare_phase = f"GPU {target_gpu} 上的模型已就绪"
    elif target_gpu == current_gpu:
        prepare_phase = f"正在 GPU {target_gpu} 加载模型（冷启动通常需要 30-90 秒）"
    else:
        prepare_phase = f"正在将模型从 GPU {current_gpu} 切换到 GPU {target_gpu}（通常需要 30-90 秒）"
        estimate += 70
    future = PREP_EXECUTOR.submit(_prepare_backend, mode, gpu_choice)
    while not future.done():
        yield gr.update(), gr.update(), gr.update(), _running_status(started, estimate, target_gpu, prepare_phase)
        time.sleep(2)
    gpu_index, migrated = future.result()
    yield gr.update(), gr.update(), gr.update(), _running_status(started, estimate, gpu_index, "模型准备完成，正在提交生成任务")

    endpoint = "/generation_all" if texture else "/shape_generation"
    url = MULTIVIEW_URL if mode == "多视图生成" else SINGLE_URL
    caption = prompt.strip() if mode == "文字生成" else None
    single = _file_arg(image) if mode == "单图生成" else None
    views = [_file_arg(p) for p in (front, back, left, right)] if mode == "多视图生成" else [None] * 4

    client = Client(url, verbose=False)
    job = client.submit(
        caption, single, *views, int(steps), float(guidance), int(seed),
        int(resolution), bool(remove_bg), int(chunks), bool(random_seed),
        api_name=endpoint,
    )
    while not job.done():
        elapsed = time.time() - started
        if mode == "文字生成" and elapsed < 40:
            phase = "正在根据文字生成参考图"
        elif texture and elapsed > estimate * 0.25:
            phase = "正在生成并烘焙 PBR 纹理" if material_mode == "PBR 材质" else "正在生成并烘焙颜色纹理（无光照材质）"
        else:
            phase = "正在生成 3D 几何模型"
        yield gr.update(), gr.update(), gr.update(), _running_status(started, estimate, gpu_index, phase)
        time.sleep(2)
    result = job.result()

    if texture:
        white_mesh, textured_mesh, _, stats, used_seed = result
        source = _result_path(textured_mesh)
        white_source = _result_path(white_mesh)
    else:
        white_mesh, _, stats, used_seed = result
        source = _result_path(white_mesh)
        white_source = source

    job_dir = JOBS_DIR / time.strftime("%Y%m%d") / f"{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}"
    job_dir.mkdir(parents=True, exist_ok=False)
    output_name = "textured_mesh.glb" if texture else "shape_mesh.glb"
    output_path = job_dir / output_name
    shutil.copy2(source, output_path)
    if material_mode == "纯色无光照":
        make_glb_unlit(output_path)
    if texture and white_source:
        shutil.copy2(white_source, job_dir / "white_mesh.obj")

    record = {
        "mode": mode,
        "prompt": prompt if mode == "文字生成" else None,
        "texture": texture,
        "material_mode": material_mode,
        "gpu": gpu_index,
        "seed": used_seed,
        "elapsed_seconds": round(time.time() - started, 2),
        "settings": {
            "steps": int(steps), "guidance": float(guidance),
            "resolution": int(resolution), "chunks": int(chunks),
            "remove_background": bool(remove_bg),
        },
        "backend_stats": stats,
        "output": str(output_path),
    }
    (job_dir / "metadata.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    yield str(output_path), str(output_path), record, f"生成完成 · GPU {gpu_index} · 种子 {used_seed} · 用时 {record['elapsed_seconds']} 秒"


CSS = """
html, body, gradio-app, .gradio-container, .main, .app { background: #f4f6f8 !important; }
html, body { width: 100%; min-height: 100%; margin: 0; }
.gradio-container { width: 100% !important; max-width: none !important; margin: 0 !important; padding: 20px clamp(16px, 2vw, 40px) 40px !important; box-sizing: border-box; }
.app-header { display: flex; align-items: end; justify-content: space-between; gap: 20px; padding: 8px 2px 18px; border-bottom: 1px solid #d8dde3; }
.app-header h1 { margin: 0; font-size: 28px; line-height: 1.15; color: #17202a; letter-spacing: 0; }
.app-header p { margin: 7px 0 0; color: #647180; font-size: 14px; }
.brand-mark { color: #0b766e; font-weight: 700; font-size: 13px; white-space: nowrap; }
.status-strip { margin: 14px 0 18px; padding: 0 !important; border: 0 !important; background: transparent !important; }
.services { display: flex; gap: 10px; flex-wrap: wrap; }
.service { display: flex; align-items: center; gap: 8px; padding: 9px 12px; border: 1px solid #d8dde3; border-radius: 6px; background: #fff; color: #26323d; }
.service small { color: #71808e; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.online { background: #159570; box-shadow: 0 0 0 3px #d8f3e9; }
.dot.offline { background: #c64646; box-shadow: 0 0 0 3px #f8dddd; }
.gpu-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-bottom: 18px; }
.gpu-card { padding: 12px 14px; background: #fff; border: 1px solid #d8dde3; border-radius: 7px; }
.gpu-card.hot { border-color: #d39949; background: #fffaf1; }
.gpu-head { display: flex; justify-content: space-between; align-items: center; color: #26323d; }
.gpu-head span { font-size: 12px; color: #087f72; font-weight: 600; }
.gpu-name { margin: 4px 0 10px; color: #7a8792; font-size: 12px; }
.meters { display: flex; justify-content: space-between; color: #55626e; font-size: 12px; }
.meter { height: 5px; margin: 8px 0; background: #e8ecef; border-radius: 3px; overflow: hidden; }
.meter i { display: block; height: 100%; background: #159570; }
.gpu-card.hot .meter i { background: #cf8b2e; }
.gpu-card small { color: #87929b; }
.gpu-error { color: #a43d3d; padding: 10px; background: #fff; border: 1px solid #ebcaca; }
.workspace { display: grid !important; grid-template-columns: minmax(360px, 5fr) minmax(480px, 7fr); gap: 18px !important; align-items: start !important; }
.workspace > div { min-width: 0 !important; width: 100% !important; }
.tool-panel, .result-panel { background: #fff; border: 1px solid #d8dde3; border-radius: 7px; padding: 18px !important; box-shadow: 0 3px 14px rgba(26, 38, 49, .05); }
.section-title h3 { margin: 0 0 4px; font-size: 17px; color: #202b35; }
.section-title p { margin: 0 0 14px; color: #74818d; font-size: 13px; }
.generate-button { min-height: 48px !important; font-size: 16px !important; font-weight: 650 !important; background: #087f72 !important; border-color: #087f72 !important; }
.task-state textarea { font-family: ui-monospace, monospace; color: #24534e !important; }
.result-tabs { margin-top: 10px; }
.main-nav > .tab-nav { position: sticky; top: 0; z-index: 20; background: #f4f6f8; padding-top: 6px; }
.empty-preview { min-height: min(590px, 62vh); }
footer { display: none !important; }
@media (max-width: 1050px) {
  .workspace { grid-template-columns: 1fr !important; }
  .result-panel { min-height: 420px; }
}
@media (max-width: 640px) {
  .gradio-container { padding: 12px !important; }
  .app-header { align-items: start; flex-direction: column; gap: 8px; }
  .service { width: 100%; }
  .service small { margin-left: auto; }
  .gpu-grid { grid-template-columns: 1fr; }
  .tool-panel, .result-panel { padding: 12px !important; }
}
"""


theme = gr.themes.Base(
    primary_hue="teal",
    neutral_hue="slate",
    font=["Noto Sans SC", "Microsoft YaHei", "sans-serif"],
)


with gr.Blocks(title="混元 3D 工作台", theme=theme, css=CSS) as app:
    gr.HTML("""
    <header class="app-header">
      <div><h1>混元 3D 工作台</h1><p>从图片或文字生成可预览、可打印的高质量 3D 模型</p></div>
      <div class="brand-mark">HUNYUAN3D 2.1 · PRIVATE</div>
    </header>
    """)
    settings_data = load_settings()
    transfer_image = gr.State(None)
    with gr.Tabs(selected="image", elem_classes="main-nav") as main_tabs:
        with gr.Tab("图片生成与编辑", id="image"):
            with gr.Row(equal_height=False, elem_classes="workspace"):
                with gr.Column(scale=5, elem_classes="tool-panel"):
                    gr.HTML('<div class="section-title"><h3>创建参考图</h3><p>通过外部图片模型生成新图或编辑已有图片</p></div>')
                    image_mode = gr.Radio(["文字生成图片", "编辑图片"], value="文字生成图片", label="任务类型")
                    edit_source = gr.Image(label="待编辑图片", type="filepath", height=260, visible=False)
                    image_prompt = gr.Textbox(label="提示词 / 修改要求", lines=6,
                                              placeholder="描述需要生成的物体，或说明希望如何修改图片")
                    image_submit = gr.Button("生成图片", variant="primary", elem_classes="generate-button")
                    image_status = gr.Textbox(label="任务状态", value="等待任务", interactive=False)
                with gr.Column(scale=7, elem_classes="result-panel"):
                    generated_image = gr.Image(label="生成结果", type="filepath", height=570,
                                               elem_classes="empty-preview")
                    with gr.Row():
                        image_download = gr.File(label="下载图片")
                        send_to_3d = gr.Button("用于生成 3D", variant="primary")

        with gr.Tab("图片转 3D 模型", id="model") as model_page:
            mode = gr.State("单图生成")
            with gr.Row(equal_height=False, elem_classes="workspace"):
                with gr.Column(scale=5, elem_classes="tool-panel"):
                    gr.HTML('<div class="section-title"><h3>生成设置</h3><p>选择输入方式并调整模型质量</p></div>')
                    with gr.Tabs(selected="single"):
                        with gr.Tab("单图生成", id="single") as single_tab:
                            image = gr.Image(label="物体图片", type="filepath", height=292)
                        with gr.Tab("多视图生成", id="multi") as multi_tab:
                            with gr.Row():
                                front = gr.Image(label="正面（必需）", type="filepath", height=172)
                                back = gr.Image(label="背面", type="filepath", height=172)
                            with gr.Row():
                                left = gr.Image(label="左侧", type="filepath", height=172)
                                right = gr.Image(label="右侧", type="filepath", height=172)
                        with gr.Tab("文字生成", id="text") as text_tab:
                            prompt = gr.Textbox(label="提示词", lines=8,
                                                placeholder="例如：一个完整的复古机器人摆件，居中，纯白背景，产品摄影")
                    preset = gr.Radio(["快速预览", "均衡", "打印精度"], value="打印精度", label="质量")
                    material_mode = gr.Radio(
                        ["PBR 材质", "纯色无光照", "仅几何白模"], value="PBR 材质", label="材质输出",
                        info="纯色无光照保留颜色贴图，不受查看器灯光影响",
                    )
                    with gr.Accordion("高级参数", open=False):
                        steps = gr.Slider(5, 100, value=50, step=1, label="推理步数")
                        guidance = gr.Slider(1, 15, value=7.0, step=0.1, label="引导强度")
                        resolution = gr.Slider(256, 512, value=512, step=128, label="Octree 分辨率")
                        chunks = gr.Slider(1000, 50000, value=20000, step=1000, label="解码分块")
                        with gr.Row():
                            seed = gr.Number(value=1234, precision=0, label="随机种子")
                            random_seed = gr.Checkbox(value=True, label="每次随机")
                            remove_bg = gr.Checkbox(value=True, label="自动去背景")
                    gpu_choice = gr.Dropdown(["自动选择", "GPU 0", "GPU 1", "GPU 2"], value="自动选择", label="执行显卡")
                    submit = gr.Button("开始生成", variant="primary", elem_classes="generate-button")
                    progress = gr.Textbox(label="任务状态", value="等待任务", interactive=False, elem_classes="task-state")
                with gr.Column(scale=7, elem_classes="result-panel"):
                    gr.HTML('<div class="section-title"><h3>生成结果</h3><p>拖动旋转模型，滚轮缩放查看细节</p></div>')
                    viewer = gr.Model3D(label="3D 模型预览", height=590, clear_color=[0.92, 0.94, 0.95, 1.0],
                                        elem_classes="empty-preview")
                    with gr.Tabs(elem_classes="result-tabs"):
                        with gr.Tab("模型文件"):
                            download = gr.File(label="下载 GLB")
                        with gr.Tab("生成记录"):
                            stats = gr.JSON(label="参数与耗时")

        with gr.Tab("设置与配置", id="settings"):
            with gr.Row(equal_height=False, elem_classes="workspace"):
                with gr.Column(scale=5, elem_classes="tool-panel"):
                    gr.HTML('<div class="section-title"><h3>图片 API</h3><p>兼容 OpenAI 图片生成接口的服务</p></div>')
                    api_url = gr.Textbox(label="API 地址", value=settings_data["api_url"], placeholder="https://example.com/v1")
                    api_key = gr.Textbox(label="API 密钥", type="password", placeholder="已保存的密钥不会回显；留空表示不修改")
                    with gr.Row():
                        test_connection = gr.Button("测试连接")
                        save_config = gr.Button("保存设置", variant="primary")
                    api_model = gr.Dropdown(label="图片模型", value=settings_data["image_model"], allow_custom_value=True,
                                            choices=[settings_data["image_model"]])
                    image_size = gr.Dropdown(["1024x1024", "1536x1024", "1024x1536", "auto"],
                                             value=settings_data["image_size"], label="图片尺寸")
                    config_status = gr.Textbox(label="连接状态", interactive=False)
                with gr.Column(scale=7, elem_classes="result-panel"):
                    gr.HTML('<div class="section-title"><h3>本地模型与 GPU</h3><p>显存、计算利用率及模型绑定状态，每 3 秒刷新</p></div>')
                    backend_status = gr.HTML(value=health())
                    gpu_dashboard = gr.HTML(value=gpu_panel())
                    refresh = gr.Button("刷新运行状态")

    image_mode.change(lambda value: gr.update(visible=value == "编辑图片"), image_mode, edit_source, queue=False)
    image_submit.click(generate_image, [image_prompt, edit_source, image_mode],
                       [generated_image, image_download, transfer_image, image_status], concurrency_limit=1)
    send_to_3d.click(lambda path: (path, gr.update(selected="model")), transfer_image,
                     [image, main_tabs], queue=False)
    refresh.click(lambda: (health(), gpu_panel()), outputs=[backend_status, gpu_dashboard], queue=False)
    test_connection.click(test_api, [api_url, api_key], [api_model, config_status], queue=False)
    save_config.click(save_settings, [api_url, api_key, api_model, image_size], config_status, queue=False)
    monitor = gr.Timer(3.0)
    monitor.tick(gpu_panel, outputs=gpu_dashboard, queue=False)
    single_tab.select(lambda: "单图生成", outputs=mode, queue=False)
    multi_tab.select(lambda: "多视图生成", outputs=mode, queue=False)
    text_tab.select(lambda: "文字生成", outputs=mode, queue=False)
    preset.change(apply_preset, preset, [steps, resolution, guidance, chunks], queue=False)
    submit.click(
        generate,
        [mode, prompt, image, front, back, left, right, material_mode, steps, guidance,
         seed, random_seed, resolution, remove_bg, chunks, gpu_choice],
        [viewer, download, stats, progress],
        concurrency_limit=1,
        concurrency_id="gpu_generation",
    )


if __name__ == "__main__":
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    app.queue(default_concurrency_limit=1, max_size=20).launch(
        server_name="0.0.0.0", server_port=7862, show_error=True,
        allowed_paths=[str(DATA_DIR)],
    )
