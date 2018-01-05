#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import math
import time
import threading
import urllib2
import SimpleHTTPServer
import SocketServer

from openshift import client, config
from prometheus_client.parser import text_string_to_metric_families


metrics_cache = {}


def scrape_metrics():
    global metrics_cache

    while True:
        t0 = time.time()
        if debug:
            print('Start scraping {}'.format(request_url))
        
        prometheus_text_response = ''
        try:
            prometheus_text_response = urllib2.urlopen(request_url).read()
        except Exception as e:
            if debug: print(e)

        new_metrics = {}
        for family in text_string_to_metric_families(prometheus_text_response):
            for sample in family.samples:
                if 'namespace' in sample[1]:
                    if sample[1]['namespace'] not in new_metrics:
                        new_metrics[sample[1]['namespace']] = {}
                    
                    if family.name not in new_metrics[sample[1]['namespace']]:
                        new_metrics[sample[1]['namespace']][family.name] = {
                            'type': family.type,
                            'documentation': family.documentation,
                            'samples': [sample],
                        }
                    else:
                        new_metrics[sample[1]['namespace']][family.name]['samples'].append(sample)
    
        metrics_cache = new_metrics

        t1 = time.time()
        total_time = t1 - t0

        if debug:
            print('End scraping. duration: {} seconds'.format(total_time))
        
        if total_time < scrape_interval_sec:
            time.sleep(scrape_interval_sec - total_time)


class Handler(SimpleHTTPServer.SimpleHTTPRequestHandler):
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
                body = 'Failed to list user projects.\n'
                if debug: raise
            
            if debug:
                print("Outputing metrics")
            
            for project in user_projects:
                for metric_family_name, attrs  in metrics_cache[project].iteritems():
                    body += '# HELP {} {}\n'.format(metric_family_name, attrs['documentation'])
                    body += '# TYPE {} {}\n'.format(metric_family_name, attrs['type'])
                
                for sample in attrs['samples']:
                    sample_metric_name = sample[0]
                    sample_value = sample[2]
                    if isinstance(sample_value, float) and math.isnan(sample_value):
                        sample_value = 'NaN'
                    sample_prom_labels = ','.join(['{}="{}"'.format(x[0], x[1]) for x in sample[1].iteritems()])
                    body += '{0} {{{1}}} {2}\n'.format(sample_metric_name, sample_prom_labels, sample_value)
        else:
            response_code = 403
            body = 'Authentication error.\n'
        
        self.send_response(response_code)
        self.send_header('Content-Type', 'text/plain; version=0.0.4')
        self.end_headers()
        self.wfile.write(body.encode())
        if debug: print("End request")


class MyServer(SocketServer.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    if 'KUBERNETES_PORT' not in os.environ:
        config.load_kube_config()
    else:
        config.load_incluster_config()
    
    upstream = os.environ.get('PROMETHEUS_UPSTREAM_TARGET', 'prometheus:9090')
    scheme = os.environ.get('PROMETHEUS_UPSTREAM_SCHEME', 'http')
    prometheus_scrape_job = os.environ.get('PROMETHEUS_SCRAPE_JOB', 'kubernetes-cadvisor')
    scrape_interval_sec = int(os.environ.get('SCRAPE_INTERVAL_SEC', '60'))
    request_url = '{}://{}/federate?match[]={{job="{}"}}'.format(scheme, upstream, prometheus_scrape_job)
    
    debug = False
    if 'DEBUG' in os.environ and os.environ['DEBUG'] in ('True', '1'):
        debug = True

    print('Starting metrics scraping thread')
    thread = threading.Thread(target=scrape_metrics)
    thread.daemon = True
    thread.start()
    time.sleep(2)

    print('Server listening on port 8080...')
    print('Debug', debug)
    httpd = MyServer(('', 8080), Handler)
    httpd.serve_forever()
