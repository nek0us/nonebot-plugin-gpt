# 固定 Playwright 与浏览器运行时版本；升级时同时调整基础镜像和 Python 包版本。
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

RUN python -m pip install --no-cache-dir "playwright==1.60.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 运行时由插件以无网络、无额外 capability、受限 CPU/内存/PID 的容器启动。
WORKDIR /workspace
