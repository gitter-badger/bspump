import abc
import random

class Trigger(abc.ABC):


	def __init__(self, app, max_triggered=None, id=None):
		self.Id = self.Id = id if id is not None else self.__class__.__name__
		self.Sources = set()

		self._max_triggered = max_triggered


	def add(self, source):
		self.Sources.add(source)


	def remove(self, source):
		self.Sources.remove(source)


	def fire(self):
		if self._max_triggered is None:
			for source in self.Sources:
				source.TriggerEvent.set()

		else:
			# Maximum number of triggered event is defined
			triggered = []
			untriggered = []
			for source in self.Sources:
				if source.TriggerEvent.is_set():
					triggered.append(source)
				else:
					untriggered.append(source)

			to_trigger = self._max_triggered - len(triggered)
			random.shuffle(untriggered)

			while to_trigger > 0:
				if len(untriggered) == 0:
					break
				source = untriggered.pop()
				source.TriggerEvent.set()
				to_trigger -= 1


	def done(self, trigger_source):
		'''
		Called by TriggerSource when cycle is completed.
		'''
		pass
