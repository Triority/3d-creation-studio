# Hunyuan3D-2.1 Compute Overlay

This overlay contains the compute-service changes used by the Vue Web application. Apply it to a clean Tencent Hunyuan3D-2.1 checkout while preserving relative paths.

## Runtime data

Do not commit model weights, virtual environments, API tokens, uploads, jobs, outputs, logs, PID files, or GPU assignment files. On the deployed server these belong under:

```text
/media/B/Triority/Hunyuan3D-2.1/
```

The source tree is stored in the persistent `app/` subdirectory. See `COMPUTE_SERVER_DEPLOYMENT.md` for the directory contract and startup procedure.

## Service model

Only `compute_agent.py` remains running continuously. It starts the single-view or multi-view model backend when a task needs it. After the configured idle timeout, both model processes are stopped so CUDA memory is fully released.

Default settings:

```text
HUNYUAN_IDLE_TIMEOUT=600
HUNYUAN_IDLE_CHECK_INTERVAL=30
```

The API token is loaded at runtime from the persistent `compute-api.token`; it is intentionally excluded from this package.
