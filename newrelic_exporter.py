#!/usr/bin/python

import json
import time
import requests
import click
import os

from datetime import datetime, timedelta
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY


class NewrelicCollector(object):
  def __init__(self, apikey, account_number):
    self.graphql_base_url = "https://api.newrelic.com/graphql"
    self.api_key = apikey
    self.account_number = account_number

  def collect(self):
    print("Collecting\n")
    
    # The metrics we want to export.
    metrics = {
        # add the metrics for apdex_target
        'apdexScore': GaugeMetricFamily('newrelic_application_apdex_score',' newrelic application apdex_score', labels=["appname"]),
        'errorRate': GaugeMetricFamily('newrelic_application_error_rate',' newrelic application error_rate', labels=["appname"]),
        'webResponseTimeAverage': GaugeMetricFamily('newrelic_application_response_time','newrelic_application web response time average', labels=["appname"]),
        'webThroughput': GaugeMetricFamily('newrelic_application_throughput','newrelic application web throughput', labels=["appname"]),
    }

    # Get all entity Guids
    headers = {'API-Key': self.api_key}
    resp  = requests.post(url=self.graphql_base_url, headers=headers, data="{actor {entitySearch(queryBuilder: {domain: APM}) {results {entities {... on ApmApplicationEntityOutline {name apmSummary {apdexScore errorRate hostCount instanceCount nonWebResponseTimeAverage nonWebThroughput responseTimeAverage throughput webResponseTimeAverage webThroughput}} guid}}}}}")
    if resp.json().get("errors"):
      print("Error getting newrelic entities:", resp.json())
      return
    # Pass the metrics to the prometheus by looping through entity
    for metric in metrics:
      for entity in  resp.json().get("data").get("actor").get("entitySearch").get("results").get("entities"):
        if entity.get("apmSummary"):
          try:
            metric_value = entity.get("apmSummary")[metric]
            if metric == 'webResponseTimeAverage':
              # Currently apdex_score is in seconds format 
              # convert apdex_score from seconds to miliseconds
              metric_value = metric_value * 1000
            metrics[metric].add_metric([entity["name"]], metric_value)
          except KeyError:
            pass
      yield metrics[metric]

    
    # Get list of deployment which happened in last 1 hour
    # Fetch the account number from the environment variable
    deploymentArray = []
    newrelic_account_number = int(self.account_number)
    resp  = requests.post(url=self.graphql_base_url, headers=headers, data='{{actor{{nrql(query:"SELECT * FROM Deployment SINCE 3600 seconds AGO "accounts:{0}){{nrql results}}}}}}'.format(json.dumps(newrelic_account_number)))
    
    # Iterate through the deployment results and extract relevant information
    for deployments in resp.json().get("data").get("actor").get("nrql").get("results"):
      if resp.json().get("errors"):
        print("Error getting newrelic deployments:", resp.json())
        return
      deploymentArray.append({
        "name": deployments.get("entity.name"),
        "timestamp": deployments.get("timestamp"),
        "version": deployments.get("version")
      })
    
    deploymentMetric = GaugeMetricFamily('newrelic_application_deployment',' newrelic application deployment', labels=["appname", "version"])
    for deployment in deploymentArray:
      # Passing timestamp as seconds because prometheus client automatically converts timestamp to milliseconds
      deploymentMetric.add_metric([deployment['name'], deployment['version']], 1, int(deployment['timestamp']/1000))
    yield deploymentMetric
    
@click.command()
@click.option('--api-key', '-a', envvar='APIKEY', help='API key for newrelic', required=True)
@click.option('--account-number','-n',envvar='NEWRELIC_ACCOUNT_NUMBER', help='Account Number for newrelic',required=True)
def main(api_key, account_number):   
  collector = NewrelicCollector(api_key, account_number)
  REGISTRY.register(collector)
  start_http_server(9126)
  while True: 
    time.sleep(1)
    
if __name__ == "__main__":
  main()

