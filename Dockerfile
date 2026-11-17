# Dockerfile —— 把 server_jwt 打包成镜像的说明书
FROM python:3.12-slim

WORKDIR /app

# 先装依赖再拷代码：依赖不常变，Docker 会缓存这一层，改代码时 build 更快
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server_jwt.py .

EXPOSE 8000

# 容器里的服务必须监听 0.0.0.0，外面才连得进来
CMD ["uvicorn", "server_jwt:app", "--host", "0.0.0.0", "--port", "8000"]
