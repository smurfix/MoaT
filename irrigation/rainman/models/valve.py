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

import six

from rainman.models import Model
from rainman.models.controller import Controller
from rainman.models.feed import Feed
from rainman.models.env import EnvGroup
from django.db import models as m
from rainman.utils import now, range_intersection,range_union,range_invert, RangeMixin
from datetime import timedelta

@six.python_2_unicode_compatible
class Valve(Model,RangeMixin):
	"""One controller of water"""
	class Meta(Model.Meta):
		unique_together = (("controller", "name"),)
		db_table="rainman_valve"
	def __str__(self):
		return self.name
	name = m.CharField(max_length=200)
	comment = m.CharField(max_length=200,blank=True)
	feed = m.ForeignKey(Feed,related_name="valves")
	controller = m.ForeignKey(Controller,related_name="valves")
	envgroup = m.ForeignKey(EnvGroup,db_column="param_group_id",related_name="valves")
	location = m.CharField(max_length=200,help_text="how to identify the valve on its controller")
	var = m.CharField(max_length=200, unique=True, help_text="name of this output, in MoaT")
	verbose = m.PositiveSmallIntegerField(default=0,help_text="Log lots of changes?")
	# 
	# This describes the area that's watered
	flow = m.FloatField(help_text="liter/sec when open")
	area = m.FloatField(help_text=u"area in m²")# 1 liter, poured onto 1 m², is 1 mm high
	max_level = m.FloatField(default=10, help_text="stop accumulating dryness") # max water level, in mm: stop counting here
	start_level = m.FloatField(default=8, help_text="start watering above this level") # max water level, in mm: stop counting here
	stop_level = m.FloatField(default=3, help_text="stop watering below this level") # min water level, in mm: start when at/above this
	shade = m.FloatField(default=1, help_text="which part of the standard evaporation rate applies here?")

	db_max_run = m.PositiveIntegerField(blank=True,null=True,help_text="maximum time-on",db_column="max_run")
	def _get_max_run(self):
			if self.db_max_run is not None:
					return timedelta(0,self.db_max_run)
	def _set_max_run(self,val):
			self.db_max_run = val.total_seconds()
	max_run = property(_get_max_run,_set_max_run)

	db_min_delay = m.PositiveIntegerField(blank=True,null=True,help_text="minimum time between runs",db_column="min_delay") 
	def _get_min_delay(self):
			if self.db_min_delay is not None:
					return timedelta(0,self.db_min_delay)
	def _set_min_delay(self,val):
			self.db_min_delay = val.total_seconds()
	min_delay = property(_get_min_delay,_set_min_delay)

	def do_shade(self,x):
		# linear
		return x*self.shade
		# quadratic might be better

	runoff = m.FloatField(default=1, help_text="how much incoming rain ends up here?")
	#
#	def get_adj_flow(self,date=None):
#		res = 1
#		for g in self.groups.all():
#			res *= g.get_adj_flow(date)
#		return res
#	adj_flow = property(get_adj_flow)

	def _watering_time(self,level=None):
		if level is None:
			level = self.start_level
		return (level-self.stop_level)*self.area/self.flow
	def raw_watering_time(self,level=None):
		res = self._watering_time(level)
		return timedelta(0,int(res))
	def watering_time(self,level=None,date=None):
		res = self._watering_time(level)
#		res *= self.get_adj_flow(date)
		return timedelta(0,int(res))
	# This describes the current state
	time = m.DateTimeField(db_index=True, default=now, help_text="time when the level was last calculated") # when was the level calculated?
	level = m.FloatField(default=0, help_text="current water capacity, in mm")
	priority = m.BooleanField(default=False, help_text="the last cycle did not finish")
	def list_groups(self):
		return u"¦".join((d.name for d in self.groups.all()))

	@property
	def adj(self):
		f = 1.0
		for g in self.groups.all():
			if g.adj:
				f *= g.adj
		return f

	def _range(self,start,end, forced=False, add=0):
		if start is None:
			start = now()
		r = []

		if forced:
			# If this pass considers force-open times, only this matters
			r.append(self._forced_range(start,end))
		else:
			# Apply groups' times 
			r.append(self._group_range(start,end))
			r.append(self._group_xrange(start,end))

			# First step finished.
			r = [range_intersection(*r)]
			# Now add any group "allowed" one-shots.
			for g in self.groups.all():
				r.append(g._allowed_range(start,end))
			r = [range_union(*r)]

			# Now add any group "not-allowed" one-shots.
			for g in self.groups.all():
				r.append(g._not_blocked_range(start,end))

			# Also apply my own exclusion times
			r.append(self._not_blocked_range(start,end))

		# Exclude times when this valve is already scheduled
		r.append(self._not_scheduled(start,end))

		# Only consider times when the controller can open the valve and
		# there's enough water for it to run
		r.append(self.controller._range(start,end,add=add))
		r.append(self.feed._range(start,end,self.flow,add=add))
		return range_intersection(*r)
	
	def _not_blocked_range(self,start,end):
		for x in self.overrides.filter(start__gte=start-timedelta(1,0),start__lt=end,running=False).order_by("start"):
			if x.end <= start:
				continue
			if x.start > start:
				yield (start,x.start-start)
			start = x.end
		if end>start:
			yield (start,end-start)
				
	def _not_scheduled(self,start,end):
		for x in self.schedules.filter(start__gte=start-timedelta(1,0),start__lt=end).order_by("start"):
			if x.end <= start:
				continue
			if x.start > start:
				yield (start,x.start-start)
			start = x.end+timedelta(0,60)
		if end>start:
			yield (start,end-start)
				
	def _forced_range(self,start,end):
		for x in self.overrides.filter(start__gte=start-timedelta(1,0),start__lt=end,running=True).order_by("start"):
			if x.end <= start:
				continue
			if x.start > start:
				yield (x.start,x.duration)
				start = x.end

	def _group_range(self,start,end):
		gx = []
		for g in self.groups.all():
			for gd in g.days.all():
				gx.append(gd._range(start,end))
		return range_union(*gx)

	def _group_xrange(self,start,end):
		gx = []
		for g in self.groups.all():
			for gd in g.xdays.all():
				gx.append(gd._range(start,end))
		return range_invert(start,end-start,range_union(*gx))
				
	groups = m.ManyToManyField('Group',db_table='rainman_group_valves')
	def list_groups(self):
		return u" ¦ ".join((d.name for d in self.groups.all()))
	@property
	def last_schedule(self):
		try:
			return self.schedules.order_by("-start")[0]
		except IndexError:
			return None

