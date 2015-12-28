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
    }


@app.route('/zones')
def index_zones():
    try:
        result = json.dumps({
            'zones': [show_zone(zone) for zone in CONTROLLER.zones.values()]})
        return result
    except Exception as e:
        LOG.exception('Failed to index zones')


@app.route('/partitions')
def index_partitions():
    try:
        result = json.dumps({
            'partitions': [show_partition(partition)
                           for partition in CONTROLLER.partitions.values()]})
        return result
    except Exception, e:
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
    return json.dumps(show_zone(zone))
