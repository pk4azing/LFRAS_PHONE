import re, os
def validate_filename(filename, pattern):
    return re.match(pattern, filename) is not None
def validate_extension(filename, allowed):
    ext = filename.split('.')[-1].lower()
    return ext in [a.lower() for a in allowed]
