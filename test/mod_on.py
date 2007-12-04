#!/usr/bin/python
# -*- coding: utf-8 -*-

from homevent.reactor import ShutdownHandler
from homevent.module import load_module
from homevent.statement import DoNothingHandler, main_words

from test import run

input = u"""\
on fuß:
	name Schau auf deine Füße
	do nothing
on foo:
	prio 49
	name Skipped One
	if false
	log ERROR "This should not be executed"
on foo:
	prio 50
	name Skipped Two
	if true:
		next handler
	log ERROR "This should also not be executed"
on foo:
	prio 55
	name Last Handler
	log DEBUG "This is logged once"
	doc "Causes the prio-60 thing to not be executed"
on foo:
	prio 60
	name not executed
	doc "Is not executed because of the former 'skip next' (until that's gone)"
	log DEBUG "This is logged once too"
on bar *:
	block:
		sync trigger $1
list on
list on Skipped One
list on Skipped Two
sync trigger bar foo
del on Last Handler
sync trigger bar foo
del on 1
list on
trigger fuß
shutdown
"""

main_words.register_statement(DoNothingHandler)
main_words.register_statement(ShutdownHandler)
load_module("block")
load_module("trigger")
load_module("on_event")
load_module("ifelse")
load_module("bool")
load_module("logging")

run("on",input)
