FROM python:3.12-slim

WORKDIR /mlflow

RUN pip install \
    mlflow==3.7.0 \
    boto3==1.35.0 \
    psycopg2-binary==2.9.10  \
    gunicorn==23.0.0

EXPOSE 5000