FROM python:3.8

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app/

RUN apt-get update && \
    apt-get install -f -y \
    bash \
    build-essential \
    gcc \
    libffi-dev \
    openssl \
    libpq-dev 

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

RUN pip install -r ./requirements.txt

COPY manage.py ./manage.py
#COPY setup.cfg ./setup.cfg
COPY middleware ./middleware

EXPOSE 8000

COPY . .
