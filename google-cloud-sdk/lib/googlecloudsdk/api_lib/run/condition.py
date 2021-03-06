# -*- coding: utf-8 -*- #
# Copyright 2018 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Wraps a Cloud Run Condition messages, making fields easier to access."""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from collections import Mapping


class Conditions(Mapping):
  """Wraps a repeated ResourceCondition messages field in a dict-like object.

  Resource means a Cloud Run resource, e.g: Configuration.

  Note, status field of conditions is converted to boolean type.
  """

  def __init__(
      self, conditions, ready_condition=None,
      observed_generation=None, generation=None):
    """Constructor.

    Args:
      conditions: A list of objects of condition_class.
      ready_condition: str, The one condition type that indicates it is ready.
      observed_generation: The observedGeneration field of the status object
      generation: The generation of the object. Incremented every time a user
        changes the object directly.
    """
    self._conditions = {}
    for cond in conditions:
      status = None  # Unset or Unknown
      if cond.status.lower() == 'true':
        status = True
      elif cond.status.lower() == 'false':
        status = False
      self._conditions[cond.type] = {
          'reason': cond.reason,
          'message': cond.message,
          'status': status}
    self._ready_condition = ready_condition
    self._fresh = (observed_generation is None or
                   (observed_generation == generation))

  def __getitem__(self, key):
    """Implements evaluation of `self[key]`."""
    return self._conditions[key]

  def __contains__(self, item):
    """Implements evaluation of `item in self`."""
    return any(cond_type == item for cond_type in self._conditions)

  def __len__(self):
    """Implements evaluation of `len(self)`."""
    return len(self._conditions)

  def __iter__(self):
    """Returns a generator yielding the condition types."""
    for cond_type in self._conditions:
      yield cond_type

  def DescriptiveMessage(self):
    """Descriptive message about what's happened to the last user operation."""
    if (self._ready_condition and
        self._ready_condition in self and
        self[self._ready_condition]['message']):
      return self[self._ready_condition]['message']
    return None

  def IsTerminal(self):
    """Whether the conditions are terminal.

    conditions are considered terminal if and only if the ready condition is
    either true or false.

    Returns:
      A bool representing if terminal.
    """
    if not self._ready_condition:
      raise NotImplementedError()
    if not self._fresh:
      return False
    if self._ready_condition not in self._conditions:
      return False
    return self._conditions[self._ready_condition]['status'] is not None

  def IsReady(self):
    if not self.IsTerminal():
      return False
    return self._conditions[self._ready_condition]['status']

  def IsFresh(self):
    return self._fresh
