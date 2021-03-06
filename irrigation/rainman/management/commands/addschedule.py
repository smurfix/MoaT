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
		Add a schedule entry.
		"""

from django.core.management.base import BaseCommand, CommandError
from rainman.models import Site,Valve,Schedule,Controller
from datetime import datetime,time,timedelta
from django.db.models import F,Q
from django.utils.timezone import utc
from optparse import make_option

class Command(BaseCommand):
	args = '<interval> <valve>'
	help = 'Create a schedule entry for a valve.'

	def add_arguments(self, parser):
		parser.add_option('-s','--site',
				action='store',
				dest='site',
				default=None,
				help='Select the site to use')
		parser.add_option('-c','--controller',
				action='store',
				dest='controller',
				default=None,
				help='Select the controller to use (may require --site)')
		parser.add_option('-f','--future',
				action='store',
				type=int,
				dest='future',
				default=300,
				help='Create the entry this many seconds in the future')

	def handle(self, *args, **options):
		q = Q()
		now = datetime.utcnow().replace(tzinfo=utc)
		if options['site']:
			q &= Q(controller__site__name=options['site'])
		if options['controller']:
			q &= Q(controller__name=options['controller'])
		duration = int(args[0])
		valve = " ".join(args[1:])
		valve = Valve.objects.get(q, var=valve)
		s=Schedule(valve=valve,start=now+timedelta(0,options["future"]),db_duration=duration)
		s.save()

