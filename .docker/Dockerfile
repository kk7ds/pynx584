FROM python:2.7

RUN pip install --no-cache-dir pynx584

ADD entrypoint.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
EXPOSE 5007
