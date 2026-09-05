import json
import os
import base64
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import unified_app as core


DATA_DIR = Path("/media/B/Triority/Hunyuan3D-2.1")
JOBS_DIR = DATA_DIR / "jobs"
TOKEN_FILE = DATA_DIR / "compute-api.token"
STATE_DIR = DATA_DIR / "api-tasks"
TOKEN = TOKEN_FILE.read_text().strip()
api = FastAPI(title="Hunyuan3D Compute Agent", version="1.0")
lock = threading.Lock()
tasks = {}
IDLE_TIMEOUT = max(60, int(os.environ.get("HUNYUAN_IDLE_TIMEOUT", "600")))
IDLE_CHECK_INTERVAL = max(10, int(os.environ.get("HUNYUAN_IDLE_CHECK_INTERVAL", "30")))
last_activity = time.time()
last_unloaded = 0.0


def authorize(authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "Invalid compute API token")


class GenerateRequest(BaseModel):
    mode: str = "单图生成"
    prompt: str = ""
    image: str | None = None
    front: str | None = None
    back: str | None = None
    left: str | None = None
    right: str | None = None
    material_mode: str = "PBR 材质"
    steps: int = 30
    guidance: float = 5.5
    seed: int = 1234
    random_seed: bool = True
    resolution: int = 384
    remove_bg: bool = True
    chunks: int = 12000
    gpu_choice: str = "自动选择"


class UploadRequest(BaseModel):
    filename: str
    data: str


def _resolve_input(value):
    if not value:
        return None
    path = Path(value).resolve()
    allowed = (DATA_DIR.resolve(), core.APP_DIR.resolve())
    if not any(path == root or root in path.parents for root in allowed):
        raise ValueError("Input path is outside allowed directories")
    return str(path)


def _run(task_id, request):
    global last_activity
    with lock:
        last_activity = time.time()
        tasks[task_id].update(status="running", stage="正在生成", started=time.time())
        try:
            iterator = core.generate(
                request.mode, request.prompt, _resolve_input(request.image),
                _resolve_input(request.front), _resolve_input(request.back),
                _resolve_input(request.left), _resolve_input(request.right),
                request.material_mode, request.steps, request.guidance, request.seed,
                request.random_seed, request.resolution, request.remove_bg,
                request.chunks, request.gpu_choice,
            )
            final = None
            for update in iterator:
                final = update
                tasks[task_id]["stage"] = update[3]
            output = final[2]["output"]
            tasks[task_id].update(status="complete", stage=final[3], output=output,
                                  metadata=final[2], finished=time.time())
        except Exception as exc:
            tasks[task_id].update(status="failed", stage=str(exc), error=traceback.format_exc(), finished=time.time())
        finally:
            last_activity = time.time()
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            (STATE_DIR / f"{task_id}.json").write_text(json.dumps(tasks[task_id], ensure_ascii=False, indent=2))


def _models_running():
    return any((DATA_DIR / name).exists() for name in ("hunyuan3d.pid", "hunyuan3d-mv.pid"))


def _stop_models():
    for script in ("stop-hunyuan3d.sh", "stop-hunyuan3d-mv.sh"):
        subprocess.run([str(core.APP_DIR / script)], cwd=core.APP_DIR, check=False, timeout=30)


def _idle_reaper():
    global last_unloaded
    while True:
        time.sleep(IDLE_CHECK_INTERVAL)
        idle_seconds = time.time() - last_activity
        if lock.locked() or idle_seconds < IDLE_TIMEOUT or not _models_running():
            continue
        try:
            _stop_models()
            last_unloaded = time.time()
            print(f"Released model GPU memory after {int(idle_seconds)} idle seconds", flush=True)
        except Exception:
            traceback.print_exc()


threading.Thread(target=_idle_reaper, name="model-idle-reaper", daemon=True).start()


def _safe_job(job_id):
    job = (JOBS_DIR / job_id).resolve()
    if JOBS_DIR.resolve() not in job.parents:
        raise HTTPException(400, "Invalid job id")
    return job


@api.get("/health", dependencies=[Depends(authorize)])
def health():
    return {"services": core.health(), "gpus": core.gpu_info(), "bindings": {
        "single": core._assigned_gpu("单图生成"), "multiview": core._assigned_gpu("多视图生成")},
        "lifecycle": {"idle_timeout": IDLE_TIMEOUT, "idle_seconds": int(time.time() - last_activity),
                      "busy": lock.locked(), "models_loaded": _models_running(),
                      "last_unloaded": last_unloaded or None}}


@api.post("/tasks", dependencies=[Depends(authorize)])
def create_task(request: GenerateRequest):
    global last_activity
    last_activity = time.time()
    task_id = uuid.uuid4().hex
    tasks[task_id] = {"id": task_id, "status": "queued", "stage": "等待执行", "created": time.time()}
    threading.Thread(target=_run, args=(task_id, request), daemon=True).start()
    return tasks[task_id]


@api.post("/uploads", dependencies=[Depends(authorize)])
def upload(request: UploadRequest):
    folder = DATA_DIR / "api-uploads" / time.strftime("%Y%m%d")
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(request.filename).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        suffix = ".png"
    path = folder / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(base64.b64decode(request.data))
    return {"path": str(path)}


@api.get("/tasks/{task_id}", dependencies=[Depends(authorize)])
def get_task(task_id: str):
    if task_id in tasks:
        return tasks[task_id]
    path = STATE_DIR / f"{task_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    raise HTTPException(404, "Task not found")


@api.get("/jobs", dependencies=[Depends(authorize)])
def list_jobs():
    result = []
    for metadata in sorted(JOBS_DIR.glob("*/*/metadata.json"), reverse=True):
        try:
            item = json.loads(metadata.read_text())
            job_dir = metadata.parent
            item["id"] = str(job_dir.relative_to(JOBS_DIR))
            item["created"] = metadata.stat().st_mtime
            item["files"] = [{"name": p.name, "size": p.stat().st_size} for p in job_dir.iterdir() if p.is_file()]
            result.append(item)
        except Exception:
            continue
    return result


@api.get("/jobs/{job_id:path}/files/{filename}", dependencies=[Depends(authorize)])
def download_job(job_id: str, filename: str):
    path = (_safe_job(job_id) / Path(filename).name).resolve()
    if not path.is_file() or path.parent != _safe_job(job_id):
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename=path.name)


@api.delete("/jobs/{job_id:path}", dependencies=[Depends(authorize)])
def delete_job(job_id: str):
    path = _safe_job(job_id)
    if not path.is_dir():
        raise HTTPException(404, "Job not found")
    shutil.rmtree(path)
    return {"deleted": job_id}
