FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN python -m pip install --no-cache-dir -r requirements-dev.txt
RUN make compile

CMD ["python", "-m", "pytest", "tests/"]
