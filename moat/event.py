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

"""\
This part of the code defines what an event is.
"""
import six

import warnings
from moat.base import Name,RaisedError
from moat.context import Context
from moat.times import now

@six.python_2_unicode_compatible
class TrySomethingElse(RuntimeError):
	"""Error if a conditional does not match"""
	def __init__(self,*args):
		self.args = args
	def __str__(self):
		return "Cannot proceed (%s)" % " ".join((str(x) for x in self.args))

class StopParsing(BaseException):
	"""Quit the current parser."""
	pass

class NeverHappens(BaseException):
	"""This exception is never raised. Needed for conditional handling."""
	pass

class EventNoNameError(ValueError):
	"""\
		You tried to create an unnamed event. That's stupid.
		"""
	pass

event_id = 0

@six.python_2_unicode_compatible
class Event(object):
	"""\
		This is an event. It happens and gets analyzed by the system.
		"""
	loglevel = None
	timestamp = None
	def __init__(self, ctx, *name):
		"""\
			Events have a context and at least one name. For example:
				Event(ctx, "startup")
				Event(ctx, "switch","toggle","sw12")
				Event(ctx, "switch","dim","livingroom","lamp12")
				Event(ctx, "timer","timeout","t123")
			"""
		self._name_check(name)
		#print("E_INIT",name,"with",ctx)
		self.name = Name(name)
		self.ctx = ctx if ctx is not None else Context()
		if "loglevel" in self.ctx:
			self.loglevel = ctx.loglevel
		self.timestamp = now()

		global event_id
		event_id += 1
		self.id = event_id

	def _name_check(self,name):
		if not len(name):
			raise EventNoNameError

	def __repr__(self):
		if not hasattr(self,"name"):
			return "%s(<uninitialized>)" % (self.__class__.__name__,)
		return "%s(%s)" % (self.__class__.__name__, ",".join(repr(n) for n in self.name))

	def __str__(self):
		try:
			return u"↯."+six.text_type(self.name)
		except Exception:
			return "↯ REPORT_ERROR: "+repr(self.name)

	def report(self, verbose=False):
		try:
			yield u"EVENT: "+six.text_type(self.name)
			for k,v in sorted(self.ctx):
				yield u"     : "+k+u"="+six.text_type(v)
		except Exception:
			yield "EVENT: REPORT_ERROR: "+repr(self.name)
	
	def list(self):
		yield (six.text_type(self.name),)

		if self.__class__ is not Event:
			yield ("type",self.__class__.__name__)
		if self.timestamp is not None:
			yield ("timestamp",self.loglevel)
		if self.loglevel is not None:
			yield ("log level",self.loglevel)
		yield ("ctx",self.ctx)

		s = super(Event,self)
		if hasattr(s,'list'): yield s
	
	def __getitem__(self,i):
		u"""… so that you can write e[0] instead of e.name[0]"""
		return self.name[i]
	
	def __getslice__(self,i,j):
		u"""… so that you can write e[2:] instead of e.name[2:]"""
		return list(self.name[i:j])
		# list() because the result may need to be modified by the caller
	
	def __setitem__(self,i,j):
		raise RuntimeError("You cannot modify an event!")

	def __len__(self):
		return len(self.name)
	def __bool__(self):
		return True
	def __iter__(self):
		return self.name.__iter__()
	def __eq__(self,x):
		return self.name.__eq__(x)
	def __ne__(self,x):
		return self.name.__ne__(x)

	def apply(self, ctx=None, drop=0):
		"""\
			Copy an event, applying substitutions.
			This code dies with an AttributeError if there are no
			matching substitutes. This is intentional.
			"""
		w = []

		if ctx is None:
			ctx = self.ctx
		else:
			ctx = ctx(ctx=self.ctx)

		for n in self.name[drop:]:
			if hasattr(n,"startswith") and n.startswith('$'):
				r = ctx[n[1:]]
#				if n == "$X":
#					import sys
#					print("c@%x %s %s"%(id(ctx),n,r), file=sys.stderr)
#					for x in ctx._report():
#						print(": ",x, file=sys.stderr)
				n = r
			w.append(n)
		return self.__class__(ctx, *self.name.apply(ctx=ctx,drop=drop))

	def dup(self, ctx=None, drop=0):
		"""\
			Copy an event, NOT applying substitutions.
			"""
		w = []

		if ctx is None:
			ctx = self.ctx
		else:
			ctx = ctx(ctx=self.ctx)

		return self.__class__(ctx, *self.name[drop:])

