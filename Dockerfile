FROM ubuntu:18.04
MAINTAINER Lior Itzhak "lior.itzhak@gmail.com"


RUN apt-get update && apt-get install -y \
#    sudo \
    curl\
#    git \
#    unixodbc \
    python3.8 \
    python3-pip && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    ln -s /usr/bin/pip3 /usr/bin/pip


RUN curl  https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/ubuntu/18.04/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update &&  ACCEPT_EULA=Y apt-get install -y msodbcsql17  unixodbc-dev



## We copy just the requirements.txt first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt
WORKDIR /app
#
RUN pip3 install  --upgrade pip && \
    pip3 install -r requirements.txt

COPY . /app

CMD [ "python3" , "app.py" ]