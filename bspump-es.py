#!/usr/bin/env python3
import logging
import asyncio
import asab
import bspump
import bspump.file
import bspump.trigger
import bspump.common
import bspump.elasticsearch

###

L = logging.getLogger(__name__)

###

class SamplePipeline(bspump.Pipeline):


	def __init__(self, app, pipeline_id):
		super().__init__(app, pipeline_id)
		self.build(
			bspump.file.FileLineSource(app, self, config={'path':'test.json'}).on(bspump.trigger.RunOnceTrigger(app)),
			bspump.common.JSONParserProcessor(app, self),
			bspump.elasticsearch.ElasticSearchSink(app, self, "ESConnection1")
		)


if __name__ == '__main__':
	app = bspump.BSPumpApplication()

	svc = app.get_service("bspump.PumpService")

	svc.add_connection(
		bspump.elasticsearch.ElasticSearchConnection(app, "ESConnection1")
	)

	# Construct and register Pipeline
	pl = SamplePipeline(app, 'SamplePipeline')
	svc.add_pipeline(pl)

	app.run()
