#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import math
import urllib2
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn

from openshift import client, config


class Handler(BaseHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        if debug:
            self.log_message('"%s" %s %s', self.requestline, str(code), str(size))

    def log_error(self, format, *args):
        if debug:
            self.log_message(format, *args)
    
    def do_GET(self):
        response_code = 200
        body = ''

        if 'x-forwarded-user' in self.headers:
            oauth_user = self.headers['x-forwarded-user']
            
            try:
                if debug:
                    print("Listing user projects")
                oapi = client.OapiApi(client.ApiClient(header_name='Impersonate-User', header_value=oauth_user))
                user_projects = [x.metadata.name for x in oapi.list_project().items]
            except:
                response_code = 500
                user_projects = []
                body = 'Failed to list user projects.\n'
            
            if debug:
                print("Outputing metrics")

            for project in user_projects:
                for prometheus_job in prometheus_jobs:
                    request_url = '{0}://{1}/federate?match[]={{job="{2}",namespace="{3}"}}'.format(
                                    scheme, upstream, prometheus_job, project)
                    try:
                        body += urllib2.urlopen(request_url).read()
                    except:
                        response_code = 500
                        body = 'Failed to get metrics.\n'
        else:
            response_code = 403
            body = 'Authentication error.\n'
        
        self.send_response(response_code)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.end_headers()
        self.wfile.write(body.encode())
        if debug: print("End request")

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


if __name__ == "__main__":
    if 'KUBERNETES_PORT' not in os.environ:
        config.load_kube_config()
    else:
        config.load_incluster_config()
    
    upstream = os.environ.get('PROMETHEUS_UPSTREAM_TARGET', 'prometheus:9090')
    scheme = os.environ.get('PROMETHEUS_UPSTREAM_SCHEME', 'http')
    prometheus_jobs = os.environ.get('PROMETHEUS_JOBS', 'kubernetes-cadvisor').split(' ')
    
    debug = False
    if 'DEBUG' in os.environ and os.environ['DEBUG'] in ('True', '1'):
        debug = True

    print('Server listening on port 8080...')
    print('Debug', debug)
    httpd = ThreadedHTTPServer(('', 8080), Handler)
    httpd.serve_forever()
