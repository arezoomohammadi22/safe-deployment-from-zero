FROM python:3.12-alpine
WORKDIR /app
COPY receiver.py /app/receiver.py
USER 10001:10001
EXPOSE 8080
CMD ["python", "receiver.py"]
