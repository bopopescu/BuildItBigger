# -*- coding: utf-8 -*- #
# Copyright 2016 Google Inc. All Rights Reserved.
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

"""Methods for suggesting corrections to command typos."""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from googlecloudsdk.command_lib.static_completion import lookup
import six


# Command noun and verb variants mapped to most likely gcloud counterpart.
SYNONYMS = {
    'change': 'update',
    # TODO(b/119555246): Delete 'copy-files' entry once
    # 'gcloud compute copy-files' is removed.
    'copy-files': 'scp',
    'create': 'add',
    'delete': 'remove',
    'describe': 'get',
    # TODO(b/119550681): Delete 'docker' entry once 'gcloud docker' is removed.
    'docker': 'auth-configure-docker',
    'get': 'describe',
    'image': 'images',
    'instance': 'instances',
    'instances': 'instance',
    'make': 'create',
    'modify': 'update',
    'patch': 'update',
    'remove': 'delete',
    'show': 'describe',
}

MIN_RATIO = 0.7  # Minimum score/top_score ratio of accepted suggestions.
MIN_SUGGESTED_GROUPS = 4  # Check for group prefix if less groups than this.
MAX_SUGGESTIONS = 10  # Maximum number of suggestions.


def _GetCanonicalCommandsHelper(tree, results, prefix):
  """Helper method to _GetCanonicalCommands.

  Args:
    tree: The root of the tree that will be traversed to find commands.
    results: The results list to append to.
    prefix: [str], the canonical command line words so far. Once we reach
      a leaf node, prefix contains a canonical command and a copy is
      appended to results.

  Returns:
    None
  """
  if not tree.get(lookup.LOOKUP_COMMANDS):
    results.append(prefix[:])
    return
  for command, command_tree in six.iteritems(tree[lookup.LOOKUP_COMMANDS]):
    if command not in ('alpha', 'beta'):
      prefix.append(command)
      _GetCanonicalCommandsHelper(command_tree, results, prefix)
      prefix.pop()


def _GetCanonicalCommands(tree):
  """Return list of all canonical commands in CLI tree in arbitrary order.

  Args:
    tree: The root of the tree that will be traversed to find commands.

  Returns:
    [[canonical_command_words]]: List of lists, all possible sequences of
      canonical command words in the tree.
  """
  results = []
  _GetCanonicalCommandsHelper(tree, results, prefix=[])
  return results


def _WordScore(index, normalized_command_word,
               canonical_command_word, canonical_command_length):
  """Returns the integer word match score for a command word.

  Args:
    index: The position of the word in the command.
    normalized_command_word: The normalized command word.
    canonical_command_word: The actual command word to compare with.
    canonical_command_length: The length of the actual command.

  Returns:
    The integer word match score, always >= 0.
  """
  score = 0

  # The match can go either way.
  if normalized_command_word in canonical_command_word:
    shorter_word = normalized_command_word
    longer_word = canonical_command_word
  elif canonical_command_word in normalized_command_word:
    shorter_word = canonical_command_word
    longer_word = normalized_command_word
  else:
    return score

  # Inner match must be a word boundary.
  hit = longer_word.find(shorter_word)
  if hit > 0 and longer_word[hit-1] != '-':
    return score

  # Partial hit.
  score += 10

  # Prefer a match in less words.
  if canonical_command_length == 1:
    score += 30
  elif canonical_command_length == 2:
    score += 20
  elif canonical_command_length == 3:
    score += 10

  # Prefer a match in order.
  if index == 0:
    score += 25
  elif index == 1:
    score += 15
  else:
    score += 5

  # Prefer matching more chars and beginning of word.
  # This also handles minor suffix diffs, like singular vs. plural.
  extra = len(longer_word) - len(shorter_word)
  if extra <= 2:
    extra = 3 - extra
    if longer_word.startswith(shorter_word):
      extra *= 2
    score += extra

  return score


def _GetScoredCommandsContaining(command_words):
  """Return scored canonical commands containing input command words.

  Args:
    command_words: List of input command words.

  Returns:
    [(canonical_command_words, score)]: List of tuples, where
      canonical_command_words is a list of strings and score is an integer > 0.
      The tuples are sorted from highest score to lowest, and commands with
      the same score appear in lexicographic order.
  """
  root = lookup.LoadCompletionCliTree()
  normalized_command_words = [command_word.lower().replace('_', '-')
                              for command_word in command_words]
  scored_commands = []
  for canonical_command_words in _GetCanonicalCommands(root):
    canonical_command_length = len(canonical_command_words)
    matched = set()
    score = 0
    for index, canonical_command_word in enumerate(canonical_command_words):
      for normalized_command_word in normalized_command_words:
        # Prefer the higher score of the normalized word or its synonym if any.
        increment = _WordScore(index,
                               normalized_command_word,
                               canonical_command_word,
                               canonical_command_length)
        alternate_command_word = SYNONYMS.get(normalized_command_word)
        if alternate_command_word:
          alternate_increment = _WordScore(index,
                                           alternate_command_word,
                                           canonical_command_word,
                                           canonical_command_length)
          if increment < alternate_increment:
            increment = alternate_increment
        if increment:
          matched.add(normalized_command_word)
          score += increment

    # Prefer all command words to match.
    if len(matched) == len(normalized_command_words):
      score += 10

    # 0 score is always ignored, no need to save.
    if score > 0:
      scored_commands.append((canonical_command_words, score))

  # Sort scores descending, commands ascending.
  scored_commands.sort(key=lambda tuple: (-tuple[1], tuple[0]))
  return scored_commands


def GetCommandSuggestions(command_words):
  """Return suggested commands containing input command words.

  Args:
    command_words: List of input command words.

  Returns:
    [command]: List, where command is a canonical command string with 'gcloud'
      prepended. Only commands whose scores have a ratio of at least MIN_RATIO
      against the top score are returned. At most MAX_SUGGESTIONS command
      strings are returned. If many commands from the same group are being
      suggested, then the common groups are suggested instead.
  """
  suggested_commands = []
  try:
    scored_commands = _GetScoredCommandsContaining(command_words)
  except lookup.CannotHandleCompletionError:
    # Don't crash error reports on static completion misconfiguration.
    scored_commands = None
  if not scored_commands:
    return suggested_commands

  # Scores are greater than zero and sorted highest to lowest.
  top_score = float(scored_commands[0][1])
  too_many = False
  suggested_groups = set()
  for command, score in scored_commands:
    if score / top_score >= MIN_RATIO:
      suggested_commands.append(' '.join(['gcloud'] + command))
      suggested_groups.add(' '.join(command[:-1]))
      if len(suggested_commands) >= MAX_SUGGESTIONS:
        too_many = True
        break

  # Too many most likely indicates the suggested commands have common groups.
  if too_many and len(suggested_groups) < MIN_SUGGESTED_GROUPS:
    min_length = len(scored_commands[0][0])
    for command, score in scored_commands:
      if score / top_score < MIN_RATIO:
        break
      if min_length > len(command):
        min_length = len(command)
    common_length = min_length - 1
    if common_length:
      suggested_groups = set()
      for command, score in scored_commands:
        if score / top_score < MIN_RATIO:
          break
        suggested_groups.add(' '.join(['gcloud'] + command[:common_length]))
        if len(suggested_groups) >= MAX_SUGGESTIONS:
          break
      suggested_commands = sorted(suggested_groups)

  return suggested_commands
