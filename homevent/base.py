# -*- coding: utf-8 -*-

##
##  Copyright © 2007-2008, Matthias Urlichs <matthias@urlichs.de>
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
	This module holds a few random constants and stuff.
	"""

SYS_PRIO = -10
MIN_PRIO = 0
MAX_PRIO = 100

class Name(tuple):
	"""A class that knows how to print itself the "right" way"""
	delim = u"¦"
	prefix = ""
	suffix = ""

	def __new__(cls,*data):
		if len(data)==1:
			data = data[0]
			if isinstance(data,basestring):
				data = data.split(" ")
		return super(Name,cls).__new__(cls,data)
	def __str__(self):
		return unicode(self).encode("utf-8")
	def __unicode__(self):
		return self.prefix + self.delim.join((unicode(x) for x in self)) + self.suffix
	def __repr__(self):
		return self.__class__.__name__+super(Name,self).__repr__()

class RaisedError(RuntimeError):
	"""An error that has been explicitly raised by a script"""
	no_backtrace = True

	def __init__(self,*params):
		self.params = params
	def __repr__(self):
		return u"‹%s: %s›" % (self.__class__.__name__, repr(self.params))
	def __str__(self):
		return u"%s: %s" % (self.__class__.__name__, " ".join(str(x) for x in self.params))
	def __unicode__(self):
		return u"%s: %s" % (self.__class__.__name__, " ".join(unicode(x) for x in self.params))

