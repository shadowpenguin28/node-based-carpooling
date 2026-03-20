# pull official base image
FROM python:3.13.12-slim
# set working directory
WORKDIR /usr/src/carpool

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*

COPY ./entrypoint.sh .
RUN sed -i 's/\r$//g' /usr/src/carpool/entrypoint.sh
RUN chmod +x /usr/src/carpool/entrypoint.sh

# copy project
COPY . .

ENTRYPOINT ["./entrypoint.sh"]