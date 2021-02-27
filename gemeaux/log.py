import logging
from os import makedirs
from os.path import exists


def LoggingBuilder(name, loggingpath, filename):

    # Critical:= An unrecoverable error, this closes the application
    # Error   := this should not have happend and is a serious flaw
    # Warning := some hickup but we can still continue within the application
    # Info    := General information
    # Debug   := Verbosity for easier debuging
    logger = logging.getLogger("gemeaux." + name)
    if logger.hasHandlers():
        return logger
    logger.setLevel(level=logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s %(name)-12s %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    try:

        if not exists(loggingpath):
            makedirs(loggingpath)
        fileHandler = logging.FileHandler(loggingpath + "/" + filename, mode="a")
        fileHandler.setFormatter(formatter)
        fileHandler.setLevel(level=logging.DEBUG)
        logger.addHandler(fileHandler)

        streamHandler = logging.StreamHandler()
        streamHandler.setFormatter(formatter)
        streamHandler.setLevel(level=logging.INFO)
        logger.addHandler(streamHandler)

    except PermissionError:
        streamHandler = logging.StreamHandler()
        streamHandler.setFormatter(formatter)
        streamHandler.setLevel(level=logging.NOTSET)
        logger.addHandler(streamHandler)

        logger.error(
            "Only use streaming handler for logging. No file output is generated."
        )

    logger.info("Logging started")
    return logger
