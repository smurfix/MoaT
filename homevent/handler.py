# -*- coding: utf-8 -*-

from __future__ import division

"""\
This code does basic configurable event mangling.

on switch *state livingroom *switch:
	send change $state lights livingroom $switch

on switch * * *:
	if neq $2 outside
	if state on alarm internal
	trigger alarm $2

Given the event "switch on livingroom main", this would cause a
"change on lights livingroom main" event if the internal alarm is off.
Otherwise a "alarm livingroom" would be triggered.

"""

from homevent.parser import SimpleStatement,ComplexStatement,\
	ImmediateCollectProcessor, main_words
from homevent.logging import log_event,log, TRACE
from homevent.run import register_worker,unregister_worker,MIN_PRIO,MAX_PRIO
from homevent.worker import HaltSequence
from twisted.internet import defer

__all__ = ["register_actor","unregister_actor"]

onHandlers = {}
_onHandler_id = 0

def register_actor(handler):
	"""\
		Register a handler for a statement in an "on..." block.
		
		See homevent.parser.Statement and StatementBlock for details.
		"""
	if handler.name in handlers:
		raise ValueError("A handler for '%s' is already registered." % (handler.
name,))
	handlers[handler.name] = handler

def unregister_actor(handler):
	"""\
		Remove this actor.
		"""
	del handlers[handler.name]

class BadArgs(RuntimeError):
	def __str__(self):
		return "Mismatch: %s does not fit %s" % (repr(self.args[0]),repr(self.args[1]))

class BadArgCount(RuntimeError):
	def __str__(self):
		return "The number of event arguments does not match"

class OnEventHandler(ComplexStatement):
	"""This is also a worker."""
	name=("on",)
	doc="on [event...]: [statements]"
	long_doc="""\
The OnEvent handler executes a statement (or a statement sequence)
when an event occurs.

Syntax:
	on [event...]:
		statement
		...

Every "*foo" in the event description is mapped to the corresponding
"$foo" argument in the list.
"""
	in_sub = False
	prio = (MIN_PRIO+MAX_PRIO)//2+1
	procs = None
	skip = False

	def get_processor(self):
		return ImmediateCollectProcessor(parent=self, ctx=self.ctx(words=self))
	processor = property(get_processor)

	def __repr__(self):
		try:
			return "‹"+self.__class__.__name__+"("+str(self.handler_id)+")›"
		except AttributeError:
			try:
				return "‹"+self.__class__.__name__+repr(self.args)+"›"
			except AttributeError:
				return "‹"+self.__class__.__name__+"(?)›"

	def does_event(self,event):
		ie = iter(event)
		ia = iter(self.args)
		ctx = {}
		pos = 0
		while True:
			try: e = ie.next()
			except StopIteration: e = StopIteration
			try: a = ia.next()
			except StopIteration: a = StopIteration
			if e is StopIteration and a is StopIteration:
				return True
			if e is StopIteration or a is StopIteration:
				return False
			if a.startswith('*'):
				if a == '*':
					pos += 1
					a = str(pos)
				else:
					a = a[1:]
				ctx[a] = e
			elif a != e:
				return False

	def grab_args(self,event,ctx):
		ie = iter(event)
		ia = iter(self.args)
		pos = 0
		while True:
			try: e = ie.next()
			except StopIteration: e = StopIteration
			try: a = ia.next()
			except StopIteration: a = StopIteration
			if e is StopIteration and a is StopIteration:
				return
			if e is StopIteration or a is StopIteration:
				raise BadArgCount
			if a.startswith('*'):
				if a == '*':
					pos += 1
					a = str(pos)
				else:
					a = a[1:]
				setattr(ctx,a,e)
			elif a != e:
				raise BadArgs(a,e)
		
	def run(self,event,**k):
		if self.procs is None:
			raise SyntaxError("‹on ...› can only be used as a complex statement")
		ctx = self.ctx(ctx=event.ctx)
		self.grab_args(event,ctx)
		d = defer.Deferred()
		for proc,event in self.procs:
			def go(_,p,e):
				return p(parent=self, ctx=self.ctx).run(e.clone(ctx))
			d.addCallback(go,proc,event)
		if self.skip:
			def skipper(_):
				raise HaltSequence(_)
			d.addCallback(skipper)
		d.callback(None)
		return d

	def input_complex(self,w):
		w = w[len(self.name):]
		log(TRACE, "Create OnEvtHandler: "+repr(w))
		self.args = w
		self.procs = []

	def add(self,proc,event):
		log(TRACE, "add",proc,event)
		self.procs.append((proc,event))

	def done(self):
		global _onHandler_id
		_onHandler_id += 1
		self.handler_id = _onHandler_id
		log(TRACE,"NewHandler",self.handler_id)
		self.name = "¦".join(self.args)
		register_worker(self)
		onHandlers[self.handler_id] = self
	
	def report(self, verbose=False):
		yield "ON "+"¦".join(self.args)
		if not verbose: return
		yield "   prio: "+str(self.prio)
		pref="proc"
		for p,e in self.procs:
			yield "   "+pref+": "+p.__name__+" "+str(e)
			pref="    "
	

class OffEventHandler(SimpleStatement):
	name = ("drop","on")
	doc = "forget about this event handler"
	def run(self,event,**k):
		w = event[len(self.name):]
		if len(w) == 1:
			worker = onHandlers[w[0]]
			unregister_worker(worker)
			del onHandlers[w[0]]
		else:
			raise SyntaxError("Usage: drop on ‹handler_id›")

class OnListHandler(SimpleStatement):
	name = ("list","on")
	doc = "list event handlers"
	def run(self,event,**k):
		w = event[len(self.name):]
		if not len(w):
			try:
				fl = len(str(max(onHandlers.iterkeys())))
			except ValueError:
				print >>self.ctx.out,"No handlers are defined."
			else:
				for id in sorted(onHandlers.iterkeys()):
					h = onHandlers[id]
					print >>self.ctx.out,str(id)+" "*(fl-len(str(id))+1),": ", \
						" ".join(h.args)
		elif len(w) == 1:
			h = onHandlers[w[0]]
			print >>self.ctx.out, h.handler_id,":"," ".join(h.name)
			if hasattr(h,"realname"): print >>self.ctx.out,"Name:",h.realname
			if hasattr(h,"doc"): print >>self.ctx.out,"Doc:",h.doc
		else:
			raise SyntaxError("Usage: list on ‹handler_id›")


class OnPrio(SimpleStatement):
	name = ("prio",)
	doc = "prioritize event handler"
	immediate = True
	long_doc="""\
This statement prioritizes an event handler.
Only one handler within each priority is actually executed.
"""
	def run(self,event,**k):
		w = event[len(self.name):]
		if len(w) != 1:
			raise SyntaxError("Usage: prio ‹priority›")
		try:
			prio = int(w[0])
		except ValueError:
			raise SyntaxError("Usage: prio ‹priority› ⇐ integer priorities only")
		self.parent.prio = prio


class OnSkip(SimpleStatement):
	name = ("skip","next")
	immediate = True
	doc = "skip later event handlers"
	long_doc="""\
This statement causes higher-priority handlers to be skipped.
NOTE: Commands in the same handler, after this one, *are* executed.
"""
	def run(self,event,**k):
		w = event[len(self.name):]
		if len(w):
			raise SyntaxError("Usage: skip next")
		self.parent.skip = True

class DoNothingHandler(SimpleStatement):
	name = ("do","nothing")
	doc = "do not do anything"
	long_doc="""\
This statement does not do anything. It's a placeholder if you want to
explicitly state that some event does not result in any action.
"""
	def run(self,event,**k):
		w = event[len(self.name):]
		if len(w):
			raise SyntaxError("Usage: do nothing")
		log(TRACE,"NOW: do nothing")


def load():
	main_words.register_statement(OnEventHandler)
	main_words.register_statement(OffEventHandler)
	main_words.register_statement(OnListHandler)
	OnEventHandler.register_statement(DoNothingHandler)
	OnEventHandler.register_statement(OnPrio)
	OnEventHandler.register_statement(OnSkip)

def unload():
	main_words.unregister_statement(OnEventHandler)
	main_words.unregister_statement(OffEventHandler)
	main_words.unregister_statement(OnListHandler)
	OnEventHandler.unregister_statement(DoNothingHandler)
	OnEventHandler.unregister_statement(OnPrio)
	OnEventHandler.unregister_statement(OnSkip)

