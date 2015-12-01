# -*- Mode: Python; test-case-name: test_command -*-
# vi:si:et:sw=4:sts=4:ts=4
# on 2015-11-14
##BP

"""
Class for managing tasks.
"""

import asyncio
from dabroker.util import import_string
from etctree.etcd import EtcTypes
from etctree.node import mtFloat,mtBase
import etcd
import inspect
from time import time
import weakref

from ..task import _VARS,  task_var_types, TASK_DIR,TASKDEF_DIR,TASK,TASKDEF

import logging
logger = logging.getLogger(__name__)

class _NOTGIVEN:
	pass

class JobIsRunningError(RuntimeError):
	"""The job is already active"""
	pass

class JobMarkGoneError(RuntimeError):
	"""The job's 'running' mark in etcd is gone (timeout, external kill)"""
	pass

@asyncio.coroutine
def coro_wrapper(proc):
	did_call = False
	if inspect.iscoroutinefunction(proc):
		proc = proc()
		did_call = True
	if inspect.isawaitable(proc):
		return (yield from proc.__await__())
	if inspect.iscoroutine(proc):
		return (yield from proc)
	if not did_call and callable(proc):
		proc = proc()
	return proc

class Task(asyncio.Task):
	"""\
		I am a task to be executed within MoaT.

		The way this works is to declare an etctree entry:
			…
				task
					invalid.domain.host // or some other random hierarchy
						task_one		// your choice
							:task
								summary: This is an example task
								taskdef: NAME
								data: # TODO: according to the schema
									foo: bar
									baz: quux
								restart: 99
								ttl: 12
								refresh: 2
								restart: 10
								retry: 10
								max-retry: 999

				meta
					task
						NAME	// also some hierarchy, set by code
							:taskdef
								code: moat.task.whatever.YourTask
								language: python
								summary: SUMMARY
								data: description (json-schema), TODO

		`moat run task_one` will find your task, read the parameters into a
		dict, and call the task object's "task" procedure.

		`self.loop` contains the asyncio loop to use.
		Set `_global_loop` to True if you need to fork a process. (TODO)

		The defaults for the following values are at /config/run/:

		`ttl` and `refresh` control how long the running state in etcd
		lasts before it is cleaned up; `refresh` says how often it is
		renewed within that timeframe.
		
		"restart" says how long to wait after a successful run, "retry" and
		"max-retry" apply to those that are not. The retry time will be
		multiplied by 1.2345 each time the job fails.
		"""
	name = "do_not_run.py"
	summary = """This is a prototype. Do not use."""
	schema = None
	description = None

	_global_loop=False

	def __init__(self, cmd, name, config={}, runner_data=None):
		"""\
			@cmd: the command object from `moat run`.
			@name: the etcd tree to use, typically /task/DOMAIN/TASKNAME
			@config: some configuration data, possibly an etctree object
			@runner_data: pass-thru attribute for the task runner
			"""
		self._cmd = weakref.ref(cmd)
		self.config = config
		self._ttl = config.get('ttl',None)
		self._refresh = config.get('refresh',None)
		self.run_data = runner_data
		self.name = name
		self.loop = cmd.root.loop
		super().__init__(coro_wrapper(self.run), loop=self.loop)

	def update_ttl(self, ttl,refresh):
		self._ttl = ttl
		self._refresh = refresh

	@classmethod
	def types(cls,types):
		"""\
			`types` is an etctree.EtcTypes instance.
			Add your subtree data types here. The default is Unicode.

			This is a class method.
			"""
		pass
	
	@classmethod
	def task_info(cls,tree):
		"""Feed my data into etcd."""
		dir = dict(
			language='python',
			code=cls.__module__+'.'+cls.__name__,
			summary=cls.summary,
			)
		if cls.schema is not None:
			d['data'] = cls.schema
		return cls.name, dir

	async def run(self):
		"""\
			Run a task with configuration from etcd.
			"""
		r = self._cmd().root
		self.loop = r.loop
		# Add the notifier. It's attached to our config data, so ignore the
		# copy that's passed in by etctree's monitoring.
		if isinstance(self.config,mtBase):
			_note = self.config.add_monitor(lambda _: self.cfg_changed())

		# this sets .etcd and .amqp attributes
		await r.setup(self)
		
		try:
			res = await self.task()
		finally:
			# Clean up
			del self.amqp
			del self.etcd
		return res

	def cfg_changed(self):
		"""\
			Override this to notify your task about changed configuration values.
			"""
		pass

	async def task(self):
		"""Override this to actually run the task"""
		raise NotImplementedError("You need to write the code that does the work!")

async def _run_state(etcd,fullname):
	"""Get a tree for the job's state. Separate function because testing"""
	from etctree.node import mtFloat
	from etctree.etcd import EtcTypes
	types = EtcTypes()
	types.register('started', cls=mtFloat)
	types.register('stopped', cls=mtFloat)
	types.register('running', cls=mtFloat)
	run_state = await etcd.tree('/status/run/'+fullname+'/'+TASK, types=types)
	return run_state

async def runner(proc,cmd,fullname, _ttl=None,_refresh=None):
	"""\
		This is MoaT's standard task runner.
		It takes care of noting the task's state in etcd.
		The task will be killed if there's a conflict.

		@proc: the code to run.
		@cmd: the command interpreter responsible for this.
		@fullname: Path to the command's state in etcd.

		@_ttl: time-to-live for the process lock.
		@_refresh: how often the lock is refreshed within the TTL.
		Thus, ttl=10 and refresh=4 would refresh the lock every 2.5
		seconds. The minimum is 1. A safety margin of 0.1 is added
		internally.

		If _ttl is a callable, it must return a (ttl,refresh) tuple.
		_refresh is ignored in that case.
		"""
	assert ':' not in fullname
	assert fullname[0] != '/'
	assert fullname[-1] != '/'
	logger.debug("Starting %s: %s",fullname,proc)
	r = cmd.root
	await r.setup()
	def get_ttl():
		if callable(_ttl):
			ttl,refresh = _ttl()
		else:
			ttl = _ttl if _ttl is not None else int(r.cfg['config']['run']['ttl'])
			refresh = _refresh if _refresh is not None else float(r.cfg['config']['run']['refresh'])
			if refresh < 1:
				refresh = 1
		refresh = (ttl/(refresh+0.1))
		return ttl,refresh

	run_state = await _run_state(r.etcd,fullname)
	ttl,refresh = get_ttl()

	try:
		if 'running' in run_state:
			raise etcd.EtcdAlreadyExist(message=fullname+'/running', payload=run_state['running']) # pragma: no cover ## timing dependant
		ttl = int(ttl)
		if ttl < 1:
			raise ValueError("TTL must be positive",ttl)
		cseq = await run_state.set("running",time(),ttl=ttl)
	except etcd.EtcdAlreadyExist:
		import pdb;pdb.set_trace()
		logger.warn("Job is already running: %s",fullname)
		raise JobIsRunningError(fullname)
	mod = await run_state.set("started",time())
	await run_state.wait(mod)
	keep_running = False # if it's been superseded, do not delete

	def aborter():
		"""If the updater doesn't work (e.g. if etcd isn't reachable)
		this will terminate the task."""
		logger.error("Aborted %s", fullname)
		nonlocal killer
		try:
			main_task.cancel()
		except Exception:
			pass
		killer = None
	killer = r.loop.call_later(ttl, aborter)

	async def updater(refresh):
		# Periodically refresh the "running" entry.

		# The initial sleep is paired with the initial TTL; otherwise, if
		# somebody changed the TTL from 1 to 100 just as we're starting up,
		# the refresh value would be far too long, the old 
		nonlocal killer
		await asyncio.sleep(refresh, loop=r.loop)
		while True:
			ttl,refresh = get_ttl()
			logger.debug("Run marker check %s",fullname)
			if 'running' not in run_state or run_state._get('running')._cseq != cseq:
				logger.warn("Run marker deleted %s",fullname)
				raise JobMarkGoneError(fullname)
			try:
				await run_state.set("running",time(),ttl=ttl)
			except (etcd.EtcdKeyNotFound,etcd.EtcdCompareFailed):
				raise JobMarkGoneError(fullname)
			killer.cancel()
			killer = r.loop.call_later(ttl,lambda: main_task.cancel())
			logger.debug("Run marker refreshed %s",fullname)
			await asyncio.sleep(refresh, loop=r.loop)
			
	# Now start the updater and the main task.
	run_task = asyncio.ensure_future(updater(refresh), loop=r.loop)
	main_task = asyncio.ensure_future(proc(), loop=r.loop)
	try:
		try:
			try:
				d,p = await asyncio.wait((main_task,run_task), loop=r.loop, return_when=asyncio.FIRST_COMPLETED)
			finally:
				if killer is not None:
					killer.cancel()
			logger.debug("Ended %s :: %s :: %s",fullname, repr(d),repr(p))
		except asyncio.CancelledError:
			# Cancelling an asyncio.wait() doesn't propagate
			logger.debug("Cancelling %s",fullname)
			try:
				main_task.cancel()
				await main_task
			except Exception:
				pass
		# At this point at least one of the two jobs has definitely exited
		# and the "killer" timer is either cancelled or has triggered.
		if run_task.done():
			# The TTL could not be refreshed: kill the job.
			if not run_task.cancelled() and isinstance(run_task.exception(), JobMarkGoneError):
				keep_running = True
			if not main_task.done():
				main_task.cancel()
				try: await main_task
				except Exception: pass
				# We'll get the error later.
		else:
			assert main_task.done()
			run_task.cancel()
			try: await run_task
			except Exception: pass
			# At this point we don't care why the update died.

		if main_task.cancelled():
			# Killed because of a timeout / refresh problem. Major fail.
			await run_state.set("state","fail")
			await run_state.set("message", "Aborted by timeout" if (killer is None) else str(run_task.exception()))
			run_task.result()
			assert False,"the previous line should have raised an error" # pragma: no cover
		else:
			# Not killed, so it either returned a result …
			try:
				res = main_task.result()
			except Exception as exc:
				# … or not.
				await run_state.set("state","error")
				await run_state.set("message",str(exc))
				raise
			else:
				await run_state.set("state","ok")
				await run_state.set("message",str(res))
	finally:
		# Now clean up everything
		await run_state.set("stopped",time())
		if not keep_running:
			try:
				await run_state.delete("running")
			except Exception as exc:
				logger.exception("Could not delete 'running' entry")
		await run_state.wait()
		await run_state.close()

		logger.debug("Ended %s",fullname)


class TaskMaster(asyncio.Future):
	"""An object which controls running and restarting a task from etcd."""
	current_retry = 1
	path = None
	job = None
	timer = None
	exc = None

	def __init__(self, cmd, path, callback=None):
		"""\
			Set up the static part of our task.
			@cmd: the command this is running because of.
			@path: the job's path under /task
			@callback(status,value): called with ("started",None), ("ok",result) or ("error",exc)
			 whenever the job state changes
			"""
		self.loop = cmd.root.loop
		self.cmd = cmd
		self.path = path
		self.name = path # for now
		self.vars = {} # standard task control vars
		self.callback = callback

		for k in _VARS:
			setattr(self,k,-1)

		super().__init__(loop=self.loop)
		
	async def init(self):
		"""Async part of initialization"""
		# In order to read the task data, we need the data definition,
		# which is attached to the taskdef. Thus, first read the poiner to
		# that "manually".
		self.etc = await self.cmd.root._get_etcd()
		self.taskdef_name = (await self.etc.get(TASK_DIR+'/'+self.path+'/'+TASK+'/taskdef')).value

		types = EtcTypes()
		task_var_types(types)
		self.taskdef = await self.etc.tree(TASKDEF_DIR+'/'+self.taskdef_name+'/'+TASKDEF, types=types)
		if self.taskdef['language'] != 'python':
			# Duh.
			raise RuntimeError("This is not a Python job. Aborting.")

		self.cls = import_string(self.taskdef['code'])

		types = EtcTypes()
		task_var_types(types)
		self.cls.types(types.step('data'))

		# Now we can read the task data and follow changes to it.
		self.task = await self.etc.tree(TASK_DIR+'/'+self.path+'/'+TASK, types=types)
		self.gcfg = self.cmd.root.etc_cfg['run']
		self.rcfg = self.cmd.root.cfg['config']['run']
		self._m1 = self.task.add_monitor(self.setup_vars)
		self._m2 = self.taskdef.add_monitor(self.setup_vars)
		self._m3 = self.gcfg.add_monitor(self.setup_vars)
		self.setup_vars()
		
		self._start()
	
	def task_var(self,k):
		for cfg in (self.taskdef, self.task, self.gcfg, self.rcfg):
			if k in cfg:
				return cfg[k]
		raise KeyError(k)

	def setup_vars(self, _=None):
		"""Copy task variables from etcd to local vars"""
		# First, check the basics
#		changed = set()
		if self.taskdef_name != self.task.get('taskdef',''):
			# bail out
			raise RuntimeError("Command changed/deleted: %s / %s" % (self.taskdef_name,self.task.get('taskdef','')))
		self.name = self.task['name']
		for k in _VARS:
			v = self.task_var(k)
#			if self.vars[k] != v:
#				changed.add(k)
			self.vars[k] = v
#		if changed:


	def _get_ttl(self):
		return self.vars['ttl'], self.vars['refresh']

	def _start(self):
		j = lambda: self.cls(self.cmd, self.name, config=self.task._get('data',{}))
		self.job = asyncio.ensure_future(runner(j, self.cmd, self.name, _ttl=self._get_ttl))
		self.job.add_done_callback(self._job_done)
		if self.callback is not None:
			self.callback("start",None)

	async def cancel(self):
		try:
			super().cancel()
		except Exception:
			return
		if self.job is not None:
			try: 
				self.job.cancel()
				await self.job
			except Exception:
				pass
		if self.timer is not None:
			try:
				self.timer.cancel()
			except Exception:
				pass

	def _timer_done(self):
		assert self.job is None
		assert self.timer is not None
		self.timer = None
		self._start()

	def _job_done(self, f):
		assert f is self.job # job ended
		assert self.timer is None
		try:
			res = self.job.result()
		except Exception as exc:
			# TODO: limit the number of retries,
			# this code only does 0 (retry=0) or 1 (max-retry=0) or inf (neither).
			if self.callback is not None:
				self.callback("error",exc)
			if self.exc is None:
				self.current_retry = self.vars['retry']
			else:
				self.current_retry = min(self.current_retry + self.vars['retry']/2, self.vars['max-retry'])
			self.exc = exc
			if not self.current_retry:
				self.set_exception(exc)
				return
		else:
			if self.callback is not None:
				self.callback("ok",res)
			self.exc = None
			self.current_retry = self.vars['restart']
			if not self.current_retry:
				self.set_result(res)
				return
		finally:
			self.job = None

		self.timer = self.loop.call_later(self.current_retry,self._timer_done)
