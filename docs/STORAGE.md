# Storage and C Drive Usage

Agentic Engineering Network stores project files under `D:\AgenticEngineeringNetwork`, but some host tools can still use `C:` unless configured.

## Current Main Cause

Docker Desktop stores Linux images, layers, build cache, and volumes inside its WSL disk image. On a default Windows install that file is usually:

```text
C:\Users\<user>\AppData\Local\Docker\wsl\disk\docker_data.vhdx
```

When the network validates a generated project it runs Docker Compose builds. Those builds can grow `docker_data.vhdx` even when the generated project itself lives on `D:`.

## What The App Does To Reduce Growth

- `setup.ps1`, `start.ps1`, and `update.ps1` dot-source `scripts\setup\use-d-drive-caches.ps1`.
- npm, pip, Playwright, Docker CLI config, and temporary files are redirected to:

```text
D:\AgenticEngineeringNetwork\data\tool-caches
D:\AgenticEngineeringNetwork\data\tmp
```

- Generated project lifecycle runs remove local sandbox images after validation by default:

```text
AEN_REMOVE_SANDBOX_IMAGES_AFTER_RUN=true
```

This keeps repeated generated-project tests from accumulating one-off Docker images.

## What Still Needs Manual Docker Desktop Configuration

Docker Desktop's main disk image location is controlled by Docker Desktop, not this repository. Move it through:

```text
Docker Desktop > Settings > Resources > Advanced > Disk image location
```

Recommended location:

```text
D:\AgenticEngineeringNetwork\data\docker-desktop
```

Restart Docker Desktop after changing it. Do not manually move or edit the VHDX while Docker Desktop is running.

## Diagnostics

Run:

```powershell
Set-Location D:\AgenticEngineeringNetwork
.\scripts\maintenance\storage-diagnostics.ps1
```

Look for:

- `docker_data.vhdx` size and location
- Docker image/build-cache size from `docker system df`
- npm, pip, Playwright, Temp, and Ollama cache locations

## Safe Manual Cleanup

To remove only generated-project sandbox images, generated-project sandbox volumes, and build cache older than 24 hours:

```powershell
Set-Location D:\AgenticEngineeringNetwork
.\scripts\maintenance\prune-generated-sandboxes.ps1
```

These broader Docker commands do not delete your project source code, but they do remove Docker caches/images that may need to be rebuilt later:

```powershell
docker builder prune
docker system prune
```

Use `docker system prune -a` only when you are comfortable deleting unused images and rebuilding them later.

## Ollama Note

If `C:\Users\<user>\.ollama` is large, old Ollama model blobs may still live there. The direct GGUF model used by this app should be stored or linked under:

```text
D:\AgenticEngineeringNetwork\models
```

After confirming the app is using `LOCAL_MODEL_PATH=models\qwen2.5-coder-7b-q4_k_m.gguf`, unused Ollama models can be removed with Ollama commands or by moving Ollama's model storage intentionally.
