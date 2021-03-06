#!/usr/bin/python
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

from moat import patch;patch()
from moat.reactor import ShutdownHandler
from moat.module import load_module
from moat.statement import main_words
from test import run

input = """\

block:
	if exists state foo bar:
		log TRACE "No‽ 1"
	else:
		log TRACE "Yes!"
	if saved state foo bar:
		log TRACE "No‽ 3"
	else:
		log TRACE "Yes!"
state foo bar:
	saved
block:
	if exists state foo bar:
		log TRACE "Yes!"
	else:
		log TRACE "No‽ 2"
	if saved state foo bar:
		log TRACE "No‽ 4"
	else:
		log TRACE "Yes!"

log TRACE Set to ONE
set state one foo bar
block:
	if saved state foo bar:
		log TRACE "Yes!"
	else:
		log TRACE "No‽ 5"
log TRACE Set to TWO
set state two foo bar
on state change foo bar:
	if equal $value three:
		log TRACE Yes It is THREE
block:
	try:
		log TRACE Set to THREE
		set state three foo bar
	catch:
		log DEBUG "No! Error! Woe!"
list state
list state foo bar
block:
	if state three foo bar:
		log TRACE "Yes!"
	else:
		log TRACE "No‽ 8"
block:
	if exists state foo bar:
		log TRACE "Yes!"
	else:
		log TRACE "No‽ 7"
block:
	if last state two foo bar:
		log TRACE "Yes!"
	else:
		log TRACE "No‽ 6"
on whatever:
	var state x foo bar
	log TRACE We got $x
log DEBUG End1
trigger whatever :sync
log DEBUG End2
list state
log DEBUG End3
shutdown
log DEBUG End4
"""

main_words.register_statement(ShutdownHandler)
load_module("state")
load_module("block")
load_module("data")
load_module("on_event")
load_module("logging")
load_module("ifelse")
load_module("bool")
load_module("trigger")
load_module("errors")

run("persist1",input)

