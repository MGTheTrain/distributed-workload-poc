FROM rayproject/ray:2.51.1-py312

WORKDIR /workspace

USER root

COPY ./workloads ./workloads
COPY ./data ./data

RUN chmod 777 data/

RUN pip install \
    pandas==2.3.3 \
    numpy==1.26.4 \
    torch==2.9.1 \
    torchvision==0.24.1 \
    pydantic==2.11.7 \
    pyarrow==19.0.1 \
    boto3==1.42.10 \
    python-multipart==0.0.21 \
    hyperopt==0.2.7 \
    mlflow==3.7.0 \
    prefect==3.6.6

ENV PYTHONUNBUFFERED=1 \
    RAY_LOG_TO_STDERR=1 \
    MLFLOW_TRACKING_URI=http://mlflow:5000

EXPOSE 6379 8265 10001 8000
