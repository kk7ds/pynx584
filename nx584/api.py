import flask
import json
import traceback


CONTROLLER = None
app = flask.Flask('nx584')


def show_zone(zone):
    return {
        'number': zone.number,
        'name': zone.name,
        'state': zone.state,
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
        print traceback.print_exc()


@app.route('/partitions')
def index_partitions():
    try:
        result = json.dumps({
            'partitions': [show_partition(partition)
                           for partition in CONTROLLER.partitions.values()]})
        return result
    except Exception, e:
        print traceback.print_exc()


@app.route('/command')
def command():
    args = flask.request.args
    if args.get('cmd') == 'arm':
        if args.get('type') == 'stay':
            CONTROLLER.arm_stay()
        else:
            CONTROLLER.arm_exit()
