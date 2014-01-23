class FastStartException(Exception):
    """
    Raised when something bad happens during processing.
    """
    pass

class FastStartSetupError(FastStartException):
    """
    Rasised when asked to process a file that does not need processing
    """
    pass

class MalformedFileError(FastStartException):
    """
    Raised when the input file is setup in an unexpected way
    """
    pass

class UnsupportedFormatError(FastStartException):
    """
    Raised when a movie file is recognized as a format not supported.
    """
    pass
