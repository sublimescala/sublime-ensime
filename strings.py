def encode_if_unicode(arg):
  if isinstance(arg,list):
  	return [encode_if_unicode(elem) for elem in arg]
  return arg.encode("utf-8") if isinstance(arg, unicode) else arg

def decode_if_str(arg):
  if isinstance(arg,list):
  	return [decode_if_str(elem) for elem in arg]
  return arg.decode("utf-8") if isinstance(arg, str) else arg
