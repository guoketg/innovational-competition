FROM python:3.11-slim

WORKDIR /app

# 判题要用 g++ 编译 C++ 关卡（1-1 试点）。--no-install-recommends 避免拖进
# 一堆文档包；build-essential 太重（含 make/gcc 全家桶），只要 g++ 本体。
# libc6-dev 显式写出，只为不依赖传递依赖：gcc-14 对 libc6-dev 只是 Recommends
# （--no-install-recommends 会跳过它），但 g++ 实际是被
# g++-14 → libstdc++-14-dev → libc6-dev 这条硬 Depends 链带进来的，
# 所以只装 g++ 也能链接。写明后即使这条链将来变了，也不会退化成
# 「能编译、链接不了」（ld: cannot find Scrt1.o / crti.o）。
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制源码
COPY . .

# Fail the image build if resource configuration points at an SVG that was
# not committed. This prevents a successful deploy with silent placeholders.
RUN python scripts/validate_resource_images.py

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8000

# 启动服务（生产模式，无热重载）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
