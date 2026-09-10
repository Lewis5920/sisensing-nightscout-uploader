FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sisensing_nightscout_uploader.py .

CMD ["python3", "-u", "sisensing_nightscout_uploader.py", "--daemon"]
