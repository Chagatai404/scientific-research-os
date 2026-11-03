"""Browser-session fixture for authority tests. Headers alone are deliberately insufficient."""
import http.client
import json

def session_headers(port):
    """A paired browser: the page holds the token from the printed pairing link and sends it with its CSRF token."""
    from ros import serve
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    connection.request('GET', '/services/session')
    response = connection.getresponse()
    csrf = json.loads(response.read())['result']['csrf']; connection.close()
    return {'X-ROS': '1', 'X-ROS-CSRF': csrf, 'X-ROS-Pair': serve.RUNNING[port].pairing, 'Sec-Fetch-Site': 'same-origin',
            'Origin': 'http://127.0.0.1:' + str(port)}

def decision(port, name, args, record=None):
    headers = session_headers(port)
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    packet = {'name': name, 'args': args, 'record': record}
    c.request('POST', '/services/human-prepare', body=json.dumps(packet), headers=headers)
    response = c.getresponse(); prepared = json.loads(response.read())
    packet['approval'] = prepared['result']['approval']
    c.request('POST', '/services/human-commit', body=json.dumps(packet), headers=headers)
    response = c.getresponse(); data = json.loads(response.read()); status = response.status; c.close()
    return status, data
