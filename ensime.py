import sublime
from sublime import *
from sublime_plugin import *
import os, threading, thread, socket, getpass
import subprocess, killableprocess, tempfile, datetime, time
import functools, inspect, traceback, random, re
from sexp import sexp
from sexp.sexp import key, sym
from string import strip
import env
import config

def environment_constructor(window):
  return EnsimeEnvironment(window)

class EnsimeApi:

  def type_check_file(self, file_path, on_complete = None):
    req = ensime_codec.encode_type_check_file(file_path)
    wrapped_on_complete = functools.partial(self.type_check_file_on_complete_wrapper, on_complete) if on_complete else None
    self.env.controller.client.async_req(req, wrapped_on_complete, call_back_into_ui_thread = True)

  def type_check_file_on_complete_wrapper(self, on_complete, payload):
    return on_complete(ensime_codec.decode_type_check_file(resp))

  def add_notes(self, notes):
    self.env.notes += notes
    for v in self.w.views():
      EnsimeHighlights(v).add(notes)

  def clear_notes(self):
    self.env.notes = []
    for v in self.w.views():
      EnsimeHighlights(v).clear_all()

  def inspect_type_at_point(self, file_path, position, on_complete):
    req = ensime_codec.encode_inspect_type_at_point(file_path, position)
    wrapped_on_complete = functools.partial(self.inspect_type_at_point_on_complete_wrapper, on_complete) if on_complete else None
    self.env.controller.client.async_req(req, wrapped_on_complete, call_back_into_ui_thread = True)

  def inspect_type_at_point_on_complete_wrapper(self, on_complete, payload):
    return on_complete(ensime_codec.decode_inspect_type_at_point(payload))

  def get_completions(self, file_path, position):
    req = ensime_codec.encode_completions(file_path, position)
    resp = self.env.controller.client.sync_req(req, timeout=0.5)
    return ensime_codec.decode_completions(resp)

  def symbol_at_point(self, file_path, position, on_complete):
    req = ensime_codec.encode_symbol_at_point(file_path, position)
    wrapped_on_complete = functools.partial(self.symbol_at_point_on_complete_wrapper, on_complete) if on_complete else None
    self.env.controller.client.async_req(req, wrapped_on_complete, call_back_into_ui_thread = True)

  def symbol_at_point_on_complete_wrapper(self, on_complete, payload):
    return on_complete(ensime_codec.decode_symbol_at_point(payload))


class EnsimeEnvironment(object):
  def __init__(self, window):
    # plugin-wide stuff (immutable)
    self.settings = sublime.load_settings("Ensime.sublime-settings")
    server_dir = self.settings.get(
      "ensime_server_path",
      "sublime_ensime\\server"
      if os.name == 'nt' else "sublime_ensime/server")
    self.server_path = (server_dir
                        if (server_dir.startswith("/") or
                            (":/" in server_dir) or
                            (":\\" in server_dir))
                        else os.path.join(sublime.packages_path(), server_dir))
    self.ensime_executable = (self.server_path + '/' +
                              ("bin\\server.bat" if os.name == 'nt'
                               else "bin/server"))
    self.plugin_root = os.path.normpath(os.path.join(self.server_path, ".."))
    self.log_root = os.path.normpath(os.path.join(self.plugin_root, "logs"))

    # instance-specific stuff (immutable)
    (root, conf) = config.load(window)
    self.project_root = root
    self.project_config = conf
    self.valid = self.project_config != None

    # lifecycle (mutable)
    self.lifecycleLock = threading.RLock()
    self.in_transition = False
    self.controller = None

    # shared state (mutable)
    self.notes = []
    self.repl_last_insert = 0
    self.repl_last_fixup = 0
    self.repl_last_history = -1
    self.repl_lock = threading.RLock()
    self.sv = window.get_output_panel("ensime_server")
    self.sv.set_name("ensime_server")
    self.sv.settings().set("word_wrap", True)
    self.cv = window.get_output_panel("ensime_client")
    self.cv.set_name("ensime_client")
    self.cv.settings().set("word_wrap", True)
    self.rv = window.get_output_panel("ensime_repl")
    self.rv.set_name("ensime_repl")
    self.rv.settings().set("word_wrap", True)
    self.curr_sel = None
    self.prev_sel = None


class EnsimeLog(object):

  def status_message(self, msg):
    sublime.set_timeout(functools.partial(sublime.status_message, msg), 0)

  def error_message(self, msg):
    sublime.set_timeout(functools.partial(sublime.error_message, msg), 0)

  def log(self, data, to_disk_only = False):
    sublime.set_timeout(functools.partial(self.log_on_ui_thread, "ui", data, to_disk_only), 0)

  def log_client(self, data, to_disk_only = False):
    sublime.set_timeout(functools.partial(self.log_on_ui_thread, "client", data, to_disk_only), 0)

  def log_server(self, data, to_disk_only = False):
    sublime.set_timeout(functools.partial(self.log_on_ui_thread, "server", data, to_disk_only), 0)

  def log_on_ui_thread(self, flavor, data, to_disk_only):
    if flavor in self.env.settings.get("log_to_console", {}):
      if not to_disk_only:
        print str(data)
    if flavor in self.env.settings.get("log_to_file", {}):
      try:
        if not os.path.exists(self.env.log_root):
          os.mkdir(self.env.log_root)
        file_name = os.path.join(self.env.log_root, flavor + ".log")
        with open(file_name, "a") as f: f.write(data + "\n")
      except:
        pass

  def view_insert(self, v, what):
    sublime.set_timeout(functools.partial(self.view_insert_on_ui_thread, v, what), 0)

  def view_insert_on_ui_thread(self, v, what):
    selection_was_at_end = (len(v.sel()) == 1 and v.sel()[0] == sublime.Region(v.size()))
    v.set_read_only(False)
    edit = v.begin_edit()
    v.insert(edit, v.size(), what or "")
    if selection_was_at_end:
      v.show(v.size())
    v.end_edit(edit)
    v.set_read_only(True)
    self.repl_insert(what)

  def view_show(self, v, focus = False):
    self.w.run_command("show_panel", {"panel": "output." + v.name()})
    if focus:
      sublime.set_timeout(functools.partial(self.w.focus_view, v), 100)
    sublime.set_timeout(functools.partial(v.show, v.size()), 200)

  def repl_prompt(self):
    return "ensime>"

  def repl_fixup_timeout(self):
    return 500

  def repl_show(self):
    self.env.repl_lock.acquire()
    try:
      last = self.env.repl_last_insert
      current = self.env.rv.size()
      if (last == current):
        self.repl_insert(self.repl_prompt(), False)
      self.view_show(self.env.rv, True)
    finally:
      self.env.repl_lock.release()

  def repl_insert(self, what, rewind = True):
    sublime.set_timeout(functools.partial(self.repl_insert_on_ui_thread, what, rewind), 0)

  def repl_insert_on_ui_thread(self, what, rewind):
    self.env.repl_lock.acquire()
    try:
      selection_was_at_end = (len(self.env.rv.sel()) == 1 and self.env.rv.sel()[0] == sublime.Region(self.env.rv.size()))
      was_read_only = self.env.rv.is_read_only()
      self.env.rv.set_read_only(False)
      edit = self.env.rv.begin_edit()
      last = self.env.repl_last_insert
      current = self.env.rv.size()
      if rewind:
        user_input = ""
        if current - last >= len(self.repl_prompt()):
          user_input = self.env.rv.substr(sublime.Region(last + len(self.repl_prompt()), current))
      self.env.rv.insert(edit, current, what or "")
      if rewind:
        self.env.repl_last_insert = self.env.rv.size()
        if current - last >= len(self.repl_prompt()):
          self.repl_schedule_fixup(user_input, self.env.repl_last_insert)
      if selection_was_at_end:
        self.env.rv.show(self.env.rv.size())
        self.env.rv.sel().clear()
        self.env.rv.sel().add(sublime.Region(self.env.rv.size()))
      self.env.rv.end_edit(edit)
      self.env.rv.set_read_only(was_read_only)
    finally:
      self.env.repl_lock.release()

  def repl_schedule_fixup(self, what, last_insert):
    sublime.set_timeout(functools.partial(self.repl_insert_fixup, what, last_insert), self.repl_fixup_timeout())

  def repl_insert_fixup(self, what, last_insert):
    self.env.repl_lock.acquire()
    try:
      if self.env.repl_last_fixup < last_insert:
        self.env.repl_last_fixup = last_insert
        if self.env.repl_last_insert == last_insert:
          selection_was_at_end = (len(self.env.rv.sel()) == 1 and self.env.rv.sel()[0] == sublime.Region(self.env.rv.size()))
          was_read_only = self.env.rv.is_read_only()
          self.env.rv.set_read_only(False)
          edit = self.env.rv.begin_edit()
          self.env.rv.insert(edit, self.env.rv.size(), self.repl_prompt() + what)
          if selection_was_at_end:
            self.env.rv.show(self.env.rv.size())
            self.env.rv.sel().clear()
            self.env.rv.sel().add(sublime.Region(self.env.rv.size()))
          self.env.rv.end_edit(edit)
          self.env.rv.set_read_only(was_read_only)
        self.repl_schedule_fixup(what, self.env.repl_last_insert)
    finally:
      self.env.repl_lock.release()

  def repl_get_input(self):
    self.env.repl_lock.acquire()
    try:
      last = self.env.repl_last_insert
      current = self.env.rv.size()
      return self.env.rv.substr(sublime.Region(last, current))[len(self.repl_prompt()):]
    finally:
      self.env.repl_lock.release()

  def repl_previous_history(self):
    try:
      with open(os.path.join(self.env.log_root, "repl.history")) as f:
        lines = f.readlines() or [""]
        index = self.env.repl_last_history
        if index < 0: index += len(lines)
        index -= 1
        if index < 0: index = 0
        self.env.repl_last_history = index
        return lines[index]
    except:
      self.log(sys.exc_info()[1])

  def repl_next_history(self):
    try:
      with open(os.path.join(self.env.log_root, "repl.history")) as f:
        lines = f.readlines() or [""]
        index = self.env.repl_last_history
        if index < 0: index += len(lines)
        index += 1
        if index >= len(lines): index = len(lines) - 1
        self.env.repl_last_history = index
        return lines[index]
    except:
      self.log(sys.exc_info()[1])

class EnsimeBase(object):
  def __init__(self, owner):
    env.environment_constructor = environment_constructor
    self.owner = owner
    if type(owner) == Window:
      self.env = env.for_window(owner)
      self.w = owner
      self.v = owner.active_view()
      self.f = None
    elif type(owner) == View:
      self.env = env.for_window(owner.window() or sublime.active_window())
      self.w = owner.window()
      self.v = owner
      self.f = owner.file_name()
    else:
      raise "unsupported owner of type: " + str(type(owner))

  def same_files(self, filename1, filename2):
    if not filename1 or not filename2:
      return False
    filename1_normalized = os.path.normcase(os.path.realpath(filename1))
    filename2_normalized = os.path.normcase(os.path.realpath(filename2))
    return filename1 == filename2

  def in_project(self, filename):
    if filename and filename.endswith("scala"):
      root = os.path.normcase(os.path.realpath(self.env.project_root))
      wannabe = os.path.normcase(os.path.realpath(filename))
      return wannabe.startswith(root)

  def project_relative_path(self, filename):
    if not self.in_project(filename):
      return None
    root = os.path.realpath(self.env.project_root)
    wannabe = os.path.realpath(filename)
    return wannabe[len(root) + 1:]

class EnsimeCommon(EnsimeBase, EnsimeLog, EnsimeApi):
  pass

class EnsimeApiImpl(EnsimeCommon):
  def __nonzero__(self):
    controller = self.env and self.env.controller
    socket = controller and controller.client and controller.client.socket
    connected = socket and socket.connected
    return not not connected

def ensime_api(owner):
  return EnsimeApiImpl(owner)

class EnsimeWindowCommand(EnsimeCommon, WindowCommand):
  def __init__(self, window):
    super(EnsimeWindowCommand, self).__init__(window)
    self.window = window

class EnsimeTextCommand(EnsimeCommon, TextCommand):
  def __init__(self, view):
    super(EnsimeTextCommand, self).__init__(view)
    self.view = view

class ScalaOnly:
  def is_enabled(self):
    return self.w and self.f and self.f.lower().endswith(".scala")

class NotRunningOnly:
  def is_enabled(self):
    return not self.env.in_transition and self.env.valid and not (self.env.controller and self.env.controller.running)

class RunningOnly:
  def is_enabled(self):
    return not self.env.in_transition and self.env.valid and self.env.controller and self.env.controller.running

class ReadyEnsimeOnly:
  def is_enabled(self):
    return not self.env.in_transition and self.env.valid and self.env.controller and self.env.controller.ready

class ConnectedEnsimeOnly:
  def is_enabled(self):
    return not self.env.in_transition and self.env.valid and self.env.controller and self.env.controller.connected

class ProjectFileOnly:
  def is_enabled(self):
    return not self.env.in_transition and self.env.valid and self.env.controller and self.env.controller.connected and self.in_project(self.v.file_name())

class EnsimeContextProvider(EventListener):
  def on_query_context(self, view, key, operator, operand, match_all):
    if key == "ensime_ready":
      try:
        return ensime_api(view).env.controller.ready
      except:
        return False
    if key == "ensime_connected":
      try:
        return ensime_api(view).env.controller.connected
      except:
        return False
    if key == "ensime_repl_enabled":
      try:
        return not not ensime_api(view).env.settings.get("log_to_console")
      except:
        return False
    if key == "ensime_repl_opened":
      return view.name() == "ensime_repl"
    return None

class EnsimeClientListener:
  def on_client_async_data(self, data):
    pass

class EnsimeClientSocket(EnsimeCommon):
  def __init__(self, owner, port, timeout, handlers):
    super(EnsimeClientSocket, self).__init__(owner)
    self.port = port
    self.timeout = timeout
    self.connected = False
    self.handlers = handlers
    self._lock = threading.RLock()
    self._connect_lock = threading.RLock()
    self._receiver = None
    self.socket = None

  def notify_async_data(self, data):
    for handler in self.handlers:
      if handler:
        handler.on_client_async_data(data)

  def receive_loop(self):
    while self.connected:
      try:
        msglen = self.socket.recv(6)
        if msglen:
          msglen = int(msglen, 16)
          # self.log_client("RECV: incoming message of " + str(msglen) + " bytes")

          buf = ""
          while len(buf) < msglen:
            chunk = self.socket.recv(msglen - len(buf))
            if chunk:
              # self.log_client("RECV: received a chunk of " + str(len(chunk)) + " bytes")
              buf += chunk
            else:
              raise "fatal error: recv returned None"
          self.log_client("RECV: " + buf)

          try:
            s = buf.decode('utf-8')
            form = sexp.read(s)
            self.notify_async_data(form)
          except:
            self.log_client("failed to parse incoming message")
            raise
        else:
          raise "fatal error: recv returned None"
      except Exception:
        self.log_client("*****    ERROR     *****")
        self.log_client(traceback.format_exc())
        self.connected = False
        self.status_message("ENSIME server has disconnected")
        if self.env.controller:
          self.env.controller.shutdown()

  def start_receiving(self):
    t = threading.Thread(name = "ensime-client-" + str(self.w.id()) + "-" + str(self.port), target = self.receive_loop)
    t.setDaemon(True)
    t.start()
    self._receiver = t

  def connect(self):
    self._connect_lock.acquire()
    try:
      s = socket.socket()
      s.settimeout(self.timeout)
      s.connect(("127.0.0.1", self.port))
      s.settimeout(None)
      self.socket = s
      self.connected = True
      self.start_receiving()
      return s
    except socket.error as e:
      self.connected = False
      self.log_client("Cannot connect to ENSIME server:  " + str(e.args))
      self.status_message("Cannot connect to ENSIME server")
      self.env.controller.shutdown()
    finally:
      self._connect_lock.release()

  def send(self, request):
    try:
      if not self.connected:
        self.connect()
      self.socket.send(request)
    except:
      self.connected = False

  def close(self):
    self._connect_lock.acquire()
    try:
      if self.socket:
        self.socket.close()
    finally:
      self.connected = False
      self._connect_lock.release()

class EnsimeCodec:
  def encode_initialize_project(self, conf):
    return [sym("swank:init-project"), conf]

  def encode_type_check_file(self, file_path):
    return [sym("swank:typecheck-file"), file_path]

  def decode_type_check_file(self, data):
    return True

  def decode_notes(self, data):
    m = sexp.sexp_to_key_map(data)
    return [self.decode_note(n) for n in m[":notes"]]

  def decode_note(self, data):
    m = sexp.sexp_to_key_map(data)
    class EnsimeNote(object): pass
    note = EnsimeNote()
    note.message = m[":msg"]
    note.file_name = m[":file"]
    note.severity = m[":severity"]
    note.start = m[":beg"]
    note.end = m[":end"]
    note.line = m[":line"]
    note.col = m[":col"]
    return note

  def encode_inspect_type_at_point(self, file_path, position):
    return [sym("swank:type-at-point"), str(file_path), int(position)]

  def decode_inspect_type_at_point(self, data):
    return self.decode_type(data)

  def encode_completions(self, file_path, position):
    return [sym("swank:completions"), str(file_path), int(position), 30, False]

  def decode_completions(self, data):
    if not data: return []
    m = sexp.sexp_to_key_map(data)
    return [self.decode_completion(p) for p in m.get(":completions", [])]

  def decode_completion(self, data):
    m = sexp.sexp_to_key_map(data)
    class EnsimeCompletion(object): pass
    completion = EnsimeCompletion()
    completion.name = m[":name"]
    completion.signature = m[":type-sig"]
    completion.is_callable = bool(m[":is-callable"]) if ":is-callable" in m else False
    completion.type_id = m[":type-id"]
    completion.to_insert = m[":to-insert"] if ":to-insert" in m else None
    return completion

  def encode_symbol_at_point(self, file_path, position):
    return [sym("swank:symbol-at-point"), str(file_path), int(position)]

  def decode_symbol_at_point(self, data):
    return self.decode_symbol(data)

  def decode_position(self, data):
    m = sexp.sexp_to_key_map(data)
    class EnsimePosition(object): pass
    position = EnsimePosition()
    position.file_name = m[":file"]
    position.offset = m[":offset"]
    return position

  def decode_types(self, data):
    if not data: return []
    return [self.decode_type(t) for t in data]

  def decode_type(self, data):
    m = sexp.sexp_to_key_map(data)
    class TypeInfo(object): pass
    info = TypeInfo()
    info.name = m[":name"]
    info.type_id = m[":type-id"]
    info.full_name = m[":full-name"] if ":full-name" in m else None
    info.decl_as = m[":decl-as"] if ":decl-as" in m else None
    info.decl_pos = self.decode_position(m[":pos"]) if ":pos" in m else None
    info.type_args = self.decode_types(m[":type-args"]) if ":type-args" in m else []
    info.outer_type_id = m[":outer-type-id"] if ":outer-type-id" in m else None
    return info

  def decode_symbol(self, data):
    m = sexp.sexp_to_key_map(data)
    class SymbolInfo(object): pass
    info = SymbolInfo()
    info.name = m[":name"]
    info.type = self.decode_type(m[":type"])
    info.decl_pos = self.decode_position(m[":decl-pos"]) if ":decl-pos" in m else None
    return info

ensime_codec = EnsimeCodec()

class EnsimeClient(EnsimeClientListener, EnsimeCommon):
  def __init__(self, owner, port_file, timeout):
    super(EnsimeClient, self).__init__(owner)
    with open(port_file) as f: self.port = int(f.read())
    self.timeout = timeout
    self.init_counters()
    methods = filter(lambda m: m[0].startswith("message_"), inspect.getmembers(self, predicate=inspect.ismethod))
    self.log_client("reflectively found " + str(len(methods)) + " message handlers: " + str(methods))
    self.handlers = dict((":" + m[0][len("message_"):].replace("_", "-"), (m[1], None, None)) for m in methods)

  def startup(self):
    self.log_client("[" + str(datetime.datetime.now()) + "] Starting ENSIME client")
    self.log_client("Launching ENSIME client socket at port " + str(self.port))
    self.socket = EnsimeClientSocket(self.owner, self.port, self.timeout, [self, self.env.controller])
    self.socket.connect()

  def shutdown(self):
    if self.socket.connected:
      self.sync_req([sym("swank:shutdown-server")])
    self.socket.close()
    self.socket = None

  def async_req(self, to_send, on_complete = None, call_back_into_ui_thread = None):
    if on_complete is not None and call_back_into_ui_thread is None:
      raise Exception("must specify a threading policy when providing a non-empty callback")
    if not self.socket:
      raise Exception("socket is either not yet initialized or is already destroyed")

    msg_id = self.next_message_id()
    self.handlers[msg_id] = (on_complete, call_back_into_ui_thread, time.time())
    msg_str = sexp.to_string([key(":swank-rpc"), to_send, msg_id])
    msg_str = "%06x" % len(msg_str) + msg_str

    self.feedback(msg_str)
    self.log_client("SEND ASYNC REQ: " + msg_str)
    self.socket.send(msg_str.encode('utf-8'))

  def sync_req(self, to_send, timeout=0):
    msg_id = self.next_message_id()
    event = threading.Event()
    self.handlers[msg_id] = (event, None, time.time())
    msg_str = sexp.to_string([key(":swank-rpc"), to_send, msg_id])
    msg_str = "%06x" % len(msg_str) + msg_str

    self.feedback(msg_str)
    self.log_client("SEND SYNC REQ: " + msg_str)
    self.socket.send(msg_str)

    max_wait = timeout or self.timeout
    event.wait(max_wait)
    if hasattr(event, "payload"):
      return event.payload
    else:
      self.log_client("sync_req #" + str(msg_id) +
                      " has timed out (didn't get a response after " +
                      str(max_wait) + " seconds)")
      return None

  def on_client_async_data(self, data):
    self.log_client("SEND ASYNC RESP: " + str(data))
    self.feedback(str(data))
    self.handle_message(data)

  # examples of responses can be seen here:
  # http://aemon.com/file_dump/ensime_manual.html#tth_sEcC.2
  def handle_message(self, data):
    # (:return (:ok (:pid nil :server-implementation (:name "ENSIMEserver") :machine nil :features nil :version "0.0.1")) 1)
    # (:background-message "Initializing Analyzer. Please wait...")
    # (:compiler-ready t)
    # (:typecheck-result (:lang :scala :is-full t :notes nil))
    msg_type = str(data[0])
    handler, _, _ = self.handlers.get(msg_type)

    if handler:
      msg_id = data[-1] if msg_type == ":return" else None
      data = data[1:-1] if msg_type == ":return" else data[1:]
      payload = None
      if len(data) == 1: payload = data[0]
      if len(data) > 1: payload = data
      return handler(msg_id, payload)
    else:
      self.log_client("unexpected message type: " + msg_type)

  def message_return(self, msg_id, payload):
    handler, call_back_into_ui_thread, req_time = self.handlers.get(msg_id)
    if handler: del self.handlers[msg_id]

    resp_time = time.time()
    self.log_client("request #" + str(msg_id) + " took " + str(resp_time - req_time) + " seconds")

    reply_type = str(payload[0])
    # (:return (:ok (:project-name nil :source-roots ("D:\\Dropbox\\Scratchpad\\Scala"))) 2)
    if reply_type == ":ok":
      payload = payload[1]
      if handler:
        if callable(handler):
          if call_back_into_ui_thread:
            sublime.set_timeout(functools.partial(handler, payload), 0)
          else:
            handler(payload)
        else:
          handler.payload = payload
          handler.set()
      else:
        self.log_client("warning: no handler registered for message #" + str(msg_id) + " with payload " + str(payload))
    # (:return (:abort 210 "Error occurred in Analyzer. Check the server log.") 3)
    elif reply_type == ":abort":
      detail = payload[2]
      if msg_id <= 2: # handshake and initialize project
        self.error_message(self.prettify_error_detail(detail))
        self.status_message("ENSIME startup has failed")
        self.env.controller.shutdown()
      else:
        self.status_message(detail)
    # (:return (:error NNN "SSS") 4)
    elif reply_type == ":error":
      detail = payload[2]
      self.error_message(self.prettify_error_detail(detail))
    else:
      self.log_client("unexpected reply type: " + reply_type)

  def call_back_into_ui_thread(vanilla):
    def wrapped(self, msg_id, payload):
      sublime.set_timeout(functools.partial(vanilla, self, msg_id, payload), 0)
    return wrapped

  @call_back_into_ui_thread
  def message_compiler_ready(self, msg_id, payload):
    filename = self.env.plugin_root + "/Encouragements.txt"
    lines = [line.strip() for line in open(filename)]
    msg = lines[random.randint(0, len(lines) - 1)]
    self.status_message(msg + " This could be the start of a beautiful program, " + getpass.getuser().capitalize()  + ".")
    if self.in_project(self.v.file_name()):
      self.v.run_command("save")

  @call_back_into_ui_thread
  def message_indexer_ready(self, msg_id, payload):
    pass

  @call_back_into_ui_thread
  def message_full_typecheck_finished(self, msg_id, payload):
    pass

  @call_back_into_ui_thread
  def message_background_message(self, msg_id, payload):
    # (:background-message 105 "Initializing Analyzer. Please wait...")
    self.status_message(payload[1])

  @call_back_into_ui_thread
  def message_java_notes(self, msg_id, payload):
    pass

  @call_back_into_ui_thread
  def message_scala_notes(self, msg_id, payload):
    notes = ensime_codec.decode_notes(payload)
    self.add_notes(notes)

  @call_back_into_ui_thread
  def message_clear_all_java_notes(self, msg_id, payload):
    pass

  @call_back_into_ui_thread
  def message_clear_all_scala_notes(self, msg_id, payload):
    self.clear_notes()

  def init_counters(self):
    self._counter = 0
    self._counterLock = threading.RLock()

  def next_message_id(self):
    self._counterLock.acquire()
    try:
      self._counter += 1
      return self._counter
    finally:
      self._counterLock.release()

  def prettify_error_detail(self, detail):
    detail = "ENSIME server has encountered a fatal error: " + detail
    if detail.endswith(". Check the server log."):
      detail = detail[0:-len(". Check the server log.")]
    if not detail.endswith("."): detail += "."
    detail += "\n\nCheck the server log at " + os.path.join(self.env.log_root, "server.log") + "."
    return detail

  def feedback(self, msg):
    msg = msg.replace("\r\n", "\n").replace("\r", "\n") + "\n"
    self.log_client(msg.strip(), to_disk_only = True)

class EnsimeServerListener:
  def on_server_data(self, data):
    pass

class EnsimeServerProcess(EnsimeCommon):
  def __init__(self, owner, command, listeners):
    super(EnsimeServerProcess, self).__init__(owner)
    self.killed = False
    self.listeners = listeners or []

    # ensure the subprocess is always killed when the editor exits
    # this doesn't work, so we have to go for hacks below
    # import atexit
    # atexit.register(self.kill)

    # HACK #1: kill ensime servers that are already running and were launched by this instance of sublime
    # this can happen when you press ctrl+s on sublime-ensime files, sublime reloads them
    # and suddenly SublimeServerCommand has a new singleton instance, and a process it hosts becomes a zombie
    processes = self.env.settings.get("processes", {})
    previous = processes.get(str(os.getpid()), None)
    if previous:
      self.log_server("killing orphaned ensime server process with pid " + str(previous))
      if os.name == "nt":
        try:
          job_name = "Global\\sublime-ensime-" + str(os.getpid())
          self.log_server("killing a job named: " + job_name)
          job = killableprocess.winprocess.OpenJobObject(0x1F001F, True, job_name)
          killableprocess.winprocess.TerminateJobObject(job, 127)
        except:
          self.log_server(sys.exc_info()[1])
      else:
        os.killpg(int(previous), signal.SIGKILL)

    # HACK #2: garbage collect ensime server processes that were started by sublimes, but weren't stopped
    # unfortunately, atexit doesn't work (see the commented code above), so we have to resort to this ugliness
    # todo. ideally, this should happen automatically from ensime
    # e.g. if -Densime.explode.when.zombied is set, then ensime automatically quits when it becomes a zombie
    if os.name == "nt":
      import ctypes
      EnumWindows = ctypes.windll.user32.EnumWindows
      EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
      GetWindowText = ctypes.windll.user32.GetWindowTextW
      GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
      IsWindowVisible = ctypes.windll.user32.IsWindowVisible
      GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
      active_sublimes = set()
      def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
          length = GetWindowTextLength(hwnd)
          buff = ctypes.create_unicode_buffer(length + 1)
          GetWindowText(hwnd, buff, length + 1)
          title = buff.value
          if title.endswith("- Sublime Text 2"):
            pid = ctypes.c_int()
            tid = GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            active_sublimes.add(pid.value)
        return True
      EnumWindows(EnumWindowsProc(foreach_window), 0)
      for sublimepid in [sublimepid for sublimepid in processes.keys() if not int(sublimepid) in active_sublimes]:
        ensimepid = processes[sublimepid]
        del processes[sublimepid]
        self.log_server("found a zombie ensime server process with pid " + str(ensimepid))
        try:
          # todo. Duh, this no longer works on Windows, but I swear it worked.
          # Due to an unknown reason, job gets killed once Sublime quits, so we have no way to dispose of the zombies later.
          job_name = "Global\\sublime-ensime-" + str(sublimepid)
          self.log_server("killing a job named: " + job_name)
          job = killableprocess.winprocess.OpenJobObject(0x1F001F, True, job_name)
          killableprocess.winprocess.TerminateJobObject(job, 127)
        except:
          self.log_server(sys.exc_info()[1])
    else:
      # todo. Vlad, please, implement similar logic for Linux
      pass

    if os.name =="nt":
      startupinfo = killableprocess.STARTUPINFO()
      startupinfo.dwFlags |= killableprocess.STARTF_USESHOWWINDOW
      startupinfo.wShowWindow |= 1 # SW_SHOWNORMAL
      creationflags = 0x8000000 # CREATE_NO_WINDOW
      self.proc = killableprocess.Popen(
        command,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        startupinfo = startupinfo,
        creationflags = creationflags,
        env = os.environ.copy(),
        cwd = self.env.server_path)
    else:
      self.proc = killableprocess.Popen(
        command,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        env = os.environ.copy(),
        cwd = self.env.server_path)
    self.log_server("started ensime server with pid " + str(self.proc.pid))
    processes[str(os.getpid())] = str(self.proc.pid)
    self.env.settings.set("processes", processes)
    # todo. this will leak pids if there are multiple sublimes launching ensimes simultaneously
    # and, in general, we should also address the fact that sublime-ensime assumes at most single ensime per window
    # finally, it's unclear whether to allow multiple ensimes for the same project launched by different sublimes
    sublime.save_settings("Ensime.sublime-settings")

    if self.proc.stdout:
      thread.start_new_thread(self.read_stdout, ())

    if self.proc.stderr:
      thread.start_new_thread(self.read_stderr, ())

  def kill(self):
    if not self.killed:
      self.killed = True
      self.proc.kill()
      self.listeners = []

  def poll(self):
    return self.proc.poll() == None

  def read_stdout(self):
    while True:
      data = os.read(self.proc.stdout.fileno(), 2**15)
      if data != "":
        for listener in self.listeners:
          if listener:
            listener.on_server_data(data)
      else:
        self.proc.stdout.close()
        break

  def read_stderr(self):
    while True:
      data = os.read(self.proc.stderr.fileno(), 2**15)
      if data != "":
        for listener in self.listeners:
          if listener:
            listener.on_server_data(data)
      else:
        self.proc.stderr.close()
        break

class EnsimeServer(EnsimeServerListener, EnsimeCommon):
  def __init__(self, owner, port_file):
    super(EnsimeServer, self).__init__(owner)
    self.port_file = port_file

  def startup(self):
    ensime_command = self.get_ensime_command()
    self.log_server("[" + str(datetime.datetime.now()) + "] Starting ENSIME server")
    self.log_server("Launching ENSIME server process with: " + str(ensime_command))
    self.proc = EnsimeServerProcess(self.owner, ensime_command, [self, self.env.controller])

  def get_ensime_command(self):
    if not os.path.exists(self.env.ensime_executable):
      message = "ENSIME executable \"" + self.env.ensime_executable + "\" does not exist."
      message += "\n\n"
      message += "If you haven't yet installed ENSIME, download it from https://github.com/sublimescala/ensime/downloads, "
      message += "and unpack it into the folder of the SublimeEnsime plugin."
      message += "\n\n"
      message += "If you have already installed ENSIME, check your Ensime.sublime-settings and make sure that "
      message += "the \"ensime_server_path\" entry points to a valid location relative to " + sublime.packages_path() + " "
      message += "(currently it points to the path shown above)."
      self.error_message(message)
      return
    return [self.env.ensime_executable, self.port_file]

  def on_server_data(self, data):
    str_data = str(data).replace("\r\n", "\n").replace("\r", "\n")
    self.log_server(str_data.strip(), to_disk_only = True)

  def shutdown(self):
    self.proc.kill()
    self.proc = None

class EnsimeController(EnsimeCommon, EnsimeClientListener, EnsimeServerListener):
  def __init__(self, owner):
    super(EnsimeController, self).__init__(owner)
    self.running = False
    self.ready = False
    self.client = None
    self.server = None

  def __getattr__(self, name):
    if name == "connected":
      # todo. can I write this in a concise way?
      return self.client and self.client.socket and hasattr(self.client.socket, "connected") and self.client.socket.connected
    raise AttributeError(str(self) + " does not have attribute " + name)

  def startup(self):
    self.env.lifecycleLock.acquire()
    try:
      if not self.running:
        self.env.in_transition = True
        self.env.controller = self
        self.running = True
        if self.env.settings.get("connect_to_external_server", False):
          self.port_file = self.env.settings.get("external_server_port_file")
          if not self.port_file:
            message = "\"connect_to_external_server\" in your Ensime.sublime-settings is set to true, "
            message += "however \"external_server_port_file\" is not specified. "
            message += "Please, set it to a meaningful value and restart ENSIME."
            sublime.set_timeout(functools.partial(sublime.error_message, message), 0)
            raise Exception("external_server_port_file not specified")
          sublime.set_timeout(functools.partial(self.request_handshake), 0)
        else:
          _, port_file = tempfile.mkstemp("ensime_port")
          self.port_file = port_file
          self.server = EnsimeServer(self.owner, port_file)
          self.server.startup()
    except:
      self.env.controller = None
      self.running = False
      raise
    finally:
      self.env.in_transition = False
      self.env.lifecycleLock.release()

  def on_server_data(self, data):
    if not self.ready and re.search("Wrote port", data):
      self.ready = True
      sublime.set_timeout(functools.partial(self.request_handshake), 0)

  def request_handshake(self):
    timeout = self.env.settings.get("rpc_timeout", 3)
    self.client = EnsimeClient(self.owner, self.port_file, timeout)
    self.client.startup()
    self.client.async_req([sym("swank:connection-info")],
                          self.__response_handshake,
                          call_back_into_ui_thread = True)

  def __response_handshake(self, server_info):
    self.status_message("Initializing... ")
    config.select_subproject(self.env.project_config,
                             self.owner,
                             self.__initialize)

  def __initialize(self, subproject_name):
    self.status_message("Starting subproject: " + str(subproject_name))
    conf = self.env.project_config + [key(":active-subproject"), subproject_name]
    req = ensime_codec.encode_initialize_project(conf)
    self.client.async_req(
      req,
      lambda _: self.status_message("Continuing to init project..."),
      call_back_into_ui_thread = True)


  def shutdown(self):
    self.env.lifecycleLock.acquire()
    try:
      if self.running:
        self.env.in_transition = True
        try:
          sublime.set_timeout(self.clear_notes, 0)
        except:
          self.log("Error shutting down ensime UI:")
          self.log(traceback.format_exc())
        try:
          if self.client:
            self.client.shutdown()
        except:
          self.log_client("Error shutting down ensime client:")
          self.log(traceback.format_exc())
        try:
          if self.server:
            self.server.shutdown()
        except:
          self.log_server("Error shutting down ensime server:")
          self.log(traceback.format_exc())
    finally:
      self.running = False
      self.env.controller = None
      self.env.in_transition = False
      self.env.lifecycleLock.release()

class EnsimeStartupCommand(NotRunningOnly, EnsimeWindowCommand):
  def is_enabled(self, enable = True):
    if not self.env.project_config: return True
    return super(EnsimeStartupCommand, self).is_enabled()

  def run(self):
    if not self.env.project_config:
      message = "ENSIME server has been unable to start, because a valid .ensime configuration file wasn't found."
      message += "\n\n"
      message += "Create a file named .ensime in the root of one of your project's folders and retry. "
      example = "(:root-dir \"d:/Dropbox/Scratchpad/Scala\" :sources (\"d:/Dropbox/Scratchpad/Scala\") :target \"d:/Dropbox/Scratchpad/Scala\")"
      message += "Here is a simple example of an .ensime file: \n\n" + example + "\n\n"
      message += "For more information refer to the \"Config File Format\" section of the docs: http://aemon.com/file_dump/ensime_manual.html"
      self.error_message(message)
      return
    EnsimeController(self.w).startup()

class EnsimeShutdownCommand(RunningOnly, EnsimeWindowCommand):
  def run(self):
    self.env.controller.shutdown()

class EnsimeRestartCommand(RunningOnly, EnsimeWindowCommand):
  def run(self):
    self.w.run_command("ensime_shutdown")
    sublime.set_timeout(functools.partial(self.w.run_command, "ensime_startup"), 100)

class EnsimeShowClientMessagesCommand(EnsimeWindowCommand):
  def run(self):
    # self.view_show(self.env.cv, False)
    client_log = os.path.join(self.env.log_root, "client.log")
    line = 1
    try:
     with open(client_log) as f: line = len(f.readlines())
    except:
      pass
    self.w.open_file("%s:%d:%d" % (client_log, line, 1), sublime.ENCODED_POSITION)

class EnsimeShowServerMessagesCommand(EnsimeWindowCommand):
  def run(self):
    # self.view_show(self.env.sv, False)
    server_log = os.path.join(self.env.log_root, "server.log")
    line = 1
    try:
     with open(server_log) as f: line = len(f.readlines())
    except:
      pass
    self.w.open_file("%s:%d:%d" % (server_log, line, 1), sublime.ENCODED_POSITION)

# rebind Enter, Escape, Backspace, Left, ShiftLeft, Home, ShiftHome
# persistent command history and Ctrl+Up/Ctrl+Down like in SublimeREPL

class EnsimeShowClientServerReplCommand(ReadyEnsimeOnly, EnsimeWindowCommand):
  def __init__(self, window):
    super(EnsimeShowClientServerReplCommand, self).__init__(window)
    self.visible = False
    self.window = window

  def run(self, toggle = True):
    self.visible = not self.visible if toggle else True
    if self.visible:
      self.repl_show()
    else:
      self.window.run_command("hide_panel", { "cancel": True })

class EnsimeReplEnterCommand(EnsimeTextCommand):
  def run(self, edit):
    user_input = self.repl_get_input().strip()
    if user_input:
      self.env.repl_lock.acquire()
      try:
        if user_input == "cls":
          self.env.rv.replace(edit, Region(0, self.env.rv.size()), "")
          self.env.repl_last_insert = 0
          self.env.repl_last_fixup = 0
          self.repl_insert(self.repl_prompt(), False)
        else:
          user_input = user_input.replace("$file", "\"" + self.w.active_view().file_name() + "\"")
          user_input = user_input.replace("$pos", str(self.w.active_view().sel()[0].begin()))
          try:
            _ = sexp.read_list(user_input)
            parsed_user_input = sexp.read(user_input)
            with open(os.path.join(self.env.log_root, "repl.history"), 'a') as f:
              f.write(user_input + "\n")
          except:
            self.status_message(str(sys.exc_info()[1]))
            return
          self.env.repl_last_insert = self.env.rv.size()
          self.env.repl_last_fixup = self.env.repl_last_insert
          self.repl_insert("\n", True)
          # self.repl_insert(self.repl_prompt(), False)
          self.repl_schedule_fixup("", self.env.repl_last_fixup + 1)
          self.env.controller.client.async_req(parsed_user_input)
      finally:
        self.env.repl_lock.release()

class EnsimeReplEscapeCommand(EnsimeTextCommand):
  def run(self, edit):
    self.env.repl_lock.acquire()
    try:
      user_input = self.repl_get_input()
      if len(user_input) == 0:
        self.w.run_command("hide_panel", {"cancel": True})
      else:
        self.w.run_command("move_to", {"to": "eof", "extend": False})
        self.w.run_command("ensime_repl_shift_home")
        self.w.run_command("right_delete")
    finally:
      self.env.repl_lock.release()

class EnsimeReplBackspaceCommand(EnsimeTextCommand):
  def run(self, edit):
    self.env.repl_lock.acquire()
    try:
      delta = self.env.rv.sel()[0].begin() - self.env.repl_last_insert - len(self.repl_prompt())
      if delta < 0:
        self.w.run_command("left_delete")
      elif delta == 0:
        return
      else:
        self.w.run_command("left_delete")
    finally:
      self.env.repl_lock.release()

class EnsimeReplLeftCommand( EnsimeTextCommand):
  def run(self, edit):
    self.env.repl_lock.acquire()
    try:
      delta = self.env.rv.sel()[0].begin() - self.env.repl_last_insert - len(self.repl_prompt())
      if delta < 0:
        self.w.run_command("move", {"by": "characters", "forward": False, "extend": False})
      elif delta == 0:
        return
      else:
        self.w.run_command("move", {"by": "characters", "forward": False, "extend": False})
    finally:
      self.env.repl_lock.release()

class EnsimeReplShiftLeftCommand(EnsimeTextCommand):
  def run(self, edit):
    self.env.repl_lock.acquire()
    try:
      delta = self.env.rv.sel()[0].begin() - self.env.repl_last_insert - len(self.repl_prompt())
      if delta < 0:
        self.w.run_command("move", {"by": "characters", "forward": False, "extend": True})
      elif delta == 0:
        return
      else:
        self.w.run_command("move", {"by": "characters", "forward": False, "extend": True})
    finally:
      self.env.repl_lock.release()

class EnsimeReplHomeCommand(EnsimeTextCommand):
  def run(self, edit):
    self.env.repl_lock.acquire()
    try:
      delta = self.env.rv.sel()[0].begin() - self.env.repl_last_insert - len(self.repl_prompt())
      if delta < 0:
        self.w.run_command("move_to", {"to": "bol", "extend": False})
      else:
        for i in range(1, delta + 1):
          self.w.run_command("move", {"by": "characters", "forward": False, "extend": False})
    finally:
      self.env.repl_lock.release()

class EnsimeReplShiftHomeCommand(EnsimeTextCommand):
  def run(self, edit):
    self.env.repl_lock.acquire()
    try:
      delta = self.env.rv.sel()[0].begin() - self.env.repl_last_insert - len(self.repl_prompt())
      if delta < 0:
        self.w.run_command("move_to", {"to": "bol", "extend": True})
      else:
        for i in range(1, delta + 1):
          self.w.run_command("move", {"by": "characters", "forward": False, "extend": True})
    finally:
      self.env.repl_lock.release()

class EnsimeReplPreviousCommand(EnsimeTextCommand):
  def run(self, edit):
    self.env.rv.show(self.env.rv.line(self.env.rv.size()).begin())
    self.w.run_command("ensime_repl_escape")
    self.repl_insert(self.repl_previous_history(), False)
    self.repl_show()

class EnsimeReplNextCommand(EnsimeTextCommand):
  def run(self, edit):
    self.env.rv.show(self.env.rv.line(self.env.rv.size()).begin())
    self.w.run_command("ensime_repl_escape")
    self.repl_insert(self.repl_next_history(), False)
    self.repl_show()

class EnsimeHighlights(EnsimeCommon):

  def refresh(self):
    self.clear_all()
    self.add(self.env.notes)

  def clear_all(self):
    self.v.erase_regions("ensime-error")
    self.v.erase_regions("ensime-error-underline")

  def add(self, notes):
    relevant_notes = filter(
      lambda note: self.same_files(note.file_name, self.v.file_name()), notes)

    # Underline specific error range
    underlines = [sublime.Region(note.start, note.end) for note in relevant_notes]
    if self.env.settings.get("error_highlight") and self.env.settings.get("error_underline"):
      self.v.add_regions(
        "ensime-error-underline",
        underlines + self.v.get_regions("ensime-error-underline"),
        "invalid.illegal",
        sublime.DRAW_EMPTY_AS_OVERWRITE)

    # Outline entire errored line
    errors = [self.v.full_line(note.start) for note in relevant_notes]
    if self.env.settings.get("error_highlight"):
      self.v.add_regions(
        "ensime-error",
        errors + self.v.get_regions("ensime-error"),
        "invalid.illegal",
        self.env.settings.get("error_icon", "dot"),
        sublime.DRAW_OUTLINED)


class EnsimeHighlightStatus(EnsimeCommon):

  def refresh(self):
    if self.env.settings.get("error_status"):
      relevant_notes = filter(
        lambda note: self.same_files(
          note.file_name, self.v.file_name()),
        self.env.notes)
      bol = self.v.line(self.v.sel()[0].begin()).begin()
      eol = self.v.line(self.v.sel()[0].begin()).end()
      msgs = [note.message for note in relevant_notes
              if (bol <= note.start and note.start <= eol) or
              (bol <= note.end and note.end <= eol)]
      statusgroup = self.env.settings.get("ensime_statusbar_group", "ensime")
      if msgs:
        maxlength = self.env.settings.get("error_status_maxlength", 150)
        status = "; ".join(msgs)
        if len(status) > maxlength:
          status = status[0:maxlength] + "..."
        sublime.set_timeout(functools.partial(self.v.set_status, statusgroup, status), 100)
      else:
        self.v.erase_status(statusgroup)


class EnsimeHighlightCommand(ProjectFileOnly, EnsimeWindowCommand):
  def run(self, enable = True):
    self.env.settings.set("error_highlight", not not enable)
    sublime.save_settings("Ensime.sublime-settings")
    EnsimeHighlights(self.v).hide()
    if enable:
      self.type_check_file(self.f)

class EnsimeShowNotesCommand(ConnectedEnsimeOnly, EnsimeTextCommand):
  def run(self, edit, current_file_only):
    v = self.v.window().new_file()
    v.set_scratch(True)
    designator = " for " + os.path.basename(self.v.file_name()) if current_file_only else ""
    v.set_name("Ensime notes" + designator)
    relevant_notes = self.env.notes
    if current_file_only:
      relevant_notes = filter(lambda note: self.same_files(note.file_name, self.v.file_name()), self.env.notes)
    errors = [self.v.full_line(note.start) for note in relevant_notes]
    edit = v.begin_edit()
    relevant_notes = filter(lambda note: self.same_files(note.file_name, self.v.file_name()), self.env.notes)
    for note in relevant_notes:
      loc = self.project_relative_path(note.file_name) + ":" + str(note.line)
      severity = note.severity
      message = note.message
      diagnostics = ": ".join(str(x) for x in [loc, severity, message])
      v.insert(edit, v.size(), diagnostics + "\n")
      v.insert(edit, v.size(), self.v.substr(self.v.full_line(note.start)))
      v.insert(edit, v.size(), " " * (note.col - 1) + "^" + "\n")
    v.sel().clear()
    v.sel().add(Region(0, 0))

class EnsimeHighlightDaemon(EventListener):
  def with_api(self, view, what):
    api = ensime_api(view)
    if api and api.in_project(view.file_name()):
      what(api)

  def on_load(self, view):
    self.with_api(view, lambda api: api.type_check_file(view.file_name()))

  def on_post_save(self, view):
    self.with_api(view, lambda api: api.type_check_file(view.file_name()))

  def on_activate(self, view):
    self.with_api(view, lambda api: EnsimeHighlights(view).refresh())

  def on_selection_modified(self, view):
    if view.sel():
      self.with_api(view, lambda api: EnsimeHighlightStatus(view).refresh())

# things might be simplified as per http://www.sublimetext.com/forum/viewtopic.php?f=6&t=7658
class EnsimeCtrlClickDaemon(EventListener):
  def on_activated(self, view):
    self.save_selection(view)

  def on_selection_modified(self, view):
    if view.sel():
      self.save_selection(view)

  def save_selection(self, view):
    curr_sel = str(view.sel())
    prev_sel = view.settings().get("curr_sel")
    if curr_sel != prev_sel:
      view.settings().set("prev_sel", prev_sel)
      view.settings().set("curr_sel", curr_sel)

class EnsimeCtrlClick(EnsimeTextCommand):
  def run(self, edit):
    is_applicable = not self.env.in_transition and self.env.valid and self.env.controller and self.env.controller.connected and self.in_project(self.v.file_name())
    if is_applicable and self.env.settings.get("ctrl_click_goes_to_definition"):
      #xeno.by: todo. even with all this magic we're not good yet
      #clicking on one of the current cursor position will confuse this command
      s_prev = self.view.settings().get("prev_sel")
      s_curr = self.view.settings().get("curr_sel")
      prev = self.parse(s_prev)
      curr = self.parse(s_curr)
      target = self.diff(prev, curr)
      diagnostics = "prev_sel = " + str(prev) + ", curr_sel = " + str(curr) + ", diff = " + str(target)
      if len(target) > 1:
        raise Exception("something is borked: " + diagnostics)
      target = target[0][0] if target else prev[0] # won't work with multiselect when prev == curr
      self.v.sel().clear()
      for rs in prev:
        self.v.sel().add(Region(rs[0], rs[1]))
      self.v.settings().set("prev_sel", s_prev)
      self.v.settings().set("curr_sel", str(self.v.sel()))
      self.v.run_command("ensime_go_to_definition", {"target": target})
      sublime.set_timeout(self.trigger_selection_update, 100)
    else:
      # additive drag_select has been applied before this command was called
      # hence we have nothing to do here
      pass

  def trigger_selection_update(self):
    #xeno.by: ugly, yes, but we need to trigger a selection update
    self.v.run_command("move", {"by": "characters", "forward": False})
    self.v.run_command("move", {"by": "characters", "forward": True})

  # [(51708, 51708), (51946, 51946)]
  def parse(self, s_sel):
    return [(int(m[0]), int(m[1])) for m in re.findall("\((\d+), (\d+)\)", s_sel)]

  def diff(self, sel1, sel2):
    return list((set(sel1) - set(sel2)) | (set(sel2) - set(sel1)))

class EnsimeAltClick(EnsimeTextCommand):
  def run(self, edit):
    is_applicable = not self.env.in_transition and self.env.valid and self.env.controller and self.env.controller.connected and self.in_project(self.v.file_name())
    if is_applicable and self.env.settings.get("alt_click_inspects_type_at_point"):
      self.v.run_command("ensime_inspect_type_at_point", {"target": self.v.sel()[0]})
    else:
      # subtractive drag_select has been applied before this command was called
      # hence we have nothing to do here
      pass

class EnsimeCtrlTilde(EnsimeWindowCommand):
  def run(self):
    if self.env.settings.get("ctrl_tilde_shows_repl"):
      self.w.run_command("ensime_show_client_server_repl", {"toggle": True})
    else:
      self.w.run_command("hide_panel", {"panel": "console"})

class EnsimeCompletionsListener(EventListener):
  def on_query_completions(self, view, prefix, locations):
    if not view.match_selector(locations[0], "source.scala"): return []
    api = ensime_api(view)
    completions = api.get_completions(view.file_name(), locations[0]) if api else None
    if completions is None: return []
    return ([(c.name + "\t" + c.signature, c.name) for c in completions],
            sublime.INHIBIT_EXPLICIT_COMPLETIONS |
            sublime.INHIBIT_WORD_COMPLETIONS)

class EnsimeInspectTypeAtPoint(ProjectFileOnly, EnsimeTextCommand):
  def run(self, edit, target= None):
    pos = int(target or self.v.sel()[0].begin())
    self.inspect_type_at_point(self.f, pos, self.handle_reply)

  def handle_reply(self, tpe):
    statusgroup = self.env.settings.get("ensime_statusbar_group", "ensime")
    if tpe.name != "<notype>":
      summary = tpe.full_name
      if tpe.type_args:
        summary += ("[" + ", ".join(map(lambda t: t.name, tpe.type_args)) + "]")
      sublime.set_timeout(functools.partial(self.v.set_status, statusgroup, summary), 100)
    else:
      statusmessage = "Type of the expression at cursor is unknown"
      sublime.set_timeout(functools.partial(self.v.set_status, statusgroup, statusmessage), 100)

class EnsimeGoToDefinition(ProjectFileOnly, EnsimeTextCommand):
  def run(self, edit, target= None):
    pos = int(target or self.v.sel()[0].begin())
    self.symbol_at_point(self.f, pos, self.handle_reply)

  def handle_reply(self, info):
    statusgroup = self.env.settings.get("ensime_statusbar_group", "ensime")
    if info.decl_pos:
      #xeno.by: fails from time to time, because sometimes self.w is None
      # v = self.w.open_file(info.decl_pos.file_name)
      v = sublime.active_window().open_file(info.decl_pos.file_name)
      v.sel().clear()
      v.sel().add(Region(info.decl_pos.offset, info.decl_pos.offset))
    else:
      statusmessage = "Definition of " + str(info.name) + " cannot be found"
      sublime.set_timeout(functools.partial(self.v.set_status, statusgroup, statusmessage), 100)
