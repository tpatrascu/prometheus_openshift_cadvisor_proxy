#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import math
import urllib.request
import http.server
import socketserver

from openshift import client, config
from prometheus_client.parser import text_string_to_metric_families


class Handler(http.server.SimpleHTTPRequestHandler):
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
            
            with urllib.request.urlopen(scheme + '://' + upstream + '/metrics') as response:
                prometheus_text_response = response.read().decode()
        
            oapi = client.OapiApi(client.ApiClient(header_name='Impersonate-User', header_value=oauth_user))
            user_projects = [x.metadata.name for x in oapi.list_project().items]

            for family in text_string_to_metric_families(prometheus_text_response):
                found_samples = []
                for sample in family.samples:
                    if 'namespace' in sample[1] and sample[1]['namespace'] in user_projects:
                        found_samples.append(sample)
                
                if found_samples:
                    body += '# HELP {} {}\n'.format(family.name, family.documentation)
                    body += '# TYPE {} {}\n'.format(family.name, family.type)
                
                for sample in found_samples:
                    sample_metric_name = sample[0]
                    sample_value = sample[2]
                    if isinstance(sample_value, float) and math.isnan(sample_value):
                        sample_value = 'NaN'
                    sample_prom_labels = ','.join(['{}="{}"'.format(x[0], x[1]) for x in sample[1].iteritems()])
                    body += '{0} {{{1}}} {2}\n'.format(sample_metric_name, sample_prom_labels, sample_value)
        else:
            response_code = 403
            body = 'Authentication error.'
        
        self.send_response(response_code)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.end_headers()
        self.wfile.write(body.encode())


class MyServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    if 'KUBERNETES_PORT' not in os.environ:
        config.load_kube_config()
    else:
        config.load_incluster_config()

    upstream = os.environ['PROMETHEUS_UPSTREAM_TARGET']
    scheme = os.environ['PROMETHEUS_UPSTREAM_SCHEME']
    debug = False
    if 'DEBUG' in os.environ and os.environ['DEBUG'] in ('True', '1'):
        debug = True

    print('Server listening on port 8080...')
    print('Debug', debug)
    httpd = MyServer(('', 8080), Handler)
    httpd.serve_forever()


