"""Browser-session fixture for authority tests. Headers alone are deliberately insufficient."""
import http.client
import json

def session_headers(port):
    """A paired browser: the pairing link sets the cookie (the session call alone never does), then the page reads its CSRF."""
    from ros import serve
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    connection.request('GET', '/?pair=' + serve.RUNNING[port].pairing)
    response = connection.getresponse(); response.read(); cookie = response.getheader('Set-Cookie').split(';', 1)[0]
    connection.request('GET', '/services/session', headers={'Cookie': cookie})
    response = connection.getresponse()
    csrf = json.loads(response.read())['result']['csrf']; connection.close()
    return {'X-ROS': '1', 'X-ROS-CSRF': csrf, 'Cookie': cookie, 'Sec-Fetch-Site': 'same-origin', 'Origin': 'http://127.0.0.1:' + str(port)}

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
