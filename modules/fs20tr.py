# -*- coding: utf-8 -*-

##
##  Copyright © 2007, Matthias Urlichs <matthias@urlichs.de>
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

"""\
This code implements a primitive FS20 transceiver based on a modified
USB sound interface (or whatever).

"""

from homevent.module import Module
from homevent.logging import log,DEBUG,TRACE,INFO,WARN
from homevent.statement import AttributedStatement,Statement, main_words
from homevent.check import Check,register_condition,unregister_condition
from homevent.run import process_event,process_failure,register_worker,unregister_worker
from homevent.context import Context
from homevent.event import Event,TrySomethingElse
from homevent.fs20 import handler,register_handler,unregister_handler, \
	PREFIX,PREFIX_TIMESTAMP
from homevent.base import Name,MIN_PRIO
from homevent.worker import ExcWorker
from homevent.reactor import shutdown_event
from homevent.twist import callLater

from twisted.internet import protocol,defer,reactor
from twisted.protocols.basic import _PauseableMixin
from twisted.python import failure
from twisted.internet.error import ProcessExitedAlready

recvs = {}
xmits = {}

class my_handler(handler):
	def do_kill(self):
		if self.transport:
			try:
				self.transport.signalProcess("KILL")
			except ProcessExitedAlready:
				pass

class FS20recv(protocol.ProcessProtocol, my_handler):
	stopped = True
	def __init__(self, name, cmd, ctx=Context, timeout=3):
		super(FS20recv,self).__init__(ctx=ctx)
		self.name = name
		self.cmd = cmd
		self.timeout = timeout
		self.timer = None
		self.dbuf = ""
		self.ebuf = ""
		self.timestamp = None
		self.last_timestamp = None
		self.last_dgram = None
		recvs[self.name] = self
		self.stopped = False

	def connectionMade(self):
		log(DEBUG,"FS20 started",self.name)
		self.transport.closeStdin() # we're not writing anything
		self._start_timer()
	
	def _stop_timer(self):
		if self.timer is not None:
			self.timer.cancel()
			self.timer = None

	def _start_timer(self):
		if self.timer is not None:
			self.timer = callLater(True,self.timeout, self.no_data)

	def no_data(self):
		self.timer = None
		self.do_kill()
		process_event(Event(Context(),"fs20","wedged",*self.name)).addErrback(process_failure)

	def dataReceived(self,data):
		db = ""
		e = ""
		if not data: return # empty line
		if data[0] in PREFIX:
			for d in data[1:]:
				if e:
					db += chr(eval("0x"+e+d))
					e=""
				else:
					e=d
			if e:
				raise ValueError("odd length",data)

			self.datagramReceived(data[0], db, timestamp=self.timestamp)
			self.timestamp = None
		elif data[0] == PREFIX_TIMESTAMP:
			self.timestamp = float(data[1:])
		else:
			process_event(Event(Context(),"fs20","unknown","prefix",data[0],data[1:])).addErrback(process_failure)


	def outReceived(self, data):
		self._stop_timer()
		data = (self.dbuf+data).split('\n')
		while len(data) > 1:
			try:
				self.dataReceived(data.pop(0))
			except Exception:
				process_failure()
		self.dbuf = data[0]
		self._start_timer()

	def errReceived(self, data):
		self._stop_timer()
		data = self.ebuf+data
		while True:
			xi = len(data)+1
			try: pi = data.index('\r')
			except ValueError: pi = xi
			try: ei = data.index('\n')
			except ValueError: ei = xi
			if pi==xi and ei==xi:
				break
			if pi < ei:
				data = data[pi+1:]
			else:
				msg = data[:ei]
				data = data[ei+1:]
				process_event(Event(Context(),"fs20","error",msg,*self.name)).addErrback(process_failure)

		self.ebuf = data
		self._start_timer()

	def inConnectionLost(self):
		pass

	def outConnectionLost(self):
		log(DEBUG,"FS20 ending",self.name)

	def errConnectionLost(self):
		pass

	def processEnded(self, status_object):
		log(DEBUG,"FS20 ended",status_object.value.exitCode, self.name)
		if self.stopped:
			del recvs[self.name]
		else:
			self.do_restart()


	def do_start(self):
		if not self.stopped:
			reactor.spawnProcess(self, self.cmd[0], self.cmd, {})
	
	def do_stop(self):
		self.stopped = True
		self.do_kill()
	
	def do_restart(self):
		if not self.stopped:
			callLater(True,5,self.do_start)
		


class FS20receive(AttributedStatement):
	name = ("fs20","receiver")
	doc = "external FS20 receiver"
	long_doc="""\
fs20 receiver ‹name…›
  - declare an external process that listens for FS20 datagrams.
"""

	cmd = None

	def run(self,ctx,**k):
		event = self.params(ctx)
		if len(event) < 1:
			raise SyntaxError(u"Usage: fs20 receiver ‹name…›")
		if self.cmd is None:
			raise SyntaxError(u"requires a 'cmd' subcommand")

		name = Name(event)
		if name in recvs:
			raise RuntimeError(u"‹%s› is already defined" % (name,))
		FS20recv(name=name, cmd=self.cmd, ctx=ctx).do_start()


class FS20listreceive(Statement):
	name = ("list","fs20","receiver")
	doc = "list external FS20 receivers"
	long_doc="""\
list fs20 receiver
  - List known FS20 receivers.
    With a name as parameter, list details for that device.
"""

	def run(self,ctx,**k):
		event = self.params(ctx)
		if len(event) < 1:
			for b in recvs.itervalues():
				print >>self.ctx.out,b.name
		else:
			b = recvs[Name(event)]
			print >>self.ctx.out,"name:",b.name
			print >>self.ctx.out,"command:",Name(b.cmd)
			print >>self.ctx.out,"running:","yes" if b.transport else "no"
			print >>self.ctx.out,"stopped:","yes" if b.stopped else "no"
		print >>self.ctx.out,"."


class FS20delreceive(Statement):
	name = ("del","fs20","receiver")
	doc = "kill of an external fs20 receiver"
	long_doc="""\
del fs20 receiver ‹name…›
  - kill and delete the receiver.
"""

	def run(self,ctx,**k):
		event = self.params(ctx)
		if not len(event):
			raise syntaxerror(u"usage: del fs20 receiver ‹name…›")
		b = recvs[Name(event)]
		b.do_stop()



class FS20xmit(protocol.ProcessProtocol, my_handler):
	stopped = True
	def __init__(self, name, cmd, ctx=Context, timeout=3):
		super(FS20xmit,self).__init__(ctx=ctx)
		self.name = name
		self.cmd = cmd
		self.timeout = timeout
		self.timer = None
		self.dbuf = ""
		self.ebuf = ""
		xmits[self.name] = self
		log(DEBUG,"*** added",self.name,self)
		self.stopped = False

	def connectionMade(self):
		log(DEBUG,"FS20 started",self.name)
#		if "homevent_test" not in os.environ:
#			self.transport.closestdout() # we're not reading anything
		self._start_timer()
		register_handler(self)
	
	def _stop_timer(self):
		if self.timer is not None:
			self.timer.cancel()
			self.timer = None

	def _start_timer(self):
		if self.timer is not None:
			self.timer = callLater(True,self.timeout, self.no_data)

	def no_data(self):
		self.timer = None
		self.do_kill()
		process_event(event(Context(),"fs20","wedged",*self.name)).addErrback(process_failure)

	def send(self,prefix,data):
		data = prefix+"".join("%02x" % ord(x)  for x in data)
		self.transport.write(data+"\n")
		return defer.succeed(None)

	def outReceived(self, data):
		data = (self.dbuf+data).split('\n')
		while len(data) > 1:
			log(DEBUG,"FS20 sender output",data.pop(0),self.name)
		self.dbuf = data[0]

	def errReceived(self, data):
		self._stop_timer()
		data = self.ebuf+data
		while True:
			xi = len(data)+1
			try: pi = data.index('\r')
			except ValueError: pi = xi
			try: ei = data.index('\n')
			except ValueError: ei = xi
			if pi==xi and ei==xi:
				break
			if pi < ei:
				data = data[pi+1:]
			else:
				msg = data[:ei]
				data = data[ei+1]
				process_event(Event(Context(),"fs20","error",msg,*self.name)).addErrback(process_failure)

		self.ebuf = data
		self._start_timer()

	def inConnectionLost(self):
		log(DEBUG,"FS20 ending",self.name)
		unregister_handler(self)

	def outConnectionLost(self):
		pass

	def errConnectionLost(self):
		pass

	def processEnded(self, status_object):
		log(DEBUG,"FS20 ended",status_object.value.exitCode, self.name)
		if self.stopped:
			del xmits[self.name]
		else:
			self.do_restart()


	def do_start(self):
		if not self.stopped:
			reactor.spawnProcess(self, self.cmd[0], self.cmd, {})
	
	def do_stop(self):
		self.stopped = True
		self.do_kill()
	
	def do_restart(self):
		if not self.stopped:
			callLater(True,5,self.do_start)
		

class FS20transmit(AttributedStatement):
	name = ("fs20","sender")
	doc = "external fs20 sender"
	long_doc="""\
fs20 sender ‹name…›
  - Declare an external process that can send FS20 datagrams.
"""

	cmd = None

	def run(self,ctx,**k):
		event = self.params(ctx)
		if len(event) < 1:
			raise SyntaxError(u"Usage: fs20 sender ‹name…›")
		if self.cmd is None:
			raise SyntaxError(u"requires a 'cmd' subcommand")
		name = Name(event)
		if name in xmits:
			raise RuntimeError(u"‹%s› is already defined" % (name,))
		FS20xmit(name=name, cmd=self.cmd, ctx=ctx).do_start()


class FS20listtransmit(Statement):
	name = ("list","fs20","sender")
	doc = "list external FS20 senders"
	long_doc="""\
list fs20 sender
  - List known FS20 senders.
    With a name as parameter, list details for that device.
"""

	def run(self,ctx,**k):
		event = self.params(ctx)
		if len(event) < 1:
			for b in xmits.itervalues():
				print >>self.ctx.out,b.name
		else:
			b = xmits[Name(event)]
			print >>self.ctx.out,"name:",b.name
			print >>self.ctx.out,"command:",Name(b.cmd)
			print >>self.ctx.out,"running:","yes" if b.transport else "no"
			print >>self.ctx.out,"stopped:","yes" if b.stopped else "no"
		print >>self.ctx.out,"."


class FS20deltransmit(Statement):
	name = ("del","fs20","sender")
	doc = "kill of an external fs20 sender"
	long_doc="""\
del fs20 sender ‹name…›
  - kill and delete the sender.
"""

	def run(self,ctx,**k):
		event = self.params(ctx)
		if not len(event):
			raise syntaxerror(u"usage: del fs20 sender ‹name…›")
		b = xmits[Name(event)]
		b.do_stop()



class FS20cmd(Statement):
	name = ("cmd",)
	doc = "set the command to use"
	long_doc=u"""\
cmd ‹command…›
  - set the actual command to use. Don't forget quoting.
	If you need it to be interpreted by a shell, use
		sh "-c" "your command | pipe | or | whatever"
"""

	def run(self,ctx,**k):
		event = self.params(ctx)
		if not len(event):
			raise syntaxerror(u"Usage: cmd ‹whatever…›")
		self.parent.cmd = Name(event)
FS20receive.register_statement(FS20cmd)
FS20transmit.register_statement(FS20cmd)


class FS20tr_shutdown(ExcWorker):
	"""\
		This worker kills off all processes.
		"""
	prio = MIN_PRIO+1

	def does_event(self,ev):
		return (ev is shutdown_event)
	def process(self,queue,*a,**k):
		for proc in recvs.itervalues():
			proc.do_stop()
		for proc in xmits.itervalues():
			proc.do_stop()
		raise TrySomethingElse

	def report(self,*a,**k):
		yield "Shutdown FS20 processes"
		return

FS20tr_shutdown = FS20tr_shutdown("FS20 process killer")



class fs20tr(Module):
	"""\
		Basic fs20 transceiver access.
		"""

	info = "Basic fs20 transceiver"

	def load(self):
		main_words.register_statement(FS20receive)
		main_words.register_statement(FS20listreceive)
		main_words.register_statement(FS20delreceive)
		main_words.register_statement(FS20transmit)
		main_words.register_statement(FS20listtransmit)
		main_words.register_statement(FS20deltransmit)
		register_worker(FS20tr_shutdown)
	
	def unload(self):
		main_words.unregister_statement(FS20receive)
		main_words.unregister_statement(FS20listreceive)
		main_words.unregister_statement(FS20delreceive)
		main_words.unregister_statement(FS20transmit)
		main_words.unregister_statement(FS20listtransmit)
		main_words.unregister_statement(FS20deltransmit)
		unregister_worker(FS20tr_shutdown)
	
init = fs20tr
