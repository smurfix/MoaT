# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, division, unicode_literals
##
##  This file is part of MoaT, the Master of all Things.
##
##  MoaT is Copyright © 2007-2015 by Matthias Urlichs <matthias@urlichs.de>,
##  it is licensed under the GPLv3. See the file `README.rst` for details,
##  including optimistic statements by the author.
##
##  This program is free software: you can redistribute it and/or modify
##  it under the terms of the GNU General Public License as published by
##  the Free Software Foundation, either version 3 of the License, or
##  (at your option) any later version.
##
##  This program is distributed in the hope that it will be useful,
##  but WITHOUT ANY WARRANTY; without even the implied warranty of
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##  GNU General Public License (included; see the file LICENSE)
##  for more details.
##
##  This header is auto-generated and may self-destruct at any time,
##  courtesy of "make update". The original is in ‘scripts/_boilerplate.py’.
##  Thus, do not remove the next line, or insert any blank lines above.
##BP

import asyncio
from time import time
from weakref import WeakValueDictionary

from etcd_tree import EtcTypes, EtcFloat,EtcInteger,EtcValue,EtcDir
from aio_etcd import StopWatching

from contextlib import suppress
from moat.dev import DEV_DIR,DEV
from moat.script.task import Task
from moat.script.util import objects

from ..proto import OnewireServer
from ..dev import OnewireDevice

import logging
logger = logging.getLogger(__name__)

import re
dev_re = re.compile(r'([0-9a-f]{2})\.([0-9a-f]{12})$', re.I)

async def trigger_hook(loop):
	"""\
		This code is intended to be overridden by tests.

		It returns a future which, when completed, should cause any
		activity to run immediately which otherwise waits for a timer.
		
		The default implementation does nothing but return a static future
		that's never completed.

		Multiple calls to this code must return the same future as long as
		that future is not completed.
		"""
	try:
		return loop._moat_open_future
	except AttributeError:
		loop._moat_open_future = f = asyncio.Future(loop=loop)
		return f

BUS_TTL=30 # presumed max time required to scan a bus
BUS_COUNT=5 # times to not find a whole bus before it's declared dead
DEV_COUNT=5 # times to not find a single device on a bus before it is declared dead

async def scanner(self, name):
	proc = getattr(self,'_scan_'+name)
	while True:
		warned = await proc()

tasks = {} # filled later

class ScanTask(Task):
	"""\
		Common class for 1wire bus scanners.

		Subclasses override the `typ` class variable with some name, and
		the `task_()` method with the periodic activity they want to
		perform. Whenever a device's `scan_for(typ)` returns a number, a
		ScanTask instance with that type will be created for the bus the
		device is on, which will run the task at least that often (in
		seconds).

		
		"""
	typ = None
	_trigger = None

	def __init__(self,parent):
		self.parent = parent
		self.env = parent.env
		self.bus = parent.bus
		self.bus_cached = parent.bus_cached
		super().__init__(parent.env.cmd,('onewire','scan',self.typ,self.env.srv_name)+self.bus.path)

	async def task(self):
		"""\
			run task_() periodically.
			
			Do not override this; override .task_ instead.
			"""
		ts = time()
		long_warned = 0
		while True:
			if self._trigger is None or self._trigger.done():
				if self._trigger is not None:
					try:
						self._trigger.result()
					except StopWatching:
						break
					# propagate an exception, if warranted
				self._trigger = asyncio.Future(loop=self.loop)
			warned = await self.task_()
			t = self.parent.timers[self.typ]
			if t is None:
				return
			# subtract the time spent during the task
			if warned and t < 10:
				t = 10
			ts += t
			nts = time()
			delay = ts - nts
			if delay < 0:
				if not long_warned:
					long_warned = int(100/t)+1
					# thus we get at most one warning every two minutes, more or less
					logger.warning("Task %s took %s seconds, should run every %s",self.name,t-delay,t)
					# TODO: write that warning to etcd instead
				ts = nts
				continue
			elif long_warned:
				long_warned -= 1
			with suppress(asyncio.TimeoutError):
				await asyncio.wait_for(self._trigger,delay, loop=self.loop)

	def trigger(self):
		"""Call to cause an immediate re-scan"""
		if self._trigger is not None and not self._trigger.done():
			self._trigger.set_result(None)

	async def task_(self):
		"""Override this to actually implement the periodic activity."""
		raise RuntimeError("You need to override '%s.task_'" % (self.__class__.__name__,))

class EtcOnewireBus(EtcDir):
	tasks = None
	_set_up = False

	def __init__(self,*a,**k):
		super().__init__(*a,**k)
		self.tasks = WeakValueDictionary()
		self.timers = {}
		env = self.env.onewire_common
		if srv:
			self.bus = env.srv.at('uncached').at(*(self.name.split(' ')))
			self.bus_cached = env.srv.at(*(self.name.split(' ')))

	@property
	def devices(self):
		d = self.env.onewire_common
		if d is None:
			return
		d = d.devices
		for f1,v in self['devices'].items():
			for f2,b in v.items():
				if b > 0:
					continue
				try:
					dev = d[f1][f2][DEV]
				except KeyError:
					continue
				if not isinstance(dev,OnewireDevice):
					# This should not happen. Otherwise we'd need to
					# convert .setup_tasks() into a task.
					raise RuntimeError("XXX: bus lookup incomplete")
				yield dev

	def has_update(self):
		super().has_update()
		if self._seq is None:
			logger.debug("Stopping tasks %s %s %s",self,self.bus.path,list(self.tasks.keys()))
			if self.tasks:
				t,self.tasks = self.tasks,WeakValueDictionary()
				for v in t.values():
					logger.info('CANCEL 16 %s',t)
					t.cancel()
		else:
			self.setup_tasks()

	def setup_tasks(self):
		if not self.env.onewire_run:
			return
		if not tasks:
			for t in objects(__name__,ScanTask):
				tasks[t.typ] = t
		for name,task in tasks.items():
			t = None
			for dev in self.devices:
				f = dev.scan_for(name)
				if f is None:
					pass
				elif t is None or t > f:
					t = f

			self.timers[name] = t
			if t is not None:
				if name not in self.tasks:
					logger.debug("Starting task %s %s %s",self,self.bus.path,name)
					self.tasks[name] = self.env.onewire_run.add_task(task(self))
			else:
				if name in self.tasks:
					t = self.tasks.pop(name)
					try:
						t.cancel()
					except Exception as ex:
						logger.exception("Ending task %s for bus %s", name,self.bus.path)

		self._set_up = True
		
EtcOnewireBus.register('broken', cls=EtcInteger)
EtcOnewireBus.register('devices','*','*', cls=EtcInteger)

class _BusTask(Task):
	schema = {'server':'str', 'delay':'float/time','update_delay':'float/time','ttl':'int'}
	@classmethod
	def types(cls,tree):
		super().types(tree)
		tree.register("delay",cls=EtcFloat)
		tree.register("update_delay",cls=EtcFloat)
		tree.register("ttl",cls=EtcInteger)

class BusRun(_BusTask):
	"""\
		This task runs all required tasks for a 1wire server's buses,
		as determined by the devices that are on the bus
		as determined by etcd.

		Bus scanning is *not* performed here.
		"""
	taskdef="onewire/run"
	summary="Run the buses of a 1wire server"
	_delay = None
	_delay_timer = None

	def add_task(self, t):
		t = asyncio.ensure_future(t, loop=self.loop)
		self.new_tasks.add(t)
		if not self.new_task_trigger.done():
			self.new_task_trigger.set_result(None)
		return t

	async def task(self):
		self.srv = None
		self.tree = None
		self.srv_name = None
		self.new_cfg = asyncio.Future(loop=self.loop)

		self.new_task_trigger = await trigger_hook(self.loop)
		self.new_tasks = set()

		server = self.config['server']
		self.srv_name = server
		update_delay = self.config.get('update_delay',None)

		# Reading the tree requires accessing self.srv.
		# Initializing self.srv requires reading the …/server directory.
		# Thus, first we get that, initialize self.srv with the data …
		tree,srv = await self.etcd.tree("/bus/onewire/"+server,sub=('server',), types=types,static=True)
		self.srv = OnewireServer(srv['host'],srv.get('port',None), loop=self.loop)

		# and then throw it away in favor of the real thing.
		self.tree = await self.etcd.tree("/bus/onewire/"+server, types=types,update_delay=update_delay)
		self.tree.onewire_common = self
		self.tree.onewire_run = self
		nsrv = self.tree['server']
		if srv != nsrv:
			new_cfg.set_result("new_server")
		nsrv.add_monitor(self.cfg_changed)
		del tree

		devtypes=EtcTypes()
		for t in OnewireDevice.dev_paths():
			devtypes.step(t[:-1]).register(DEV,cls=t[-1])
		self.devices = await self.etcd.tree(DEV_DIR+(OnewireDevice.prefix,), types=devtypes,update_delay=update_delay)
		self._trigger = await trigger_hook(self.loop)

		self.tasks = {self.tree.stopped, self.devices.stopped, self.new_cfg,self.new_task_trigger,self._trigger}
		try:
			while True:
				if self.new_cfg.done():
					break
				if self.tree.stopped.done() or self.tree.stopped.done():
					break

				assert self._trigger in self.tasks
				d,self.tasks = await asyncio.wait(self.tasks, loop=self.loop, return_when=asyncio.FIRST_COMPLETED)
				if self._trigger.done():
					try:
						self._trigger.result()
					except StopWatching:
						break
					else:
						self.trigger()
						self._trigger = await trigger_hook(self.loop)
						self.tasks.add(self._trigger)

				if self.new_task_trigger.done():
					self.new_task_trigger = await trigger_hook(self.loop)
					self.tasks.add(self.new_task_trigger)
				if self.new_tasks:
					self.tasks |= self.new_tasks
					self.new_tasks = set()

				for t in d:
					try:
						t.result()
					except asyncio.CancelledError as exc:
						logger.info("Cancelled: %s", t)

		except Exception as exc:
			logger.exception("Something broke")
			raise
		finally:
			if self.tasks:
				for t in self.tasks:
					if not t.done():
						logger.info('CANCEL 17 %s',t)
						try:
							t.cancel()
						except Exception:
							logger.exception("Cancelling %s",t)
				await asyncio.wait(self.tasks, loop=self.loop, return_when=asyncio.ALL_COMPLETED)
			pass
		for t in d:
			if t is not self._trigger:
				t.result()
			# this will re-raise whatever exception triggered the first wait, if any

		await self.tree.close()
		await self.devices.close()

	def _timeout(self,exc=None):
		"""Called from timer"""
		if self._delay is not None and not self._delay.done():
			if exc is None:
				self._delay.set_result("timeout")
			else:
				# This is for the benefit of testing
				self._delay.set_exception(exc)

	def trigger(self):
		"""Tell all tasks to run now. Used mainly for testing."""
		for t in self.tasks:
			if hasattr(t,'trigger'):
				t.trigger()

	def cfg_changed(self, d=None):
		"""\
			Called from task machinery when my basic configuration changes.
			Rather than trying to fix it all up, this stops (and thus
			restarts) the whole thing.
			"""
		if d is None:
			d = self.config
		if not d.notify_seq:
			# Initial call. Not an update. Ignore.
			return
		logger.warn("Config changed %s %s", self,d)
		if not self.new_cfg.done():
			self.new_cfg.set_result(None)


class BusScan(_BusTask):
	"""This task scans all buses of a 1wire server."""
	taskdef="onewire/scan"
	summary="Scan the buses of a 1wire server"
	_delay = None
	_delay_timer = None

	async def _scan_one(self, *bus):
		"""Scan a single bus"""
		b = " ".join(bus)
		bb = self.srv_name+" "+b

		old_devices = set()
		try:
			k = self.old_buses.remove(b)
		except KeyError:
			# The bus is new
			logger.info("New 1wire bus: %s",bb)

			await self.tree['bus'].set(b,{'broken':0,'devices':{}})
			dev_counter = self.tree['bus'][b]['devices']
		else:
			# The bus is known. Remember which devices we think are on it
			dev_counter = self.tree['bus'][b]['devices']
			for d,v in dev_counter.items():
				for e in v.keys():
					old_devices.add((d,e))

		for f in await self.srv.dir('uncached',*bus):
			m = dev_re.match(f)
			if m is None:
				continue
			f1 = m.group(1).lower()
			f2 = m.group(2).lower()
			if (f1,f2) in old_devices:
				old_devices.remove((f1,f2))
			if f1 == '1f':
				await self._scan_one(*(bus+(f,'main')))
				await self._scan_one(*(bus+(f,'aux')))

			if f1 not in self.devices:
				await self.devices.set(f1,{})
			d = await self.devices[f1]
			if f2 not in d:
				await self.devices[f1].set(f2,{DEV:{'path':bb}})
			fd = await d[f2][DEV]
			await fd.setup()
			op = fd.get('path','')
			if op != bb:
				if ' ' in op:
					self.drop_device(fd,delete=False)
				await fd.set('path',bb)

			if f1 not in dev_counter:
				await dev_counter.set(f1,{})
			if f2 not in dev_counter[f1]:
				await dev_counter[f1].set(f2,0)

		# Now mark devices which we didn't see as down.
		# Protect against intermittent failures.
		for f1,f2 in old_devices:
			try:
				errors = dev_counter[f1][f2]
			except KeyError: # pragma: no cover
				# possible race condition
				continue
			if errors >= DEV_COUNT:
				# kill it.
				try:
					dev = self.devices[f1][f2][DEV]
				except KeyError:
					pass
				else:
					await self.drop_device(dev)
			else:
				# wait a bit
				await dev_counter[f1].set(f2,errors+1)

		# Mark this bus as "scanning OK".
		bus = self.tree['bus'][b]
		try:
			errors = bus['broken']
		except KeyError:
			errors = 99
		if errors > 0:
			await bus.set('broken',0)

	async def drop_device(self,dev, delete=True):
		"""When a device vanishes, remove it from the bus it has been at"""
		try:
			p = dev['path']
		except KeyError:
			return
		try:
			s,b = p.split(' ',1)
		except ValueError:
			pass
		else:
			if s == self.srv_name:
				dt = self.tree['bus'][b]['devices']
				drop = False
			else:
				dt = await self.tree.lookup('bus','onewire',s,'bus',b,'devices')
				drop = True
			try:
				f1 = dev.parent.parent.name
				f2 = dev.parent.name
			except AttributeError:
				pass # parent==None: node gone, don't bother
			else:
				try:
					await dt[f1].delete(f2)
				except KeyError as exc:
					logger.exception("Bus node gone? %s.%s on %s %s",f1,f2,s,b)
			finally:
				if drop:
					await dt.close()
		if delete:
			await dev.delete('path')

	async def drop_bus(self,bus):
		"""Somebody unplugged a whole bus"""
		logger.warning("Bus '%s %s' has vanished", self.srv_name,bus.name)
		for f1,v in bus.items():
			for f2 in bus.keys():
				try:
					dev = self.devices[f1][f2][DEV]
				except KeyError:
					pass
				else:
					await self.drop_device(dev, delete=False)
			await self.tree['bus'].delete(bus.name)

	async def task(self):
		self.srv = None
		self.tree = None

		server = self.config['server']
		self.srv_name = server

		# Reading the tree requires accessing self.srv.
		# Initializing self.srv requires reading the …/server directory.
		# Thus, first we get that, initialize self.srv with the data …
		self.tree = await self.etcd.tree.lookup('bus','onewire',server,'server')
		self.srv = OnewireServer(srv['host'],srv.get('port',None), loop=self.loop)

		# and then throw it away in favor of the real thing.
		self.tree = await self.etcd.tree("/bus/onewire/"+server, types=types,env=self)
		del tree

		devtypes=EtcTypes()
		for t in OnewireDevice.dev_paths():
			devtypes.step(t[:-1]).register(DEV,cls=t[-1])
		#tree = await self.cmd.root._get_tree()
		#self.devices = await tree.subdir(DEV_DIR+(OnewireDevice.prefix,))
		self.devices = await self.etcd.tree(DEV_DIR+(OnewireDevice.prefix,), types=devtypes,env=self)
		#self.devices.env = self
		#self.devices._types = devtypes

		if 'scanning' in self.tree:
			# somebody else is processing this bus. Grumble.
			logger.info("Scanning '%s' not possible, locked.",self.srv_name)
			return 2
		await self.tree.set('scanning',value=time(),ttl=BUS_TTL)
		try:
			self.old_buses = set()
			if 'bus' in self.tree:
				for k in self.tree['bus'].keys():
					self.old_buses.add(k)
			else:
				await self.tree.set('bus',{})
			for bus in await self.srv.dir('uncached'):
				if bus.startswith('bus.'):
					await self._scan_one(bus)

			# Delete buses which haven't been seen for some time
			# (to protect against intermittent failures)
			for bus in self.old_buses:
				bus = self.tree['bus'][bus]
				v = bus['broken']
				if v < BUS_COUNT:
					logger.info("Bus '%s' not seen",bus)
					await bus.set('broken',v+1)
				else:
					await self.drop_bus(bus)

		finally:
			if not self.tree.stopped.done():
				await self.tree.delete('scanning')

