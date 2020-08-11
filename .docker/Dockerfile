FROM python:2.7

ENV LISTEN=0.0.0.0

RUN pip install --no-cache-dir pynx584

ADD entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 5007

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
