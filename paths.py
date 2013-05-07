import os

def encode_path(path):
  if not path:
    return path

  if os.name == "nt":
    if os.path.isabs(path):
      drive, rest = os.path.splitdrive(path)
      return "/" + drive[:-1].upper() + rest.replace("\\", "/")
    else:
      return path.replace("\\", "/")
  else:
    return path

def decode_path(path):
  if not path:
    return path

  if os.name == "nt":
    if path.startswith("/"):
      path = path[1:]
      iof = path.find("/")
      if iof == -1:
        drive = path
        rest = ""
      else:
        drive = path[:iof]
        rest = path[iof:]
      return (drive + ":" + rest).replace("/", "\\")
    else:
      return path.replace("/", "\\")
  else:
    return path

def same_paths(path1, path2):
  if not path1 or not path2:
    return False
  path1_normalized = os.path.normcase(os.path.realpath(path1))
  path2_normalized = os.path.normcase(os.path.realpath(path2))
  return path1_normalized == path2_normalized

def normalize_path(path):
  if not path:
    return None
  return os.path.normcase(os.path.realpath(path))

def is_subpath(root, wannabe):
  if not root or not wannabe:
    return False
  root = os.path.normcase(os.path.realpath(root))
  wannabe = os.path.normcase(os.path.realpath(wannabe)).encode("utf-8")
  return wannabe.startswith(root)

def relative_path(root, wannabe):
  if not root or not wannabe:
    return None
  if not is_subpath(root, wannabe):
    return None
  root = os.path.normcase(os.path.realpath(root))
  wannabe = os.path.normcase(os.path.realpath(wannabe))
  return wannabe[len(root) + 1:]