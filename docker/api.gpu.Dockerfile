FROM docker:29.5.2-cli AS docker-cli

FROM nvidia/cuda:12.6.3-devel-ubuntu24.04

WORKDIR /workspace
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace/packages/agents:/workspace/packages/orchestration:/workspace/packages/sandbox:/workspace/packages/git:/workspace/packages/logs:/workspace/packages/shared:/workspace/packages/database:/workspace/packages/security:/workspace/apps/api
ENV CUDA_STUBS_PATH=/usr/local/cuda/lib64/stubs
ENV LIBRARY_PATH=/usr/local/cuda/lib64/stubs
ENV CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=86 -DCMAKE_LIBRARY_PATH=/usr/local/cuda/lib64/stubs -DCMAKE_EXE_LINKER_FLAGS=-Wl,-rpath-link,/usr/local/cuda/lib64/stubs"
ENV FORCE_CMAKE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        ninja-build \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose

RUN ln -sf ${CUDA_STUBS_PATH}/libcuda.so ${CUDA_STUBS_PATH}/libcuda.so.1

COPY apps/api/requirements.txt /tmp/requirements.txt
COPY apps/api/requirements-models.txt /tmp/requirements-models.txt
RUN python3 -m pip install --break-system-packages --no-cache-dir -r /tmp/requirements-models.txt

COPY . /workspace

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
