import abc
import logging
import json
import asyncio
import time
import aiohttp

import asab
from ..abc.sink import Sink

#

L = logging.getLogger(__name__)

#

class ElasticSearchSink(Sink):


	ConfigDefaults = {
		"index_prefix" : "bspump_",
		"doctype": "doc",
		"time_period": "d",
		"rollover_mechanism": 'time',
		"max_index_size": 30*1024*1024*1024, #This is 30GB
		"timeout": 30

	}


	def __init__(self, app, pipeline, connection, id=None, config=None):
		super().__init__(app, pipeline, id=id, config=config)

		self._doctype = self.Config['doctype']

		self._connection = pipeline.locate_connection(app, connection)

		ro = self.Config['rollover_mechanism']
		if ro == 'time':
			self._rollover_mechanism = ElasticSearchTimeRollover(app, self)
		elif ro == 'size':
			self._rollover_mechanism = ElasticSearchSizeRollover(app, self,  self._connection)
		else:
			if ro != 'fixed':
				L.warning("Unknown rollover mechanism: '{}', defaulting to fixed".format(ro))
			self._rollover_mechanism = ElasticSearchFixedRollover(app, self)

		app.PubSub.subscribe("ElasticSearchConnection.pause!", self._connection_throttle)
		app.PubSub.subscribe("ElasticSearchConnection.unpause!", self._connection_throttle)
	

	def process(self, context, event):
		assert self._rollover_mechanism.Index is not None
		data = '{{"index": {{ "_index": "{}", "_type": "{}" }}\n{}\n'.format(self._rollover_mechanism.Index, self._doctype, json.dumps(event))
		ret = self._connection.consume(data)


	def _connection_throttle(self, event_name, connection):
		if connection != self._connection:
			return

		if event_name == "ElasticSearchConnection.pause!":
			self.Pipeline.throttle(self, True)
		elif event_name == "ElasticSearchConnection.unpause!":
			self.Pipeline.throttle(self, False)
		else:
			raise RuntimeError("Unexpected event name '{}'".format(event_name))

###

class ElasticSearchBaseRollover(abc.ABC):

	def __init__(self, app, essink):
		asyncio.ensure_future(self.refresh_index(), loop=app.Loop)
		app.PubSub.subscribe("Application.tick/600!", self.refresh_index)

		# Throttle pipeline till we have index resolved
		self.Pipeline = essink.Pipeline
		self.Pipeline.throttle(self, True)
		self.Throttled = True

		self.IndexPrefix = essink.Config['index_prefix']
		self.Index = None

		self.Timeout = essink.Config['timeout']


	@abc.abstractmethod
	async def refresh_index(self, event_name=None):
		if (self.Throttled == True) and (self.Index is not None):
			self.Pipeline.throttle(self, False)


class ElasticSearchFixedRollover(ElasticSearchBaseRollover):
	
	async def refresh_index(self, event_name=None):
		self.Index = self.IndexPrefix
		return await super().refresh_index(event_name)


class ElasticSearchTimeRollover(ElasticSearchBaseRollover):

	def __init__(self, app, essink):
		super().__init__(app, essink)
		self.TimePeriod = self.parse_index_period(essink.Config['time_period'])


	async def refresh_index(self, event_name=None):
		seqno = int((time.time() - 1500000000) / self.TimePeriod)
		self.Index = "{}{:05}".format(self.IndexPrefix, seqno)
		return await super().refresh_index(event_name)


	def parse_index_period(self, value):
		if value == 'd': return 60*60*24 # 1 day
		elif value == 'w': return 60*60*24*7 # 7 days
		elif value == 'm': return 60*60*24*28 # 28 days

		return int(value) # Otherwise use value in seconds


class ElasticSearchSizeRollover(ElasticSearchBaseRollover):

	def __init__(self, app, essink, connection):
		super().__init__(app, essink)
		self.MaxIndexSize = int(essink.Config['max_index_size'])
		self.Connection = connection


	async def refresh_index(self, event_name=None):

		url_get_index_size = self.Connection.get_url() + '{}*/_stats/store'.format(self.IndexPrefix)

		async with aiohttp.ClientSession() as session:
			response = await session.get(url_get_index_size, timeout=self.Timeout)

		if response.status != 200:
			L.error("Failed to get indices' statistics from ElasticSearch.")

		resp_body = await response.text()
		data = json.loads(resp_body)

		if data["_shards"]["failed"] != 0:
			L.warning("There was one or more failed shards in the query.")

		# Create a list of indices and sort them 
		ls = []
		for index_name, index_stats in data['indices'].items():
			ls.append(index_name)

		sorted_ls = sorted(ls, key=lambda item: item.rsplit('_', 1)[-1], reverse=True)

		if len(sorted_ls) > 0:
			if (data['indices'][sorted_ls[0]]['primaries']['store']['size_in_bytes'] > self.MaxIndexSize)  and (self.Index is not None):
				_ , split_index = self.Index.rsplit('_',1)
				split_index =int(split_index) + 1
				self.Index = self.IndexPrefix + '{:05}'.format(split_index[1])

		if self.Index is None:
			self.Index = self.IndexPrefix + '{:05}'.format(1)

		return await super().refresh_index(event_name)

