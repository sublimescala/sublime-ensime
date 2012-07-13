import sublime
from sublime import *
from sublime_plugin import *
import difflib


def diff_view_with_disk(view):
  old_s = open(view.file_name()).read()
  new_s = view.substr(Region(0, view.size()))
  return diff(old_s, new_s)


def diff(old_s, new_s):
  """Returns operations necessary to transform old_s into new_s.
  Note: We optimize for the (hypothetically)common case where edits will
  be localized to one small area of a large file.
  """
  limit = min(len(old_s),len(new_s))

  # Find first index (counting from the start) where the
  # strings differ.
  i = 0
  while i < limit:
    if new_s[i] != old_s[i]:
      break
    i += 1

  i = max(i-1, 0)

  # Find first index (counting from the end) where the
  # strings differ.
  j = 1
  while j < (limit - i):  # Cursors should not overlap
    if new_s[-j] != old_s[-j]:
      break
    j += 1

  j = j-1

  # Do diff, only over the modified window.
  d = difflib.SequenceMatcher(isjunk=None,
                              a=old_s[i:len(old_s) - j],
                              b=new_s[i:len(new_s) - j])

  ops = []
  for (op,i1,i2,j1,j2) in d.get_opcodes():
      # Re-add the window offset.
      k1 = i1 + i
      k2 = i2 + i
      l1 = j1 + i
      l2 = j2 + i
      if op == 'delete':
          ops.append(['-', k1, k2])
      elif op == 'insert':
          ops.append(['+', k1, new_s[l1:l2]])
      elif op == 'replace':
          ops.append(['*', k1, k2, new_s[l1:l2]])

  return ops



def apply_operations(input, ops):
  newLen = len(input) + net_length_change(ops)
  result = ""
  offset = 0
  src_cursor = 0
  for op in ops:
    i = op[1]
    copy_len = i - src_cursor
    result += input[src_cursor:src_cursor + copy_len]
    src_cursor += copy_len
    if op[0] == '+':
      [plus, i, text] = op
      result += text
      offset += len(text)
    elif op[0] == '*':
      [mult, i, j, text] = op
      result += text
      offset += len(text) - (j - i)
      src_cursor += (j - i)
    elif op[0] == '-':
      [minus, i, j] = op
      offset -= (j - i)
      src_cursor += (j - i)
  copy_len = len(input) - src_cursor
  result += input[src_cursor:src_cursor + copy_len]
  return result


def net_length_change(ops):
  offset = 0
  for op in ops:
    if op[0] == '+':
      [plus, i, text] = op
      offset += len(text)
    elif op[0] == '*':
      [mult, i, j, text] = op
      offset += len(text) - (j - i)
    elif op[0] == '-':
      [minus, i, j] = op
      offset -= (j - i)
  return offset


def _check(old, new):
  assert apply_operations(old, diff(old, new)) == new

if __name__ == "__main__":
  _check("abc", "abc")
  _check("abc", "qbc")
  _check("abc", "qabc")
  _check("abc", "abcd")
  _check("abc", "aqbqcq")
  _check("abc", "qqqqqbc")
  _check("abc", "")
  _check("abc\n   def", "abc   def")
  _check("", "abcdef")
  _check("abcdef", "abcabcdef")
  _check("abcdef", "abcdefabcabcdef")
  _check("abcdef", "abc")
  _check("abcde", "abcabcde")

