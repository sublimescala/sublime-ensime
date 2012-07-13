import re

class Keyword:
  def __init__(self, s):
    self.val = s
  def __repr__(self):
    return self.val
  def __eq__(self, k):
    return type(k) == type(self) and self.val == k.val

class Symbol:
  def __init__(self, s):
    self.val = s
  def __repr__(self):
    return self.val
  def __eq__(self, k):
    return type(k) == type(self) and self.val == k.val

def sexp_to_key_map(sexp):
    try:
      key_type = type(key(":key"))
      result = {}
      for i in xrange(0, len(sexp), 2):
          k,val = sexp[i],sexp[i+1]
          if type(k) == key_type:
              result[str(k)] = val
      return result
    except:
      raise Exception("not a sexp: %s" % sexp)

def key(s):
  return Keyword(s)

def sym(s):
  return Symbol(s)

def read(s):
  "Read a sexp expression from a string."
  return read_form(s)[0]

def read_form(str):
  "Read a form."
  if len(str) == 0:
    raise SyntaxError('unexpected EOF while reading form')
  ch = str[0]
  if ch.isspace():
    raise SyntaxError('unexpected whitespace while reading form')
  elif ch == '(':
    return read_list(str)
  elif ch == '"':
    return read_string(str)
  elif ch == ':':
    return read_keyword(str)
  elif ch.isdigit() or ch == "-":
    return read_int(str)
  elif ch.isalpha():
    return read_symbol(str)
  else:
    raise SyntaxError('unexpected character in read_form: ' + ch)

def read_list(str):
  "Read a list from a string."
  if len(str) == 0:
    raise SyntaxError('unexpected EOF while reading list')
  if str[0] != '(':
    raise SyntaxError('expected ( as first char of list')
  str = str[1:]
  lst = []
  while(len(str) > 0):
    ch = str[0]
    if ch.isspace():
      str = str[1:]
      continue
    elif ch == ')':
      return (lst,str[1:])
    else:
      val,remain = read_form(str)
      lst.append(val)
      str = remain
  raise SyntaxError('EOF while reading list')

def read_string(str):
  "Read a string."
  if len(str) == 0:
    raise SyntaxError('unexpected EOF while reading string')
  if str[0] != '"':
    raise SyntaxError('expected ( as first char of string')
  str = str[1:]
  s = ""
  escaped = False
  while(len(str) > 0):
    ch = str[0]
    if ch == '"' and not escaped:
      return (s.replace("\\\\", "\\"),str[1:])
    elif escaped:
      escaped = False
    elif ch == "\\":
      escaped = True
    s = s + ch
    str = str[1:]
  raise SyntaxError('EOF while reading string')


def read_keyword(str):
  "Read a keyword."
  if len(str) == 0:
    raise SyntaxError('unexpected EOF while reading keyword')
  if str[0] != ':':
    raise SyntaxError('expected : as first char of keyword')
  str = str[1:]
  s = ""
  while(len(str) > 0):
    ch = str[0]
    if not (ch.isalpha() or ch.isdigit() or ch == '-'):
      return (Keyword(":" + s),str)
    else:
      s = s + ch
      str = str[1:]

  if len(s) > 1:
    return (Keyword(":" + s),str)
  else:
    raise SyntaxError('EOF while reading keyword')


def read_symbol(str):
  "Read a symbol."
  if len(str) == 0:
    raise SyntaxError('unexpected EOF while reading symbol')
  if not str[0].isalpha():
    raise SyntaxError('expected alpha char as first char of symbol')
  s = ""
  while(len(str) > 0):
    ch = str[0]
    if not (ch.isalpha() or ch.isdigit() or ch == '-' or ch == ":"):
      if s == "t":
        return (True,str)
      elif s == "nil":
        return (False,str)
      else:
        return (Symbol(s),str)
    else:
      s = s + ch
      str = str[1:]

  if len(s) > 0:
    return (Symbol(s),str)
  else:
    raise SyntaxError('EOF while reading symbol')


def read_int(str):
  "Read an integer."
  if len(str) == 0:
    raise SyntaxError('unexpected EOF while reading int')
  s = ""
  while(len(str) > 0):
    ch = str[0]
    if not (ch.isdigit() or ch == '-'):
      return (int(s),str)
    else:
      s = s + ch
      str = str[1:]

  if len(s) > 0:
    return (int(s),str)
  else:
    raise SyntaxError('EOF while reading int')


def to_string(exp):
  "Convert a Python object back into a Lisp-readable string."
  if isinstance(exp, list):
    return '(' + ' '.join(map(to_string, exp)) + ')'
  else:
    return atom_to_str(exp)

def atom_to_str(exp):
  if exp and (type(exp) == type(True)):
    return "t"
  elif (not exp) and (type(exp) == type(False)):
    return "nil"
  elif isinstance(exp, basestring):
    return "\"" + exp.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
  else:
    return str(exp)

def repl(prompt='lis.py> '):
  "A prompt-read-eval-print loop."
  while True:
    val = eval(parse(raw_input(prompt)))
    if val is not None: print to_string(val)


if __name__ == "__main__":
  print(str(read("nil")))
  print(str(read("(\"a b c\")")))
  print(str(read("(a b c)")))
  print(str(read("(:notes (:notes ((:file \"/Users/aemon/projects/cutey_ape/googleclient/experimental/qt_ape/src/apeoutlinemodel.cpp\" :line 37 :col 100 :beg nil :end nil :severity error :msg \"expected ')'\"))))")))
  print(str(read("-4342323")))
  print(str(read(":dude")))
  print(str(read("ape")))
  print(str(read("((((((nil))))))")))
  print(str(read("\"hello \\face\"")))
  print(str(read("\"hello \\fa\\\"ce\"")))
  print(str(read("(:swank-rpc (swank:connection-info) 1)")))
  print(to_string([7147L, [['+', 6227, u'a\n    an'], ['-', 7137, 7138]]]))
