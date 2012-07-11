import sublime
from sublime import *
from sublime_plugin import *
import sexp
from sexp import sexp
from sexp.sexp import key, sym
import functools


def load(window):
  """Intelligently guess the appropriate .ensime file location for the
  given window. Load the .ensime and parse as s-expression.
  Return: (inferred project root directory, config sexp)
  """
  prj_files = [(f + "/.ensime") for f in window.folders()
               if os.path.exists(f + "/.ensime")]
  for f in prj_files:
    root = os.path.dirname(f)
    src = "()"
    with open(f) as open_file:
      src = open_file.read()
    conf = sexp.read(src)
    m = sexp.sexp_to_key_map(conf)
    if m.get(":root-dir"):
      root = m[":root-dir"]
    else:
      conf = conf + [key(":root-dir"), root]
    return (root, conf)

  sublime.error_message(
      "Couldn't find a .ensime file at the root of your project.")
  return (None, None)

def select_subproject(conf, window, on_complete):
  """If more than one subproject is described in the given config sexp,
  prompt the user. Otherwise, return the sole subproject name."""
  m = sexp.sexp_to_key_map(conf)
  subprojects = [sexp.sexp_to_key_map(p) for p in m.get(":subprojects", [])]
  names = [p[":name"] for p in subprojects]
  if len(names) > 1:
    window.show_quick_panel(
        names, lambda i: on_complete(names[i]))
  elif len(names) == 1:
    sublime.set_timeout(functools.partial(on_complete, names[0]), 0)
  else:
    sublime.set_timeout(functools.partial(on_complete, None), 0)


