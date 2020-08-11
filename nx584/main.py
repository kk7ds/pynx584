import argparse
import logging
import logging.handlers
import os
import threading

from nx584 import api
from nx584 import controller

LOG_FORMAT = '%(asctime)-15s %(module)s %(levelname)s %(message)s'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.ini',
                        metavar='FILE',
                        help='Path to config file')
    parser.add_argument('--debug', default=False, action='store_true',
                        help='Enable debug')
    parser.add_argument('--log', default=None,
                        metavar='FILE',
                        help='Path to log file')
    parser.add_argument('--connect', default=None,
                        metavar='HOST:PORT',
                        help='Host and port to connect for serial stream')
    parser.add_argument('--serial', default=None,
                        metavar='PORT',
                        help='Serial port to open for stream')
    parser.add_argument('--baudrate', default=38400, type=int,
                        metavar='BAUD',
                        help='Serial baudrate')
    parser.add_argument('--listen', default='127.0.0.1',
                        metavar='ADDR',
                        help='Listen address (defaults to 127.0.0.1)')
    parser.add_argument('--port', default=5007, type=int,
                        help='Listen port (defaults to 5007)')
    args = parser.parse_args()

    LOG = logging.getLogger()
    LOG.setLevel(logging.DEBUG)
    formatter = logging.Formatter(LOG_FORMAT)
    istty = os.isatty(0)

    if args.debug and not istty:
        debug_handler = logging.handlers.RotatingFileHandler(
            'debug.log',
            maxBytes=1024*1024*10,
            backupCount=3)
        debug_handler.setFormatter(formatter)
        debug_handler.setLevel(logging.DEBUG)
        LOG.addHandler(debug_handler)

    if istty:
        verbose_handler = logging.StreamHandler()
        verbose_handler.setFormatter(formatter)
        verbose_handler.setLevel(args.debug and logging.DEBUG or logging.INFO)
        LOG.addHandler(verbose_handler)

    if args.log:
        log_handler = logging.handlers.RotatingFileHandler(
            args.log,
            maxBytes=1024*1024*10,
            backupCount=3)
        log_handler.setFormatter(formatter)
        log_handler.setLevel(logging.INFO)
        LOG.addHandler(log_handler)

    LOG.info('Ready')
    logging.getLogger('connectionpool').setLevel(logging.WARNING)

    if args.connect:
        host, port = args.connect.split(':')
        ctrl = controller.NXController((host, int(port)),
                                       args.config)
    elif args.serial:
        ctrl = controller.NXController((args.serial, args.baudrate),
                                       args.config)
    else:
        LOG.error('Either host:port or serial and baudrate are required')
        return

    api.CONTROLLER = ctrl

    t = threading.Thread(target=ctrl.controller_loop)
    t.daemon = True
    t.start()

    api.app.run(debug=False, host=args.listen, port=args.port, threaded=True)
