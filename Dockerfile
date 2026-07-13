FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/bash botuser && \
    chown -R botuser:botuser /app
USER botuser

CMD ["python", "bot.py"]