FROM python:3.14

ENV LISTEN=0.0.0.0

COPY setup.py nx584_server nx584_client /src/
COPY nx584 /src/nx584
RUN pip install --no-cache-dir /src

EXPOSE 5007

ENTRYPOINT ["/usr/local/bin/nx584_server", "--listen", "0.0.0.0"]
CMD ["--help"]
