FROM python:3.12-slim
WORKDIR /app
COPY server.py licenses.json ./
ENV OASIS_PUBLIC_URL=""
EXPOSE 8080
CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "8080"]
