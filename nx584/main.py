import argparse
import logging
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
    args = parser.parse_args()

    if args.debug:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(level=level, format=LOG_FORMAT,
                        filename=args.log)
    logging.getLogger('connectionpool').setLevel(logging.WARNING)

    ctrl = controller.NXController('/dev/ttyUSB0', 38400, args.config)
    api.CONTROLLER = ctrl

    t = threading.Thread(target=ctrl.controller_loop)
    t.daemon = True
    t.start()

    api.app.run(debug=False, host='0.0.0.0', port=5000)
