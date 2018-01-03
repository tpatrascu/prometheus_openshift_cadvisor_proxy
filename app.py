#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import math
import urllib.request

from sanic import Sanic
from sanic.response import text

from openshift import client, config

from prometheus_client.parser import text_string_to_metric_families


app = Sanic()


@app.route("/metrics")
async def metrics(request):
    if 'x-forwarded-user' in request.headers:
        oauth_user = request.headers['x-forwarded-user']
    else:
        return text('Authentication failure', status=403, content_type="text/plain; version=0.0.4")
    
    with urllib.request.urlopen(scheme + '://' + upstream + '/metrics') as response:
        prometheus_text_response = response.read().decode()
    
    oapi = client.OapiApi(client.ApiClient(header_name='Impersonate-User', header_value=oauth_user))
    user_projects = [x.metadata.name for x in oapi.list_project().items]

    body = ''

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
            sample_prom_labels = ','.join(['{}="{}"'.format(x[0], x[1]) for x in sample[1].items()])
            body += '{0} {{{1}}} {2}\n'.format(sample_metric_name, sample_prom_labels, sample_value)
    
    return text(body, status=200, content_type="text/plain; version=0.0.4")


if __name__ == "__main__":
    if 'KUBERNETES_PORT' not in os.environ:
        config.load_kube_config()
    else:
        config.load_incluster_config()

    upstream = os.environ['PROMETHEUS_UPSTREAM_TARGET']
    scheme = os.environ['PROMETHEUS_UPSTREAM_SCHEME']
    debug = False
    if 'DEBUG' in os.environ and os.environ['DEBUG'] in ('True', 1):
        debug = True

    app.run(host="0.0.0.0", port=8080)


