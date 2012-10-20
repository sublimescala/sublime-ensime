import inspect, functools
from functools import partial as bind
import sexp
from sexp import key, sym

############################## DATA STRUCTURES ##############################

class ActiveRecord(object):
  @classmethod
  def parse_list(cls, raw):
    if not raw: return []
    if type(raw[0]) == type(key(":key")):
      m = sexp.sexp_to_key_map(raw)
      field = ":" + cls.__name__.lower() + "s"
      return [cls.parse(raw) for raw in (m[field] if field in m else [])]
    else:
      return [cls.parse(raw) for raw in raw]

  @classmethod
  def parse(cls, raw):
    if not raw: return None
    m = sexp.sexp_to_key_map(raw)
    self = cls()
    populate = getattr(self, "populate")
    populate(m)
    return self

class Note(ActiveRecord):
  def populate(self, m):
    self.message = m[":msg"]
    self.file_name = m[":file"]
    self.severity = m[":severity"]
    self.start = m[":beg"]
    self.end = m[":end"]
    self.line = m[":line"]
    self.col = m[":col"]

class Completion(ActiveRecord):
  def populate(self, m):
    self.name = m[":name"]
    self.signature = m[":type-sig"]
    self.is_callable = bool(m[":is-callable"]) if ":is-callable" in m else False
    self.type_id = m[":type-id"]
    self.to_insert = m[":to-insert"] if ":to-insert" in m else None

class Position(ActiveRecord):
  def populate(self, m):
    self.file_name = m[":file"] if ":file" in m else None
    self.offset = m[":offset"] if ":offset" in m else None
    self.start = m[":start"] if ":start" in m else None
    self.end = m[":end"] if ":end" in m else None

class Symbol(ActiveRecord):
  def populate(self, m):
    self.name = m[":name"]
    self.type = Type.parse(m[":type"])
    self.decl_pos = Position.parse(m[":decl-pos"]) if ":decl-pos" in m else None
    self.is_callable = bool(m[":is-callable"]) if ":is-callable" in m else False
    self.owner_type_id = m[":owner-type-id"] if ":owner-type-id" in m else None

class Type(ActiveRecord):
  def populate(self, m):
    self.name = m[":name"]
    self.type_id = m[":type-id"]
    if ":arrow-type" in m:
      self.arrow_type = True
      self.result_type = Type.parse(m[":result-type"])
      self.param_sections = Params.parse_list(m[":param-sections"]) if ":param-sections" in m else []
    else:
      self.arrow_type = False
      self.full_name = m[":full-name"] if ":full-name" in m else None
      self.decl_as = m[":decl-as"] if ":decl-as" in m else None
      self.decl_pos = Position.parse(m[":pos"]) if ":pos" in m else None
      self.type_args = Type.parse_list(m[":type-args"]) if ":type-args" in m else []
      self.outer_type_id = m[":outer-type-id"] if ":outer-type-id" in m else None
      self.members = Member.parse_list(m[":members"]) if ":members" in m else []

class SymbolSearchResults(ActiveRecord):
  #  we override parse here because raw contains a List of SymbolSearchResult.
  # The ActiveRecord parse method expects raw to contain an object at this point
  # and calls sexp_to_key_map. . 
  @classmethod
  def parse(cls, raw):
    if not raw: return None
    self = cls()
    self.populate(raw)
    return self

  def populate(self, m):
    self.results = SymbolSearchResult.parse_list(m)

class SymbolSearchResult(ActiveRecord):
  def populate(self, m):
    self.name = m[":name"]
    self.local_name = m[":local-name"]
    self.decl_as = m[":decl-as"] if ":decl-as" in m else None
    self.pos = Position.parse(m[":pos"]) if ":pos" in m else None


class RefactorResult(ActiveRecord):
  def populate(self, m):
    self.done = True

class Member(ActiveRecord):
  def populate(self, m):
    pass

class Params(ActiveRecord):
  def populate(self, m):
    self.is_implicit = bool(m[":is-implicit"]) if ":is-implicit" in m else False
    self.params = Param.parse_list(m[":params"]) if ":params" in m else []

class Param(ActiveRecord):
  def populate(self, m):
    pass

class DebugEvent(ActiveRecord):
  def populate(self, m):
    self.type = str(m[":type"])
    if self.type == "output":
      self.body = m[":body"]
    elif self.type == "step":
      self.thread_id = m[":thread-id"]
      self.thread_name = m[":thread-name"]
      self.file_name = m[":file"]
      self.line = m[":line"]
    elif self.type == "breakpoint":
      self.thread_id = m[":thread-id"]
      self.thread_name = m[":thread-name"]
      self.file_name = m[":file"]
      self.line = m[":line"]
    elif self.type == "death":
      pass
    elif self.type == "start":
      pass
    elif self.type == "disconnect":
      pass
    elif self.type == "exception":
      self.exception_id = m[":exception"]
      self.thread_id = m[":thread-id"]
      self.thread_name = m[":thread-name"]
      self.file_name = m[":file"]
      self.line = m[":line"]
    elif self.type == "threadStart":
      self.thread_id = m[":thread-id"]
    elif self.type == "threadDeath":
      self.thread_id = m[":thread-id"]
    else:
      raise Exception("unexpected debug event of type " + str(self.type) + ": " + str(m))

class DebugStartResult(ActiveRecord):
  def __nonzero__(self):
    return not self.error

  def populate(self, m):
    status = m[":status"]
    if status == "success":
      self.error = False
    elif status == "error":
      self.error = True
      self.code = m[":error-code"]
      self.details = m[":details"]
    else:
      raise Exception("unexpected status: " + str(status))

class DebugBacktrace(ActiveRecord):
  def populate(self, m):
    self.frames = DebugStackFrame.parse_list(m[":frames"]) if ":frames" in m else []
    self.thread_id = m[":thread-id"]
    self.thread_name = m[":thread-name"]

class DebugStackFrame(ActiveRecord):
  def populate(self, m):
    self.index = m[":index"]
    self.locals = DebugStackLocal.parse_list(m[":locals"]) if ":locals" in m else []
    self.num_args = m[":num-args"]
    self.class_name = m[":class-name"]
    self.method_name = m[":method-name"]
    self.pc_location = DebugSourcePosition.parse(m[":pc-location"])
    self.this_object_id = m[":this-object-id"]

class DebugSourcePosition(ActiveRecord):
  def populate(self, m):
    self.file_name = m[":file"]
    self.line = m[":line"]

class DebugStackLocal(ActiveRecord):
  def populate(self, m):
    self.index = m[":index"]
    self.name = m[":name"]
    self.summary = m[":summary"]
    self.type_name = m[":type-name"]

class DebugValue(ActiveRecord):
  def populate(self, m):
    self.type = m[":val-type"]
    self.type_name = m[":type-name"]
    self.length = m[":length"] if ":length" in m else None
    self.element_type_name = m[":element-type-name"] if ":element-type-name" in m else None
    self.summary = m[":summary"] if ":summary" in m else None
    self.object_id = m[":object_id"] if ":object_id" in m else None
    self.fields = DebugObjectField.parse_list(m[":fields"]) if ":fields" in m else []
    if str(self.type) == "null" or str(self.type) == "prim" or str(self.type) == "obj" or str(self.type) == "str" or str(self.type) == "arr":
      pass
    else:
      raise Exception("unexpected debug value of type " + str(self.type) + ": " + str(m))

class DebugObjectField(ActiveRecord):
  def populate(self, m):
    self.index = m[":index"]
    self.name = m[":name"]
    self.summary = m[":summary"]
    self.type_name = m[":type-name"]

############################## REMOTE PROCEDURES ##############################

def _mk_req(func, *args, **kwargs):
  if kwargs: raise Exception("kwargs are not supported for " + str(func))
  req = []
  def translate_name(name):
    if name.startswith("_"): name = name[1:]
    name = name.replace("_", "-")
    return name
  req.append(sym("swank:" + translate_name(func.__name__)))
  (spec_args, spec_varargs, spec_keywords, spec_defaults) = inspect.getargspec(func)
  if len(spec_args) != len(args):
    preamble = "argc mismatch in signature of " + str(func) + ": "
    expected = "expected " + str(len(spec_args)) + " args " + str(spec_args) + ", "
    actual = "actual " + str(len(args)) + " args " + str(args) + " with types " + str(map(lambda a: type(a), args))
    raise Exception(preamble + expected + actual)
  if spec_varargs: raise Exception("varargs in signature of " + str(func))
  if spec_keywords: raise Exception("keywords in signature of " + str(func))
  if spec_defaults: raise Exception("defaults in signature of " + str(func))
  req.extend(args[1:]) # strip off self
  return req

def async_rpc(*args):
  parser = args[0] if args else lambda raw: not not raw
  def wrapper(func):
    def wrapped(*args, **kwargs):
      self = args[0]
      if callable(args[-1]):
        on_complete = args[-1]
        args = args[:-1]
      else: on_complete = None
      req = _mk_req(func, *args, **kwargs)
      def callback(payload):
        data = parser(payload)
        if (on_complete): on_complete(data)
      self.env.controller.client.async_req(req, callback, call_back_into_ui_thread = True)
    return wrapped
  return wrapper

def sync_rpc(*args):
  parser = args[0] if args else lambda raw: not not raw
  def wrapper(func):
    def wrapped(*args, **kwargs):
      self = args[0]
      req = _mk_req(func, *args, **kwargs)
      timeout = self.env.settings.get("timeout_" + func.__name__)
      raw = self.env.controller.client.sync_req(req, timeout = timeout)
      return parser(raw)
    return wrapped
  return wrapper

class Rpc(object):
  def __init__(self, env):
    self.env = env

  @async_rpc()
  def init_project(self, conf): pass

  @sync_rpc()
  def shutdown_server(self): pass

  @async_rpc()
  def typecheck_file(self, file_name): pass

  @async_rpc()
  def patch_source(self, file_name, edits): pass

  @sync_rpc(Completion.parse_list)
  def completions(self, file_name, position, max_results, case_sensitive, reload_from_disk): pass

  @async_rpc(Type.parse)
  def type_at_point(self, file_name, position): pass

  @async_rpc(Symbol.parse)
  def symbol_at_point(self, file_name, position): pass

  @async_rpc(SymbolSearchResults.parse_list)
  def import_suggestions(self, file_name, position, type_names, max_results): pass

  @async_rpc(RefactorResult.parse)
  def prepare_refactor(self, procedure_id, refactor_type, parameters, require_confirmation): pass

  @async_rpc()
  def debug_set_break(self, file_name, line): pass

  @async_rpc()
  def debug_clear_break(self, file_name, line): pass

  @async_rpc()
  def debug_clear_all_breaks(self): pass

  @async_rpc(DebugStartResult.parse)
  def _debug_start(self, command_line): pass

  def debug_start(self, launch, breakpoints, on_complete = None):
    def set_breakpoints(breakpoints, status):
      if status:
        if breakpoints: self.debug_set_break(breakpoints[0].file_name, breakpoints[0].line, bind(set_breakpoints, breakpoints[1:]))
        else: self._debug_start(launch.command_line)
      elif on_complete: on_complete(status)
    def clear_breakpoints():
      def callback(status):
        if status: set_breakpoints(breakpoints, status)
        elif on_complete: on_complete(status)
      self.debug_clear_all_breaks(callback)
    clear_breakpoints()

  @async_rpc()
  def debug_stop(self): pass

  @async_rpc()
  def debug_step(self, thread_id): pass

  @async_rpc()
  def debug_next(self, thread_id): pass

  @async_rpc()
  def debug_continue(self, thread_id): pass

  @async_rpc()
  def debug_backtrace(self, thread_id, first_frame, num_frames): pass
