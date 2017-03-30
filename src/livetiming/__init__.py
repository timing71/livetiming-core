from dotenv import load_dotenv, find_dotenv

try:
    maybe_dotenv = find_dotenv("livetiming.env", raise_error_if_not_found=True)
    load_dotenv(maybe_dotenv)
except IOError:
    pass
