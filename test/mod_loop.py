#!/usr/bin/python
# -*- coding: utf-8 -*-

##
##  Copyright (C) 2007  Matthias Urlichs <matthias@urlichs.de>
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

import homevent as h
from homevent.reactor import ShutdownHandler
from homevent.module import load_module
from test import run

input = """\
async:
	wait for 1.9:
		name Foo Bar
wait for 0.2
block:
	log DEBUG Start
	while exists wait Foo Bar:
		log DEBUG waiting
		wait for 0.7
		log DEBUG testing
	log DEBUG Done

shutdown
"""

h.main_words.register_statement(ShutdownHandler)
load_module("loop")
load_module("wait")
load_module("block")
load_module("logging")

run("loop",input)

