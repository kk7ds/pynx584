import threading

from nx584 import api
from nx584 import controller


def main():
    ctrl = controller.NXController('/dev/ttyUSB0', 38400)
    api.CONTROLLER = ctrl

    print 'Thread'
    t = threading.Thread(target=ctrl.controller_loop)
    print 'Run'
    t.daemon = True
    t.start()

    print 'Running api'
    api.app.run(debug=False, host='0.0.0.0', port=5000)
