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
list module
list module on_event
list worker
list event

on foo:
	block:
		wait for 0.3:
			name foo waiter
wait for 0.1
trigger foo
wait for 0.1
list event
list event 4
wait for 0.3

shutdown
"""

h.main_words.register_statement(ShutdownHandler)
load_module("trigger")
load_module("wait")
load_module("block")
load_module("list")
load_module("on_event")

run("list",input)

