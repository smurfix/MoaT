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
	try:
		log TRACE Yes A

	try:
		log TRACE Yes B
	catch:
		log ERROR No 1
	
	try:
		log TRACE Yes C
	catch:
		log ERROR No 11
	catch:
		log ERROR No 12
	
	try:
		log TRACE Yes D
		trigger error Foo A
		log ERROR No 21

	try:
		log TRACE Yes E
		trigger error Foo B
		log ERROR No 31
	catch:
		log TRACE Yes F $2

	try:
		log TRACE Yes G
		trigger error Foo C
		log ERROR No 41
	catch:
		log TRACE Yes H $2
	catch:
		log ERROR No 42

	try:
		log TRACE Yes I
		trigger error Foo D
		log ERROR No 51
	catch:
		log TRACE Yes J $2
		trigger error Foo E
		log ERROR No 52

	try:
		log TRACE Yes K
		trigger error Foo F
		log ERROR No 61
	catch:
		log TRACE Yes L $2
		trigger error Foo G
		log ERROR No 62
	catch:
		log TRACE Yes M $2

	try:
		log DEBUG $foobar
		log ERROR No 71
	catch KeyError:
		log TRACE Yes N KEY
	catch AttributeError:
		log TRACE Yes N ATTR
	catch:
		log ERROR No 72

	try:
		trigger error Foo Bar
		log ERROR No 81
	catch Foo:
		log ERROR No 82
	catch Foo Bar Baz:
		log ERROR No 83
	catch Foo Bar:
		log TRACE Yes O
	catch:
		log ERROR No 84
		
	try:
		trigger error Foo Bar
		log ERROR No 91
	catch *a:
		log ERROR No 92
	catch *a *b *c:
		log ERROR No 93
	catch *a *b:
		log TRACE Yes P $a $b
	catch:
		log ERROR No 94
		
shutdown
"""

main_words.register_statement(ShutdownHandler)
load_module("logging")
load_module("errors")
load_module("bool")
load_module("block")

run("errors",input)
