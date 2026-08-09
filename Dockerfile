# Backend del Durak Переводной — immagine per qualsiasi host persistente
# (VPS, Railway, Fly.io, ecc.). Su Render conviene render.yaml.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8765
EXPOSE 8765

CMD ["python", "-m", "server.app"]
