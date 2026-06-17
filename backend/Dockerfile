FROM python:3.12-alpine

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

# Copy the application source code and static assets into /app
COPY app/ /app/app/
COPY static/ /app/static/

EXPOSE 8000
# Use a shell command to change to /app before launching uvicorn
CMD ["sh", "-c", "cd /app && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
