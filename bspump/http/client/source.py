from .abcsource import HTTPABCClientSource

###

class HTTPClientSource(HTTPABCClientSource):

	async def read(self, response):
		response = await response.read()
		self.process(response)

###

class HTTPClientTextSource(HTTPABCClientSource):

	ConfigDefaults = {
		'encoding': '',
	}

	def __init__(self, app, pipeline, id=None, config=None):
		super().__init__(app, pipeline, id=id, config=config)

		self.encoding = self.Config['encoding']
		if self.encoding == '': self.encoding = None

	async def read(self, response):
		response = await response.text(encoding=self.encoding)
		self.process(response)

###

class HTTPClientLineSource(HTTPClientTextSource):


	async def read(self, response):
		response = await response.text(encoding=self.encoding)

		for line in response.split('\n'):
			self.process(line)
