import tempfile

from gemeaux import LoggingBuilder


def test_logging_builder():
    f = tempfile.TemporaryDirectory()
    x = LoggingBuilder("test", f.name, "test.log")
    y = LoggingBuilder("test", f.name, "test.log")
    z = LoggingBuilder("test123", f.name, "test123.log")

    assert x == y
    assert z != y
    assert z != x
    # assert os.path.isfile(f.name+"/test.log") is True  # needs mocking of Logger.hasHandlers
    # assert os.path.isfile(f.name+"/test123.log") is True # needs mocking of Logger.hasHandlers
    f.cleanup()
