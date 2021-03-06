import abc
import logging
import asyncio
from .config import ConfigObject

#

L = logging.getLogger(__name__)

#

class Source(abc.ABC, ConfigObject):

	'''
Each source represent a coroutine/Future/Task that is running in the context of the main loop.
The coroutine method main() contains an implementation of each particular source.

Source MUST await a pipeline ready state prior producing the event.
It is acomplished by `await self.Pipeline.ready()` call.
	'''

	def __init__(self, app, pipeline, id=None, config=None):
		super().__init__("pipeline:{}:{}".format(pipeline.Id, id if id is not None else self.__class__.__name__), config=config)

		self.Id = id if id is not None else self.__class__.__name__
		self.Pipeline = pipeline

		self.MainCoro = None # Contains a main coroutine `main()` if Pipeline is started


	async def process(self, event, context=None):
		'''
		This method is used to emit event into a pipeline.
		'''
		while not self.Pipeline._ready.is_set():
			await self.Pipeline.ready()

		return self.Pipeline.process(event, context=context)


	def start(self, loop):
		if self.MainCoro is not None: return
		self.MainCoro = asyncio.ensure_future(self.main(), loop=loop)


	async def stop(self):
		if self.MainCoro is None: return # Source is not started
		self.MainCoro.cancel()
		await self.MainCoro
		if not self.MainCoro.done():
			L.warning("Source '{}' refused to stop: {}".format(self.Id, self.MainCoro))


	@abc.abstractmethod
	async def main(self):
		raise NotImplemented()


	async def stopped(self):
		'''
		Helper that simplyfies the implementation of sources:

		async def main(self):
			... initialize resources here

			await self.stopped()

			... finalize resources here
		'''
		try:
			while True:
				await asyncio.sleep(60)

		except asyncio.CancelledError:
			pass


	def rest_get(self):
		return {
			"Id": self.Id,
			"Class": self.__class__.__name__
		}

#

class TriggerSource(Source):

	'''
	This is an abstract source class intended as a base for implementation of 'cyclic' sources such as file readers, SQL extractors etc.
	You need to provide a trigger class and implement cycle() method.

	You also may overload the main() method to provide additional parameters for a cycle() method.

	async def main(self):
		async with aiohttp.ClientSession(loop=self.Loop) as session:
			await super().main(session)


	async def cycle(self, session):
		session.get(...)

	'''

	def __init__(self, app, pipeline, id=None, config=None):
		super().__init__(app, pipeline, id=id, config=config)

		self.TriggerEvent = asyncio.Event(loop=app.Loop)
		self.TriggerEvent.clear()
		self.Triggers = set()


	def on(self, trigger):
		'''
		Add trigger
		'''
		trigger.add(self)
		self.Triggers.add(trigger)
		return self


	async def main(self, *args, **kwags):
		while True:
			# Wait for pipeline is ready
			await self.Pipeline.ready()

			# Wait for a trigger
			await self.TriggerEvent.wait()

			# Send begin on a cycle event
			self.Pipeline.PubSub.publish("bspump.pipeline.cycle_begin!", pipeline=self.Pipeline)

			# Execute one cycle
			try:
				await self.cycle(*args, **kwags)
			except BaseException as e:
				self.Pipeline.set_error(e, None)

			# Send end of a cycle event
			self.Pipeline.PubSub.publish("bspump.pipeline.cycle_end!", pipeline=self.Pipeline)

			self.TriggerEvent.clear()
			for trigger in self.Triggers:
				trigger.done(self)


	@abc.abstractmethod
	async def cycle(self, *args, **kwags):
		raise NotImplemented()

	def rest_get(self):
		return super().rest_get().update({
			"triggered": self.TriggerEvent.is_set()
		})
