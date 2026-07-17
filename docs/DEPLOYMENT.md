# Deployment Guide

## Local Docker Deployment

```powershell
Set-Location D:\AgenticEngineeringNetwork
Copy-Item .env.example .env
docker compose build
docker compose up -d postgres api web
```

Open:

- `http://localhost:3000`
- `http://localhost:8000/docs`

## Release Package

```powershell
.\scripts\deployment\package-release.ps1
```

The package is written to `D:\AgenticEngineeringNetwork\deployment-package.zip`.

## Rollback

```powershell
docker compose down
git checkout <known-good-tag>
docker compose build
docker compose up -d postgres api web
```

Database rollback should be handled with explicit migration tooling before production use.

## GPU Runtime

The default API build uses `docker/api.gpu.Dockerfile` and requires Docker Desktop GPU support for NVIDIA acceleration.

Verify GPU visibility with:

```powershell
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
docker compose exec -T api nvidia-smi
```

Ollama remains optional and can be started with:

```powershell
docker compose --profile ollama up -d ollama
```
