FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY externalscaler.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. externalscaler.proto
COPY estimators.py server.py ./
EXPOSE 9090
CMD ["python", "server.py"]
