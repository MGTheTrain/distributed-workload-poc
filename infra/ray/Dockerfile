FROM rayproject/ray:2.51.1-py312

WORKDIR /workspace

COPY ./workloads/etl ./workloads/etl
COPY ./workloads/tuning ./workloads/tuning
COPY ./workloads/training ./workloads/training
COPY ./workloads/inference ./workloads/inference

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
    mlflow==3.7.0

EXPOSE 6379 8265 10001 8000
