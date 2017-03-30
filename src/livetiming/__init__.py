from dotenv import load_dotenv, find_dotenv


def load_env():
    try:
        maybe_dotenv = find_dotenv("livetiming.env", raise_error_if_not_found=True, usecwd=True)
        load_dotenv(maybe_dotenv)
    except IOError:
        pass
