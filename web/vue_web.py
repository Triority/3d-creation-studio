import asyncio
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import tempfile
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import local_web as core


DIST = Path(__file__).resolve().parent / "web-dist"
SECRET_FILE = core.ROOT / ".web-session-secret"
PASSWORD_FILE = core.ROOT / ".web-password"
SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
if not SECRET_FILE.exists():
    SECRET_FILE.write_text(secrets.token_hex(32)); os.chmod(SECRET_FILE, 0o600)
SECRET = SECRET_FILE.read_text().strip().encode()
COOKIE_VALUE = hmac.new(SECRET, b"hunyuan-user", hashlib.sha256).hexdigest()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()


def set_password(password):
    salt = secrets.token_bytes(16)
    PASSWORD_FILE.write_text(f"{salt.hex()}${password_hash(password, salt)}")
    os.chmod(PASSWORD_FILE, 0o600)


def verify_password(password):
    if not PASSWORD_FILE.exists():
        set_password(os.environ.get("HUNYUAN_INITIAL_PASSWORD", "change-this-password"))
    salt_hex, expected = PASSWORD_FILE.read_text().strip().split("$", 1)
    return hmac.compare_digest(password_hash(password, bytes.fromhex(salt_hex)), expected)


def api_error(exc):
    message = getattr(exc, "message", None) or str(exc)
    return HTTPException(400, message)


def image_record(item):
    path = Path(item["local_image"])
    return {"id": item["id"], "mode": item.get("mode", ""), "prompt": item.get("prompt", ""),
            "created": item.get("created", 0), "model": item.get("model", ""),
            "size": path.stat().st_size, "url": f"/api/images/{item['id']}/file"}


def model_record(item):
    path = Path(item["local_glb"])
    return {"id": item["id"], "mode": item.get("mode", ""),
            "material": item.get("material_mode", ""), "seed": item.get("seed"),
            "elapsed": item.get("elapsed_seconds"), "size": path.stat().st_size,
            "url": f"/api/models/{item['id']}/file"}


def safe_record(records, record_id, path_key):
    item = next((x for x in records if x["id"] == record_id), None)
    if not item:
        raise HTTPException(404, "记录不存在")
    path = Path(item[path_key]).resolve()
    if not path.is_file():
        raise HTTPException(404, "文件不存在")
    return item, path


class LoginBody(BaseModel): password: str
class ComputeSettings(BaseModel): url: str; token: str = ""
class ImageSettings(BaseModel): url: str; key: str = ""; model: str
class PasswordBody(BaseModel): current: str; new: str; confirm: str
class TransferBody(BaseModel): image_id: str; target: str


app = FastAPI()


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    public = request.url.path in ("/login", "/api/login", "/health") or request.url.path.startswith("/assets/")
    if not public and request.cookies.get("hunyuan_session") != COOKIE_VALUE:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "请先登录"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/health")
def health(): return {"status": "ok"}


@app.post("/api/login")
async def login(body: LoginBody):
    if not verify_password(body.password):
        await asyncio.sleep(3)
        raise HTTPException(401, "密码错误，请稍后重试")
    response = JSONResponse({"ok": True})
    response.set_cookie("hunyuan_session", COOKIE_VALUE, httponly=True, samesite="strict", max_age=86400 * 30)
    return response


@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True}); response.delete_cookie("hunyuan_session"); return response


@app.get("/api/settings")
def get_settings():
    cfg = core.settings()
    return {"compute_url": cfg["compute_url"], "compute_token_saved": bool(cfg["compute_token"]),
            "sub2api_url": cfg["sub2api_url"], "sub2api_key_saved": bool(cfg["sub2api_key"]),
            "image_model": cfg["image_model"]}


@app.put("/api/settings/compute")
def save_compute(body: ComputeSettings):
    try: core.save_compute_settings(body.url, body.token)
    except Exception as exc: raise api_error(exc)
    return {"message": "计算服务器配置已保存"}


@app.put("/api/settings/image")
def save_image_settings(body: ImageSettings):
    try: core.save_sub2api_settings(body.url, body.key, body.model)
    except Exception as exc: raise api_error(exc)
    return {"message": "图片 API 配置已保存"}


@app.post("/api/settings/password")
async def change_password(body: PasswordBody):
    global COOKIE_VALUE
    if not verify_password(body.current):
        await asyncio.sleep(3); raise HTTPException(400, "当前密码错误")
    if len(body.new) < 8: raise HTTPException(400, "新密码至少需要 8 个字符")
    if body.new != body.confirm: raise HTTPException(400, "两次输入的新密码不一致")
    set_password(body.new)
    COOKIE_VALUE = hmac.new(SECRET, secrets.token_bytes(32), hashlib.sha256).hexdigest()
    return {"message": "密码已修改，请重新登录"}


@app.post("/api/test/compute")
def test_compute(body: ComputeSettings):
    token = core.saved_secret(body.token, "compute_token")
    try:
        data = core.request_json(body.url, "/health", token)
        return {"message": f"连接成功，发现 {len(data.get('gpus', []))} 张 GPU", "gpus": data.get("gpus", [])}
    except Exception as exc: raise api_error(exc)


@app.post("/api/test/image")
def test_image(body: ImageSettings):
    key = core.saved_secret(body.key, "sub2api_key")
    try:
        data = core.request_json(body.url, "/models", key)
        models = sorted(x["id"] for x in data.get("data", []))
        images = [x for x in models if "image" in x.lower() or "dall-e" in x.lower()]
        return {"message": f"连接成功，发现 {len(images)} 个图片模型", "models": images}
    except Exception as exc: raise api_error(exc)


@app.get("/api/gpus")
def gpu_status():
    cfg = core.settings()
    try: return {"gpus": core.request_json(cfg["compute_url"], "/health", cfg["compute_token"])["gpus"]}
    except Exception as exc: raise api_error(exc)


@app.get("/api/images")
def images():
    core.migrate_legacy_images()
    return {"items": [image_record(x) for x in core._image_jobs()]}


@app.post("/api/images/generate")
async def generate_image(prompt: str = Form(...), mode: str = Form(...), source: UploadFile | None = File(None)):
    temp_path = None
    try:
        if source:
            suffix = Path(source.filename or "source.png").suffix or ".png"
            handle, temp_path = tempfile.mkstemp(suffix=suffix)
            os.close(handle)
            with open(temp_path, "wb") as output: shutil.copyfileobj(source.file, output)
        result = await run_in_threadpool(core.create_image, prompt, temp_path, mode)
        item = core._image_jobs()[0]
        return {"message": result[3], "item": image_record(item)}
    except Exception as exc: raise api_error(exc)
    finally:
        if temp_path: Path(temp_path).unlink(missing_ok=True)


@app.get("/api/images/{date}/{job}/file")
def image_file(date: str, job: str, download: bool = False):
    _, path = safe_record(core._image_jobs(), f"{date}/{job}", "local_image")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0], filename=path.name if download else None)


@app.delete("/api/images/{date}/{job}")
def delete_image(date: str, job: str):
    _, path = safe_record(core._image_jobs(), f"{date}/{job}", "local_image")
    shutil.rmtree(path.parent); return {"ok": True}


@app.get("/api/models")
def models(sync: bool = False):
    if sync:
        try: core.sync_remote_jobs()
        except Exception: pass
    return {"items": [model_record(x) for x in core._local_jobs()]}


@app.get("/api/models/{date}/{job}/file")
def model_file(date: str, job: str, download: bool = False):
    _, path = safe_record(core._local_jobs(), f"{date}/{job}", "local_glb")
    return FileResponse(path, media_type="model/gltf-binary", filename=path.name if download else None)


@app.delete("/api/models/{date}/{job}")
def delete_model(date: str, job: str):
    _, path = safe_record(core._local_jobs(), f"{date}/{job}", "local_glb")
    shutil.rmtree(path.parent); return {"ok": True}


@app.post("/api/models/generate")
async def generate_model(material: str = Form(...), quality: str = Form(...), gpu: str = Form(...),
                         front: UploadFile = File(...), back: UploadFile | None = File(None),
                         left: UploadFile | None = File(None), right: UploadFile | None = File(None)):
    presets = {"快速预览": (10, 256, 8000), "均衡": (30, 384, 12000), "打印精度": (50, 512, 20000)}
    if quality not in presets: raise HTTPException(400, "无效的质量设置")
    cfg = core.settings(); temporary = []
    try:
        async def store(upload):
            if not upload: return None
            handle, name = tempfile.mkstemp(suffix=Path(upload.filename or ".png").suffix)
            os.close(handle); temporary.append(name)
            with open(name, "wb") as target: shutil.copyfileobj(upload.file, target)
            return await run_in_threadpool(core.upload, name)
        main = await store(front); other = [await store(x) for x in (back, left, right)]
        multiview = any(other); steps, resolution, chunks = presets[quality]
        payload = {"mode": "多视图生成" if multiview else "单图生成", "prompt": "",
                   "image": None if multiview else main, "front": main if multiview else None,
                   "back": other[0], "left": other[1], "right": other[2], "material_mode": material,
                   "steps": steps, "resolution": resolution, "chunks": chunks, "gpu_choice": gpu}
        task = await run_in_threadpool(core.request_json, cfg["compute_url"], "/tasks", cfg["compute_token"], payload)
        return {"task_id": task["id"]}
    except Exception as exc: raise api_error(exc)
    finally:
        for name in temporary: Path(name).unlink(missing_ok=True)


@app.get("/api/tasks/{task_id}")
def task_status(task_id: str):
    cfg = core.settings()
    try:
        state = core.request_json(cfg["compute_url"], f"/tasks/{task_id}", cfg["compute_token"])
        if state.get("status") == "complete": core.sync_remote_jobs()
        return state
    except Exception as exc: raise api_error(exc)


if DIST.exists(): app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
def spa(path: str):
    index = DIST / "index.html"
    if not index.exists(): raise HTTPException(503, "Vue 前端尚未构建")
    return FileResponse(index)


if __name__ == "__main__": uvicorn.run(app, host="0.0.0.0", port=7864)
