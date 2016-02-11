import flask
import json
import logging


LOG = logging.getLogger('api')
CONTROLLER = None
app = flask.Flask('nx584')


def show_zone(zone):
    return {
        'number': zone.number,
        'name': zone.name,
        'state': zone.state,
        'bypassed': zone.bypassed,
        'condition_flags': zone.condition_flags,
        'type_flags': zone.type_flags,
    }


def show_partition(partition):
    return {
        'number': partition.number,
        'condition_flags': partition.condition_flags,
        'armed': 'Armed' in partition.condition_flags,
        'last_user': partition.last_user,
    }


def show_user(user):
    if all([x > 9 for x in user.pin]):
        pin = None
    else:
        pin = ''.join([str(c) if c < 10 else '' for c in user.pin])
    return {
        'number': user.number,
        'pin': pin,
        'authority_flags': user.authority_flags,
        'authorized_partitions': user.authorized_partitions,
    }


@app.route('/zones')
def index_zones():
    try:
        result = json.dumps({
            'zones': [show_zone(zone) for zone in CONTROLLER.zones.values()]})
        return flask.Response(result,
                              mimetype='application/json')
    except Exception as e:
        LOG.exception('Failed to index zones')


@app.route('/partitions')
def index_partitions():
    try:
        result = json.dumps({
            'partitions': [show_partition(partition)
                           for partition in CONTROLLER.partitions.values()]})
        return flask.Response(result,
                              mimetype='application/json')
    except Exception as e:
        LOG.exception('Failed to index partitions')


@app.route('/command')
def command():
    args = flask.request.args
    if args.get('cmd') == 'arm':
        if args.get('type') == 'stay':
            CONTROLLER.arm_stay()
        elif args.get('type') == 'exit':
            CONTROLLER.arm_exit()
        else:
            CONTROLLER.arm_auto()
    elif args.get('cmd') == 'disarm':
        CONTROLLER.disarm(args.get('master_pin'))
    return flask.Response()


@app.route('/zones/<int:zone>', methods=['PUT'])
def put_zone(zone):
    zone = CONTROLLER.zones.get(zone)
    if not zone:
        flask.abort(404)
    zonedata = flask.request.json
    if 'bypassed' in zonedata:
        want_bypass = zonedata['bypassed']
        if want_bypass == zone.bypassed:
            flask.abort(409)
        CONTROLLER.zone_bypass_toggle(zone.number)
    result = json.dumps(show_zone(zone))
    return flask.Response(result,
                          mimetype='application/json')


@app.route('/users/<int:user>')
def get_user(user):
    args = flask.request.args
    master_pin = flask.request.headers.get('Master-Pin')
    if not master_pin:
        return 'Master PIN required', 403
    if user not in CONTROLLER.users:
        if 'retry' not in args:
            CONTROLLER.get_user_info(master_pin, user)
            return '', 202
        else:
            return 'Not Found', 404

    user = CONTROLLER.users[user]
    result = json.dumps(show_user(user))
    return flask.Response(result,
                          mimetype='application/json')


@app.route('/users/<int:user>', methods=['PUT'])
def put_user(user):
    if user == 1:
        return 'I refuse to let you break your master user', 403
    master_pin = flask.request.headers.get('Master-Pin')
    if not master_pin:
        return 'Master PIN required', 403
    if user not in CONTROLLER.users:
        CONTROLLER.get_user_info(master_pin, user)
        return '', 204

    user = CONTROLLER.users[user]
    if 'master' in ''.join(user.authority_flags).lower():
        return 'I refuse to let you break a master user', 403

    userdata = flask.request.json
    changed = []
    if 'pin' in userdata:
        pin = userdata['pin']
        changed.append('pin')
        if pin is None:
            user.pin = [15] * 6
        elif len(pin) == 4:
            user.pin = [int(i) for i in pin] + [15, 15]
        elif len(pin) == 6:
            user.pin = [int(i) for i in pin]
        else:
            return 'Invalid PIN format', 400

    if changed:
        CONTROLLER.set_user_info(master_pin, user, changed)

    return flask.Response(json.dumps(show_user(user)),
                          mimetype='application/json')


@app.route('/events')
def get_events():
    index = int(flask.request.args.get('index', 0))
    timeout = int(flask.request.args.get('timeout', 10))
    events = CONTROLLER.event_queue.get(index, timeout=timeout)
    if events:
        index = events[-1].number
        events = [event.payload for event in events]
    return flask.Response(json.dumps({'events': events,
                                      'index': index}),
                          mimetype='application/json')


@app.route('/version')
def get_version():
    return flask.Response(json.dumps({'version': '1.1'}),
                          mimetype='application/json')
