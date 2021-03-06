# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function, division, unicode_literals
##
##  This file is part of MoaT, the Master of all Things.
##
##  MoaT is Copyright © 2007-2016 by Matthias Urlichs <matthias@urlichs.de>,
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
from etcd_tree import EtcFloat,EtcString,EtcDir, ReloadRecursive
from qbroker.util import import_string

from . import _VARS, TASKDEF_DIR,TASKDEF
from moat.types import TYPEDEF,TYPEDEF_DIR
from moat.types.etcd import recEtcDir, MoatRef
from moat.util import do_async

import logging
logger = logging.getLogger(__name__)

def _setup_task_vars(types):
	"""Tasks have several global config variables. Their types are set here.
		This is called with the class/typepath to register:
		TASK_DIR/**/TASK or TASKSEF_DIR/**/TASKDEF
		"""
	from etcd_tree.etcd import EtcTypes
	from etcd_tree.node import EtcFloat,EtcInteger
	for t in _VARS:
		if t == "ttl":
			types.register(t)(EtcInteger)
		elif t == "one-shot":
			types.register(t)(EtcInteger) # bool, actually
		else:
			types.register(t)(EtcFloat)

class TaskdefName(EtcString):
	def _ext_update(self, pre):
		super()._ext_update(pre)
		do_async(self.parent._update_taskdef,self._value, _loop=self._loop)

	async def init(self):
		await self.parent._update_taskdef(self._value)

class TaskDir(recEtcDir,EtcDir):
	"""\
		etcd directory for tasks: /task/**/:task

		This stores the data for one instantiation of a Task.
		"""
	
	taskdef = None
	taskdef_name = ''
	taskdef_ready = None

	# the actual task, if running
	# managed by moat.script.task.TaskMaster
	# IMPORTANT: only to be used for debugging and testing!
	_task = None

	def __init__(self,*a,**k):
		super().__init__(*a,**k)
		self.taskdef_ready = asyncio.Event(loop=self._loop)

	@property
	def cls(self):
		return self.taskdef.cls

	async def _update_taskdef(self,name=None):
		if name != self.taskdef_name:
			if 'data' in self:
				self['data'].throw_away()
			td_path = tuple(x for x in name.split('/') if x != "")
			self.taskdef = await self.root.subdir(TASKDEF_DIR+td_path+(TASKDEF,), create=False)
			self.taskdef_name = name
			if 'data' in self:
				await self['data']
		self.taskdef_ready.set()

	def has_update(self):
		if 'taskdef_name' not in self or self.seq == 0:
			return
		if self.taskdef_name != self['taskdef_name']:
			self.taskdef_ready.clear()
			do_async(self._update_taskdef,self['taskdef_name'], _loop=self._loop)
			
	async def _fill_data(self,pre,recursive):
		if not recursive:
			raise ReloadRecursive
		for c in pre.child_nodes:
			if c.name == 'taskdef':
				await self._update_taskdef(c.value)
				break
		await super()._fill_data(pre,recursive)

	def subtype(self,*path,dir=None,pre=None,recursive=None):
		if len(path)==1:
			if path[0] == 'taskdef':
				return TaskdefName
			elif path[0] == 'parent':
				return MoatRef
		elif len(path)==2 and path[0] == 'data':
			name = self.taskdef['data'][path[1]]
			typ_path = tuple(x for x in name.split('/') if x != "")
			typ = self.root.lookup(TYPEDEF_DIR+typ_path+(TYPEDEF,))
			return typ._type.etcd_class
		return super().subtype(*path,dir=dir,pre=pre,recursive=recursive)

_setup_task_vars(TaskDir)
TaskDir.register('parent',MoatRef)

class TaskDef(recEtcDir,EtcDir):
	"""\
		etcd directory for task definitions: /meta/task/**/:taskdef

		This stores generic parameters for a Task (name, filepath/class/code, …).
		"""

	cls = None

	async def init(self):
		await super().init()
		self._update_cls()

	def has_update(self):
		super().has_update()
		self._update_cls()

	def _update_cls(self):
		if self.get('language','') == 'python':
			try:
				self.cls = import_string(self['code'])
			except (ImportError,AttributeError):
				logger.error("%s: Unable to import %s", '/'.join(self.path[:-1]),self['code'])
				self.cls = None

		else:
			self.cls = None
	
_setup_task_vars(TaskDef)

class TaskState(recEtcDir,EtcDir):
	"""\
		etcd directory for task state: /status/task/**/:task

		This stores the actual state of a running Task.
		"""

	@property
	def state(self):
		"""Return a human-readable (but fixed) string describing this task's state"""
		if 'running' in self:
			return 'run'
		elif 'started' in self and ('stopped' not in self or self['started']>self['stopped']):
			return 'crash'
		else:
			return self.get('state','?')

TaskState.register('started')(EtcFloat)
TaskState.register('stopped')(EtcFloat)
TaskState.register('running')(EtcFloat)
TaskState.register('debug_time')(EtcFloat)

