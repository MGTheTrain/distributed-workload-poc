FROM prefecthq/prefect:3-python3.12

WORKDIR /opt/prefect

RUN pip install \
    ray==2.51.1 \
    mlflow==3.7.0 \
    pandas==2.3.3 \
    torch==2.9.1 \
    torchvision==0.24.1

EXPOSE 4200
